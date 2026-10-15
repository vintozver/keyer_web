# -*- coding: utf-8 -*-

import http.client

from bson import ObjectId
from bson.errors import InvalidId

from ..ext.paramed_cgi import Handler as paramed_cgi_Handler
from ...module.mongo.unit import UnitDocument


class Handler(paramed_cgi_Handler):
    def connect_unit(self):
        try:
            unit_id = self.cgi_params.param_post('unit_id')
        except self.cgi_params.NotFoundError:
            unit_id = None
        if unit_id is None:
            units = list(UnitDocument.objects.limit(2))
            if len(units) != 1:
                self.unit_error(http.client.BAD_REQUEST, 'Select a unit using unit_id')
                return None
            unit = units[0]
        else:
            try:
                unit = UnitDocument.objects(id=ObjectId(unit_id)).first() if isinstance(unit_id, str) else None
            except (InvalidId, TypeError):
                unit = None
            if unit is None:
                self.unit_error(http.client.NOT_FOUND, 'Unknown unit')
                return None
        return http.client.HTTPConnection(unit.host, unit.port)

    def unit_error(self, status, message):
        self.req.setResponseCode(status, http.client.responses[status])
        self.req.setHeader('Cache-Control', 'no-store')
        self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
        self.req.write(message)
