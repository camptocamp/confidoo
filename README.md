# Confidoo

Declarative Odoo configuration

Confidoo applies declarative config to Odoo databases — syncing models, records, and system parameters into the correct state for each environment automatically.

## Installation

Install with [uv](https://docs.astral.sh/uv/) (recommended):

    uv tool install git+https://github.com/camptocamp/confidoo

Install with [pipx](https://pypa.github.io/pipx/):

    pipx install git+https://github.com/camptocamp/confidoo


## Usage

To apply a configuration, run:

    confidoo apply /path/to/config.ini

Alternatively, the configuration can be piped in:

    confidoo apply < /path/to/config.ini

Or..

    echo $CONFIDOO_CONFIG | confidoo apply


## Configuration

The configuration is an INI format file that defines the models, records, and system parameters to sync.

Sections are used to group settings by model, record, or system parameter.

### Example

```ini
# Model-wide settings (all records of this model)
# Section Syntax: [model:model_name]
[model:ir.mail_server]
smtp_port = 22
smtp_user = username

# Record settings using xml-id
# Section Syntax: [record:xml_id]
[record:customer_module.sftp_server]
sftp_port = 9999
sftp_user = username

# Additionally, config parameters can be set with
[config:set_param]
param.key = value1
another.parameter = value2
```

### Model-wide Settings

Model-wide settings are applied to all records of the model.

The table name will be guessed from the model name, by replacing `.` with `_`. However, if the model uses a custom table name, it can be specified with a `_table` attribute.

```ini
[model:custom.module.model]
_table = custom_table

some_column = value1
```

### Record Settings

Record settings are applied to a specific record, matched by its xml-id.

Similarly to the model-wide settings, the table name will be guessed from the model name, by replacing `.` with `_`. However, if the model uses a custom table name, it can be specified with a `_table` attribute.

### System Parameter Settings

System parameter settings are applied to a specific system parameter, matched by its key.
The config parameter will be created or updated with the given value.
