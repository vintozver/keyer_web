# -*- coding: utf-8 -*-

import types

from ....util.context import AutoRefContextItem
from ....module import session as mod_session


class SessionController(AutoRefContextItem):
    def __init__(self, req):
        super(SessionController, self).__init__()
        self.req = req

    def new(self):
        return mod_session.MongoDbSession(self.session_cookie_reader, self.session_cookie_writer)

    def delete(self):
        pass

    def session_cookie_reader(self):
        return self.req.getCookie('sid', True, True)

    def session_cookie_writer(self, value):
        self.req.addCookie('sid', value, expires=None, domain=None, path='/', secure=False)


class Session(object):
    class Wrapper(object):
        def __init__(self, method, require=True):
            self.method = method
            self.require = require

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
                instance.req.context.ref('session', lambda: SessionController(instance.req))
                try:
                    return self.method(*args, **kwargs)
                finally:
                    instance.req.context.unref('session')

            return types.MethodType(wrapper, instance)

        def __call__(self, instance, *args, **kwargs):
            return self.__get__(instance, type(instance))(*args, **kwargs)

    def __init__(self, require=True):
        self.require = require

    def __call__(self, method):
        return self.Wrapper(method, self.require)


__all__ = ['Session']
