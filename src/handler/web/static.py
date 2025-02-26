# -*- coding: utf-8 -*-

import importlib.resources
import http.client
import os.path

from ..ext.paramed_cgi import Handler as _Handler, HandlerError as _HandlerError


class HandlerError(_HandlerError):
    pass


class Handler(_Handler):
    STATIC_PATH = os.path.normpath(str(importlib.resources.files(__package__).joinpath('../../static')))

    def view_notfound(self, err):
        from . import skeleton as mod_tmpl
        try:
            content = mod_tmpl.TemplateFactory(self.req, 'error_notfound').render({'description': err})
        except mod_tmpl.TemplateError:
            raise HandlerError('Template error')
        self.req.setResponseCode(http.client.NOT_FOUND, http.client.responses[http.client.NOT_FOUND])
        self.req.setHeader('Content-Type', 'text/html; charset=utf-8')
        self.req.write(content)

    # noinspection PyMethodOverriding
    def __call__(self, path):
        if path.find('/') != 0:
            raise HandlerError('Попытка взлома! Допускается только полный путь к документу')
        rel_path = os.path.normpath(path)[1:]  # will remove all "../", make path "safe"

        from ..ext import static as mod
        file_path = os.path.join(self.STATIC_PATH, rel_path)
        if os.path.isfile(file_path):
            try:
                return mod.Handler(self.req)(path=file_path)
            except mod.NotFoundError as err:
                return self.view_notfound(err.args[0])
            except mod.HandlerError as err:
                raise HandlerError('Error in dependent handler', err)

        return self.view_notfound('Not found')
