import datetime
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

from bson import ObjectId
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
import jwt
import mongoengine
from pymongo import MongoClient
from pymongo.errors import BulkWriteError, OperationFailure

from keyer_web.handler.web import backend, callback_config, callback_log, frontend
from keyer_web.handler.web import card_revoke, remote_unlock
from keyer_web.module.mongo import log, user
from keyer_web.module.mongo.unit import KeyItem, UnitDocument
from keyer_web.util.web import unit_auth
from keyer_web.util.web.request import Request


def request(body, method='POST', path='/log', content_type='application/json'):
    return Request({
        'PATH_INFO': path, 'REQUEST_METHOD': method,
        'wsgi.input': io.BytesIO(body), 'CONTENT_TYPE': content_type,
    })


def event(**values):
    return {'oid': str(ObjectId()), 'event': 'card_tap', **values}


class LogCallbackTests(unittest.TestCase):
    def setUp(self):
        self.unit_id = ObjectId()

    def invoke(self, payload=None, body=None, **kwargs):
        req = request(body if body is not None else json.dumps(payload).encode(), **kwargs)
        req.unit = SimpleNamespace(id=self.unit_id)
        with patch.object(callback_log, 'store_batch') as store:
            callback_log.Handler(req)()
        return req, store

    def test_each_unit_event_is_bound_to_authenticated_unit(self):
        items = [event(event=kind) for kind in log.UNIT_EVENTS]
        req, store = self.invoke({'events': items})
        self.assertEqual(req.status_code, 200)
        self.assertEqual(json.loads(b''.join(req.response_body)), {
            'accepted': [item['oid'] for item in items],
        })
        self.assertEqual(req.responseHeaders['Cache-Control'], 'no-store')
        for item, document in zip(items, store.call_args.args[0]):
            document.validate()
            self.assertEqual(document.oid, ObjectId(item['oid']))
            self.assertIsNone(document.user_id)
            self.assertEqual(document.name, '')
            self.assertEqual(document.event, item['event'])
            self.assertEqual(document.unit_id, self.unit_id)

    def test_unit_event_does_not_bind_user_identity(self):
        req, store = self.invoke({'events': [event()]})
        self.assertEqual(req.status_code, 200)
        self.assertIsNone(store.call_args.args[0][0].user_id)
        self.assertEqual(store.call_args.args[0][0].name, '')

    def test_invalid_payload_never_writes_any_events(self):
        item = event()
        cases = [
            None, [], {}, {'events': []}, {'events': {}},
            {'events': [item], 'unit_id': str(ObjectId())},
            {'events': [item, item]}, {'events': [None]},
            {'events': [event(oid=None)]}, {'events': [event(oid=42)]},
            {'events': [event(oid='bad')]}, {'events': [event(user_id=str(ObjectId()))]},
            {'events': [event(name='Resident')]}, {'events': [event(event='remote_unlock')]},
            {'events': [event(event='revocation')]}, {'events': [event(event={})]},
            {'events': [event(unit_id=str(ObjectId()))]},
            {'events': [event(), event(oid='bad')]},
            {'events': [event() for _ in range(callback_log.MAX_EVENTS + 1)]},
        ]
        for payload in cases:
            with self.subTest(payload=str(payload)[:150]):
                req, store = self.invoke(payload)
                self.assertEqual(req.status_code, 400)
                self.assertIn('error', json.loads(b''.join(req.response_body)))
                store.assert_not_called()

    def test_malformed_json_and_encoding(self):
        for body in (b'{', b'\xff'):
            req, store = self.invoke(body=body)
            self.assertEqual(req.status_code, 400)
            store.assert_not_called()

    def test_method_media_type_and_size_limits(self):
        cases = [
            ({'method': 'GET'}, 405),
            ({'content_type': 'text/plain'}, 415),
            ({'body': b' ' * (callback_log.MAX_BODY_BYTES + 1)}, 413),
        ]
        for kwargs, status in cases:
            req, store = self.invoke({'events': [event()]}, **kwargs)
            self.assertEqual(req.status_code, status)
            store.assert_not_called()
            if status == 405:
                self.assertEqual(req.responseHeaders['Allow'], 'POST')
        req, _ = self.invoke({'events': [event()]}, content_type='application/json; charset=utf-8')
        self.assertEqual(req.status_code, 200)

    def test_maximum_batch_size_is_accepted(self):
        req, store = self.invoke({'events': [
            event() for _ in range(callback_log.MAX_EVENTS)
        ]})
        self.assertEqual(req.status_code, 200)
        self.assertEqual(len(store.call_args.args[0]), callback_log.MAX_EVENTS)

    def test_conflict_and_storage_failures_are_not_acknowledged(self):
        for error, status in (
            (log.EventConflict('Conflict'), 409),
            (OperationFailure('Transactions require a replica set', code=20), 503),
        ):
            req = request(json.dumps({'events': [event()]}).encode())
            req.unit = SimpleNamespace(id=self.unit_id)
            with (
                patch.object(callback_log, 'store_batch', side_effect=error),
                patch.object(callback_log, 'Logger') as logger,
            ):
                callback_log.Handler(req)()
            self.assertEqual(req.status_code, status)
            self.assertNotIn('accepted', json.loads(b''.join(req.response_body)))
            if status == 503:
                logger.return_value.traceback.assert_called_once()

    def test_signed_batch_dispatch_on_both_routers(self):
        private_key = ed25519.Ed25519PrivateKey.generate()
        unit = UnitDocument(
            id=self.unit_id, name='Door', host='localhost',
            keyset=[KeyItem(id='signing', pub=private_key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))])
        token = jwt.encode({}, private_key, algorithm='EdDSA', headers={
            'unit_id': str(unit.id), 'kid': 'signing',
            'dt': datetime.datetime.now(datetime.UTC).isoformat(),
        })
        for router in (frontend.Handler, backend.Handler):
            for path in ('/log', '/log/'):
                req = request(json.dumps({'events': [event()]}).encode(), path=path)
                req.requestHeaders['Authorization'] = 'Bearer ' + token
                with (
                    patch.object(unit_auth, 'UnitDocument') as units,
                    patch.object(callback_log, 'store_batch') as store,
                ):
                    units.objects.return_value.first.return_value = unit
                    router(req)()
                self.assertEqual(req.status_code, 200)
                self.assertEqual(store.call_args.args[0][0].unit_id, unit.id)
                self.assertEqual(req.context.items, {})


