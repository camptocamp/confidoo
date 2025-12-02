"""Tests for the confidoo applier."""

from unittest.mock import MagicMock

import pytest

from confidoo.applier import apply_config
from confidoo.parser import ConfigParam, ModelConfig, ParsedConfig, RecordConfig


class TestApplyConfig:
    """Tests for apply_config function."""

    def test_apply_model_config(self):
        """Test applying model-wide settings."""
        # Setup mock environment
        mock_records = MagicMock()
        mock_model = MagicMock()
        mock_model._fields = {"smtp_port": True, "smtp_user": True}
        mock_model.search.return_value = mock_records

        mock_env = {"ir.mail_server": mock_model}

        config = ParsedConfig(
            models=[
                ModelConfig(
                    model_name="ir.mail_server",
                    field_values={"smtp_port": "22", "smtp_user": "username"},
                )
            ]
        )

        apply_config(config, mock_env)

        mock_model.search.assert_called_once_with([])
        mock_records.write.assert_called_once_with({"smtp_port": "22", "smtp_user": "username"})

    def test_apply_record_config(self):
        """Test applying record-specific settings."""
        # Setup mock environment
        mock_record = MagicMock()
        mock_record._fields = {"sftp_port": True, "sftp_user": True}

        mock_env = MagicMock()
        mock_env.ref.return_value = mock_record

        config = ParsedConfig(
            records=[
                RecordConfig(
                    xml_id="customer_module.sftp_server",
                    field_values={"sftp_port": "9999", "sftp_user": "username"},
                )
            ]
        )

        apply_config(config, mock_env)

        mock_env.ref.assert_called_once_with("customer_module.sftp_server", raise_if_not_found=False)
        mock_record.write.assert_called_once_with({"sftp_port": "9999", "sftp_user": "username"})

    def test_apply_config_param(self):
        """Test applying config parameters."""
        # Setup mock environment
        mock_config_param = MagicMock()

        mock_env = {"ir.config_parameter": mock_config_param}

        config = ParsedConfig(
            config_params=[ConfigParam(key="param.key", value="value1")]
        )

        apply_config(config, mock_env)

        mock_config_param.set_param.assert_called_once_with("param.key", "value1")

    def test_apply_model_not_found_raises_error(self):
        """Test that missing model raises error when raise_on_error is True."""
        mock_env = {}

        config = ParsedConfig(
            models=[
                ModelConfig(
                    model_name="unknown.model",
                    field_values={"field": "value"},
                )
            ]
        )

        with pytest.raises(ValueError, match="Model not found"):
            apply_config(config, mock_env, raise_on_error=True)

    def test_apply_model_not_found_silent(self):
        """Test that missing model is silently ignored when raise_on_error is False."""
        mock_env = {}

        config = ParsedConfig(
            models=[
                ModelConfig(
                    model_name="unknown.model",
                    field_values={"field": "value"},
                )
            ]
        )

        # Should not raise
        apply_config(config, mock_env, raise_on_error=False)

    def test_apply_record_not_found_raises_error(self):
        """Test that missing record raises error when raise_on_error is True."""
        mock_env = MagicMock()
        mock_env.ref.return_value = None

        config = ParsedConfig(
            records=[
                RecordConfig(
                    xml_id="unknown.record",
                    field_values={"field": "value"},
                )
            ]
        )

        with pytest.raises(ValueError, match="Record not found"):
            apply_config(config, mock_env, raise_on_error=True)

    def test_apply_record_not_found_silent(self):
        """Test that missing record is silently ignored when raise_on_error is False."""
        mock_env = MagicMock()
        mock_env.ref.return_value = None

        config = ParsedConfig(
            records=[
                RecordConfig(
                    xml_id="unknown.record",
                    field_values={"field": "value"},
                )
            ]
        )

        # Should not raise
        apply_config(config, mock_env, raise_on_error=False)

    def test_apply_field_not_found_in_model_raises_error(self):
        """Test that missing field in model raises error when raise_on_error is True."""
        mock_model = MagicMock()
        mock_model._fields = {"existing_field": True}

        mock_env = {"test.model": mock_model}

        config = ParsedConfig(
            models=[
                ModelConfig(
                    model_name="test.model",
                    field_values={"nonexistent_field": "value"},
                )
            ]
        )

        with pytest.raises(ValueError, match="Field 'nonexistent_field' not found"):
            apply_config(config, mock_env, raise_on_error=True)

    def test_apply_field_not_found_in_record_raises_error(self):
        """Test that missing field in record raises error when raise_on_error is True."""
        mock_record = MagicMock()
        mock_record._fields = {"existing_field": True}

        mock_env = MagicMock()
        mock_env.ref.return_value = mock_record

        config = ParsedConfig(
            records=[
                RecordConfig(
                    xml_id="test.record",
                    field_values={"nonexistent_field": "value"},
                )
            ]
        )

        with pytest.raises(ValueError, match="Field 'nonexistent_field' not found"):
            apply_config(config, mock_env, raise_on_error=True)

    def test_apply_empty_model_records(self):
        """Test that no write is called when model has no records."""
        mock_records = MagicMock()
        mock_records.__bool__ = MagicMock(return_value=False)  # Empty recordset
        mock_model = MagicMock()
        mock_model._fields = {"field": True}
        mock_model.search.return_value = mock_records

        mock_env = {"test.model": mock_model}

        config = ParsedConfig(
            models=[
                ModelConfig(
                    model_name="test.model",
                    field_values={"field": "value"},
                )
            ]
        )

        apply_config(config, mock_env)

        mock_model.search.assert_called_once_with([])
        mock_records.write.assert_not_called()
