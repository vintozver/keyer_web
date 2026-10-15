# -*- coding: utf-8 -*-

from .. import mongo as mod_mongo


class KeyItem(mod_mongo.mongoengine.EmbeddedDocument):
    id = mod_mongo.mongoengine.StringField(required=True)
    pub = mod_mongo.mongoengine.BinaryField(required=False)
    crt = mod_mongo.mongoengine.BinaryField(required=False)

    def clean(self):
        if bool(self.pub) == bool(self.crt):
            raise mod_mongo.mongoengine.ValidationError('Specify exactly one of pub or crt')


class UnitDocument(mod_mongo.mongoengine.Document):
    meta = {'db_alias': mod_mongo.mongoengine_alias, 'collection': 'unit', 'strict': False}

    name = mod_mongo.mongoengine.StringField(required=True, max_length=128)
    host = mod_mongo.mongoengine.StringField(required=True)
    port = mod_mongo.mongoengine.IntField(default=80, min_value=1, max_value=65535)
    keyset = mod_mongo.mongoengine.EmbeddedDocumentListField(KeyItem, default=list)

    def clean(self):
        key_ids = [key.id for key in self.keyset]
        if len(key_ids) != len(set(key_ids)):
            raise mod_mongo.mongoengine.ValidationError('Signing key ids must be unique within a unit')