class LogStorageTests(unittest.TestCase):
    def test_schema(self):
        for kind in log.EVENTS:
            document = log.LogEvent(event=kind)
            document.validate()
            self.assertIsInstance(document.oid, ObjectId)
            self.assertEqual(document.to_mongo()['_id'], document.oid)
            self.assertIsNone(document.to_mongo()['unit_id'])
        with self.assertRaises(mongoengine.ValidationError):
            log.LogEvent(event='invalid').validate()

    def test_batch_uses_one_transaction_and_immutable_upserts(self):
        collection = MagicMock()
        session = collection.database.client.start_session.return_value.__enter__.return_value
        session.with_transaction.side_effect = lambda callback, **kwargs: callback(session)
        documents = [log.LogEvent(event=kind) for kind in log.UNIT_EVENTS]
        with patch.object(log.LogEvent, '_get_collection', return_value=collection):
            log.store_batch(documents)
        session.with_transaction.assert_called_once()
        options = session.with_transaction.call_args.kwargs
        self.assertEqual(options['read_concern'].document, {'level': 'snapshot'})
        self.assertEqual(options['write_concern'].document, {'w': 'majority'})
        args, kwargs = collection.bulk_write.call_args
        self.assertTrue(kwargs['ordered'])
        self.assertIs(kwargs['session'], session)
        self.assertEqual(len(args[0]), 3)
        for operation, document in zip(args[0], documents):
            self.assertEqual(operation._filter, dict(document.to_mongo()))
            self.assertEqual(operation._doc, {'$setOnInsert': dict(document.to_mongo())})

    def test_only_duplicate_key_errors_become_conflicts(self):
        collection = MagicMock()
        session = collection.database.client.start_session.return_value.__enter__.return_value
        for code, expected in ((11000, log.EventConflict), (121, BulkWriteError)):
            error = BulkWriteError({'writeErrors': [{'code': code}]})
            session.with_transaction.side_effect = error
            with (
                self.subTest(code=code),
                patch.object(log.LogEvent, '_get_collection', return_value=collection),
                self.assertRaises(expected),
            ):
                log.store_batch([log.LogEvent(event='card_tap')])

    def test_invalid_document_prevents_database_access(self):
        with (
            patch.object(log.LogEvent, '_get_collection') as collection,
            self.assertRaises(mongoengine.ValidationError),
        ):
            log.store_batch([log.LogEvent(event='bad')])
        collection.assert_not_called()


