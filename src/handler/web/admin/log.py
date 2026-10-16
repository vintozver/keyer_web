# -*- coding: utf-8 -*-

import http.client

from bson import ObjectId
from bson.errors import InvalidId

from .. import skeleton
from ...ext.decorator.session import Session
from ....module.mongo.log import LogEvent
from ....module.mongo.user import UserDocument


class Handler:
    def __init__(self, req):
        self.req = req

    def error(self, status, message):
        self.req.setResponseCode(status, http.client.responses[status])
        self.req.setHeader('Content-Type', 'text/plain; charset=utf-8')
        self.req.write(message)

    @Session()
    def __call__(self):
        self.req.setHeader('Cache-Control', 'no-store')
        session = self.req.context.session
        user_id = session.get('user_id')
        try:
            user = UserDocument.objects(
                id=ObjectId(user_id), active=True, admin=True).first() if user_id else None
        except (InvalidId, TypeError):
            user = None
        if user is None:
            return self.error(http.client.FORBIDDEN, 'Active administrator access required')
        if self.req.method != 'GET':
            self.req.setHeader('Allow', 'GET')
            return self.error(http.client.METHOD_NOT_ALLOWED, 'Method unsupported')
        content = skeleton.TemplateFactory(self.req, 'admin.log').render({
            'events': list(LogEvent.objects.order_by('-oid').limit(300)),
        })
        self.req.setHeader('Content-Type', 'text/html; charset=utf-8')
        self.req.write(content)
