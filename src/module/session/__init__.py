# Author: Vitaly Greck <vintozver@ya.ru>

import random
import re
import datetime
import uuid


class SessionError(Exception):
    pass


import collections.abc


class Session(collections.abc.MutableMapping):
    def create(self):
        """Create a new session ID and hash
        This function must insert the new session ID into self.id, the new session hash into self.hash

        This function must be overridden by subclasses.
        """
        raise NotImplementedError

    def load(self, session_id, session_hash):
        """Load the session dictionary from somewhere

        This function must be overridden by subclasses.

        It should return True if the load was successful, or False if the session could
        not be found. Any other type of error should raise an exception as usual."""
        raise NotImplementedError

    def save(self):
        """Save the session dictionary to somewhere
        This function must be overridden by subclasses."""
        raise NotImplementedError

    @classmethod
    def tidy(cls):
        pass

    def __init__(self, cookie_reader, cookie_writer):
        self.id = None
        self.hash = None
        self.created = None
        self.updated = None
        self.data = dict()

        cookie_val = cookie_reader()
        if cookie_val is not None:
            regex = re.match(r'^(\w+)\|(\w+)$', cookie_val)
            if regex is None:
                raise SessionError('Cookie value does not match regular expression')
            session_id = regex.group(1)
            session_hash = regex.group(2)
            del regex
            if self.load(session_id, session_hash):
                return
            del session_id
            del session_hash
        self.created = datetime.datetime.now(datetime.UTC)
        self.create()
        cookie_writer('%s|%s' % (self.id, self.hash))

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def __delitem__(self, key):
        del self.data[key]

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)


class MemorySession(Session):
    _sessions = dict()

    def create(self):
        self.id = uuid.uuid4()
        self.hash = '%x' % random.SystemRandom().getrandbits(128)

        session = dict()
        session['created'] = self.created
        session['data'] = self.data.copy()
        self._sessions[self.id] = session

    def load(self, session_id, session_hash):
        try:
            session = self._sessions[session_id]
        except KeyError:
            return False
        if session['hash'] != session_hash:
            return False
        self.id = session_id
        self.hash = session_hash
        self.created = session['created']
        self.updated = session.get('updated')
        self.data = session['data']
        return True

    def save(self):
        session = self._sessions[self.id]
        session['updated'] = self.updated
        session['data'] = self.data.copy()

    @classmethod
    def tidy(cls, max_idle=0, max_age=0):
        now = datetime.datetime.now(datetime.UTC)
        for k in cls._sessions:
            if (max_age and k["created"] < now - max_age) or (max_idle and k["updated"] < now - max_idle):
                del cls._sessions[k]


import os
import errno
import fcntl
import time
import pickle


