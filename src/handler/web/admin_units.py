# -*- coding: utf-8 -*-

import http.client
import secrets

from bson import ObjectId
from bson.errors import InvalidId
from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, ed448, rsa
from mongoengine import ValidationError

from . import skeleton
from ..ext.decorator.session import Session
from ..ext.paramed_cgi import Handler as BaseHandler
from ...module.mongo.unit import UnitDocument, KeyItem
from ...module.mongo.user import UserDocument


class Handler(BaseHandler):
    def error(self, status, message):
        self.req.setResponseCode(status, http.client.responses[status])
        self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
        self.req.write(message)

    def parameter(self, name, allow_empty=False):
        value = self.cgi_params.param_post(name)
        if not isinstance(value, str):
            raise ValueError('Parameters must be strings')
        value = value.strip()
        if not value and not allow_empty:
            raise ValueError('Required parameter is empty')
        return value

    @staticmethod
    def signing_key(key_id, material):
        encoded = material.encode('utf-8')
        if material.startswith('-----BEGIN CERTIFICATE-----'):
            certificate = x509.load_pem_x509_certificate(encoded)
            public_key = certificate.public_key()
            key = KeyItem(id=key_id, crt=certificate.public_bytes(serialization.Encoding.DER))
        else:
            public_key = serialization.load_pem_public_key(encoded)
            key = KeyItem(id=key_id, pub=public_key.public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
        if not isinstance(public_key, (rsa.RSAPublicKey, ec.EllipticCurvePublicKey,
                                       ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
            raise ValueError('Unsupported signing key type')
        return key

    def change(self):
        action = self.parameter('action')
        unit_id = self.parameter('unit_id', allow_empty=True)
        if action not in ('save', 'delete', 'add_key', 'delete_key'):
            raise ValueError('Unknown action')
        if unit_id:
            unit = UnitDocument.objects(id=ObjectId(unit_id)).first()
            if unit is None:
                self.error(http.client.NOT_FOUND, 'Unit not found')
                return
        elif action == 'save':
            unit = UnitDocument()
        else:
            raise ValueError('Unit id required')

        if action == 'delete':
            unit.delete()
        elif action == 'save':
            unit.name = self.parameter('name')
            unit.host = self.parameter('host')
            unit.port = int(self.parameter('port'))
            unit.save()
        elif action == 'add_key':
            key = self.signing_key(self.parameter('key_id'), self.parameter('material'))
            unit.keyset.append(key)
            unit.save()
        else:
            key_id = self.parameter('key_id')
            if not any(key.id == key_id for key in unit.keyset):
                self.error(http.client.NOT_FOUND, 'Signing key not found')
                return
            unit.keyset = [key for key in unit.keyset if key.id != key_id]
            unit.save()
        self.req.setResponseCode(http.client.SEE_OTHER, http.client.responses[http.client.SEE_OTHER])
        self.req.setHeader('Location', '/admin/units')

    @Session()
    def __call__(self):
        self.req.setHeader('Cache-Control', 'no-store')
        session = self.req.context.session
        user_id = session.get('user_id')
        try:
            user = UserDocument.objects(id=ObjectId(user_id), active=True, admin=True).first() if user_id else None
        except (InvalidId, TypeError):
            user = None
        if user is None:
            return self.error(http.client.FORBIDDEN, 'Active administrator access required')
        if self.req.method not in ('GET', 'POST'):
            self.req.setHeader('Allow', 'GET, POST')
            return self.error(http.client.METHOD_NOT_ALLOWED, 'Method unsupported')
        if self.req.method == 'POST':
            token = session.get('admin_csrf')
            try:
                supplied_token = self.cgi_params.param_post('csrf_token')
            except self.cgi_params.NotFoundError:
                supplied_token = None
            if (not isinstance(token, str) or not isinstance(supplied_token, str)
                    or not secrets.compare_digest(token.encode(), supplied_token.encode())):
                return self.error(http.client.FORBIDDEN, 'Invalid CSRF token')
            try:
                return self.change()
            except (self.cgi_params.NotFoundError, InvalidId, ValueError, TypeError,
                    ValidationError, UnsupportedAlgorithm):
                return self.error(
                    http.client.BAD_REQUEST,
                    'Invalid unit or signing key. Check required fields, port (1-65535), '
                    'unique key id, and PEM public key or certificate. Private keys are not accepted.')
        if not session.get('admin_csrf'):
            session['admin_csrf'] = secrets.token_urlsafe(32)
            session.save()
        content = skeleton.TemplateFactory(self.req, 'admin_units').render({
            'units': list(UnitDocument.objects.order_by('name', 'id')),
            'csrf_token': session['admin_csrf'],
        })
        self.req.setHeader('Content-Type', 'text/html; charset=utf-8')
        self.req.write(content)
