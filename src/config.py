# -*- coding: utf-8 -*-

import pytz
import yaml


try:
    with open('config.yaml', encoding='utf-8') as config_file:
        settings = yaml.safe_load(config_file) or {}
except FileNotFoundError:
    settings = {}

mongodb_uri = settings.get('mongodb_uri', 'mongodb://localhost/keyer')

_mail = settings.get('mail', {})
smtp_host = _mail.get('smtp_host', 'localhost')
smtp_port = _mail.get('smtp_port', 25)
from_name = _mail.get('from_name', 'Key Card Access System')
from_email = _mail.get('from_email', 'noreply@localhost')

_remote_unit = settings.get('remote_unit', {})
remote_unit_host = _remote_unit.get('host', '::1')
remote_unit_port = _remote_unit.get('port', 80)

product_name = "Keyer UI"
product_description = "Aspen Grove OA, Keyer. Kent, WA, USA. All rights reserved."
timezone = pytz.timezone("America/Los_Angeles")
