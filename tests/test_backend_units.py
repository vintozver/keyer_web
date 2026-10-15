import datetime
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from bson import ObjectId
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.x509.oid import NameOID
import jwt
import mongoengine
from jinja2 import DictLoader
import keyer_web

from keyer_web.handler.web import backend, callback_config, frontend, remote_unit
from keyer_web.handler.web import card_depersonalize, card_personalize, card_revoke, remote_unlock
from keyer_web.handler.ext.paramed_cgi import Params
from keyer_web.module.mongo import user
from keyer_web.module.mongo.unit import KeyItem, UnitDocument
from keyer_web.module.template import Environment
from keyer_web.util.web import Application
from keyer_web.util.web.backend import Application as BackendApplication
from keyer_web.util.web.frontend import Application as FrontendApplication
from keyer_web.util.web.request import Request
from keyer_web.util.web import unit_auth


def request(path='/config', token=None, method='GET', body=b''):
    env = {
        'PATH_INFO': path, 'REQUEST_METHOD': method,
        'wsgi.input': io.BytesIO(body),
        'CONTENT_TYPE': 'application/x-www-form-urlencoded',
    }
    if token is not None:
        env['HTTP_AUTHORIZATION'] = 'Bearer ' + token
    return Request(env)


class UnitAuthenticationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_key = cls.private_key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'test unit')])
        now = datetime.datetime.now(datetime.UTC)
        cls.certificate = (
            x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(cls.private_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .sign(cls.private_key, hashes.SHA256())
            .public_bytes(serialization.Encoding.DER)
        )

    def setUp(self):
        self.unit = UnitDocument(
            id=ObjectId(), name='Door', host='::1', port=8080,
            keyset=[KeyItem(id='key-1', pub=self.public_key)])
        self.objects = Mock()
        self.objects.return_value.first.return_value = self.unit
        self.lookup = patch.object(
            unit_auth, 'UnitDocument', SimpleNamespace(objects=self.objects))
        self.lookup.start()
        self.addCleanup(self.lookup.stop)

    def token(self, headers=None, payload=None, key=None, algorithm='RS256'):
        values = {
            'unit_id': str(self.unit.id), 'kid': 'key-1',
            'dt': datetime.datetime.now(datetime.UTC).isoformat(),
        }
        values.update(headers or {})
        values = {name: value for name, value in values.items() if value is not None}
        return jwt.encode(
            payload or {}, key or self.private_key, algorithm=algorithm, headers=values)

    def test_signed_public_key_token(self):
        unit, payload = unit_auth.authenticate(request(token=self.token(payload={'value': 1})))
        self.assertIs(unit, self.unit)
        self.assertEqual(payload, {'value': 1})
        self.objects.assert_called_once_with(id=self.unit.id)

    def test_signed_certificate_token(self):
        self.unit.keyset = [KeyItem(id='key-1', crt=self.certificate)]
        self.assertIs(unit_auth.authenticate(request(token=self.token()))[0], self.unit)

    def test_key_rotation(self):
        self.unit.keyset.insert(0, KeyItem(id='old-key', pub=b'invalid'))
        self.assertIs(unit_auth.authenticate(request(token=self.token()))[0], self.unit)

    def test_eddsa_token(self):
        private_key = ed25519.Ed25519PrivateKey.generate()
        self.unit.keyset[0].pub = private_key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        self.assertIs(unit_auth.authenticate(
            request(token=self.token(key=private_key, algorithm='EdDSA')))[0], self.unit)

    def test_invalid_headers(self):
        cases = [
            {'unit_id': None}, {'unit_id': ''}, {'unit_id': 'not-an-oid'},
            {'unit_id': 42}, {'kid': None}, {'kid': ''}, {'kid': 'unknown'},
            {'dt': None}, {'dt': 123}, {'dt': 'NaN'}, {'dt': '999999999999999999999'},
            {'dt': '2026-10-15T17:16:08'},
            {'dt': (datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=301)).isoformat()},
            {'dt': (datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=301)).isoformat()},
        ]
        for headers in cases:
            with self.subTest(headers=headers), self.assertRaises(unit_auth.AuthenticationError):
                unit_auth.authenticate(request(token=self.token(headers)))

    def test_missing_malformed_or_unsigned_token(self):
        tokens = [
            None, 'not-a-jwt',
            jwt.encode({}, key=None, algorithm='none', headers={
                'unit_id': str(self.unit.id), 'kid': 'key-1',
                'dt': datetime.datetime.now(datetime.UTC).isoformat()}),
            self.token(key='test-hmac-key-that-is-at-least-32-bytes', algorithm='HS256'),
        ]
        for token in tokens:
            with self.subTest(token=token), self.assertRaises(unit_auth.AuthenticationError):
                unit_auth.authenticate(request(token=token))

    def test_wrong_signature(self):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with self.assertRaises(unit_auth.AuthenticationError):
            unit_auth.authenticate(request(token=self.token(key=other)))

    def test_algorithm_incompatible_with_registered_key_returns_401(self):
        token = self.token(key=ed25519.Ed25519PrivateKey.generate(), algorithm='EdDSA')
        req = request(token=token)
        frontend.Handler(req)()
        self.assertEqual(req.status_code, 401)

    def test_unknown_unit(self):
        self.objects.return_value.first.return_value = None
        with self.assertRaises(unit_auth.AuthenticationError):
            unit_auth.authenticate(request(token=self.token()))

    def test_expired_and_future_claims(self):
        now = datetime.datetime.now(datetime.UTC).timestamp()
        for payload in ({'exp': now - 10}, {'nbf': now + 600}):
            with self.subTest(payload=payload), self.assertRaises(unit_auth.AuthenticationError):
                unit_auth.authenticate(request(token=self.token(payload=payload)))

    def test_invalid_stored_key(self):
        for key in (
            KeyItem(id='key-1'), KeyItem(id='key-1', pub=b'bad'),
            KeyItem(id='key-1', crt=b'bad'),
            KeyItem(id='key-1', pub=self.public_key, crt=self.certificate),
        ):
            self.unit.keyset = [key]
            with self.subTest(key=key), self.assertRaises(unit_auth.AuthenticationError):
                unit_auth.authenticate(request(token=self.token()))

    def test_config_dispatch_with_jwt_and_no_session(self):
        req = request(token=self.token())
        with (
            patch.object(callback_config.mod_mongo_user, 'UserDocument') as users,
            patch.object(callback_config.mod_mongo_card, 'IssuedCard') as issued,
            patch.object(callback_config.mod_mongo_card, 'RevokedCard') as revoked,
        ):
            users.objects.return_value = []
            issued.objects.return_value = []
            revoked.objects.return_value = []
            frontend.Handler(req)()
        self.assertEqual(req.status_code, 200)
        self.assertEqual(json.loads(b''.join(req.response_body)), {
            'users': {}, 'issued_cards': {}, 'revoked_cards': {}})
        self.assertEqual(req.responseHeaders['Cache-Control'], 'no-store')
        self.assertIs(req.unit, self.unit)
        self.assertEqual(req.context.items, {})
        self.assertEqual(len(req.cookie), 0)

    def test_callbacks_require_jwt_on_shared_and_legacy_routers(self):
        for handler in (frontend.Handler, backend.Handler):
            for path in ('/config', '/config/', '/log', '/log/'):
                req = request(path)
                with self.subTest(handler=handler, path=path):
                    handler(req)()
                    self.assertEqual(req.status_code, 401)
                    self.assertEqual(req.responseHeaders['WWW-Authenticate'], 'Bearer')
                    self.assertEqual(req.responseHeaders['Cache-Control'], 'no-store')

    def test_wsgi_entry_points_are_identical(self):
        self.assertIs(Application, FrontendApplication)
        self.assertIs(Application, BackendApplication)
        for app in (Application, FrontendApplication, BackendApplication):
            responder = Mock()
            response = app({'PATH_INFO': '/config', 'wsgi.input': io.BytesIO()}, responder)
            self.assertEqual(responder.call_args.args[0], '401 Unauthorized')
            self.assertIn('error', json.loads(b''.join(response)))


