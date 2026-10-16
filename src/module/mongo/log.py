# -*- coding: utf-8 -*-

from pymongo import UpdateOne
from pymongo.errors import BulkWriteError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from .. import mongo as mod_mongo


UNIT_EVENTS = ('card_tap', 'card_personalize', 'card_format')
EVENTS = UNIT_EVENTS + ('remote_unlock', 'revocation')


class LogEvent(mod_mongo.mongoengine.Document):
    meta = {'db_alias': mod_mongo.mongoengine_alias, 'collection': 'log'}

    oid = mod_mongo.mongoengine.ObjectIdField(
        db_field='_id', primary_key=True, default=mod_mongo.bson.ObjectId)
    card_id = mod_mongo.mongoengine.UUIDField(null=True)
    user_id = mod_mongo.mongoengine.ObjectIdField(null=True)
    name = mod_mongo.mongoengine.StringField(max_length=128, default='')
    event = mod_mongo.mongoengine.StringField(required=True, choices=EVENTS)
    unit_id = mod_mongo.mongoengine.ObjectIdField(null=True)


class EventConflict(Exception):
    pass


def store_batch(events):
    documents = []
    for event in events:
        event.validate()
        documents.append(dict(event.to_mongo()))
    collection = LogEvent._get_collection()
    operations = [
        UpdateOne(
            (
                {
                    key: document[key]
                    for key in ('_id', 'card_id', 'unit_id', 'event')
                }
                if document.get('card_id') is not None else document
            ),
            {'$setOnInsert': document},
            upsert=True)
        for document in documents
    ]

    def commit(session):
        collection.bulk_write(operations, ordered=True, session=session)

    try:
        with collection.database.client.start_session() as session:
            session.with_transaction(
                commit, read_concern=ReadConcern('snapshot'),
                write_concern=WriteConcern('majority'))
    except BulkWriteError as err:
        errors = err.details.get('writeErrors', [])
        if errors and all(item['code'] == 11000 for item in errors) and not err.details.get('writeConcernErrors'):
            raise EventConflict('An event oid is already stored with different data') from err
        raise
