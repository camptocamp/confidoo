"""Tests for the confidoo parser."""

import pytest

from confidoo.parser import (
    ConfigParam,
    ModelConfig,
    ParsedConfig,
    RecordConfig,
    parse_config,
)


class TestParseConfig:
    """Tests for parse_config function."""

    def test_parse_model_config(self):
        """Test parsing model-wide settings."""
        config_text = """
[model:ir.mail_server]
smtp_port = 22
smtp_user = username
"""
        result = parse_config(config_text)

        assert len(result.models) == 1
        assert len(result.records) == 0
        assert len(result.config_params) == 0

        model = result.models[0]
        assert model.model_name == "ir.mail_server"
        assert model.field_values == {"smtp_port": "22", "smtp_user": "username"}

    def test_parse_record_config(self):
        """Test parsing record-specific settings."""
        config_text = """
[record:customer_module.sftp_server]
sftp_port = 9999
sftp_user = username
"""
        result = parse_config(config_text)

        assert len(result.models) == 0
        assert len(result.records) == 1
        assert len(result.config_params) == 0

        record = result.records[0]
        assert record.xml_id == "customer_module.sftp_server"
        assert record.field_values == {"sftp_port": "9999", "sftp_user": "username"}

    def test_parse_config_params(self):
        """Test parsing config parameters."""
        config_text = """
[config:set_param]
param.key = value1
another.param = value2
"""
        result = parse_config(config_text)

        assert len(result.models) == 0
        assert len(result.records) == 0
        assert len(result.config_params) == 2

        # Check params (order may vary based on dict iteration)
        param_dict = {p.key: p.value for p in result.config_params}
        assert param_dict == {"param.key": "value1", "another.param": "value2"}

    def test_parse_mixed_config(self):
        """Test parsing configuration with all section types."""
        config_text = """
# Model-wide settings (all records of this model)
[model:ir.mail_server]
smtp_port = 22
smtp_user = username

# Record settings using xml-id
[record:customer_module.sftp_server]
sftp_port = 9999
sftp_user = username

# Config parameters
[config:set_param]
param.key = value1
"""
        result = parse_config(config_text)

        assert len(result.models) == 1
        assert len(result.records) == 1
        assert len(result.config_params) == 1

        assert result.models[0].model_name == "ir.mail_server"
        assert result.records[0].xml_id == "customer_module.sftp_server"
        assert result.config_params[0].key == "param.key"
        assert result.config_params[0].value == "value1"

    def test_parse_empty_config(self):
        """Test parsing empty configuration."""
        result = parse_config("")

        assert len(result.models) == 0
        assert len(result.records) == 0
        assert len(result.config_params) == 0

    def test_parse_unknown_section_raises_error(self):
        """Test that unknown section types raise an error."""
        config_text = """
[unknown:section]
key = value
"""
        with pytest.raises(ValueError, match="Unknown section type"):
            parse_config(config_text)

    def test_parse_multiple_models(self):
        """Test parsing multiple model sections."""
        config_text = """
[model:res.partner]
active = true

[model:res.users]
active = true
login = admin
"""
        result = parse_config(config_text)

        assert len(result.models) == 2
        assert result.models[0].model_name == "res.partner"
        assert result.models[0].field_values == {"active": "true"}
        assert result.models[1].model_name == "res.users"
        assert result.models[1].field_values == {"active": "true", "login": "admin"}

    def test_parse_multiple_records(self):
        """Test parsing multiple record sections."""
        config_text = """
[record:base.user_admin]
login = superadmin

[record:base.user_demo]
active = false
"""
        result = parse_config(config_text)

        assert len(result.records) == 2
        assert result.records[0].xml_id == "base.user_admin"
        assert result.records[1].xml_id == "base.user_demo"
