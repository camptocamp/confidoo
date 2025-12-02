# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Tests for the Confidoo configuration parser."""

import textwrap

import pytest

from confidoo.config import (
    ConfidooConfigParser,
    ConfigParamOperation,
    ModelOperation,
    OperationType,
    ParsedConfig,
    RecordOperation,
    parse_config,
)
from confidoo.exceptions import ConfigParseError, InvalidSectionError


class TestParseModelSection:
    """Tests for parsing model sections."""

    def test_parse_simple_model(self):
        """Test parsing a simple model section."""
        config_text = textwrap.dedent(
            """
            [model:ir.mail_server]
            smtp_port = 22
            smtp_user = username
        """
        )
        config = parse_config(config_text)
        assert len(config) == 1
        operation = config.operations[0]
        assert isinstance(operation, ModelOperation)
        assert operation.operation_type == OperationType.MODEL
        assert operation.identifier == "ir.mail_server"
        assert operation.fields == {"smtp_port": "22", "smtp_user": "username"}
        assert operation.table is None

    def test_parse_model_with_table(self):
        """Test parsing model section with custom table."""
        config_text = textwrap.dedent(
            """
            [model:custom.model]
            _table = custom_table_name
            field1 = value1
        """
        )
        config = parse_config(config_text)
        operation = config.operations[0]
        assert isinstance(operation, ModelOperation)
        assert operation.table == "custom_table_name"
        assert "_table" not in operation.fields
        assert operation.fields == {"field1": "value1"}

    def test_parse_model_case_insensitive_fields(self):
        """Test that field names are case-insensitive (normalized to lowercase)."""
        config_text = textwrap.dedent(
            """
            [model:test.model]
            FieldName = value1
            Field_Name = value2
        """
        )
        config = parse_config(config_text)
        operation = config.operations[0]
        # ConfigParser normalizes field names to lowercase
        # Different original cases become different normalized keys
        assert "fieldname" in operation.fields
        assert "field_name" in operation.fields
        assert operation.fields["fieldname"] == "value1"
        assert operation.fields["field_name"] == "value2"


class TestParseRecordSection:
    """Tests for parsing record sections."""

    def test_parse_simple_record(self):
        """Test parsing a simple record section."""
        config_text = textwrap.dedent(
            """
            [record:customer_module.sftp_server]
            sftp_port = 9999
            sftp_user = username
        """
        )
        config = parse_config(config_text)
        assert len(config) == 1
        operation = config.operations[0]
        assert isinstance(operation, RecordOperation)
        assert operation.operation_type == OperationType.RECORD
        assert operation.identifier == "customer_module.sftp_server"
        assert operation.fields == {"sftp_port": "9999", "sftp_user": "username"}
        assert operation.table is None

    def test_parse_record_with_table(self):
        """Test parsing record section with custom table."""
        config_text = textwrap.dedent(
            """
            [record:module.record_id]
            _table = custom_table
            field1 = value1
        """
        )
        config = parse_config(config_text)
        operation = config.operations[0]
        assert isinstance(operation, RecordOperation)
        assert operation.table == "custom_table"
        assert "_table" not in operation.fields


class TestParseConfigSection:
    """Tests for parsing config parameter sections."""

    def test_parse_config_params(self):
        """Test parsing config parameter section."""
        config_text = textwrap.dedent(
            """
            [config:set_param]
            ribbon.name = Test
            database.uuid = 0000-0000-0000-0000
        """
        )
        config = parse_config(config_text)
        assert len(config) == 1
        operation = config.operations[0]
        assert isinstance(operation, ConfigParamOperation)
        assert operation.operation_type == OperationType.CONFIG
        assert operation.identifier == "set_param"
        assert operation.fields == {
            "ribbon.name": "Test",
            "database.uuid": "0000-0000-0000-0000",
        }
        assert operation.table is None

    def test_parse_config_empty_values(self):
        """Test parsing empty values for unsetting parameters."""
        config_text = textwrap.dedent(
            """
            [config:set_param]
            database.expiration_date =
            database.expiration_reason =
        """
        )
        config = parse_config(config_text)
        operation = config.operations[0]
        assert operation.fields["database.expiration_date"] is None
        assert operation.fields["database.expiration_reason"] is None

    def test_parse_config_with_table_raises_error(self):
        """Test error when config section has _table attribute."""
        config_text = textwrap.dedent(
            """
            [config:set_param]
            _table = invalid
            param = value
        """
        )
        with pytest.raises(InvalidSectionError, match="cannot have _table attribute"):
            parse_config(config_text)


class TestOrderPreservation:
    """Tests for section order preservation."""

    def test_parse_order_preserved(self):
        """Test that sections are parsed in file order."""
        config_text = textwrap.dedent(
            """
            [model:first]
            field1 = value1

            [record:second]
            field2 = value2

            [config:set_param]
            field3 = value3

            [model:fourth]
            field4 = value4
        """
        )
        config = parse_config(config_text)
        assert len(config) == 4
        assert config.operations[0].identifier == "first"
        assert isinstance(config.operations[0], ModelOperation)
        assert config.operations[1].identifier == "second"
        assert isinstance(config.operations[1], RecordOperation)
        assert config.operations[2].identifier == "set_param"
        assert isinstance(config.operations[2], ConfigParamOperation)
        assert config.operations[3].identifier == "fourth"
        assert isinstance(config.operations[3], ModelOperation)

    def test_parse_iteration_order(self):
        """Test that iteration maintains order."""
        config_text = textwrap.dedent(
            """
            [model:one]
            f = v

            [record:two]
            f = v

            [config:set_param]
            f = v
        """
        )
        config = parse_config(config_text)
        identifiers = [operation.identifier for operation in config]
        assert identifiers == ["one", "two", "set_param"]


