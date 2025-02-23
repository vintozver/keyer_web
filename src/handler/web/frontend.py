# -*- coding: utf-8 -*-

import collections.abc
import http.client
import importlib
import re
import sys
import traceback

from functools import reduce

from ...util.handler import Handler as _Handler, HandlerError as _HandlerError
from ...util.logger import Logger


class Handler(_Handler):
    ROUTE_MAP = [
        {'regex': re.compile(r'^/$'), 'handler': 'handler.web.index'},
        {'regex': re.compile(r'^/static(/.*)$'), 'handler': 'handler.web.static', 'params': {'path': lambda rex: rex.group(1)}},
        {'regex': re.compile(r'^/card_personalize/?$'), 'handler': 'handler.web.card_personalize'},
        {'regex': re.compile(r'^/card_revoke/?$'), 'handler': 'handler.web.card_revoke'},
        {'regex': re.compile(r'^/remote_unlock/?$'), 'handler': 'handler.web.remote_unlock'},
    ]

    @classmethod
    def handle_map(cls, route_map, path):
        for route_item in route_map:
            regex = route_item['regex']
            match = regex.match(path)
            if match is not None:
                if 'map' in route_item:
                    result = cls.handle_map(route_item['map'], regex.sub('', path, 1))
                    if result is not None:
                        return result
                else:
                    params = dict()
                    for param_key, param_value in route_item.get('params', {}).items():
                        if isinstance(param_value, collections.abc.Callable):
                            params[param_key] = param_value(match)
                        else:
                            params[param_key] = param_value
                    return route_item['handler'], params

    def view_notfound(self, err):
        from .skeleton import TemplateFactory, TemplateError
        try:
            content = TemplateFactory(self.req, 'error_notfound').render({'description': err})
        except TemplateError:
            raise HandlerError('Template error')
        self.req.setResponseCode(http.client.NOT_FOUND, http.client.responses[http.client.NOT_FOUND])
        self.req.setHeader('Content-Type', 'text/html; charset=utf-8')
        self.req.write(content)

    def view_error(self, err_type, err_value, err_tb):
        tb = reduce(
            lambda line_up, line_down: line_up + '\n' + line_down,
            ['%s: %s' % (item[0], item[1]) for item in traceback.extract_tb(err_tb)]
        )
        from .skeleton import TemplateFactory, TemplateError
        try:
            content = TemplateFactory(self.req, 'error_internal').render({'err_type': err_type, 'err_value': err_value, 'err_tb': tb})
            self.req.setHeader('Content-Type', 'text/html; charset=utf-8')
        except TemplateError:
            content = '''\
При обработке запроса произошла ошибка\n
Тип ошибки: %s\n
Значение ошибки: %s\n
Информация для разработчика:\n%s\
''' % (err_type, err_value, tb)
            self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
        self.req.setResponseCode(http.client.INTERNAL_SERVER_ERROR, http.client.responses[http.client.INTERNAL_SERVER_ERROR])
        self.req.write(content)

    def __call__(self):
        try:
            module = self.handle_map(self.ROUTE_MAP, self.req.path)
            if module is None:
                return self.view_notfound('No handler found')
            module_name, module_params = module

            module = importlib.import_module("..." + module_name, __package__)
            module_handler = module.Handler(self.req)
            return module_handler(**module_params)
        except:
            err_type, err_value, err_tb = sys.exc_info()
            Logger(self.req).traceback(err_type, err_value, err_tb)
            return self.view_error(err_type, err_value, err_tb)


class HandlerError(_HandlerError):
    pass
