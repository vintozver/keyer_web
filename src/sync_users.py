# -*- coding: utf-8 -*-

"""Synchronize the users in the database with the list supplied on the standard input.

The input is tab separated with 3 fields: unit number, name, email.
The unit number is disregarded.
"""

import sys

from .module.mongo import user as mod_mongo_user


def read_input(stream) -> dict[str, str]:
    """Parse the input stream, return the mapping of the email to the name."""

    users = dict()
    for line_number, line in enumerate(stream, start=1):
        line = line.rstrip('\r\n')
        if not line.strip():
            continue
        fields = line.split('\t')
        if len(fields) != 3:
            raise ValueError('line %d: expected 3 tab separated fields, got %d' % (line_number, len(fields)))
        name = fields[1].strip()
        email = fields[2].strip()
        if not email:
            raise ValueError('line %d: email is empty' % line_number)
        users[email.lower()] = name
    return users


def sync_users(users: dict[str, str]) -> None:
    """Create/update the users from the input, unset the active flag of the remaining ones."""

    for email, name in users.items():
        user = mod_mongo_user.UserDocument.objects(email=email).first()
        if user is None:
            mod_mongo_user.UserDocument(name=name, email=email, active=True).save()
            sys.stderr.write('created: %s\n' % email)
            continue
        changes = []
        if user.name != name:
            user.name = name
            changes.append('name')
        if user.active is False:
            user.active = True
            changes.append('active')
        if changes:
            user.save()
            sys.stderr.write('updated (%s): %s\n' % (', '.join(changes), email))

    for user in mod_mongo_user.UserDocument.objects():
        if user.admin:
            continue
        if (user.email or '').lower() in users:
            continue
        if user.active is False:
            continue
        mod_mongo_user.UserDocument.objects(id=user.id).update_one(unset__active=True)
        sys.stderr.write('active unset: %s\n' % user.email)


def main() -> int:
    try:
        users = read_input(sys.stdin)
    except ValueError as err:
        sys.stderr.write('%s\n' % err)
        return 1
    sync_users(users)
    return 0


if __name__ == '__main__':
    sys.exit(main())
