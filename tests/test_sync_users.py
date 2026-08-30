import sys
from types import ModuleType
import unittest
from unittest.mock import patch

mongo_user = ModuleType('keyer_web.module.mongo.user')
mongo_user.UserDocument = type('UserDocument', (), {'objects': None})
mongo = ModuleType('keyer_web.module.mongo')
mongo.user = mongo_user
module = ModuleType('keyer_web.module')
module.mongo = mongo
sys.modules.setdefault('keyer_web.module', module)
sys.modules.setdefault('keyer_web.module.mongo', mongo)
sys.modules.setdefault('keyer_web.module.mongo.user', mongo_user)

from keyer_web import sync_users


class UserDocument:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.save_calls = 0

    def save(self):
        self.save_calls += 1


class Query:
    def __init__(self, user=None):
        self.user = user

    def first(self):
        return self.user


class UserDocumentManager:
    def __init__(self, user=None):
        self.user = user

    def __call__(self, **kwargs):
        if 'email' in kwargs:
            return Query(self.user if kwargs['email'] == self.user.email else None)
        if kwargs == {'active__ne': False}:
            return []
        raise AssertionError('unexpected query')


class SyncUsersTests(unittest.TestCase):
    def test_main_parses_default_flags(self):
        with (
            patch.object(sync_users, 'read_input', return_value={}),
            patch.object(sync_users, 'sync_users') as sync,
        ):
            self.assertEqual(sync_users.main(['--default-flags', 'staff']), 0)

        sync.assert_called_once_with({}, 'staff')

    def test_main_defaults_flags_to_unset(self):
        with (
            patch.object(sync_users, 'read_input', return_value={}),
            patch.object(sync_users, 'sync_users') as sync,
        ):
            self.assertEqual(sync_users.main([]), 0)

        sync.assert_called_once_with({}, None)

    def test_default_flags_are_assigned_only_to_created_users(self):
        existing = UserDocument(
            name='Old Name',
            email='existing@example.com',
            active=True,
            flags='existing',
        )
        manager = UserDocumentManager(existing)
        created = []

        class SyncedUserDocument(UserDocument):
            objects = manager

            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                created.append(self)

        with patch.object(sync_users.mod_mongo_user, 'UserDocument', SyncedUserDocument):
            sync_users.sync_users(
                {
                    'new@example.com': 'New User',
                    'existing@example.com': 'Updated Name',
                },
                default_flags='new',
            )

        self.assertEqual(created[0].flags, 'new')
        self.assertEqual(existing.flags, 'existing')
        self.assertEqual(existing.name, 'Updated Name')


if __name__ == '__main__':
    unittest.main()
