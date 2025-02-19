# -*- coding: utf-8 -*-


import io
import codecs
import urllib.parse
import datetime
import http.cookies
import wsgiref.headers

from ..context import Context as _Context


class RequestException(BaseException):
    pass


class Request(object):
    def __init__(self, env):
        self.context = _Context()

        self.secure = 'HTTPS' in env
        self.method = env.get('REQUEST_METHOD', 'GET')
        self.path = env.get('PATH_INFO', '/')
        self.query_string = env.get('QUERY_STRING', '')
        self.uri = urllib.parse.urlunsplit(('', '', self.path, self.query_string, ''))
        self.clientproto = env.get('SERVER_PROTOCOL', 'HTTP/0.9')

        self.client_address = env.get('REMOTE_ADDR', '')
        self.client_host = env.get('REMOTE_HOST', '')
        self.remote_user = env.get('REMOTE_USER', None)
        self.remote_ident = env.get('REMOTE_IDENT', None)

        self.requestHeaders = wsgiref.headers.Headers([])
        self.responseHeaders = wsgiref.headers.Headers([])
        self.received_cookies = dict()  # incoming cookies
        self.cookie = http.cookies.SimpleCookie()  # outgoing cookies

        self.request_body = env['wsgi.input'].read()
        env['wsgi.input'] = io.BytesIO(self.request_body)  # after response body is read, it will be assigned a string iterator and can be reused
        self.response_body = list()

        self._parseHeaders(env)
        self._parseCookies()

        self.status_code = 200
        self.status_message = 'OK'

    def __repr__(self):
        return '<%s %s %s>' % (self.method, self.uri, self.clientproto)

    def _parseHeaders(self, env):
        def env2name(env):
            return env.split('HTTP_', 1)[1].replace('_', '-').lower()

        # headers use escape sequences which must be decoded. Use undocumented function codecs.escape_decode to perform this task. Standard codecs don't help
        for header_name, header_value in [(env2name(_name_value[0]), codecs.escape_decode(_name_value[1])[0].decode('utf-8')) for _name_value in env.items() if _name_value[0].startswith('HTTP_')]:
            self.requestHeaders.add_header(header_name, header_value)
        if 'CONTENT_LENGTH' in env:
            self.requestHeaders['Content-Length'] = '%s' % env['CONTENT_LENGTH']
        if 'CONTENT_TYPE' in env:
            self.requestHeaders['Content-Type'] = env['CONTENT_TYPE']

    def _parseCookies(self):
        """
        Parse cookie headers.

        This method is not intended for users.
        """
        cookieheaders = self.requestHeaders.get_all('Cookie')
        for cookietxt in cookieheaders:
            if cookietxt:
                for cook in cookietxt.split(';'):
                    cook = cook.lstrip()
                    try:
                        k, v = cook.split('=', 1)
                        self.received_cookies[k] = v
                    except ValueError:
                        pass

    def __getattr__(self, item):
        if item == 'request_headers':
            return self.requestHeaders
        if item == 'response_headers':
            return self.responseHeaders
        raise AttributeError

    def isSecure(self):
        return self.secure

    def setResponseCode(self, code, message):
        """
        Set the HTTP response code and message.
        """
        if not isinstance(code, int):
            raise TypeError("HTTP response code must be int or long")
        if not isinstance(message, (str)):
            raise TypeError("HTTP response message must be str")
        self.status_code = code
        self.status_message = message

    def getHeader(self, key):
        """
        Get an HTTP request header.

        @type key: C{str}
        @param key: The name of the header to get the value of.

        @rtype: C{str} or C{NoneType}
        @return: The value of the specified header, or C{None} if that header
            was not present in the request.
        """
        return self.requestHeaders[key]

    def setHeader(self, name, value):
        """
        Set an HTTP response header.  Overrides any previously set values for
        this header.

        @type name: C{str}
        @param name: The name of the header for which to set the value.

        @type value: C{str}
        @param value: The value to set for the named header.
        """
        self.responseHeaders[name] = value

    def getCookie(self, key, received=True, sent=False):
        """
        Get a cookie that was sent from the network.
        """
        if received:
            cookie = self.received_cookies.get(key)
            if cookie:
                return cookie
        if sent:
            cookie = self.cookie.get(key)
            if cookie is not None:
                return cookie.value
        return None

    def addCookie(self, k, v, domain=None, path=None, secure=None, max_age=None, expires=None, comment=None):
        """
        Set an outgoing HTTP cookie.
        """
        self.cookie[k] = v
        if domain is not None:
            self.cookie[k]['domain'] = domain
        if path is not None:
            self.cookie[k]['path'] = path
        if secure:
            self.cookie[k]['secure'] = secure
        if max_age is not None:
            self.cookie[k]['max_age'] = max_age
        if expires is not None:
            self.cookie[k]['expires'] = expires
        if comment is not None:
            self.cookie[k]['comment'] = comment

    def write(self, data, encoding='utf-8'):
        if isinstance(data, str):
            data = data.encode(encoding)
        if isinstance(data, bytes):
            self.response_body.append(data)
        else:
            raise TypeError('data type must be "str" or "bytes"')


