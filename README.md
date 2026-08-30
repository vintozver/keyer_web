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

mail:
  smtp_host: localhost
  smtp_port: 25
  from_name: Key Card Access System
  from_email: noreply@localhost

remote_unit:
  host: "::1"
  port: 80
```

The MongoDB database is selected from the database path in `mongodb_uri`, so
the URI must include a database name. When omitted, settings use the values
shown above.
