# -*- coding: utf-8 -*-

import configparser

from . import _parser


try:
    try:
        smtp_host = _parser.get('mail', 'smtp_host')
    except configparser.NoOptionError:
        smtp_host = 'localhost'
    try:
        smtp_port = _parser.getint('mail', 'smtp_port')
    except configparser.NoOptionError:
        smtp_port = 25
    try:
        smtp_user = _parser.get('mail', 'smtp_user')
    except configparser.NoOptionError:
        smtp_user = None
    try:
        from_name = _parser.get('mail', 'from_name')
    except configparser.NoOptionError:
        from_name = 'Key Card Access System'
    try:
        from_email = _parser.get('mail', 'from_email')
    except configparser.NoOptionError:
        from_email = 'noreply@localhost'
except configparser.NoSectionError:
    smtp_host = 'localhost'
    smtp_port = 25
    smtp_user = None
    smtp_password = None
    from_name = 'Key Card Access System'
    from_email = 'noreply@localhost'
