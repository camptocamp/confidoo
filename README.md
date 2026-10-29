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
- `--database` / `-d` (or `PGDATABASE`)
- `--db-user` / `-u` (or `PGUSER`)
- `--db-password` / `-p` (or `PGPASSWORD`)
- `--db-host` / `-h` (or `PGHOST`, default: `localhost`)
- `--db-port` / `-P` (or `PGPORT`, default: `5432`)

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

Configuration files use INI format with three section types:

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

### Repeated Sections

Sections can be repeated. Each occurrence is a separate operation, and operations are
applied in the order they appear in the file:

```ini
[config:set_param]
web.base.url = https://staging.example.com

[model:ir.mail_server]
active = False

[config:set_param]
mail.catchall.domain =
```

A key can't be repeated within a single section occurrence.

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
```
