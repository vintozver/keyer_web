# -*- coding: utf-8 -*-

import os.path
import jinja2

import pkg_resources
from . import Environment as _Environment


class TemplateLoader(jinja2.BaseLoader):
    def get_source(self, environment, template):
        template_path = pkg_resources.resource_filename(__name__, os.path.join('../../template', '%s.tmpl' % template.replace('.', '/')))

        mtime = os.path.getmtime(template_path)

        def uptodate():
            try:
                return os.path.getmtime(template_path) == mtime
            except OSError:
                return False

        try:
            return open(template_path, 'rb').read().decode('utf-8'), 'Template: %s' % template, uptodate
        except OSError:
            raise TemplateError(template)


def TemplateFactory(xtmpl_name, globals=None):
    try:
        return _Environment(TemplateLoader()).get_template(xtmpl_name, globals=globals)
    except jinja2.TemplateNotFound as err:
        raise TemplateError('Template not imported', xtmpl_name)
    except jinja2.TemplateError as err:
        raise TemplateError('Template error', xtmpl_name, err)


class TemplateError(Exception):
    pass


__all__ = ['TemplateFactory', 'TemplateError']
