# -*- coding: utf-8 -*-

import importlib as _importlib
import urllib.parse as _urllib_parse

import yaml as _yaml


try:
    with open('config.yaml', encoding='utf-8') as _config_file:
        settings = _yaml.safe_load(_config_file) or {}
except FileNotFoundError:
    settings = {}

mongodb_uri = settings.get('mongodb_uri', 'mongodb://localhost/keyer')
name = _urllib_parse.urlparse(mongodb_uri).path.lstrip('/') or 'keyer'


def _import_sub():
    def inject(_partition):
        try:
            module = _importlib.import_module("." + _partition, __package__)
        except ImportError as err:
            return
        if _partition in globals():
            globals()[_partition].__dict__.update(module.__dict__)
        else:
            globals()[_partition] = module

    partitions = ['main', 'mail', 'remote_unit']
    for partition in partitions:
        inject(partition)

_import_sub()


__all__ = ['settings', 'mongodb_uri', 'name']
