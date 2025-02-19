# -*- coding: utf-8 -*-

import types
import io
import cgi
import json
import urllib.parse

from ....util import context as _context


def _params_ex(fs, param, not_found_exc):
    if fs is None:
        raise not_found_exc()

    if param in fs:
        objs = fs[param]
        if not (type(objs) is type([])):
            objs = [objs]
    else:
        objs = []

    return objs


class QueryString(object):
    class NotFoundError(Exception):
        pass

    class ParseError(Exception):
        pass

    def __init__(self, req):
        if req.query_string:
            self.fs = urllib.parse.parse_qs(req.query_string, True, True)
        else:
            self.fs = ()

    def paramlist(self, name):
        return _params_ex(self.fs, name, self.NotFoundError)

    def param(self, name):
        value_iterator = iter(self.paramlist(name))
        try:
            return next(value_iterator)
        except StopIteration:
            raise self.NotFoundError


class QueryStringContextItem(_context.AutoRefContextItem):
    def __init__(self, req):
        super(QueryStringContextItem, self).__init__()
        self.req = req

    def new(self):
        return QueryString(self.req)

    def delete(self):
        pass


class QueryStringParser(object):
    class Wrapper(object):
        def __init__(self, method):
            self.method = method

        def __get__(self, instance, owner):
            def wrapper(*args, **kwargs):
                # assertion checks for bound methods
                if instance is None:
                    raise AssertionError('Session decorator allows only bound methods')
                # assertion checks for additional request presence requirements
                try:
                    instance.req
                except AttributeError:
                    raise AssertionError('Session decorator allows only bound methods, bound to objects with \'req\' attribute')
                instance.req.context.ref('request_body_parser', lambda: RequestBodyParserContextItem(instance.req))
                try:
                    return self.method(*args, **kwargs)
                finally:
                    instance.req.context.unref('request_body_parser')

            return types.MethodType(wrapper, instance)

        def __call__(self, instance, *args, **kwargs):
            return self.__get__(instance, type(instance))(*args, **kwargs)

    def __init__(self, require=True):
        self.require = require

    def __call__(self, method):
        return self.Wrapper(method)


class Form(object):
    class NotFoundError(Exception):
        pass

    class ParseError(Exception):
        pass

    def __init__(self, fs):
        self.fs = fs

    def _paramlist(self, name):
        return map(lambda item_map: str(item_map.value), filter(lambda item_filter: item_filter.filename is None, _params_ex(self.fs, name, self.NotFoundError)))

    def paramlist(self, name):
        return list(self._paramlist(name))

    def param(self, name):
        value_iterator = self._paramlist(name)
        try:
            return next(value_iterator)
        except StopIteration:
            raise self.NotFoundError

    def _filelist(self, name):
        return filter(lambda item_filter: item_filter.filename is not None, _params_ex(self.fs, name, self.NotFoundError))

    def filelist(self, name):
        return list(self._filelist(name))

    def file(self, name):
        value_iterator = self._filelist(name)
        try:
            return next(value_iterator)
        except StopIteration:
            raise self.NotFoundError


class RequestBodyParserImpl(object):
    def __init__(self, req):
        self.req = req

    def as_json(self):
        hdr_value, hdr_params = cgi.parse_header(self.req.request_headers.get('Content-Type'))
        if hdr_value not in ['text/json', 'application/json']:
            raise RuntimeError('Content-Type is unexpected', hdr_value, hdr_params)
        return json.loads(self.req.request_body.decode(hdr_params.get('charset') or 'utf-8'))

    def as_form(self):
        if not self.req.request_body:
            return Form(cgi.FieldStorage())

        environ = {'REQUEST_METHOD': 'POST'}
        value = self.req.requestHeaders.get('Content-Type')
        if value:
            environ['CONTENT_TYPE'] = value
        value = self.req.requestHeaders.get('Content-Length')
        if value:
            environ['CONTENT_LENGTH'] = value
        value = self.req.requestHeaders.get('Content-Disposition')
        if value:
            environ['CONTENT_DISPOSITION'] = value

        return Form(cgi.FieldStorage(io.BytesIO(self.req.request_body), environ=environ, keep_blank_values=True, strict_parsing=True))


class RequestBodyParserContextItem(_context.AutoRefContextItem):
    def __init__(self, req):
        super(RequestBodyParserContextItem, self).__init__()
        self.req = req

    def new(self):
        return RequestBodyParserImpl(self.req)

    def delete(self):
        pass


class RequestBodyParser(object):
    class Wrapper(object):
        def __init__(self, method):
            self.method = method

        def __get__(self, instance, owner):
            def wrapper(*args, **kwargs):
                # assertion checks for bound methods
                if instance is None:
                    raise AssertionError('Session decorator allows only bound methods')
                # assertion checks for additional request presence requirements
                try:
                    instance.req
                except AttributeError:
                    raise AssertionError('Session decorator allows only bound methods, bound to objects with \'req\' attribute')
                instance.req.context.ref('request_body_parser', lambda: RequestBodyParserContextItem(instance.req))
                try:
                    return self.method(*args, **kwargs)
                finally:
                    instance.req.context.unref('request_body_parser')

            return types.MethodType(wrapper, instance)

        def __call__(self, instance, *args, **kwargs):
            return self.__get__(instance, type(instance))(*args, **kwargs)

    def __init__(self, require=True):
        self.require = require

    def __call__(self, method):
        return self.Wrapper(method)


class RequestBodyFormContextItem(_context.AutoRefContextItem):
    def __init__(self, req):
        super(RequestBodyFormContextItem, self).__init__()
        self.req = req

    def new(self):
        return RequestBodyParserImpl(self.req).as_form()

    def delete(self):
        pass


class RequestBodyForm(object):
    class Wrapper(object):
        def __init__(self, method):
            self.method = method

        def __get__(self, instance, owner):
            def wrapper(*args, **kwargs):
                # assertion checks for bound methods
                if instance is None:
                    raise AssertionError('Session decorator allows only bound methods')
                # assertion checks for additional request presence requirements
                try:
                    instance.req
                except AttributeError:
                    raise AssertionError('Session decorator allows only bound methods, bound to objects with \'req\' attribute')
                instance.req.context.ref('request_body_form', lambda: RequestBodyFormContextItem(instance.req))
                try:
                    return self.method(*args, **kwargs)
                finally:
                    instance.req.context.unref('request_body_form')

            return types.MethodType(wrapper, instance)

        def __call__(self, instance, *args, **kwargs):
            return self.__get__(instance, type(instance))(*args, **kwargs)

    def __init__(self, require=True):
        self.require = require

    def __call__(self, method):
        return self.Wrapper(method)


__all__ = ['QueryStringParser', 'RequestBodyParser', 'RequestBodyForm']
