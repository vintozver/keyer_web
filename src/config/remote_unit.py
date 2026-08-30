# -*- coding: utf-8 -*-

from . import settings as _settings


_remote_unit = _settings.get('remote_unit', {})
host = _remote_unit.get('host', '::1')
port = _remote_unit.get('port', 80)
