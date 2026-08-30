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

remote_unit:
  host: "::1"
  port: 80
```

The MongoDB database is selected from the database path in `mongodb_uri`, so
the URI must include a database name. When omitted, settings use the values
shown above.
