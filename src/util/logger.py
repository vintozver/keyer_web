# -*- coding: utf-8 -*-

import logging
import os.path

from functools import reduce


class NullStream(logging.Handler):
    def read(self, *args, **kwargs):
        pass

    def write(self, *args, **kwargs):
        pass

    def flush(self):
        pass


logging.basicConfig(
        stream=NullStream(),
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
)


def logger_setup():
    import logging
    logger = logging.getLogger('traceback')
    handler = logging.FileHandler(os.path.join('log', 'traceback_web.txt'))
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S'))
    logger.addHandler(handler)
logger_setup()


class Logger(object):
    def __init__(self, req):
        self.req = req

    def traceback(self, err_type, err_value, err_tb):
        import traceback
        tb = reduce(
                lambda line_up, line_down: line_up + '\n' + line_down,
                ['%s: %s' % (item[0], item[1]) for item in traceback.extract_tb(err_tb)]
        )

        logger = logging.getLogger('traceback')
        logger.error('''%(method)s %(host)s %(uri)s
Тип: %(type)s
Значение: %(value)s
Трасса:
%(tb)s

''' % {'type': err_type, 'value': err_value, 'tb': tb, 'method': self.req.method, 'host': self.req.requestHeaders.get('Host'), 'uri': self.req.uri}
                    )