class ResponseIterator(object):
    """
    Iterable combined of response body list and response iterator
    Response body will be yielded first, then iterator will be iterated and yielded.
    """

    def __init__(self, response_body, response_iterator=None):
        self.response_body = response_body
        self.response_iterator = response_iterator or ()

    def __len__(self):
        return len(self.response_body) + len(self.response_iterator)

    def __iter__(self):
        for response_body in self.response_body:
            yield response_body
        for response_item in self.response_iterator:
            if isinstance(response_item, bytes):
                yield response_item
            elif isinstance(response_item, str):
                yield response_item.encode('utf-8')
            else:
                raise TypeError('response may only generate the sequence "str" and "bytes"')


class RequestProcessor(object):
    """
    Request processor. Performs handler creation, invocation, pre and post request processing, rendering of results to WSGI
    """

    def __init__(self, handler_class, req=None):
        """
        Class instance init
        :param handler_class: handler class, which will be create when request is processed
        :param req: optional keyword. It's *required* to pass it as a keyword argument. If not None, this one will be used instead of creating one from env while processing the request.
        :return: class instance
        """
        self.req = req
        self.handler_class = handler_class

    def process(self, env, responder):
        """
        WSGI entry point
        :param env: standard WSGI parameter (environ)
        :param responder: standard WSGI parameter (start_response)
        :return: standard WSGI (iterable)
        """
        req = self.req or Request(env)

        req.setHeader('Date', datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT'))

        # Run the request processing first
        response_iterator = self.handler_class(req)() or ()
        # Then, create a response iterator
        response_iterator = ResponseIterator(req.response_body, response_iterator)

        # Content-Length autodetection
        # Case 1: `len(req.response_body) == 1 and len(response_iterator) == 0`.
        # Case 2: `len(req.response_body) == 0 and len(response_iterator) == 1`.
        # So, in sum, they should be 1

        # Try simplified response if qualify, with `Content-Type` header automatic set
        try:
            len_response_iterator = len(response_iterator)
        except (TypeError, ValueError, KeyError, AttributeError, NotImplementedError):
            len_response_iterator = None

        def simple_response_body(response_body):
            if 'Content-Length' not in req.responseHeaders:
                req.setHeader('Content-Length', '%s' % len(response_body))
            return response_body,

        if len_response_iterator == 1:
            response_iterator = simple_response_body(next(iter(response_iterator)))
        # Otherwise, full response.

        # Set cookie header before calling responder
        for acookie in list(req.cookie.keys()):
            req.responseHeaders.add_header('Set-Cookie', str(req.cookie[acookie].OutputString()))

        # PEP 3333: https://www.python.org/dev/peps/pep-3333/#the-write-callable
        responder('%d %s' % (req.status_code, req.status_message), req.responseHeaders.items())  # Don't use write() callable
        return response_iterator


__all__ = ['Request', 'RequestProcessor', 'RequestException']
