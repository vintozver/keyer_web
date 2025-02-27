# -*- coding: utf-8 -*-

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

        try:
            param_identifier = self.cgi_params.param_post('identifier')
        except self.cgi_params.NotFoundError:
            param_identifier = None
        if param_identifier is not None:
            param_identifier = uuid.UUID(param_identifier)

        card = mod_mongo_card.IssuedCard.objects(id=param_identifier).get()
        if not user.admin and card.user_id != user.id and card.email != user.email:
            self.req.setResponseCode(http.client.FORBIDDEN, http.client.responses[http.client.FORBIDDEN])
            self.req.setHeader('Cache-Control', 'public, no-cache')
            self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
            self.req.write('Not your card')

        conn = http.client.HTTPConnection(config.remote_unit.host)
        try:
            conn.request('PATCH', '/', headers={'X-Card-Identifier': card.id.hex})
            resp = conn.getresponse()
            if resp.status == http.client.ACCEPTED:
                revoked_card = mod_mongo_card.RevokedCard()
                revoked_card.id = card.id
                if card.user_id is not None:
                    revoked_card.user_id = card.user_id
                if card.email is not None:
                    revoked_card.email = card.email
                revoked_card.mifare_classic_access_key_B = card.mifare_classic_access_key_B
                revoked_card.issued = card.issued
                revoked_card.save()
                card.delete()

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
