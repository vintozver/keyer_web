# -*- coding: utf-8 -*-

import http.client
import json
import sys
import uuid

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError

from ...module.mongo import card as mod_mongo_card
from ...module.mongo.log import EventConflict, LogEvent, UNIT_EVENTS, store_batch
from ...module.mongo import user as mod_mongo_user
from ...util.handler import Handler as _Handler
from ...util.logger import Logger


MAX_EVENTS = 1000
MAX_BODY_BYTES = 1024 * 1024


def resolve_card_identities(card_ids):
    cards = {
        card.id: card
        for card in mod_mongo_card.IssuedCard.objects(id__in=list(card_ids))
    }
    cards.update({
        card.id: card
        for card in mod_mongo_card.RevokedCard.objects(id__in=list(card_ids))
        if card.id not in cards
    })

    user_ids = {card.user_id for card in cards.values() if card.user_id is not None}
    emails = {
        card.email for card in cards.values()
        if card.user_id is None and card.email is not None
    }
    users_by_id = {
        user.id: user
        for user in mod_mongo_user.UserDocument.objects(id__in=list(user_ids))
    } if user_ids else {}
    users_by_email = {
        user.email: user
        for user in mod_mongo_user.UserDocument.objects(email__in=list(emails))
    } if emails else {}
    identities = {}
    for card_id, card in cards.items():
        user = (
            users_by_id.get(card.user_id) if card.user_id is not None
            else users_by_email.get(card.email)
        )
        if user is not None:
            identities[card_id] = (user.id, user.name or '')
    return identities


def parse_events(payload, unit_id):
    if not isinstance(payload, dict) or set(payload) != {'events'}:
        raise ValueError('Expected a JSON object containing only events')
    items = payload['events']
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_EVENTS:
        raise ValueError('events must contain between 1 and %s entries' % MAX_EVENTS)
    parsed = []
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {'oid', 'event', 'card_id'}:
            raise ValueError('Each event requires only oid, event and card_id')
        oid = item['oid']
        if not isinstance(oid, str) or not ObjectId.is_valid(oid):
            raise ValueError('oid must be a 24-character hexadecimal ObjectId')
        if not isinstance(item['card_id'], str):
            raise ValueError('card_id must be a UUID')
        try:
            card_id = uuid.UUID(item['card_id'])
        except ValueError as err:
            raise ValueError('card_id must be a UUID') from err
        if item['event'] not in UNIT_EVENTS:
            raise ValueError('Units may only report card_tap, card_personalize and card_format')
        oid = ObjectId(oid)
        if oid in seen:
            raise ValueError('Duplicate oid in batch')
        seen.add(oid)
        parsed.append((oid, item['event'], card_id))
    identities = resolve_card_identities({card_id for _, _, card_id in parsed})
    events = []
    for oid, event, card_id in parsed:
        user_id, name = identities.get(card_id, (None, ''))
        events.append(LogEvent(
            oid=oid, card_id=card_id, event=event, unit_id=unit_id,
            user_id=user_id, name=name))
    return events


class Handler(_Handler):
    def respond(self, status, payload):
        self.req.setResponseCode(status, http.client.responses[status])
        self.req.setHeader('Cache-Control', 'no-store')
        self.req.setHeader('Content-Type', 'application/json')
        self.req.write(json.dumps(payload))

    def __call__(self):
        if self.req.method != 'POST':
            self.req.setHeader('Allow', 'POST')
            return self.respond(http.client.METHOD_NOT_ALLOWED, {'error': 'Use POST'})
        content_type = (self.req.getHeader('Content-Type') or '').split(';', 1)[0].strip().lower()
        if content_type != 'application/json':
            return self.respond(http.client.UNSUPPORTED_MEDIA_TYPE, {'error': 'Use application/json'})
        if len(self.req.request_body) > MAX_BODY_BYTES:
            return self.respond(http.client.REQUEST_ENTITY_TOO_LARGE, {'error': 'Batch exceeds 1 MiB'})
        try:
            events = parse_events(json.loads(self.req.request_body), self.req.unit.id)
        except (ValueError, UnicodeDecodeError, InvalidId) as err:
            return self.respond(http.client.BAD_REQUEST, {'error': str(err)})
        except PyMongoError:
            Logger(self.req).traceback(*sys.exc_info())
            return self.respond(http.client.SERVICE_UNAVAILABLE, {
                'error': 'Log storage unavailable; retain the batch and retry',
            })
        try:
            store_batch(events)
        except EventConflict as err:
            return self.respond(http.client.CONFLICT, {'error': str(err)})
        except PyMongoError:
            Logger(self.req).traceback(*sys.exc_info())
            return self.respond(http.client.SERVICE_UNAVAILABLE, {
                'error': 'Log storage unavailable; retain the batch and retry',
            })
        return self.respond(http.client.OK, {'accepted': [str(event.oid) for event in events]})
