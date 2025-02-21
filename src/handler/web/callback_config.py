# -*- coding: utf-8 -*-

import json
import http.client

from ..ext.decorator.session import Session as _deco_Session
from ..ext.paramed_cgi import Handler as paramed_cgi_Handler
from ..ext.paramed_cgi import HandlerError as paramed_cgi_HandlerError
from ...module.mongo import user as mod_mongo_user
from ...module.mongo import card as mod_mongo_card


class HandlerError(paramed_cgi_HandlerError):
    pass


class Handler(paramed_cgi_Handler):
    @_deco_Session()
    def __call__(self):
        if self.req.method != 'GET':
            raise HandlerError('Method unsupported')

        user_map = dict(map(lambda user: (user.id, user), mod_mongo_user.UserDocument.objects()))

        # see https://github.com/vintozver/keyer/blob/master/src/dispatcher.py
        # for the schema compatibility
        response = {
            'users': dict(map(lambda user: (
                user.email,
                [user.name, user.flags, user.id.generation_time.isoformat()]
            ), user_map.values())),
            'issued_cards': dict(map(lambda issued_card: (
                issued_card.id.hex,
                [
                    issued_card.mifare_classic_access_key_B.hex(),
                    user_map[issued_card.user_id].email,
                    issued_card.issued.isoformat(),
                ]
            ), mod_mongo_card.IssuedCard.objects())),
            'revoked_cards': dict(map(lambda revoked_card: (
                revoked_card.id.hex,
                [
                    revoked_card.mifare_classic_access_key_B.hex(),
                    user_map[revoked_card.user_id].email,
                    revoked_card.issued.isoformat(),
                    revoked_card.revoked.isoformat(),
                ]
            ), mod_mongo_card.RevokedCard.objects())),
        }

        self.req.setResponseCode(http.client.OK, http.client.responses[http.client.OK])
        self.req.setHeader('Cache-Control', 'public, no-cache')
        self.req.setHeader('Content-Type', 'application/json')
        self.req.write(json.dumps(response))