class UnitModelAndSelectionTests(unittest.TestCase):
    def setUp(self):
        self.unit = UnitDocument(id=ObjectId(), name='Front door', host='::1', port=8080)

    def test_model_defaults_and_objectid(self):
        self.unit.validate()
        self.assertEqual(UnitDocument(name='Door', host='localhost').port, 80)
        self.assertEqual(self.unit.to_mongo()['_id'], self.unit.id)

    def test_invalid_keysets(self):
        for keys in (
            [KeyItem(id='empty')],
            [KeyItem(id='both', pub=b'pub', crt=b'crt')],
            [KeyItem(id='duplicate', pub=b'one'), KeyItem(id='duplicate', crt=b'two')],
        ):
            self.unit.keyset = keys
            with self.subTest(keys=keys), self.assertRaises(mongoengine.ValidationError):
                self.unit.validate()

    def test_template_lists_units_and_passes_selection_to_commands(self):
        source = (Path(keyer_web.__file__).parent / 'template' / 'index.tmpl').read_text()
        environment = Environment(DictLoader({
            'skeleton': '{% block body_content %}{% endblock %}',
            'index': source,
        }))
        self.unit.name = '<script>not markup</script>'
        content = environment.get_template('index').render(
            user=SimpleNamespace(name='User', admin=False), cards=[], units=[self.unit])
        self.assertIn(str(self.unit.id), content)
        self.assertIn('&lt;script&gt;not markup&lt;/script&gt;', content)
        self.assertEqual(content.count('"unit_id": $("#unit_id").val() || ""'), 4)

    def test_browser_routes_remain_available(self):
        for path in ('/', '/static/jquery.js', '/card_personalize', '/card_depersonalize',
                     '/card_revoke', '/remote_unlock'):
            self.assertIsNotNone(frontend.Handler.handle_map(frontend.Handler.ROUTE_MAP, path))

    def test_unit_connection_uses_database_host_and_port(self):
        handler = remote_unit.Handler(request(
            '/remote_unlock', method='POST',
            body=('unit_id=' + str(self.unit.id)).encode()))
        objects = Mock()
        objects.return_value.first.return_value = self.unit
        with (
            patch.object(remote_unit, 'UnitDocument', SimpleNamespace(objects=objects)),
            patch.object(remote_unit.http.client, 'HTTPConnection') as connection,
        ):
            self.assertIs(handler.connect_unit(), connection.return_value)
            connection.assert_called_once_with('::1', 8080)
            objects.assert_called_once_with(id=self.unit.id)

    def test_json_unit_selection_and_card_identifier(self):
        req = request('/card_revoke', method='POST', body=json.dumps({
            'unit_id': str(self.unit.id), 'identifier': 'card-id',
        }).encode())
        req.requestHeaders['Content-Type'] = 'application/json; charset=utf-8'
        handler = remote_unit.Handler(req)
        objects = Mock()
        objects.return_value.first.return_value = self.unit
        with (
            patch.object(remote_unit, 'UnitDocument', SimpleNamespace(objects=objects)),
            patch.object(remote_unit.http.client, 'HTTPConnection') as connection,
        ):
            self.assertIs(handler.connect_unit(), connection.return_value)
            self.assertEqual(handler.cgi_params.param_post('identifier'), 'card-id')
            self.assertEqual(handler.cgi_params.paramlist_post('identifier'), ['card-id'])
            with self.assertRaises(Params.NotFoundError):
                handler.cgi_params.param_post('missing')
            connection.assert_called_once_with('::1', 8080)

    def test_single_unit_fallback_and_ambiguous_selection(self):
        for units in ([self.unit], [], [self.unit, self.unit]):
            handler = remote_unit.Handler(request('/remote_unlock', method='POST'))
            objects = Mock()
            objects.limit.return_value = units
            with (
                patch.object(remote_unit, 'UnitDocument', SimpleNamespace(objects=objects)),
                patch.object(remote_unit.http.client, 'HTTPConnection') as connection,
                self.subTest(units=units),
            ):
                result = handler.connect_unit()
                if len(units) == 1:
                    self.assertIs(result, connection.return_value)
                else:
                    self.assertIsNone(result)
                    self.assertEqual(handler.req.status_code, 400)
                    connection.assert_not_called()

    def test_invalid_or_unknown_unit_does_not_connect(self):
        for unit_id in ('invalid', '', str(ObjectId())):
            handler = remote_unit.Handler(request(
                '/remote_unlock', method='POST', body=('unit_id=' + unit_id).encode()))
            objects = Mock()
            objects.return_value.first.return_value = None
            with (
                patch.object(remote_unit, 'UnitDocument', SimpleNamespace(objects=objects)),
                patch.object(remote_unit.http.client, 'HTTPConnection') as connection,
                self.subTest(unit_id=unit_id),
            ):
                self.assertIsNone(handler.connect_unit())
                self.assertEqual(handler.req.status_code, 404)
                connection.assert_not_called()

    def test_all_commands_stop_when_unit_selection_fails(self):
        for module in (card_depersonalize, card_personalize, card_revoke, remote_unlock):
            req = request('/command', method='POST', body=b'identifier=00000000000000000000000000000001')
            user_id = ObjectId()
            req.context = SimpleNamespace(session={'user_id': str(user_id)})
            handler = module.Handler(req)
            active_user = SimpleNamespace(id=user_id, email='test@example.com', admin=True)
            with (
                patch.object(user, 'UserDocument') as users,
                patch.object(module.Handler, 'connect_unit', return_value=None) as connect,
                patch.object(card_revoke.mod_mongo_card, 'IssuedCard') as cards,
                self.subTest(module=module),
            ):
                users.objects.return_value.get.return_value = active_user
                cards.objects.return_value.get.return_value = SimpleNamespace(
                    user_id=user_id, email=active_user.email)
                module.Handler.__dict__['__call__'].method(handler)
                connect.assert_called_once_with()

    def test_forbidden_commands_never_connect_to_unit(self):
        for module in (card_depersonalize, card_revoke):
            req = request('/command', method='POST', body=b'identifier=00000000000000000000000000000001')
            user_id = ObjectId()
            req.context = SimpleNamespace(session={'user_id': str(user_id)})
            handler = module.Handler(req)
            with (
                patch.object(user, 'UserDocument') as users,
                patch.object(module.Handler, 'connect_unit') as connect,
                patch.object(card_revoke.mod_mongo_card, 'IssuedCard') as cards,
                self.subTest(module=module),
            ):
                users.objects.return_value.get.return_value = SimpleNamespace(
                    id=user_id, email='test@example.com', admin=False)
                cards.objects.return_value.get.return_value = SimpleNamespace(
                    user_id=ObjectId(), email='other@example.com')
                module.Handler.__dict__['__call__'].method(handler)
                self.assertEqual(req.status_code, 403)
                connect.assert_not_called()


if __name__ == '__main__':
    unittest.main()
