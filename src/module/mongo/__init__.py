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
        return pymongo.MongoClient(
            config.mongodb_uri, document_class=OrderedDict, tz_aware=True)

    def delete(self):
        pass


mongoengine_alias = object()
mongoengine.register_connection(
    mongoengine_alias, name=config.name, host=config.mongodb_uri,
    document_class=OrderedDict, tz_aware=True)


__all__ = ['bson', 'pymongo', 'gridfs', 'DbSessionController', 'mongoengine', 'mongoengine_alias']
