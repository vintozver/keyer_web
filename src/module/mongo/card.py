# -*- coding: utf-8 -*-

import datetime

from .. import mongo as mod_mongo


class IssuedCard(mod_mongo.mongoengine.Document):
    meta = {'db_alias': mod_mongo.mongoengine_alias, 'collection': 'issued_card', 'strict': False}

    id = mod_mongo.mongoengine.UUIDField(db_field='_id', primary_key=True, required=True)
    email = mod_mongo.mongoengine.EmailField()  # email associated with the card; the card has the SHA256 of it stored
    user_id = mod_mongo.mongoengine.ObjectIdField()
    mifare_classic_access_key_B = mod_mongo.mongoengine.BinaryField(max_bytes=6)
    issued = mod_mongo.mongoengine.DateTimeField(required=True, default=lambda: datetime.datetime.now(tz=datetime.UTC))


class RevokedCard(mod_mongo.mongoengine.Document):
    meta = {'db_alias': mod_mongo.mongoengine_alias, 'collection': 'revoked_card', 'strict': False}

    id = mod_mongo.mongoengine.UUIDField(db_field='_id', primary_key=True, required=True)
    email = mod_mongo.mongoengine.EmailField()  # email associated with the card; the card has the SHA256 of it stored
    user_id = mod_mongo.mongoengine.ObjectIdField()
    mifare_classic_access_key_B = mod_mongo.mongoengine.BinaryField(max_bytes=6)
    issued = mod_mongo.mongoengine.DateTimeField(required=True, default=lambda: datetime.datetime.now(tz=datetime.UTC))
    revoked = mod_mongo.mongoengine.DateTimeField(required=True, default=lambda: datetime.datetime.now(tz=datetime.UTC))
