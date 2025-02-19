# -*- coding: utf-8 -*-

from collections import OrderedDict
import bson
import gridfs
import mongoengine
import pymongo
import pymongo.errors

from ...util.context import AutoRefContextItem as _AutoRefContextItem
from ... import config


class DbSessionController(_AutoRefContextItem):
    def new(self):
        kwargs = dict()
        if config.db_mongo.user:
            kwargs['username'] = config.db_mongo.user
            kwargs['password'] = config.db_mongo.password
            kwargs['authSource'] = config.db_mongo.name
        return pymongo.MongoClient(
            config.db_mongo.host, config.db_mongo.port,
            document_class=OrderedDict, tz_aware=True,
            **kwargs)

    def delete(self):
        pass


mongoengine_alias = object()
mongoengine_connection_kwargs = dict()
if config.db_mongo.user is not None:
    mongoengine_connection_kwargs['username'] = config.db_mongo.user
    mongoengine_connection_kwargs['password'] = config.db_mongo.password
    mongoengine_connection_kwargs['authSource'] = config.db_mongo.name
mongoengine_connection_kwargs['document_class'] = OrderedDict
mongoengine_connection_kwargs['tz_aware'] = True
mongoengine.register_connection(
    mongoengine_alias,
    name=config.db_mongo.name, host=config.db_mongo.host, port=config.db_mongo.port,
    **mongoengine_connection_kwargs)


__all__ = ['bson', 'pymongo', 'gridfs', 'DbSessionController', 'mongoengine', 'mongoengine_alias']
