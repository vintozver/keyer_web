# -*- coding: utf-8 -*-

from .. import mongo as mod_mongo


class UserDocument(mod_mongo.mongoengine.Document):
    meta = {'db_alias': mod_mongo.mongoengine_alias, 'collection': 'users', 'strict': False}

    name = mod_mongo.mongoengine.StringField(max_length=128)
    email = mod_mongo.mongoengine.StringField(max_length=64, unique=True)
    flags = mod_mongo.mongoengine.StringField(max_length=16)
