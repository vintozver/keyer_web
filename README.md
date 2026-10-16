# keyer_web

## Build

Build a wheel with pip:

```sh
python -m pip wheel .
```

The build downloads the required JavaScript and CSS resources and includes
them, along with the templates, in the wheel.

## Configuration

Create `config.yaml` in the application's working directory:

```yaml
mongodb_uri: mongodb://localhost/keyer
timezone: America/Los_Angeles

product:
  name: Keyer UI
  description: Aspen Grove OA, Keyer. Kent, WA, USA. All rights reserved.

smtp:
  host: localhost
  port: 25
  from:
    name: Key Card Access System
    email: noreply@localhost

```

The MongoDB database is selected from the database path in `mongodb_uri`, so
the URI must include a database name. When omitted, settings use the values
shown above.

## Units and endpoints

Active admin users can open **Manage keyer units** from the home page, or visit
`/admin/unit`, to create, edit, or delete units and add or remove signing keys.
Administrators can view the latest 300 logged events at `/admin/log`.
All management requests require an active administrator session; changes are
POST-only and protected by a session-bound CSRF token. Paste a PEM public key
or X.509 certificate when adding a key; it is validated and converted to DER
for storage. Private keys are never accepted. Key ids must be unique within
the unit. To rotate a key, add the new key before removing the old one.
Deleting a unit removes its keyset and prevents further callback authentication.
The first administrator must already be provisioned in the `user` collection
with `active: true` and `admin: true`.

Serve `keyer_web.util.web.Application` as the WSGI application. The existing
`keyer_web.util.web.frontend.Application` and
`keyer_web.util.web.backend.Application` entry points remain compatible aliases
for the same routes. Browser routes and unit callbacks now share one listener;
browser authentication still uses sessions.

Provision units in MongoDB's `unit` collection using
`keyer_web.module.mongo.unit.UnitDocument`. Each document has an automatic
ObjectId `id` (stored as `_id`), `name`, `host`, `port` (default 80), and a
`keyset` list of embedded `KeyItem` documents. Each key has a unit-local unique
string `id` and exactly one of `pub` (DER SubjectPublicKeyInfo public key) or
`crt` (DER X.509 certificate), stored as BSON binary. Store only public
material here; private signing keys stay on the units. The certificate is
provisioned as a trusted signing key, not verified against a certificate authority.

Move the old YAML `remote_unit.host` and `remote_unit.port` values into a unit
document and remove that YAML section; it is no longer read. Select a unit in
the browser for card operations and remote unlocking. Direct POST clients
must send `unit_id` as a form/JSON parameter when multiple units exist. If
exactly one exists, omitting `unit_id` selects it automatically. Hosts and
ports are read only from provisioned unit documents, never from request data.
Card and user configuration remains shared across all units.

Unit callbacks (`GET /config` and `POST /log`, with optional trailing slash) require
an `Authorization` header containing the `Bearer` scheme followed by the JWT.
Use PyJWT to sign a JSON-object payload (an empty object is sufficient for
both callbacks) with these **protected JWT headers**:

- `unit_id`: the unit ObjectId as a 24-character hexadecimal string.
- `kid`: an id from that unit's keyset.
- `dt`: a timezone-aware ISO 8601 datetime, for example `2026-10-15T17:16:08Z`.

The server accepts timestamps within 300 seconds of its clock (past or future).
Use HTTPS and keep unit clocks synchronized. A token can be reused within this
window; `dt` is a freshness check, not single-use replay protection.
Supported asymmetric algorithms are RS256/384/512, PS256/384/512,
ES256/384/512, and EdDSA. Unsigned and HMAC tokens are rejected. Standard JWT
expiry/not-before claims are checked when present. Invalid credentials receive
401 with a `WWW-Authenticate` bearer challenge; session cookies cannot authorize callbacks.
Successful configuration responses use `Cache-Control: no-store`.

## Event log

MongoDB's `log` collection stores `LogEvent` documents with these fields:

| Model field | BSON field/type | Meaning |
| --- | --- | --- |
| `oid` | `_id`, ObjectId | Unique event identifier, generated once when the event occurs |
| `card_id` | UUID or null | Unit-reported card UUID; null for controller events |
| `user_id` | ObjectId or null | User resolved from the card record; acting user for controller commands |
| `name` | string, at most 128 characters | Snapshot of the resolved user's name; empty when unknown |
| `event` | string | `card_tap`, `remote_unlock`, `card_personalize`, `card_format`, or `revocation` |
| `unit_id` | ObjectId or null | Unit involved, when applicable |

ObjectIds include the event creation time at second resolution. Generate the
ObjectId on the unit **at collection time**, not at upload time. Controller
events retain historical name snapshots even if a user is later renamed or
deleted. Unit events retain the reported card UUID, and retries with the same
event/card pair keep the original identity snapshot. The controller resolves
the reported card UUID against issued and revoked cards, then looks up its user
by stored user id (or by email for legacy card records). Unknown cards or users
use `user_id: null` and `name: ""`.

The controller records `remote_unlock` after the selected unit returns HTTP 200,
and `revocation` after the selected unit accepts the command and the controller
updates the card records. These describe acknowledged commands, not independently
verified relay actuation. Failed commands do not produce success events.
Personalization and formatting are recorded by the unit callback only, avoiding
duplicate entries for the same physical operation. Audit write failures are
surfaced as errors, not reported as success. A controller command may already
have taken effect when its audit write fails; the external operation and MongoDB
cannot be committed as one transaction.

