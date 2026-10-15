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

Unit callbacks (`GET /config`, with optional trailing slash) require
an `Authorization` header containing the `Bearer` scheme followed by the JWT.
The existing `/log` route is also protected,
but its callback implementation is not included in this repository.
Use PyJWT to sign a JSON-object payload (an empty object is sufficient for
`/config`) with these **protected JWT headers**:

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
