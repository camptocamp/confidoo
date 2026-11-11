# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Configuration parser for Confidoo.

This module provides data models and parsing logic for Confidoo INI configuration files.
"""

from __future__ import annotations

import re
from configparser import ConfigParser
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, ClassVar

from .exceptions import ConfigParseError, InvalidSectionError

if TYPE_CHECKING:
    from collections.abc import Container
    from typing import TextIO


class OperationType(str, Enum):
    """Types of configuration operations."""

    MODEL = "model"
    RECORD = "record"
    CONFIG = "config"
    SQL = "sql"


# Section pattern: [type:identifier]
SECTION_PATTERN = re.compile(
    rf"^(?P<type>{'|'.join(t.value for t in OperationType)}):(?P<identifier>.+)$"
)


@dataclass(slots=True, frozen=True)
class ConfigOperation:
    """Base class for configuration operations.

    Represents a single section in the INI file with its type,
    identifier, and field values.
    """

    operation_type: ClassVar[OperationType]

    # Special section attributes this operation supports, mapped to the
    # dataclass field they set. E.g. {"_table": "table"}
    attributes: ClassVar[dict[str, str]] = {}

    # Special section attributes that must be set
    required_attributes: ClassVar[frozenset[str]] = frozenset()

    identifier: str
    fields: dict[str, str | None]

    def __post_init__(self) -> None:
        """Validate operation data."""
        if not self.identifier:  # pragma: no cover
            msg = f"Operation identifier cannot be empty for {self.operation_type}"
            raise ValueError(msg)
        self._validate()

    def _validate(self) -> None:
        """Validate operation-specific data. Override in subclasses."""

    def __str__(self) -> str:
        return f"{self.operation_type.value}:{self.identifier}"


@dataclass(slots=True, frozen=True)
class TableOperation(ConfigOperation):
    """Base class for operations that update a model's table.

    The table name is inferred from the model name, unless set with the
    ``_table`` attribute.
    """

    attributes: ClassVar[dict[str, str]] = {"_table": "table"}

    table: str | None = None


@dataclass(slots=True, frozen=True)
class ModelOperation(TableOperation):
    """Model-wide configuration operation.

    Example: [model:ir.mail_server]
    """

    operation_type: ClassVar[OperationType] = OperationType.MODEL


@dataclass(slots=True, frozen=True)
class RecordOperation(TableOperation):
    """Record-specific configuration operation.

    Example: [record:customer_module.sftp_server]
    """

    operation_type: ClassVar[OperationType] = OperationType.RECORD


@dataclass(slots=True, frozen=True)
class ConfigParamOperation(ConfigOperation):
    """System parameter configuration operation.

    Example: [config:set_param]
    """

    operation_type: ClassVar[OperationType] = OperationType.CONFIG


@dataclass(slots=True, frozen=True)
class SqlOperation(ConfigOperation):
    """Raw SQL query operation.

    The query is stored in the ``_query`` attribute, and every other key is
    a named query parameter, referenced in the query as ``%(name)s``.

    The query is passed to psycopg2 as is, so psycopg2's parameter rules
    apply: as ``%`` starts a placeholder, a literal ``%`` must be written
    ``%%`` (e.g. ``LIKE 'foo%%'``).

    Example: [sql:set-endpoint-apikey]
    """

    operation_type: ClassVar[OperationType] = OperationType.SQL
    attributes: ClassVar[dict[str, str]] = {"_query": "query"}
    required_attributes: ClassVar[frozenset[str]] = frozenset({"_query"})

    # A '%' in the query: an escaped literal '%%', a %(name)s placeholder
    # (invalid without the trailing 's', e.g. %(name)d), or (no group
    # matched) an invalid bare '%'. Names have no whitespace, so an unclosed
    # '%(' doesn't run on into the rest of the query
    percent_pattern: ClassVar[re.Pattern[str]] = re.compile(
        r"%(?:(?P<escaped>%)|\((?P<name>[^)\s]*)\)(?P<conversion>s)?)?"
    )

    query: str

    def _validate(self) -> None:
        """Validate the query and its parameters.

        Every placeholder must be named, unquoted and have a parameter, every
        parameter must be used, and any literal ``%`` must be escaped as ``%%``.

        Raises:
            InvalidSectionError: If the query doesn't match its parameters
        """
        section = repr(str(self))
        placeholders: set[str] = set()
        for match in self.percent_pattern.finditer(self.query):
            name = match["name"]
            if match["escaped"]:
                continue
            if name is None:
                msg = (
                    f"Invalid '%' in query of section: {section}. "
                    f"Use %(name)s for parameters, and %% for a literal '%'."
                )
                raise InvalidSectionError(msg)
            if match["conversion"] is None:
                found = self.query[match.start() : match.end() + 1]
                msg = (
                    f"Invalid query parameter {found} in section: {section}. "
                    f"Placeholders must end in 's' (%({name})s), whatever the "
                    f"value's type."
                )
                raise InvalidSectionError(msg)
            if not name:
                msg = f"Empty query parameter name %()s in section: {section}"
                raise InvalidSectionError(msg)
            # psycopg2 quotes values itself: a quoted placeholder ends up outside
            # the string literal, e.g. '%(x)s' -> ''value''
            before = self.query[match.start() - 1 : match.start()]
            after = self.query[match.end() : match.end() + 1]
            if before in ("'", '"') or after in ("'", '"'):
                msg = (
                    f"Quoted query parameter {match[0]} in section: {section}. "
                    f"Remove the quotes: values are quoted automatically."
                )
                raise InvalidSectionError(msg)
            placeholders.add(name)

        if undefined := sorted(placeholders - self.fields.keys()):
            msg = (
                f"Undefined query parameter(s) {', '.join(undefined)} in section: "
                f"{section}."
            )
            # INI keys are lowercased, so a name with uppercase can't be defined
            if any(name != name.lower() for name in undefined):
                msg += " Parameter names must be lowercase."
            raise InvalidSectionError(msg)

        if unused := sorted(self.fields.keys() - placeholders):
            msg = (
                f"Unused query parameter(s) {', '.join(unused)} in section: "
                f"{section}. Reference them in the query as %(name)s."
            )
            raise InvalidSectionError(msg)


# Operation class for each section type
OPERATION_CLASSES: dict[OperationType, type[ConfigOperation]] = {
    cls.operation_type: cls
    for cls in (ModelOperation, RecordOperation, ConfigParamOperation, SqlOperation)
}


@dataclass(slots=True)
class ParsedConfig:
    """Container for parsed configuration.

    Maintains insertion order of operations as they appear in the config file.
    This is critical for ensuring rules are applied in the correct sequence.
    """

    operations: list[ConfigOperation] = field(default_factory=list)

    def add_operation(self, operation: ConfigOperation) -> None:
        """Add an operation to the configuration."""
        self.operations.append(operation)

    def __iter__(self):
        """Iterate over operations in insertion order."""
        return iter(self.operations)

    def __len__(self) -> int:
        """Return number of operations."""
        return len(self.operations)


class ConfidooConfigParser:
    """Parser for Confidoo INI configuration files.

    Parses INI files with special section syntax:
    - [model:model_name] - Model-wide settings
    - [record:xml_id] - Record-specific settings
    - [config:set_param] - System parameter settings
    - [sql:identifier] - Raw SQL query

    Preserves section order as they appear in the file.
    """

    def parse(self, content: str) -> ParsedConfig:
        """Parse configuration from a string.

        Args:
            content: INI configuration content

        Returns:
            ParsedConfig object with ordered operations

        Raises:
            ConfigParseError: If the content is invalid INI format, or has
                [DEFAULT] keys
            InvalidSectionError: If section syntax is invalid
        """
        ini = ConfigParser(
            # Disable variable interpolation
            interpolation=None,
            # Support empty values (e.g., param =)
            allow_no_value=True,
        )
        try:
            ini.read_string(content)
        except Exception as e:
            msg = f"Failed to parse INI content: {e}"
            raise ConfigParseError(msg) from e

        # ConfigParser merges [DEFAULT] keys into every section, where they
        # would become fields, parameters or query parameters
        if defaults := ini.defaults():
            msg = (
                f"[{ini.default_section}] sections aren't supported, "
                f"found keys: {', '.join(defaults)}"
            )
            raise ConfigParseError(msg)

        return self._build_config(ini)

    def parse_file(self, file: TextIO) -> ParsedConfig:
        """Parse configuration from a file object.

        Args:
            file: File-like object containing INI configuration

        Returns:
            ParsedConfig object with ordered operations

        Raises:
            ConfigParseError: If the content is invalid INI format
            InvalidSectionError: If section syntax is invalid
        """
        return self.parse(file.read())

    def _build_config(self, ini: ConfigParser) -> ParsedConfig:
        """Build ParsedConfig from the internal ConfigParser.

        Operations are processed in the order they appear in the file.
        ConfigParser maintains insertion order since Python 3.7.
        """
        config = ParsedConfig()

        for section_name in ini.sections():
            operation = self._parse_section(ini, section_name)
            config.add_operation(operation)

        return config

    def _parse_section(self, ini: ConfigParser, section_name: str) -> ConfigOperation:
        """Parse a single section.

        Args:
            ini: INI parser holding the section
            section_name: Raw section name from INI file

        Returns:
            Appropriate ConfigOperation subclass instance

        Raises:
            InvalidSectionError: If section name doesn't match expected pattern
        """
        match = SECTION_PATTERN.match(section_name)
        if not match:
            msg = (
                f"Invalid section name: {section_name!r}. "
                f"Expected format: [type:identifier] where type is one of: "
                f"{', '.join(t.value for t in OperationType)}"
            )
            raise InvalidSectionError(msg)

        operation_type = OperationType(match.group("type"))
        identifier = match.group("identifier").strip()

        if not identifier:
            msg = f"Empty identifier in section: {section_name!r}"
            raise InvalidSectionError(msg)

        # Extract fields and the operation's special attributes
        operation_class = OPERATION_CLASSES[operation_type]
        fields, attrs = self._extract_fields(
            ini, section_name, operation_class.attributes
        )

        if missing := sorted(operation_class.required_attributes - attrs.keys()):
            msg = f"Missing {', '.join(missing)} attribute in section: {section_name!r}"
            raise InvalidSectionError(msg)

        kwargs = {
            operation_class.attributes[key]: value for key, value in attrs.items()
        }
        return operation_class(identifier=identifier, fields=fields, **kwargs)

    def _extract_fields(
        self, ini: ConfigParser, section_name: str, attributes: Container[str]
    ) -> tuple[dict[str, str | None], dict[str, str]]:
        """Extract fields and special attributes from a section.

        Args:
            ini: INI parser holding the section
            section_name: Section name to extract fields from
            attributes: Special attributes supported by the section's operation.
                Any other key, even starting with ``_``, is a regular field

        Returns:
            Tuple of (fields_dict, attrs_dict)
            - fields_dict: Regular fields (excludes special attributes)
            - attrs_dict: Special attributes that are set

        Raises:
            InvalidSectionError: If a special attribute is empty
        """
        fields: dict[str, str | None] = {}
        attrs: dict[str, str] = {}

        for key, raw_value in ini.items(section_name):
            # None or blank value means empty assignment (e.g., "field =")
            value = (raw_value or "").strip() or None

            if key not in attributes:
                # Regular fields store None to unset parameters
                fields[key] = value
            elif value is None:
                msg = f"{key} attribute cannot be empty in section: {section_name!r}"
                raise InvalidSectionError(msg)
            else:
                attrs[key] = value

        return fields, attrs


def parse_config(content: str) -> ParsedConfig:
    """Parse a Confidoo configuration string.

    Convenience function for one-off parsing.

    Args:
        content: INI configuration content

    Returns:
        ParsedConfig object with ordered operations

    Raises:
        ConfigParseError: If the content is invalid
        InvalidSectionError: If section syntax is invalid
    """
    parser = ConfidooConfigParser()
    return parser.parse(content)


def parse_config_file(file: TextIO) -> ParsedConfig:
    """Parse a Confidoo configuration file.

    Convenience function for one-off parsing.

    Args:
        file: File-like object containing INI configuration

    Returns:
        ParsedConfig object with ordered operations

    Raises:
        ConfigParseError: If the content is invalid
        InvalidSectionError: If section syntax is invalid
    """
    parser = ConfidooConfigParser()
    return parser.parse_file(file)
