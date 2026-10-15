import datetime
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from bson import ObjectId
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dsa, rsa
from cryptography.x509.oid import NameOID
from jinja2 import DictLoader
import keyer_web

from keyer_web.handler.ext.decorator import session as session_decorator
from keyer_web.handler.web import admin_units, frontend
from keyer_web.module.mongo.unit import KeyItem, UnitDocument
from keyer_web.module.template import Environment
from keyer_web.util.web.request import Request


class AdminSession(dict):
    def save(self):
        self.saved = True


class AdminUnitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_pem = cls.private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()

    def setUp(self):
        self.user_id = ObjectId()
        self.session = AdminSession(user_id=str(self.user_id), admin_csrf='test-csrf')
        self.unit = UnitDocument(id=ObjectId(), name='Door', host='localhost', port=8080)
        self.users = Mock()
        self.users.objects.return_value.first.return_value = SimpleNamespace(admin=True)
        self.units = Mock(wraps=UnitDocument, objects=Mock())
        self.units.objects.return_value.first.return_value = self.unit
        self.units.objects.order_by.return_value = [self.unit]
        for target, name, value in (
            (admin_units, 'UserDocument', self.users),
            (admin_units, 'UnitDocument', self.units),
            (session_decorator.mod_session, 'MongoDbSession', Mock(return_value=self.session)),
        ):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, method='GET', **params):
        body = urlencode(params).encode()
        req = Request({
            'PATH_INFO': '/admin/units', 'REQUEST_METHOD': method,
            'CONTENT_TYPE': 'application/x-www-form-urlencoded',
            'CONTENT_LENGTH': str(len(body)), 'wsgi.input': io.BytesIO(body),
        })
        frontend.Handler(req)()
        return req

    def post(self, action='save', **params):
        return self.call('POST', action=action, csrf_token='test-csrf',
                         unit_id=str(self.unit.id), **params)

    def test_admin_get_lists_units_and_preserves_csrf_token(self):
        req = self.call()
        self.assertEqual(req.status_code, 200)
        self.assertEqual(req.responseHeaders['Cache-Control'], 'no-store')
        self.assertIn(str(self.unit.id).encode(), b''.join(req.response_body))
        self.assertIn(b'test-csrf', b''.join(req.response_body))
        self.users.objects.assert_called_once_with(id=self.user_id, active=True, admin=True)

    def test_first_get_creates_and_saves_csrf_token(self):
        del self.session['admin_csrf']
        self.assertEqual(self.call().status_code, 200)
        self.assertGreaterEqual(len(self.session['admin_csrf']), 32)
        self.assertTrue(self.session.saved)

    def test_anonymous_invalid_deleted_inactive_or_nonadmin_user_is_denied(self):
        for user_id in (None, 'invalid', str(self.user_id)):
            self.session['user_id'] = user_id
            self.users.objects.return_value.first.return_value = None
            for method in ('GET', 'POST'):
                with self.subTest(user_id=user_id, method=method):
                    self.assertEqual(self.call(method).status_code, 403)
        self.units.objects.assert_not_called()
        self.units.objects.order_by.assert_not_called()

    def test_post_requires_session_bound_csrf_token(self):
        for supplied in (None, 'wrong', 'é'):
            params = {} if supplied is None else {'csrf_token': supplied}
            with self.subTest(supplied=supplied):
                self.assertEqual(self.call('POST', action='delete', **params).status_code, 403)
        del self.session['admin_csrf']
        self.assertEqual(self.call('POST', csrf_token='test-csrf').status_code, 403)
        self.units.objects.assert_not_called()

    def test_unsupported_methods_do_not_modify_units(self):
        for method in ('PUT', 'DELETE', 'PATCH'):
            with self.subTest(method=method):
                req = self.call(method)
                self.assertEqual(req.status_code, 405)
                self.assertEqual(req.responseHeaders['Allow'], 'GET, POST')
        self.units.objects.assert_not_called()

    def test_create_unit(self):
        with patch.object(UnitDocument, 'save', autospec=True) as save:
            req = self.call('POST', csrf_token='test-csrf', action='save', unit_id='',
                            name='New door', host='::1', port='80')
            self.assertEqual(req.status_code, 303)
            self.assertEqual(req.responseHeaders['Location'], '/admin/units')
            unit = save.call_args.args[0]
            unit.validate()
            self.assertEqual((unit.name, unit.host, unit.port), ('New door', '::1', 80))

    def test_edit_unit_preserves_keys(self):
        self.unit.keyset = [KeyItem(id='existing', pub=b'public')]
        with patch.object(UnitDocument, 'save', autospec=True) as save:
            req = self.post(name='Updated', host='new-host', port='1234')
            self.assertEqual(req.status_code, 303)
            save.assert_called_once_with(self.unit)
        self.assertEqual((self.unit.name, self.unit.host, self.unit.port),
                         ('Updated', 'new-host', 1234))
        self.assertEqual(self.unit.keyset[0].id, 'existing')

    def test_delete_unit(self):
        with patch.object(UnitDocument, 'delete', autospec=True) as delete:
            self.assertEqual(self.post('delete').status_code, 303)
            delete.assert_called_once_with(self.unit)

    def test_add_public_key_stores_der(self):
        with patch.object(UnitDocument, 'save', autospec=True) as save:
            self.assertEqual(self.post('add_key', key_id='new', material=self.public_pem).status_code, 303)
            save.assert_called_once_with(self.unit)
        self.unit.validate()
        key = self.unit.keyset[0]
        self.assertEqual(key.id, 'new')
        self.assertFalse(key.crt)
        self.assertEqual(serialization.load_der_public_key(key.pub).public_numbers(),
                         self.private_key.public_key().public_numbers())

    def test_add_certificate_stores_der(self):
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Unit')])
        now = datetime.datetime.now(datetime.UTC)
        certificate = (
            x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(self.private_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
            .sign(self.private_key, hashes.SHA256()))
        pem = certificate.public_bytes(serialization.Encoding.PEM).decode()
        with patch.object(UnitDocument, 'save', autospec=True):
            self.assertEqual(self.post('add_key', key_id='cert', material=pem).status_code, 303)
        self.assertEqual(self.unit.keyset[0].crt, certificate.public_bytes(serialization.Encoding.DER))
        self.assertFalse(self.unit.keyset[0].pub)

    def test_remove_key_preserves_other_keys(self):
        self.unit.keyset = [KeyItem(id='old', pub=b'one'), KeyItem(id='new', pub=b'two')]
        with patch.object(UnitDocument, 'save', autospec=True):
            self.assertEqual(self.post('delete_key', key_id='old').status_code, 303)
        self.assertEqual([key.id for key in self.unit.keyset], ['new'])

    def test_invalid_private_or_unsupported_key_is_rejected(self):
        private_pem = self.private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()
        unsupported = dsa.generate_private_key(key_size=1024).public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        for material in ('not a key', private_pem, unsupported):
            with patch.object(UnitDocument, 'save', autospec=True) as save, self.subTest(material=material[:20]):
                self.assertEqual(self.post('add_key', key_id='bad', material=material).status_code, 400)
                save.assert_not_called()
        self.assertEqual(self.unit.keyset, [])

    def test_invalid_fields_or_duplicate_key_are_rejected_by_validation(self):
        for name, host, port in (('', 'host', '80'), ('x', '', '80'),
                                 ('x', 'host', '0'), ('x', 'host', '65536'),
                                 ('x', 'host', 'invalid')):
            with (
                patch.object(UnitDocument, 'save', autospec=True, side_effect=lambda unit: unit.validate()),
                self.subTest(name=name, host=host, port=port),
            ):
                self.assertEqual(self.post(name=name, host=host, port=port).status_code, 400)
        self.unit.name, self.unit.host, self.unit.port = 'Door', 'localhost', 80
        self.unit.keyset = [KeyItem(id='duplicate', pub=b'existing')]
        with patch.object(UnitDocument, 'save', autospec=True, side_effect=lambda unit: unit.validate()):
            self.assertEqual(self.post('add_key', key_id='duplicate', material=self.public_pem).status_code, 400)

    def test_unknown_unit_action_or_key_is_rejected(self):
        self.assertEqual(self.post('unknown').status_code, 400)
        self.assertEqual(self.post('delete_key', key_id='missing').status_code, 404)
        self.units.objects.return_value.first.return_value = None
        self.assertEqual(self.post('delete').status_code, 404)
        self.assertEqual(self.call('POST', csrf_token='test-csrf',
                                   action='delete', unit_id='bad').status_code, 400)

    def test_admin_template_escapes_unit_and_key_fields(self):
        self.unit.name = '<script>alert(1)</script>'
        self.unit.host = '"><script>'
        self.unit.keyset = [KeyItem(id='"><script>', pub=b'public')]
        content = b''.join(self.call().response_body).decode()
        self.assertNotIn(self.unit.name, content)
        self.assertIn('&lt;script&gt;', content)
        self.assertNotIn('value=""><script>', content)

    def test_navigation_link_is_admin_only(self):
        source = (Path(keyer_web.__file__).parent / 'template' / 'index.tmpl').read_text()
        environment = Environment(DictLoader({
            'skeleton': '{% block body_content %}{% endblock %}', 'index': source}))
        for admin in (False, True):
            content = environment.get_template('index').render(
                user=SimpleNamespace(name='User', admin=admin), cards=[], units=[])
            self.assertEqual('href="/admin/units"' in content, admin)


if __name__ == '__main__':
    unittest.main()
