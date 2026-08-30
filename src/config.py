# -*- coding: utf-8 -*-

import yaml
from zoneinfo import ZoneInfo


try:
    with open('config.yaml', encoding='utf-8') as config_file:
        settings = yaml.safe_load(config_file) or {}
except FileNotFoundError:
    settings = {}

mongodb_uri = settings.get('mongodb_uri', 'mongodb://localhost/keyer')

_smtp = settings.get('smtp', {})
smtp_host = _smtp.get('host', 'localhost')
smtp_port = _smtp.get('port', 25)
_smtp_from = _smtp.get('from', {})
smtp_from_name = _smtp_from.get('name', 'Key Card Access System')
smtp_from_email = _smtp_from.get('email', 'noreply@localhost')

_remote_unit = settings.get('remote_unit', {})
remote_unit_host = _remote_unit.get('host', '::1')
remote_unit_port = _remote_unit.get('port', 80)

_product = settings.get('product', {})
product_name = _product.get('name', 'Keyer UI')
product_description = _product.get(
    'description',
    'Aspen Grove OA, Keyer. Kent, WA, USA. All rights reserved.',
)
timezone = ZoneInfo(settings.get('timezone', 'America/Los_Angeles'))
