# -*- coding: utf-8 -*-

import binascii
import json
import http.client
import uuid

from ..ext.decorator.session import Session as _deco_Session
from ..ext.paramed_cgi import Handler as paramed_cgi_Handler
from ..ext.paramed_cgi import HandlerError as paramed_cgi_HandlerError
from ...module import mongo as mod_mongo
from ...module.mongo import user as mod_mongo_user
from ...module.mongo import card as mod_mongo_card
from ... import config


class HandlerError(paramed_cgi_HandlerError):
    pass


class Handler(paramed_cgi_Handler):
    @_deco_Session()
    def __call__(self):
        if self.req.method != 'POST':
            raise HandlerError('Method unsupported')

        user_id = self.req.context.session['user_id']
        user = mod_mongo_user.UserDocument.objects(id=mod_mongo.bson.objectid.ObjectId(user_id), active=True).get()

        if not user.admin:
            self.req.setResponseCode(http.client.FORBIDDEN, http.client.responses[http.client.FORBIDDEN])
            self.req.setHeader('Cache-Control', 'public, no-cache')
            self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
            self.req.write('Not admin')

        conn = http.client.HTTPConnection(config.remote_unit.host)
        try:
            conn.request('DELETE', '/')
            resp = conn.getresponse()
            if resp.status == http.client.OK:
                json_old_card = json.loads(resp.read())
                old_card_identifier = uuid.UUID(json_old_card['identifier'])

                mod_mongo_card.IssuedCard.objects(id=old_card_identifier).delete()
                mod_mongo_card.RevokedCard.objects(id=old_card_identifier).delete()

                self.req.setResponseCode(http.client.OK, http.client.responses[http.client.OK])
                self.req.setHeader('Cache-Control', 'public, no-cache')
                self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
                self.req.write('')
            else:
                self.req.setResponseCode(resp.status, resp.reason)
                self.req.setHeader('Cache-Control', 'public, no-cache')
                self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
                self.req.write(resp.read())
        finally:
            conn.close()