class TestErrorHandling:
    """Tests for error handling and validation."""

    def test_invalid_section_format(self):
        """Test error on invalid section format."""
        config_text = textwrap.dedent(
            """
            [invalid_section]
            field = value
        """
        )
        with pytest.raises(InvalidSectionError, match="Invalid section name"):
            parse_config(config_text)

    def test_empty_identifier(self):
        """Test error on empty identifier."""
        config_text = textwrap.dedent(
            """
            [model:]
            field = value
        """
        )
        # The regex catches this as invalid section name first
        with pytest.raises(InvalidSectionError, match="Invalid section name"):
            parse_config(config_text)

    def test_empty_table_attribute(self):
        """Test error when _table attribute is empty."""
        config_text = textwrap.dedent(
            """
            [model:test.model]
            _table =
            field = value
        """
        )
        with pytest.raises(
            InvalidSectionError, match="_table attribute cannot be empty"
        ):
            parse_config(config_text)

    def test_invalid_ini_syntax(self):
        """Test error on invalid INI syntax."""
        config_text = textwrap.dedent(
            """
            [model:test
            field = value
        """
        )
        with pytest.raises(ConfigParseError, match="Failed to parse INI content"):
            parse_config(config_text)

    def test_unknown_section_type(self):
        """Test error on unknown section type."""
        config_text = textwrap.dedent(
            """
            [unknown:identifier]
            field = value
        """
        )
        with pytest.raises(InvalidSectionError, match="Invalid section name"):
            parse_config(config_text)


class TestParserClass:
    """Tests for the ConfidooConfigParser class."""

    def test_parser_reusability(self):
        """Test that parser can be reused."""
        parser = ConfidooConfigParser()

        config1 = parser.parse("[model:test1]\nfield = value1")
        assert len(config1) == 1
        assert config1.operations[0].identifier == "test1"

        config2 = parser.parse("[model:test2]\nfield = value2")
        assert len(config2) == 1
        assert config2.operations[0].identifier == "test2"

    def test_parse_file(self):
        """Test parsing from file object."""
        from io import StringIO

        parser = ConfidooConfigParser()
        file_obj = StringIO("[model:test]\nfield = value")

        config = parser.parse_file(file_obj)
        assert len(config) == 1
        assert config.operations[0].identifier == "test"


class TestParsedConfig:
    """Tests for ParsedConfig container."""

    def test_empty_config(self):
        """Test empty configuration."""
        config = ParsedConfig()
        assert len(config) == 0
        assert list(config) == []

    def test_add_operation(self):
        """Test adding operations."""
        config = ParsedConfig()
        operation1 = ModelOperation(identifier="test1", fields={"f": "v"})
        operation2 = RecordOperation(identifier="test2", fields={"f": "v"})

        config.add_operation(operation1)
        config.add_operation(operation2)

        assert len(config) == 2
        assert config.operations[0] is operation1
        assert config.operations[1] is operation2


class TestComplexScenarios:
    """Tests for complex configuration scenarios."""

    def test_parse_test_fixture(self):
        """Test parsing the test fixture file."""
        config_text = textwrap.dedent(
            """
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

            # Additionally, config parameters can be set with system parameter syntax
            [config:set_param]
            ribbon.name = "Test"
            database.uuid = "0000-0000-0000-0000"

            # And even removed/unset
            database.expiration_reason =
            database.expiration_date =
        """
        )
        config = parse_config(config_text)
        assert len(config) == 3

        # Check model operation
        model_operation = config.operations[0]
        assert isinstance(model_operation, ModelOperation)
        assert model_operation.identifier == "ir.mail_server"
        assert model_operation.fields == {"smtp_port": "22", "smtp_user": "username"}

        # Check record operation
        record_operation = config.operations[1]
        assert isinstance(record_operation, RecordOperation)
        assert record_operation.identifier == "customer_module.sftp_server"
        assert record_operation.fields == {"sftp_port": "9999", "sftp_user": "username"}

        # Check config operation
        config_operation = config.operations[2]
        assert isinstance(config_operation, ConfigParamOperation)
        assert config_operation.identifier == "set_param"
        assert config_operation.fields["ribbon.name"] == '"Test"'
        assert config_operation.fields["database.uuid"] == '"0000-0000-0000-0000"'
        assert config_operation.fields["database.expiration_reason"] is None
        assert config_operation.fields["database.expiration_date"] is None

    def test_mixed_quoted_values(self):
        """Test handling of quoted and unquoted values."""
        config_text = textwrap.dedent(
            """
            [config:set_param]
            quoted = "value with spaces"
            unquoted = value_no_spaces
            number = 123
        """
        )
        config = parse_config(config_text)
        operation = config.operations[0]
        assert operation.fields["quoted"] == '"value with spaces"'
        assert operation.fields["unquoted"] == "value_no_spaces"
        assert operation.fields["number"] == "123"
