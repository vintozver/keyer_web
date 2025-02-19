# -*- coding: utf-8 -*-

import jinja2

from ... import config


class BytecodeCache(jinja2.BytecodeCache):
    def load_bytecode(self, bucket):
        with mod.DbSessionController() as db_session:
            try:
                value = db_session.get('template##cache##%s' % bucket.key)
            except mod.redis.RedisError:
                value = None
            if value is not None:
                bucket.bytecode_from_string(value)

    def dump_bytecode(self, bucket):
        with mod.DbSessionController() as db_session:
            value = bucket.bytecode_to_string()
            try:
                db_session.set('template##cache##%s' % bucket.key, value)
            except mod.redis.RedisError:
                pass

    def clear(self):
        pass


class Template(jinja2.Template):
    def new_context(self, vars=None, shared=False, locals=None):
        def safe_strings(value):
            if isinstance(value, bytes):
                return value.decode('utf-8')
            return value

        if isinstance(vars, dict):
            vars = dict(((safe_strings(k), safe_strings(v)) for k, v in vars.items()))
        if isinstance(shared, dict):
            shared = dict(((safe_strings(k), safe_strings(v)) for k, v in shared.items()))
        if isinstance(locals, dict):
            locals = dict(((safe_strings(k), safe_strings(v)) for k, v in locals.items()))
        return super(Template, self).new_context(vars, shared, locals)


import datetime
import json
from ...util.value import build_url as _url


class Environment(jinja2.Environment):
    def __init__(self, template_loader):
        super(Environment, self).__init__(
            extensions=['jinja2.ext.loopcontrols', 'jinja2.ext.do', 'jinja2.ext.i18n'],
            #bytecode_cache=BytecodeCache(),
            loader=template_loader,
        )

        self.globals['config'] = config
        self.filters['url'] = lambda kwargs: _url(**kwargs)
        self.filters['json'] = lambda arg: json.dumps(arg)

        def filter_datetime(arg, fmt):
            if isinstance(arg, datetime.datetime):
                return arg.strftime(fmt)
            else:
                return 'Not a datetime'
        self.filters['datetime'] = filter_datetime

        self.template_class = Template
