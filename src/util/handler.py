# -*- coding: utf-8 -*-


class Handler(object):
    def __init__(self, req):
        self.req = req

    def __call__(self):
        raise NotImplementedError

    def __iter__(self):
        return
        yield


class HandlerError(Exception):
    pass


__all__ = [Handler, HandlerError]
