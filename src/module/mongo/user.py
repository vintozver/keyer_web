# -*- coding: utf-8 -*-

from .. import mongo as mod_mongo


class UserDocument(mod_mongo.mongoengine.Document):
    meta = {'db_alias': mod_mongo.mongoengine_alias, 'collection': 'user', 'strict': False}

    name = mod_mongo.mongoengine.StringField(max_length=128)
    email = mod_mongo.mongoengine.EmailField(unique=True)
    active = mod_mongo.mongoengine.BooleanField(required=False, default=True)
    admin = mod_mongo.mongoengine.BooleanField(required=False, default=False)
    flags = mod_mongo.mongoengine.StringField(max_length=16)
    options = mod_mongo.mongoengine.DictField()
