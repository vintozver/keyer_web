# -*- coding: utf-8 -*-

from . import settings as _settings


_mail = _settings.get('mail', {})
smtp_host = _mail.get('smtp_host', 'localhost')
smtp_port = _mail.get('smtp_port', 25)
smtp_user = _mail.get('smtp_user')
smtp_password = _mail.get('smtp_password')
from_name = _mail.get('from_name', 'Key Card Access System')
from_email = _mail.get('from_email', 'noreply@localhost')