class FileSession(Session):
    def create(self):
        while 1:
            Session.create(self)
            try:
                os.lstat("%s/%s" % (self.basedir, self["id"][:2]))
            except OSError as x:
                if x.errno == errno.ENOENT:
                    os.mkdir("%s/%s" % (self.basedir, self["id"][:2]), 0o700)
            try:
                fd = os.open("%s/%s/%s" % (self.basedir, self["id"][:2], self["id"][2:]), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
            except OSError as x:
                if x.errno != errno.EEXIST:
                    raise
                continue
            try:
                os.write(fd, "%d\n" % self.created)
                os.write(fd, pickle.dumps({}, 1))
                break
            finally:
                os.close(fd)

    def load(self):
        try:
            f = open("%s/%s/%s" % (self.basedir, self["id"][:2], self["id"][2:]), "r+b")
        except IOError as x:
            if x[0] != errno.ENOENT:
                raise
            return 0
        try:
            fcntl.lockf(f.fileno(), fcntl.LOCK_EX)
            self.created = int(f.readline().strip())
            self.update(pickle.load(f))
            return 1
        finally:
            f.close()

    def save(self):
        with open("%s/%s/%s" % (self.basedir, self["id"][:2], self["id"][2:]), "r+b") as f:
            fcntl.lockf(f.fileno(), fcntl.LOCK_EX)
            f.write("%d\n" % self.created)
            pickle.dump(self.copy(), f, 1)
            f.truncate()
            f.flush()

    @classmethod
    def tidy(cls, max_idle=0, max_age=0, basedir=None):
        if not max_idle and not max_age:
            return
        basedir = cls._find_basedir(basedir)
        now = time.time()
        for d in os.listdir(basedir):
            if len(d) != 2 or not d.isalnum():
                continue
            for f in os.listdir("%s/%s" % (basedir, d)):
                if len(f) != 6 or not f.isalnum():
                    continue
                p = "%s/%s/%s" % (basedir, d, f)
                try:
                    f = open(p, "rb")
                    age = int(f.readline().strip())
                finally:
                    f.close()
                if (max_idle and os.lstat(p).st_mtime < now - max_idle) or \
                        (max_age and age < now - max_age):
                    os.remove(p)

    tidy = classmethod(tidy)

    def _find_basedir(basedir):
        if basedir is None:
            basedir = os.environ.get("TMPDIR", "/tmp")
        while basedir[-1] == "/":
            basedir = basedir[:-1]
        basedir = "%s/sessions-%d" % (basedir, os.getuid())
        try:
            st = os.lstat(basedir)
            if st[4] != os.getuid():
                raise Error("Sessions basedir is not owned by user %d" % os.getuid())
        except OSError as x:
            if x[0] == errno.ENOENT:
                os.mkdir(basedir, 0o700)
        return basedir

    _find_basedir = staticmethod(_find_basedir)

    def __init__(self, basedir=None, **kwargs):
        self.basedir = self._find_basedir(basedir)
        Session.__init__(self, **kwargs)


class GenericSQLSession(Session):
    def create(self):
        while 1:
            Session.create(self)
            try:
                self.dbc.execute("INSERT INTO %s (ID,hash,created,updated,data)"
                                 " VALUES (%%s,%%s,%%s,%%s,%%s)" % (self.table,),
                                 (self["id"], self["hash"], int(self.created), int(self.created),
                                  pickle.dumps({}, 1)))
                self.dbc.execute("COMMIT")
            except self.dbc.IntegrityError:
                pass
            else:
                break

    def load(self):
        self.dbc.execute("SELECT created,data FROM %s WHERE ID=%%s" % (self.table,),
                         (self["id"],))
        if self.dbc.rowcount == 0:
            return 0
        row = self.dbc.fetchone()
        self.created = row[0]
        self.update(pickle.loads(row[1]))
        return 1

    def save(self):
        self.dbc.execute("UPDATE %s SET updated=%%s,data=%%s"
                         " WHERE ID=%%s" % (self.table,), (int(time.time()),
                                                           pickle.dumps(self.copy(), 1), self["id"]))
        self.dbc.execute("COMMIT")

    @classmethod
    def tidy(cls, dbc, table="sessions", max_idle=0, max_age=0):
        now = time.time()
        if max_idle:
            dbc.execute("DELETE FROM %s WHERE updated < %%s" % (table,),
                        (now - max_idle,))
        if max_age:
            dbc.execute("DELETE FROM %s WHERE created < %%s" % (table,),
                        (now - max_age,))
        if max_idle or max_age:
            dbc.execute("COMMIT")

    tidy = staticmethod(tidy)

    def __init__(self, dbc, table="sessions", **kwargs):
        self.dbc = dbc
        self.table = table
        Session.__init__(self, **kwargs)


from ... import config
from ...module import mongo as mod_mongo


class MongoDbSession(Session):
    def create(self):
        self.id = mod_mongo.bson.objectid.ObjectId()
        self.hash = '%x' % random.SystemRandom().getrandbits(128)

        with mod_mongo.DbSessionController() as db_session:
            db_collection = db_session[config.db_mongo.name]['sessions']
            db_collection.insert_one(mod_mongo.bson.son.SON({'_id': self.id, 'hash': self.hash, 'created': self.created, 'data': self.data}))

    def load(self, session_id, session_hash):
        # This is necessary for the base class calls. Base class tries to load the session from cookies, but cookies can only handle binary data, not structures
        if isinstance(session_id, (bytes, str)):
            session_id = mod_mongo.bson.objectid.ObjectId(session_id)

        with mod_mongo.DbSessionController() as db_session:
            db_collection = db_session[config.db_mongo.name]['sessions']
            session = db_collection.find_one(mod_mongo.bson.son.SON({'_id': session_id}))

        if session is None:
            return False
        try:
            if session["hash"] != session_hash:
                return False
        except KeyError:
            return False
        self.id = session_id
        self.hash = session_hash
        self.created = session["created"]
        self.updated = session.get("updated")
        self.data = session["data"]
        return True

    def save(self):
        self.updated = datetime.datetime.now(datetime.UTC)
        with mod_mongo.DbSessionController() as db_session:
            db_collection = db_session[config.db_mongo.name]['sessions']
            db_collection.update_one(
                mod_mongo.bson.son.SON({'_id': self.id}),
                mod_mongo.bson.son.SON({'$set': {'updated': self.updated, 'data': self.data}}),
            )

    @classmethod
    def tidy(cls, max_idle=0, max_age=0):
        dt = datetime.datetime.now(datetime.UTC)
        with mod_mongo.DbSessionController() as db_session:
            if max_idle:
                db_session[config.db_mongo.name]['sessions'].delete_many(mod_mongo.bson.son.SON({'updated': {'$lt': dt - max_idle}}))
            if max_age:
                db_session[config.db_mongo.name]['sessions'].delete_many(mod_mongo.bson.son.SON({'created': {'$lt': dt - max_age}}))