class ControllerAuditTests(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(
            id=ObjectId(), name='Resident', email='resident@example.com', admin=False)
        self.unit = SimpleNamespace(id=ObjectId(), host='localhost', port=80)

    def test_config_does_not_expose_user_ids_or_change_existing_tuples(self):
        self.user.flags = 'R*'
        req = request(b'', method='GET', path='/config')
        with (
            patch.object(callback_config.mod_mongo_user, 'UserDocument') as users,
            patch.object(callback_config.mod_mongo_card, 'IssuedCard') as issued,
            patch.object(callback_config.mod_mongo_card, 'RevokedCard') as revoked,
        ):
            users.objects.return_value = [self.user]
            issued.objects.return_value = revoked.objects.return_value = []
            callback_config.Handler(req)()
        payload = json.loads(b''.join(req.response_body))
        self.assertNotIn('user_ids', payload)
        self.assertEqual(payload['users'][self.user.email], [
            self.user.name, self.user.flags, self.user.id.generation_time.isoformat(),
        ])
        users.objects.assert_called_once_with(active=True)

    def invoke(self, module, status, log_error=None):
        req = request(
            json.dumps({'unit_id': str(self.unit.id), 'identifier': '0' * 32}).encode(),
            path='/command')
        req.context.session = {'user_id': str(self.user.id)}
        connection = Mock()
        connection.getresponse.return_value.status = status
        connection.getresponse.return_value.reason = 'Unit response'
        connection.getresponse.return_value.read.return_value = b'unit response'
        with (
            patch.object(user, 'UserDocument') as users,
            patch('keyer_web.handler.web.remote_unit.UnitDocument') as units,
            patch('keyer_web.handler.web.remote_unit.http.client.HTTPConnection', return_value=connection),
            patch.object(module, 'LogEvent') as audit,
            patch.object(card_revoke.mod_mongo_card, 'IssuedCard') as issued,
            patch.object(card_revoke.mod_mongo_card, 'RevokedCard'),
        ):
            users.objects.return_value.get.return_value = self.user
            units.objects.return_value.first.return_value = self.unit
            card = issued.objects.return_value.get.return_value
            card.user_id = self.user.id
            card.email = self.user.email
            if log_error is not None:
                audit.return_value.save.side_effect = log_error
            module.Handler.__dict__['__call__'].method(module.Handler(req))
        return req, connection, audit

    def test_successful_controller_operations_record_actor_and_unit(self):
        for module, status, kind in (
            (remote_unlock, 200, 'remote_unlock'), (card_revoke, 202, 'revocation'),
        ):
            req, connection, audit = self.invoke(module, status)
            self.assertEqual(req.status_code, 200)
            audit.assert_called_once_with(
                user_id=self.user.id, name=self.user.name, event=kind, unit_id=self.unit.id)
            audit.return_value.save.assert_called_once_with()
            connection.close.assert_called_once_with()

    def test_failed_controller_operations_do_not_record_success(self):
        for module in (remote_unlock, card_revoke):
            req, connection, audit = self.invoke(module, 503)
            self.assertEqual(req.status_code, 503)
            audit.assert_not_called()
            connection.close.assert_called_once_with()

    def test_audit_storage_failure_is_not_silenced(self):
        for module, status in ((remote_unlock, 200), (card_revoke, 202)):
            with self.assertRaises(OperationFailure):
                self.invoke(module, status, log_error=OperationFailure('Unavailable'))


@unittest.skipUnless(os.environ.get('KEYER_TEST_MONGODB_URI'), 'Set KEYER_TEST_MONGODB_URI to a replica set')
class LogTransactionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = MongoClient(os.environ['KEYER_TEST_MONGODB_URI'], serverSelectionTimeoutMS=5000)
        cls.database = cls.client['keyer_log_test_' + str(ObjectId())]

    @classmethod
    def tearDownClass(cls):
        cls.client.drop_database(cls.database.name)
        cls.client.close()

    def setUp(self):
        self.collection = self.database['log']
        self.collection.delete_many({})
        self.lookup = patch.object(log.LogEvent, '_get_collection', return_value=self.collection)
        self.lookup.start()
        self.addCleanup(self.lookup.stop)

    def test_commit_and_identical_retry(self):
        items = callback_log.parse_events({'events': [event(), event()]}, ObjectId())
        log.store_batch(items)
        log.store_batch(items)
        self.assertEqual(self.collection.count_documents({}), 2)
        self.assertEqual(self.collection.find_one({'_id': items[0].oid}), dict(items[0].to_mongo()))

    def test_conflicting_event_rolls_back_new_events(self):
        unit_id = ObjectId()
        original = event()
        log.store_batch(callback_log.parse_events({'events': [original]}, unit_id))
        for changes in (
            {'event': 'card_format'},
        ):
            new = event()
            batch = callback_log.parse_events({'events': [new, {**original, **changes}]}, unit_id)
            with self.assertRaises(log.EventConflict):
                log.store_batch(batch)
            self.assertIsNone(self.collection.find_one({'_id': ObjectId(new['oid'])}))
            self.assertEqual(self.collection.count_documents({}), 1)

    def test_unit_cannot_reuse_another_units_event_oid(self):
        original = event()
        log.store_batch(callback_log.parse_events({'events': [original]}, ObjectId()))
        with self.assertRaises(log.EventConflict):
            log.store_batch(callback_log.parse_events({'events': [event(), original]}, ObjectId()))
        self.assertEqual(self.collection.count_documents({}), 1)

    def test_existing_event_and_new_event_can_be_acknowledged_together(self):
        original, new = event(), event()
        unit_id = ObjectId()
        log.store_batch(callback_log.parse_events({'events': [original]}, unit_id))
        log.store_batch(callback_log.parse_events({'events': [original, new]}, unit_id))
        self.assertEqual(self.collection.count_documents({}), 2)

    def test_concurrent_identical_uploads_remain_idempotent(self):
        items = callback_log.parse_events({'events': [event(), event()]}, ObjectId())
        barrier = threading.Barrier(4)

        def upload():
            barrier.wait(timeout=10)
            log.store_batch(items)

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(upload) for _ in range(4)]
            for future in futures:
                future.result(timeout=30)
        self.assertEqual(self.collection.count_documents({}), 2)

    def test_authenticated_endpoint_commits_then_rolls_back_conflict(self):
        private_key = ed25519.Ed25519PrivateKey.generate()
        unit = UnitDocument(
            id=ObjectId(), name='Door', host='localhost',
            keyset=[KeyItem(id='signing', pub=private_key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))])
        original, new = event(), event()
        for items, status in (
            ([original], 200),
            ([original], 200),
            ([new, {**original, 'event': 'card_format'}], 409),
        ):
            req = request(json.dumps({'events': items}).encode())
            req.requestHeaders['Authorization'] = 'Bearer ' + jwt.encode(
                {}, private_key, algorithm='EdDSA', headers={
                    'unit_id': str(unit.id), 'kid': 'signing',
                    'dt': datetime.datetime.now(datetime.UTC).isoformat(),
                })
            with patch.object(unit_auth, 'UnitDocument') as units:
                units.objects.return_value.first.return_value = unit
                frontend.Handler(req)()
            self.assertEqual(req.status_code, status)
        self.assertEqual(self.collection.count_documents({}), 1)
        self.assertIsNone(self.collection.find_one({'_id': ObjectId(new['oid'])}))


if __name__ == '__main__':
    unittest.main()
