# Confidoo

[![tests](https://github.com/camptocamp/confidoo/actions/workflows/test.yml/badge.svg)](https://github.com/camptocamp/confidoo/actions/workflows/test.yml)
[![prek](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/j178/prek/master/docs/assets/badge-v0.json)](https://github.com/j178/prek)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![ty](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ty/main/assets/badge/v0.json)](https://github.com/astral-sh/ty)

Declarative Odoo configuration

Confidoo applies declarative config to Odoo databases — syncing models, records, and system parameters into the correct state for each environment automatically.

## Installation

Install with [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv tool install git+https://github.com/camptocamp/confidoo
```

Or with [pipx](https://pypa.github.io/pipx/):

```bash
pipx install git+https://github.com/camptocamp/confidoo
```

## Quick Start

```bash
# Apply configuration from file
confidoo apply config.ini \
  --database mydb \
  --db-user odoo \
  --db-password secret

# Or use environment variables
export PGDATABASE=mydb PGUSER=odoo PGPASSWORD=secret
confidoo apply config.ini

# Or pipe configuration
cat config.ini | confidoo apply -d mydb -u odoo -p secret
```

## Usage

### Database Connection

Database credentials can be provided via CLI options or PostgreSQL environment variables:

**CLI Options:**
- `--database` / `-d` (or `PGDATABASE`, required)
- `--db-user` / `-u` (or `PGUSER`, optional)
- `--db-password` / `-p` (or `PGPASSWORD`, optional)
- `--db-host` / `-h` (or `PGHOST`, optional): host name, or Unix socket directory
- `--db-port` / `-P` (or `PGPORT`, optional)

Only the database is required. Options that are not set are not passed to the
PostgreSQL client library (libpq), which then applies its own defaults: the current
OS user, the password from `~/.pgpass` (or no password, for `peer` / `trust`
authentication), the local Unix socket, and port `5432`.

```bash
# Connect through the local Unix socket as the current OS user
confidoo apply config.ini -d mydb
```

**Debug Mode:**
```bash
confidoo --debug apply config.ini
```

### Input Methods

Configuration can be provided in three ways:

```bash
# File argument
confidoo apply config.ini

# Pipe from stdin
confidoo apply < config.ini

# Environment variable
echo $CONFIDOO_CONFIG | confidoo apply
```

## Configuration Format

Configuration files use INI format with four section types:

### Model-wide Settings

Apply settings to **all records** of a model:

```ini
[model:ir.cron]
active = False

[model:ir.mail_server]
smtp_port = 587
smtp_user = admin@example.com
```

**Custom table name:**
```ini
[model:custom.module.model]
_table = custom_table_name
some_column = value
```

### Record Settings

Apply settings to a **specific record** by XML ID:

```ini
[record:base.partner_admin]
name = Admin User
email = admin@example.com

[record:base.user_admin]
active = True
```

**Custom table name:**
```ini
[record:my_module.custom_record]
_table = custom_table
field_name = value
```

### System Parameters

Create or update system parameters:

```ini
[config:set_param]
ribbon.name = Production
database.uuid = 1234-5678-9012-3456
web.base.url = https://example.com
```

**Unset parameters** (remove by leaving value empty):
```ini
[config:set_param]
database.expiration_reason =
database.expiration_date =
```

### Raw SQL

When the other section types aren't enough (e.g. the records to update depend on a
related record), run a raw SQL query:

```ini
[sql:set-endpoint-apikey]
_query = UPDATE endpoint_endpoint
    SET value = %(value)s
    WHERE name = 'apikey'
      AND backend_id = (
        SELECT id FROM endpoint_backend WHERE tech_name = %(backend)s
      )
value = my-secret-key
backend = foo
```

- The identifier after `sql:` is any label, unique within the file
- `_query` holds the query. Indent the following lines to write it on multiple lines.
  As it's an INI value, an indented line starting with `#` or `;` is dropped as a
  comment (use SQL `--` comments instead), and an unindented line starts a new key
- Every other key is a query parameter (see below)

Like every other section, the query runs in the same transaction, in the order it
appears in the file: if any section fails, nothing is applied. Don't use transaction
control statements (`COMMIT`, `ROLLBACK`, `BEGIN`, `SAVEPOINT`...) in the query: they
would break this guarantee, e.g. changes committed before a later section fails can't
be rolled back.

The log reports the number of rows affected (or returned) by the query, as given by
psycopg2. For a query with several statements, it's the count of the last one.

#### Query parameters

Parameters use the named placeholder syntax of
[psycopg2](https://www.psycopg.org/docs/usage.html#passing-parameters-to-sql-queries),
the PostgreSQL driver Confidoo is built on: a key `name = value` is referenced in the
query as `%(name)s`.

- Values are quoted and escaped by psycopg2, so they can't break the query or inject
  SQL. Don't add quotes around placeholders: write `= %(name)s`, not `= '%(name)s'`
  (a quoted placeholder is rejected)
- The trailing `s` is part of the syntax, whatever the value's type
- An empty value (`name =`) is passed as `NULL`. Values are stripped of leading and
  trailing spaces, so for an empty string, convert it in the query:
  `SET ref = COALESCE(%(ref)s, '')`
- Every parameter must be used in the query, and every placeholder must be defined
- Parameter names must be lowercase, as INI keys are case-insensitive (`Name` is read
  as `name`)

#### Literal `%` must be written `%%`

Because `%` starts a placeholder, a literal `%` in the query must be doubled: psycopg2
turns `%%` back into `%` before running it. This applies to every sql section, even one
without parameters, and is the same rule as in any Python code using psycopg2.

```ini
[sql:disable-test-servers]
_query = UPDATE ir_mail_server
    SET active = false
    WHERE smtp_host LIKE %(domain)s OR name LIKE 'Test%%'
domain = %.example.com
```

Here the query runs as `... WHERE smtp_host LIKE '%.example.com' OR name LIKE 'Test%'`.
Parameter values are not affected: `%` in a value (like `domain` above) is written as
is.

A single `%` (or a positional `%s`) is rejected when the configuration is parsed, before
connecting to the database:

```
Invalid '%' in query of section: 'sql:disable-test-servers'.
Use %(name)s for parameters, and %% for a literal '%'.
```

## Complete Example

```ini
# Disable all scheduled actions
[model:ir.cron]
active = False

# Update specific partner
[record:base.partner_admin]
name = Confidoo Admin
email = admin@confidoo.com

# Set system parameters
[config:set_param]
ribbon.name = Test Environment
database.uuid = 0000-0000-0000-0000

# Remove expiration settings
database.expiration_reason =
database.expiration_date =

# Set the API key of a specific endpoint
[sql:set-endpoint-apikey]
_query = UPDATE endpoint_endpoint
    SET value = %(value)s
    WHERE name = 'apikey'
      AND backend_id = (
        SELECT id FROM endpoint_backend WHERE tech_name = %(backend)s
      )
value = my-secret-key
backend = foo
```
