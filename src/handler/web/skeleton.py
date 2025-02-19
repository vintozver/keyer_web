# -*- coding: utf-8 -*-

from ..ext.decorator.session import Session as _deco_Session
from ...module.template.filesystem import TemplateFactory as _TemplateFactory, TemplateError as _TemplateError
from ...util.handler import Handler as _Handler, HandlerError as _HandlerError


class HandlerError(_HandlerError):
    pass


class Handler(_Handler):
    @_deco_Session()
    def tmpl_params(self):
        tmpl_params = dict()
        return tmpl_params


def TemplateFactory(req, name):
    try:
        tmpl_params = Handler(req).tmpl_params()
    except HandlerError as err:
        raise _TemplateError('Error retrieving skeleton params', err)
    return _TemplateFactory(name, globals=tmpl_params)


TemplateError = _TemplateError


__all__ = ['TemplateFactory', 'TemplateError']
