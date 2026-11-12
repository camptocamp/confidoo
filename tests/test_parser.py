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
    SqlOperation,
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
        assert not hasattr(operation, "table")

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

    def test_parse_config_with_table_is_a_param(self):
        """Test _table is a regular parameter in config sections."""
        config_text = textwrap.dedent(
            """
            [config:set_param]
            _table = value
            param = value
        """
        )
        operation = parse_config(config_text).operations[0]
        assert operation.fields == {"_table": "value", "param": "value"}


class TestParseSqlSection:
    """Tests for parsing raw SQL sections."""

    def test_parse_sql_with_params(self):
        """Test parsing a multi-line query with named parameters."""
        config_text = textwrap.dedent(
            """
            [sql:set-endpoint-apikey]
            _query = UPDATE endpoint_endpoint
                SET value = %(value)s
                WHERE name = 'apikey'
                  AND backend_id = (
                    SELECT id FROM endpoint_backend WHERE tech_name = %(backend)s
                  )
            value = secret
            backend = foo
        """
        )
        config = parse_config(config_text)
        assert len(config) == 1
        operation = config.operations[0]
        assert isinstance(operation, SqlOperation)
        assert operation.identifier == "set-endpoint-apikey"
        assert operation.fields == {"value": "secret", "backend": "foo"}
        assert operation.query.startswith("UPDATE endpoint_endpoint\n")
        assert "tech_name = %(backend)s" in operation.query
        assert str(operation) == "sql:set-endpoint-apikey"

    def test_parse_sql_without_params(self):
        """Test parsing a query without parameters."""
        config = parse_config(
            "[sql:disable-crons]\n_query = UPDATE ir_cron SET active = false\n"
        )
        operation = config.operations[0]
        assert isinstance(operation, SqlOperation)
        assert operation.query == "UPDATE ir_cron SET active = false"
        assert operation.fields == {}

    def test_parse_sql_empty_param(self):
        """Test that an empty parameter value is parsed as None (SQL NULL)."""
        config_text = textwrap.dedent(
            """
            [sql:reset]
            _query = UPDATE res_partner SET email = %(email)s
            email =
        """
        )
        operation = parse_config(config_text).operations[0]
        assert operation.fields == {"email": None}

    def test_parse_sql_escaped_percent(self):
        """Test that an escaped literal '%%' is accepted."""
        config_text = textwrap.dedent(
            """
            [sql:like]
            _query = UPDATE res_partner SET email = %(email)s WHERE name LIKE 'foo%%'
            email = foo@example.com
        """
        )
        operation = parse_config(config_text).operations[0]
        assert isinstance(operation, SqlOperation)
        assert "LIKE 'foo%%'" in operation.query

    def test_parse_multiple_sql_sections(self):
        """Test that multiple sql sections are kept in order."""
        config_text = textwrap.dedent(
            """
            [sql:first]
            _query = SELECT 1

            [model:ir.cron]
            active = False

            [sql:second]
            _query = SELECT 2
        """
        )
        config = parse_config(config_text)
        assert [str(operation) for operation in config] == [
            "sql:first",
            "model:ir.cron",
            "sql:second",
        ]

    @pytest.mark.parametrize(
        ("config_text", "fields"),
        [
            ("[model:ir.cron]\n_query = foo\n", {"_query": "foo"}),
            ("[record:base.a]\n_query = foo\n", {"_query": "foo"}),
            ("[config:set_param]\n_query =\n", {"_query": None}),
            ("[model:ir.cron]\n_other = foo\n", {"_other": "foo"}),
        ],
    )
    def test_other_attributes_are_fields(self, config_text, fields):
        """Test keys that aren't the operation's special attributes are fields."""
        operation = parse_config(config_text).operations[0]
        assert operation.fields == fields

    @pytest.mark.parametrize(
        ("config_text", "match"),
        [
            ("[sql:q]\nvalue = foo\n", "Missing _query attribute"),
            ("[sql:q]\n_query =\n", "_query attribute cannot be empty"),
            (
                "[sql:q]\n_query = SELECT 1\n_table = foo\n",
                r"Unused query parameter\(s\) _table",
            ),
            (
                "[sql:q]\n_query = SELECT %(foo)s, %(bar)s\nfoo = 1\n",
                r"Undefined query parameter\(s\) bar",
            ),
            ("[sql:q]\n_query = SELECT 1\nfoo = 1\n", "Unused query parameter"),
            ("[sql:q]\n_query = SELECT %(Foo)s\nfoo = 1\n", "must be lowercase"),
            ("[sql:q]\n_query = SELECT %()s\n", "Empty query parameter name"),
            ("[sql:q]\n_query = SELECT %(n)i\nn = 1\n", r"Invalid placeholder %\(n\)i"),
            ("[sql:q]\n_query = SELECT %(n)\nn = 1\n", r"Use %\(n\)s for a parameter"),
            ("[sql:q]\n_query = SELECT %(n)d\n", r"Invalid XML ID reference %\(n\)d"),
            ("[sql:q]\n_query = SELECT %(n)d\n", r"For a parameter, use %\(n\)s\."),
            ("[sql:q]\n_query = SELECT %(base.)d\n", r"XML ID: %\(module\.name\)d\.$"),
            ("[sql:q]\n_query = SELECT %(.x)d\n", "Invalid XML ID reference"),
            ("[sql:q]\n_query = SELECT %(base.x)d\nx = 1\n", "Unused query parameter"),
            ("[sql:q]\n_query = SELECT '%(x)s'\nx = 1\n", "Quoted query parameter"),
            ("[sql:q]\n_query = SELECT '%(x)s\nx = 1\n", "Quoted query parameter"),
            ('[sql:q]\n_query = SELECT %(x)s"\nx = 1\n', "Quoted query parameter"),
            ("[sql:q]\n_query = SELECT %s\n", "Invalid '%'"),
            (
                "[sql:q]\n_query = SELECT %(foo\n    FROM t WHERE id IN (1)\n",
                r"Invalid '%' in query of section: 'sql:q'\.",
            ),
            (
                "[sql:q]\n_query = SELECT '%%(foo)s'\nfoo = 1\n",
                "Unused query parameter",
            ),
            ("[sql:q]\n_query = SELECT 1 WHERE 'a' LIKE 'a%'\n", "Invalid '%'"),
        ],
    )
    def test_parse_sql_invalid(self, config_text, match):
        """Test invalid sql sections raise a descriptive error."""
        with pytest.raises(InvalidSectionError, match=match):
            parse_config(config_text)

    def test_parse_sql_xmlid_references(self):
        """Test XML ID references need no parameter, and are rendered as ids."""
        config_text = textwrap.dedent(
            """
            [sql:xmlid]
            _query = UPDATE res_partner SET name = %(name)s
                WHERE id IN (%(base.main_partner)d, %(base.partner_admin)d)
                AND parent_id = %(base.main_partner)d AND ref LIKE 'x%%'
            name = Foo
        """
        )
        operation = parse_config(config_text).operations[0]
        assert isinstance(operation, SqlOperation)
        assert operation.fields == {"name": "Foo"}

        resolved = []

        def resolve_xmlid(xmlid):
            resolved.append(xmlid)
            return {"base.main_partner": 1, "base.partner_admin": 3}[xmlid]

        assert operation.render_query(resolve_xmlid) == (
            "UPDATE res_partner SET name = %(name)s\n"
            "WHERE id IN (1, 3)\n"
            "AND parent_id = 1 AND ref LIKE 'x%%'"
        )
        assert resolved == ["base.main_partner", "base.partner_admin"]

    def test_parse_sql_undefined_lowercase_param_no_hint(self):
        """Test the lowercase hint is only given for names with uppercase."""
        with pytest.raises(InvalidSectionError) as exc_info:
            parse_config("[sql:q]\n_query = SELECT %(foo)s\n")
        assert "lowercase" not in str(exc_info.value)


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

    def test_default_section_keys(self):
        """Test [DEFAULT] keys are rejected instead of merged into every section."""
        config_text = textwrap.dedent(
            """
            [DEFAULT]
            foo = bar

            [model:ir.cron]
            active = False
        """
        )
        with pytest.raises(
            ConfigParseError, match=r"\[DEFAULT\] sections aren't supported.*foo"
        ):
            parse_config(config_text)

    def test_empty_default_section(self):
        """Test an empty [DEFAULT] section is harmless."""
        config = parse_config("[DEFAULT]\n\n[model:ir.cron]\nactive = False\n")
        assert config.operations[0].fields == {"active": "False"}

    def test_default_section_keys_not_kept_on_reuse(self):
        """Test [DEFAULT] keys of a failed parse don't leak into the next one."""
        parser = ConfidooConfigParser()
        with pytest.raises(ConfigParseError):
            parser.parse("[DEFAULT]\nfoo = bar\n")
        config = parser.parse("[model:ir.cron]\nactive = False\n")
        assert config.operations[0].fields == {"active": "False"}

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
