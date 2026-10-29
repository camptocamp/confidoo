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


class TestRepeatedSections:
    """Tests for repeated sections, each applied as its own operation."""

    def test_repeated_config_sections(self):
        """Test that repeated config sections become separate ordered operations."""
        config_text = textwrap.dedent(
            """
            [config:set_param]
            web.base.url = https://staging.example.com

            [model:ir.mail_server]
            active = False

            [config:set_param]
            mail.catchall.domain =
        """
        )
        config = parse_config(config_text)
        assert len(config) == 3
        first, second, third = config.operations
        assert isinstance(first, ConfigParamOperation)
        assert first.identifier == "set_param"
        assert first.fields == {"web.base.url": "https://staging.example.com"}
        assert isinstance(second, ModelOperation)
        assert second.identifier == "ir.mail_server"
        assert second.fields == {"active": "False"}
        assert isinstance(third, ConfigParamOperation)
        assert third.identifier == "set_param"
        assert third.fields == {"mail.catchall.domain": None}

    def test_repeated_record_sections(self):
        """Test that repeated record sections are not merged."""
        config_text = textwrap.dedent(
            """
            [record:base.user_admin]
            active = False

            [model:res.users]
            login = changed

            [record:base.user_admin]
            active = True
            _table = custom_users
        """
        )
        config = parse_config(config_text)
        assert [str(op) for op in config] == [
            "record:base.user_admin",
            "model:res.users",
            "record:base.user_admin",
        ]
        assert config.operations[0].fields == {"active": "False"}
        assert config.operations[0].table is None
        assert config.operations[2].fields == {"active": "True"}
        assert config.operations[2].table == "custom_users"

    def test_repeated_model_sections_back_to_back(self):
        """Test that consecutive repeated model sections keep the same key."""
        config_text = textwrap.dedent(
            """
            [model:ir.cron]
            active = False

            [model:ir.cron]
            active = True
        """
        )
        config = parse_config(config_text)
        assert len(config) == 2
        assert all(isinstance(op, ModelOperation) for op in config)
        assert all(op.identifier == "ir.cron" for op in config)
        assert config.operations[0].fields == {"active": "False"}
        assert config.operations[1].fields == {"active": "True"}

    def test_duplicate_key_within_occurrence_raises_error(self):
        """Test that duplicate keys within a single occurrence still fail."""
        config_text = textwrap.dedent(
            """
            [config:set_param]
            key = one

            [config:set_param]
            key = two
            key = three
        """
        )
        with pytest.raises(
            ConfigParseError,
            match=r"option 'key' in section 'config:set_param' already exists",
        ):
            parse_config(config_text)

    def test_invalid_repeated_section_uses_real_name(self):
        """Test that errors report the section name as written by the user."""
        config_text = textwrap.dedent(
            """
            [model:ir.cron]
            active = False

            [invalid_section]
            field = value

            [invalid_section]
            field = value
        """
        )
        with pytest.raises(
            InvalidSectionError, match=r"Invalid section name: 'invalid_section'\."
        ):
            parse_config(config_text)

    def test_repeated_config_section_with_table_uses_real_name(self):
        """Test that _table errors on a repeated section report the real name."""
        config_text = textwrap.dedent(
            """
            [config:set_param]
            key = value

            [config:set_param]
            _table = custom
        """
        )
        with pytest.raises(
            InvalidSectionError,
            match=r"Config sections cannot have _table attribute: 'config:set_param'$",
        ):
            parse_config(config_text)

    def test_bracketed_values_are_not_section_headers(self):
        """Test that values and continuation lines with brackets are kept as is."""
        config_text = textwrap.dedent(
            """
            [config:set_param]
            first = [config:set_param]
            multi = line one
                [model:ir.cron]
        """
        )
        config = parse_config(config_text)
        assert len(config) == 1
        assert config.operations[0].fields == {
            "first": "[config:set_param]",
            "multi": "line one\n[model:ir.cron]",
        }

    def test_parser_reuse_with_repeated_sections(self):
        """Test that occurrence tracking is reset between parses."""
        parser = ConfidooConfigParser()
        content = "[model:a]\nf = 1\n[model:a]\nf = 2\n"
        first = parser.parse(content)
        second = parser.parse(content)
        assert first.operations == second.operations
        assert [op.fields for op in second] == [{"f": "1"}, {"f": "2"}]

    def test_default_section_is_unaffected(self):
        """Test that DEFAULT values are still inherited by every section."""
        config_text = textwrap.dedent(
            """
            [DEFAULT]
            shared = yes

            [model:a]
            f = 1

            [model:a]
            f = 2
        """
        )
        config = parse_config(config_text)
        assert [op.fields for op in config] == [
            {"f": "1", "shared": "yes"},
            {"f": "2", "shared": "yes"},
        ]


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
            ribbon.name = Test
            database.uuid = 0000-0000-0000-0000

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
        assert config_operation.fields["ribbon.name"] == "Test"
        assert config_operation.fields["database.uuid"] == "0000-0000-0000-0000"
        assert config_operation.fields["database.expiration_reason"] is None
        assert config_operation.fields["database.expiration_date"] is None

    def test_mixed_values(self):
        """Test handling of mixed values."""
        config_text = textwrap.dedent(
            """
            [config:set_param]
            spaces = value with spaces
            simple = value_no_spaces
            number = 123
        """
        )
        config = parse_config(config_text)
        operation = config.operations[0]
        assert operation.fields["spaces"] == "value with spaces"
        assert operation.fields["simple"] == "value_no_spaces"
        assert operation.fields["number"] == "123"
