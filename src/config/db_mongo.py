# -*- coding: utf-8 -*-

import configparser

from . import _parser


try:
    try:
        host = _parser.get('db_mongo', 'host')
    except configparser.NoOptionError:
        host = 'localhost'
    try:
        port = _parser.getint('db_mongo', 'port')
    except configparser.NoOptionError:
        port = 27017
    try:
        user = _parser.get('db_mongo', 'user')
    except configparser.NoOptionError:
        user = None
    try:
        password = _parser.get('db_mongo', 'password')
    except configparser.NoOptionError:
        password = None
    try:
        name = _parser.get('db_mongo', 'name')
    except configparser.NoOptionError:
        name = 'keyer'
except configparser.NoSectionError:
    host = 'localhost'
    port = 27017
    user = None
    password = None
    name = 'keyer'
