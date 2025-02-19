# -*- coding: utf-8 -*-

import configparser as _configparser
import importlib as _importlib
import sys as _sys


_parser = _configparser.RawConfigParser()
_parser.read('config.txt')


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

    partitions = ['main', 'db_mongo', 'mail', 'remote_unit']
    for partition in partitions:
        inject(partition)

_import_sub()


__all__ = ['_parser']
