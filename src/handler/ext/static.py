# -*- coding: utf-8 -*-

import re
import os
import stat
import hashlib
import datetime
import mimetypes
import email
import email.utils
import email.generator
import http.client
import typing

from ...util.handler import Handler as _Handler, HandlerError as _HandlerError


class HandlerError(_HandlerError):
    pass


class NotFoundError(HandlerError):
    pass


class Handler(_Handler):
    @classmethod
    def get_etag(cls, fileobj, filelen):
        filegen = cls.file_generator_limited(fileobj, filelen)
        hasher = hashlib.md5()
        for chunk in filegen:
            hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def match_hdr(hdr, etag):
        hdr_etags = re.compile('\\*|(?:W/)?"[^"]*"').findall(hdr)
        if not etag or not hdr_etags:
            return False
        if hdr_etags[0] == '*':
            return True

        # Use a weak comparison when comparing entity-tags.
        def val(x):
            return x[2:] if x.startswith('W/') else x

        match = False
        for hdr_etag in hdr_etags:
            if val(hdr_etag) == val(etag):
                match = True
                break
        return match

    @classmethod
    def get_ranges(cls, hdr, length):
        """
        :param hdr: header value
        :param length: content length of the resource requested (whole, not the range)
        :return: a list of (start, stop) indices from a Range header, or None.

        Each (start, stop) tuple will be composed of two ints, which are suitable
        for use in a slicing operation. That is, the header "Range: bytes=3-6",
        if applied against a Python string, is requesting resource[3:7]. This
        function will return the list [(3, 7)].

        If this function returns an empty list, you should return HTTP 416.
        """

        if not hdr:
            return None

        bytesunit, byteranges = hdr.split("=", 1)
        if bytesunit != 'bytes':
            return None

        result = list()
        for brange in byteranges.split(","):
            start, stop = [x.strip() for x in brange.split("-", 1)]
            if start:
                if not stop:
                    stop = length - 1
                start, stop = list(map(int, (start, stop)))
                if start >= length:
                    # From rfc 2616 sec 14.16:
                    # "If the server receives a request (other than one
                    # including an If-Range request-header field) with an
                    # unsatisfiable Range request-header field (that is,
                    # all of whose byte-range-spec values have a first-byte-pos
                    # value greater than the current length of the selected
                    # resource), it SHOULD return a response code of 416
                    # (Requested range not satisfiable)."
                    continue
                if stop < start:
                    # From rfc 2616 sec 14.16:
                    # "If the server ignores a byte-range-spec because it
                    # is syntactically invalid, the server SHOULD treat
                    # the request as if the invalid Range header field
                    # did not exist. (Normally, this means return a 200
                    # response containing the full entity)."
                    return None
                result.append((start, stop + 1))
            else:
                if not stop:
                    # See rfc quote above.
                    return None
                # Negative subscript (last N bytes)
                result.append((length - int(stop), length))

        return result

    @classmethod
    def file_generator_limited(cls, fileobj, count, chunk_size=65536):
        """Yield the given file object in chunks, stopping after `count`
        bytes has been emitted.  Default chunk size is 64kB. (Core)
        """
        remaining = count
        while remaining > 0:
            chunk = fileobj.read(min(chunk_size, remaining))
            chunklen = len(chunk)
            if chunklen == 0:
                return
            remaining -= chunklen
            yield chunk

    @classmethod
    def mimetype(cls, path):
        mime_type, encoding = mimetypes.guess_type(path)
        # per RFC 6713, use the appropriate type for a gzip compressed file
        if encoding == 'gzip':
            return 'application/gzip'
        # As of 2015-07-21 there is no bzip2 encoding defined at
        # http://www.iana.org/assignments/media-types/media-types.xhtml
        # So for that (and any other encoding), use octet-stream.
        elif encoding is not None:
            return 'application/octet-stream'
        elif mime_type is not None:
            return mime_type
        # if mime_type not detected, use application/octet-stream
        else:
            return 'application/octet-stream'

    def view_method_not_allowed(self):
        content = 'Static handler only allows GET and HEAD methods'
        self.req.setResponseCode(http.client.METHOD_NOT_ALLOWED, http.client.responses[http.client.METHOD_NOT_ALLOWED])
        self.req.setHeader('Content-Type', 'text/plain')
        self.req.setHeader('Content-Length', '%d' % len(content))
        self.req.write(content)

    def view_not_modified(self, etag=None):
        self.req.setResponseCode(http.client.NOT_MODIFIED, http.client.responses[http.client.NOT_MODIFIED])
        if etag:
            self.req.setHeader('ETag', etag)

    def view_precondition_failed(self):
        self.req.setResponseCode(http.client.PRECONDITION_FAILED, http.client.responses[http.client.PRECONDITION_FAILED])

    # noinspection PyMethodOverriding
    def __call__(self, path: str):
        if self.req.method == 'GET':
            body_render = True
        elif self.req.method == 'HEAD':
            body_render = False
        else:
            return self.view_method_not_allowed()

        try:
            st = os.stat(path)
        except OSError:
            raise NotFoundError('Requested file not found')

        # Check if path is a directory.
        if stat.S_ISDIR(st.st_mode):
            # Let the caller deal with it as they like.
            raise NotFoundError('Requested file is a directory')

        modified = datetime.datetime.fromtimestamp(st.st_mtime, datetime.UTC).replace(microsecond=0)  # RFC formats don't suppport microseconds
        c_len = st.st_size
        bodyfile = open(path, 'rb')
        etag = self.get_etag(bodyfile, c_len)
        bodyfile.seek(0)  # seek back to beginning of the file

        # Process "If-Unmodified-Since" header first
        since = self.req.request_headers.get('If-Unmodified-Since')
        if since:
            since = email.utils.parsedate_to_datetime(since)
        if since and since < modified:
            return self.view_precondition_failed()
        # Process "If-Modified-Since" header first
        since = self.req.request_headers.get('If-Modified-Since')
        if since:
            since = email.utils.parsedate_to_datetime(since)
        if since and since >= modified:
            return self.view_not_modified(etag)

        hdr = self.req.request_headers.get('If-Match', '')
        if hdr and not self.match_hdr(hdr, etag):
            return self.view_precondition_failed()

        hdr = self.req.request_headers.get('If-None-Match', '')
        if hdr and self.match_hdr(hdr, etag):
            return self.view_not_modified(etag)

        content_type = self.mimetype(path)

        # Set the Last-Modified response header, so that
        # modified-since validation code can work.
        self.req.setHeader('Last-Modified', email.utils.format_datetime(modified, True))
        self.req.setHeader('ETag', etag)
        self.req.setHeader('Content-Type', content_type)

        # HTTP/1.0 didn't have Range/Accept-Ranges headers, or the 206 code
        if self.req.clientproto < 'HTTP/1.0':
            self.req.setHeader('Content-Length', '%d' % c_len)
            if body_render:
                self.req.write(bodyfile.read())
            return

        self.req.setHeader('Accept-Ranges', 'bytes')
        r = self.get_ranges(self.req.request_headers.get('Range'), c_len)
        # In case of parsing failed, proceed normally
        if r is None:
            self.req.setResponseCode(200, 'OK')
            self.req.setHeader('Content-Length', '%d' % c_len)
            if body_render:
                self.req.write(bodyfile.read())
            return

        if not r:
            self.req.setResponseCode(416, 'Invalid Range (first-byte-pos greater than Content-Length)')
            self.req.setHeader('Content-Range', 'bytes */%s' % c_len)
        elif len(r) == 1:
            # Return a single-part response.
            start, stop = r[0]
            if stop > c_len:
                stop = c_len
            r_len = stop - start
            self.req.setResponseCode(206, 'Partial Content')
            self.req.setHeader('Content-Range', 'bytes %s-%s/%s' % (start, stop - 1, c_len))
            self.req.setHeader('Content-Length', r_len)
            if body_render:
                bodyfile.seek(start)
                for file_part in self.file_generator_limited(bodyfile, r_len):
                    self.req.write(file_part)
        else:
            # Return a multipart/byteranges response.
            boundary = email.generator._make_boundary()

            self.req.setResponseCode(206, 'Partial Content')
            self.req.setHeader('Content-Type', "multipart/byteranges; boundary=%s" % boundary)

            def file_ranges():
                # Apache compatibility:
                yield "\r\n"

                for start, stop in r:
                    yield "--" + boundary
                    yield "\r\nContent-type: %s" % content_type
                    yield ("\r\nContent-range: bytes %s-%s/%s\r\n\r\n"
                           % (start, stop - 1, c_len))
                    bodyfile.seek(start)
                    for chunk in self.file_generator_limited(bodyfile, stop - start):
                        yield chunk
                    yield "\r\n"
                # Final boundary
                yield "--" + boundary + "--"

                # Apache compatibility:
                yield "\r\n"

            for file_range in file_ranges():
                self.req.write(file_range)
