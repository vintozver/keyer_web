# -*- coding: utf-8 -*-

import datetime

import jwt
from bson import ObjectId
from bson.errors import InvalidId
from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization

from ...module.mongo.unit import UnitDocument


TOKEN_MAX_AGE = 300
JWT_ALGORITHMS = ('RS256', 'RS384', 'RS512', 'PS256', 'PS384', 'PS512',
                  'ES256', 'ES384', 'ES512', 'EdDSA')


class AuthenticationError(Exception):
    pass


def authenticate(req):
    authorization = req.getHeader('Authorization') or ''
    if not authorization.startswith('Bearer '):
        raise AuthenticationError('A signed JWT is required')
    token = authorization[7:].strip()
    try:
        header = jwt.get_unverified_header(token)
        unit_id, key_id, dt = (header.get(name) for name in ('unit_id', 'kid', 'dt'))
        if not all(isinstance(value, str) and value for value in (unit_id, key_id, dt)):
            raise AuthenticationError('JWT unit_id, kid and dt headers are required')
        if header.get('alg') not in JWT_ALGORITHMS:
            raise AuthenticationError('Unsupported signing algorithm')
        token_time = datetime.datetime.fromisoformat(dt.replace('Z', '+00:00'))
        if token_time.tzinfo is None or token_time.utcoffset() is None:
            raise AuthenticationError('JWT dt must include a timezone')
        if abs((datetime.datetime.now(datetime.UTC) - token_time).total_seconds()) > TOKEN_MAX_AGE:
            raise AuthenticationError('JWT dt is outside the allowed time window')
        unit = UnitDocument.objects(id=ObjectId(unit_id)).first()
        if unit is None:
            raise AuthenticationError('Unknown unit')
        key = next((item for item in unit.keyset if item.id == key_id), None)
        if key is None or bool(key.pub) == bool(key.crt):
            raise AuthenticationError('Unknown signing key')
        public_key = (
            serialization.load_der_public_key(bytes(key.pub)) if key.pub
            else x509.load_der_x509_certificate(bytes(key.crt)).public_key()
        )
        payload = jwt.decode(token, public_key, algorithms=JWT_ALGORITHMS)
    except (jwt.InvalidTokenError, InvalidId, ValueError, TypeError, OverflowError,
            UnsupportedAlgorithm) as err:
        raise AuthenticationError('Invalid JWT') from err
    return unit, payload