### Atomic batch upload

`POST /log` accepts `Content-Type: application/json` and the same unit JWT as
`/config`. Send the following body (the JWT payload can remain `{}`):

```json
{
  "events": [
    {
      "oid": "6aefe9c80000000000000001",
      "event": "card_tap",
      "card_id": "6aefe9c8000000000000000000000002"
    }
  ]
}
```

The top-level object must contain only `events`. Each entry must contain exactly
`oid`, `event`, and `card_id`; `card_id` is the tapped card UUID (32 hexadecimal
digits or the standard hyphenated UUID form). Units may send only `card_tap`,
`card_personalize`, and `card_format`. The server supplies `unit_id` from the
authenticated JWT and resolves user identity from the card record; units never
send user ids or names. If no matching card/user exists, the event is still
stored with empty identity fields.

Batches must contain 1-1000 events, have no duplicate ObjectIds, and fit within
1 MiB. All entries are validated before writes. All inserts/upserts run in a
single MongoDB transaction with snapshot read concern and majority write concern.
**MongoDB must be a replica set (a single-node replica set is sufficient) or a
sharded cluster; standalone MongoDB cannot accept log batches.** Configure the
database user to permit sessions, transactions, and writes to `log`.

On committed success, HTTP 200 returns:

```json
{"accepted": ["6aefe9c80000000000000001"]}
```

Only remove these acknowledged events from the unit's buffer. Resending identical
events with their original ObjectIds is safe, including retries after a lost
response and batches mixing acknowledged and new events. Existing events are
immutable. Reusing an ObjectId with different data or from another unit returns
409 and rolls back the entire batch, including new events.

Invalid batches return 400, invalid/missing JWTs return 401, unsupported methods
return 405 (`Allow: POST`), oversized bodies return 413, and non-JSON media types
return 415. Database/transaction failures return 503 without an acknowledgement.
No error response acknowledges a subset of the batch. Retain events on network
errors, timeouts, or any non-200 response; use fresh JWTs on retries. A 400/409
requires investigation rather than repeatedly discarding or regenerating events.
Callback responses use `Cache-Control: no-store`.

### Companion `keyer` implementation proposal

The current units do not upload events yet. Add the following in the companion
repository before relying on card-event coverage:

- In `storage.Base`/`storage.RemoteHttp`, introduce a thread-safe in-memory event
  queue and a periodic uploader (for example every five seconds), independent of
  the five-minute configuration refresh. Use `bson.ObjectId` from a declared
  `pymongo` dependency to generate stable event ids. Never block the dispatcher
  on a controller HTTP request.
- `GET /config` continues to return the existing `users` tuples without a
  separate user-id mapping. Enqueue the stable event ObjectId, event type, and
  tapped card UUID; the controller resolves user identity when receiving events.
- In `Dispatcher.idle_card_tap_process`, enqueue exactly one `card_tap` per
  presentation, including denied or unrecognized cards, with the card UUID and
  no user id or name. Track the physical presentation, not every read in the
  polling loop. In `personalize_card` and `depersonalize_card`, enqueue
  `card_personalize` and `card_format` only after confirmed success, including
  the affected card UUID.
- Snapshot a prefix of up to 1000 queued events under a lock, release the lock
  during HTTPS upload to `https://<control.endpoint>/log`, and sign a fresh JWT
  with the existing unit key and headers. Permit only one upload at a time.
  On HTTP 200, verify that `accepted` exactly matches the submitted ObjectIds
  before removing that prefix under the lock. Preserve events appended during
  upload and retain the original prefix on errors, including malformed 200
  responses. Retry with backoff without regenerating ids or snapshots.
- Make queue overflow an explicit reported failure, not silent event loss.
  Attempt a bounded final flush at shutdown. Memory-only buffering necessarily
  loses pending events on power loss/restart; disk persistence would be a
  separate reliability improvement. Local-file mode needs an explicit uploader
  configuration if it is also expected to report to the controller.
- Cover concurrent enqueue/upload, lost acknowledgements, identical retries,
  offline recovery, denied taps, formatting, and shutdown in
  hardware-independent tests. Do not duplicate controller-owned remote unlock
  or revocation events in the uploader.

### Testing

Run the regular suite with `python -m unittest discover -s tests`. To also verify
real commits, retries and all-or-nothing rollback, point the integration tests at
a disposable MongoDB replica set:

```sh
KEYER_TEST_MONGODB_URI='mongodb://localhost:27017/?replicaSet=rs0' \
  python -m unittest discover -s tests -p test_logging.py
```

The integration tests create and remove their own uniquely named database.

## Syncing the users

The `keyer-sync-users` console script synchronizes the users with a list read
from the standard input. The input is tab separated with 3 fields: unit number,
name, email. The unit number is disregarded.

```sh
keyer-sync-users [--default-flags FLAGS] < users.tsv
```

Users present in the input are created (with `active=True`) when their email is
not known yet, otherwise their name is updated and `active` is set to `True`
when it was explicitly `False`. Non-admin users which are missing from the input
keep an explicit `active=False`, otherwise their `active` attribute is unset.
`--default-flags` sets `flags` only for newly created users; when omitted, flags
are left unset as before.
