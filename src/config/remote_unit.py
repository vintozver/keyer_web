# -*- coding: utf-8 -*-

import configparser

from . import _parser


try:
    try:
        host = _parser.get('remote_unit', 'host')
    except configparser.NoOptionError:
        host = '::1'
    try:
        port = _parser.getint('remote_unit', 'port')
    except configparser.NoOptionError:
        port = 80
except configparser.NoSectionError:
    host = '::1'
    port = 80
