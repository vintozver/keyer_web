#!run/python_env/bin/python
# -*- coding: utf-8 -*-


from .request import Request, RequestProcessor


def Application(env, responder):
    req = Request(env)

    from ...handler.web.frontend import Handler, HandlerError
    try:
        return RequestProcessor(Handler, req=req).process(env, responder)
    except HandlerError as err:
        raise RuntimeError('Application handler error', err)
