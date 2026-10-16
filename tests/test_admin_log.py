import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from bson import ObjectId

from keyer_web.handler.ext.decorator import session as session_decorator
from keyer_web.handler.web import frontend
from keyer_web.handler.web.admin import log as admin_log
from keyer_web.util.web.request import Request


class AdminSession(dict):
    def save(self):
        pass


class AdminLogTests(unittest.TestCase):
    def setUp(self):
        self.session = AdminSession(user_id=str(ObjectId()))
        self.users = Mock()
        self.users.objects.return_value.first.return_value = SimpleNamespace(admin=True)
        self.events_query = Mock()
        self.events_query.order_by.return_value.limit.return_value = []
        self.patches = [
            patch.object(admin_log, 'UserDocument', SimpleNamespace(objects=self.users.objects)),
            patch.object(admin_log, 'LogEvent', SimpleNamespace(objects=self.events_query)),
            patch.object(
                session_decorator.mod_session, 'MongoDbSession',
                Mock(return_value=self.session)),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def call(self, path='/admin/log', method='GET'):
        req = Request({
            'PATH_INFO': path, 'REQUEST_METHOD': method,
            'wsgi.input': io.BytesIO(b''),
        })
        frontend.Handler(req)()
        return req

    def test_admin_page_lists_at_most_300_recent_events(self):
        req = self.call()
        self.assertEqual(req.status_code, 200)
        self.assertEqual(req.responseHeaders['Cache-Control'], 'no-store')
        self.events_query.order_by.assert_called_once_with('-oid')
        self.events_query.order_by.return_value.limit.assert_called_once_with(300)
        self.assertIn(b'Showing the latest 0 events.', b''.join(req.response_body))

    def test_page_renders_event_values_escaped(self):
        event = SimpleNamespace(
            oid=ObjectId(), event='<script>', card_id=None, name='<img>',
            user_id=None, unit_id=None)
        self.events_query.order_by.return_value.limit.return_value = [event]
        content = b''.join(self.call().response_body)
        self.assertIn(b'&lt;script&gt;', content)
        self.assertIn(b'&lt;img&gt;', content)
        self.assertNotIn(b'<script>', content)
        self.assertNotIn(b'<img>', content)

    def test_non_admin_is_denied_and_other_methods_are_rejected(self):
        self.users.objects.return_value.first.return_value = None
        self.assertEqual(self.call().status_code, 403)
        self.users.objects.return_value.first.return_value = SimpleNamespace(admin=True)
        req = self.call(method='POST')
        self.assertEqual(req.status_code, 405)
        self.assertEqual(req.responseHeaders['Allow'], 'GET')
        self.events_query.order_by.assert_not_called()


if __name__ == '__main__':
    unittest.main()
