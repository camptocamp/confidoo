# confidoo

Declarative Odoo configuration tool.

## Installation

```bash
pip install confidoo
```

## Usage

### Configuration File Format

The configuration file uses an INI-style format with specific section types:

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
```

### Python API

```python
from confidoo import parse_config, apply_config

# Parse configuration
config_text = """
[model:ir.mail_server]
smtp_port = 22
smtp_user = username

[record:customer_module.sftp_server]
sftp_port = 9999

[config:set_param]
param.key = value1
"""

config = parse_config(config_text)

# Apply to Odoo environment
# env is an odoo.api.Environment instance
apply_config(config, env)
```

### Section Types

- `[model:model_name]` - Settings applied to all records of a model
- `[record:xml_id]` - Settings applied to a specific record by XML ID
- `[config:set_param]` - Odoo config parameters (ir.config_parameter)

## Development

```bash
pip install -e ".[test]"
pytest
```

## License

GPL-3.0-or-later
