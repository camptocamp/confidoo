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
    from typing import TextIO


# Section pattern: [type:identifier]
SECTION_PATTERN = re.compile(r"^(?P<type>model|record|config):(?P<identifier>.+)$")

# Identifier of a record section selecting by field: model:column=value
# (an XMLID contains neither ':' nor '=', so the two forms are distinct)
FIELD_IDENTIFIER_PATTERN = re.compile(
    r"^(?P<model>[^:=\s]+):(?P<column>[^:=\s]+)=(?P<value>.+)$"
)

# Reserved field name for custom table specification
RESERVED_TABLE_FIELD = "_table"

# Reserved field name for the behaviour of record sections when the record is missing
RESERVED_ON_MISSING_FIELD = "_on_missing"

# Allowed _on_missing values: fail (raise, roll back everything; the default) or
# warning (log a warning and go on)
ON_MISSING_CHOICES = ("fail", "warning")
DEFAULT_ON_MISSING = "fail"


class OperationType(str, Enum):
    """Types of configuration operations."""

    MODEL = "model"
    RECORD = "record"
    CONFIG = "config"


@dataclass(slots=True, frozen=True)
class ConfigOperation:
    """Base class for configuration operations.

    Represents a single section in the INI file with its type,
    identifier, and field values.
    """

    operation_type: ClassVar[OperationType]

    identifier: str
    fields: dict[str, str | None]
    table: str | None = None

    def __post_init__(self) -> None:
        """Validate operation data."""
        if not self.identifier:  # pragma: no cover
            msg = f"Operation identifier cannot be empty for {self.operation_type}"
            raise ValueError(msg)

    def __str__(self) -> str:
        return f"{self.operation_type.value}:{self.identifier}"


@dataclass(slots=True, frozen=True)
class ModelOperation(ConfigOperation):
    """Model-wide configuration operation.

    Example: [model:ir.mail_server]
    """

    operation_type: ClassVar[OperationType] = OperationType.MODEL


@dataclass(slots=True, frozen=True)
class RecordOperation(ConfigOperation):
    """Record-specific configuration operation.

    Example: [record:customer_module.sftp_server]
    """

    operation_type: ClassVar[OperationType] = OperationType.RECORD

    # What to do when the XMLID cannot be resolved: see ON_MISSING_CHOICES
    on_missing: str = DEFAULT_ON_MISSING


@dataclass(slots=True, frozen=True)
class FieldOperation(ConfigOperation):
    """Record configuration operation selecting the record by a unique field.

    The identifier is ``model:column=value``, e.g.
    [record:res.partner:tech_name=my_partner] updates the record of
    ``res.partner`` whose ``tech_name`` column equals ``my_partner``.
    """

    operation_type: ClassVar[OperationType] = OperationType.RECORD

    # What to do when no record matches: see ON_MISSING_CHOICES
    on_missing: str = DEFAULT_ON_MISSING

    def __post_init__(self) -> None:
        """Validate operation data, including the identifier format."""
        ConfigOperation.__post_init__(self)
        if not FIELD_IDENTIFIER_PATTERN.match(self.identifier):
            msg = (
                f"Invalid field identifier: {self.identifier!r}. "
                f"Expected format: [record:model:column=value]"
            )
            raise InvalidSectionError(msg)

    @property
    def model(self) -> str:
        """Odoo model name of the targeted record."""
        return self._match().group("model")

    @property
    def column(self) -> str:
        """Column used to select the record."""
        return self._match().group("column")

    @property
    def value(self) -> str:
        """Value the column must match."""
        return self._match().group("value")

    def _match(self) -> re.Match[str]:
        match = FIELD_IDENTIFIER_PATTERN.match(self.identifier)
        assert match is not None  # validated in __post_init__
        return match


@dataclass(slots=True, frozen=True)
class ConfigParamOperation(ConfigOperation):
    """System parameter configuration operation.

    Example: [config:set_param]
    """

    operation_type: ClassVar[OperationType] = OperationType.CONFIG


# Operation class for each section type (FieldOperation is a record section too,
# picked by the parser from the identifier format)
OPERATION_CLASSES: dict[OperationType, type[ConfigOperation]] = {
    cls.operation_type: cls
    for cls in (ModelOperation, RecordOperation, ConfigParamOperation)
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
    - [record:model:column=value] - Record selected by a unique field
    - [config:set_param] - System parameter settings

    Preserves section order as they appear in the file.
    """

    def __init__(self) -> None:
        """Initialize the parser."""
        self._parser = ConfigParser(
            # Disable variable interpolation
            interpolation=None,
            # Support empty values (e.g., param =)
            allow_no_value=True,
        )

    def parse(self, content: str) -> ParsedConfig:
        """Parse configuration from a string.

        Args:
            content: INI configuration content

        Returns:
            ParsedConfig object with ordered operations

        Raises:
            ConfigParseError: If the content is invalid INI format
            InvalidSectionError: If section syntax is invalid
        """
        # Clear any previous state to allow parser reusability
        self._parser.clear()

        try:
            self._parser.read_string(content)
        except Exception as e:
            msg = f"Failed to parse INI content: {e}"
            raise ConfigParseError(msg) from e

        return self._build_config()

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

    def _build_config(self) -> ParsedConfig:
        """Build ParsedConfig from the internal ConfigParser.

        Operations are processed in the order they appear in the file.
        ConfigParser maintains insertion order since Python 3.7.
        """
        config = ParsedConfig()

        for section_name in self._parser.sections():
            operation = self._parse_section(section_name)
            config.add_operation(operation)

        return config

    def _parse_section(self, section_name: str) -> ConfigOperation:
        """Parse a single section.

        Args:
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
                f"model, record, config"
            )
            raise InvalidSectionError(msg)

        operation_type = OperationType(match.group("type"))
        identifier = match.group("identifier").strip()

        if not identifier:
            msg = f"Empty identifier in section: {section_name!r}"
            raise InvalidSectionError(msg)

        # Extract fields and special attributes
        fields, table = self._extract_fields(section_name)

        if operation_type == OperationType.CONFIG and table is not None:
            msg = f"Config sections cannot have _table attribute: {section_name!r}"
            raise InvalidSectionError(msg)

        operation_class = OPERATION_CLASSES[operation_type]
        if operation_type == OperationType.RECORD:
            on_missing = fields.pop(RESERVED_ON_MISSING_FIELD, None)
            on_missing = on_missing or DEFAULT_ON_MISSING
            if on_missing not in ON_MISSING_CHOICES:
                msg = (
                    f"Invalid {RESERVED_ON_MISSING_FIELD} value {on_missing!r} in "
                    f"section {section_name!r}. "
                    f"Expected one of: {', '.join(ON_MISSING_CHOICES)}"
                )
                raise InvalidSectionError(msg)
            if FIELD_IDENTIFIER_PATTERN.match(identifier):
                record_class: type[RecordOperation | FieldOperation] = FieldOperation
            elif ":" in identifier or "=" in identifier:
                msg = (
                    f"Invalid record identifier: {identifier!r}. Expected an XMLID "
                    f"or model:column=value in section {section_name!r}"
                )
                raise InvalidSectionError(msg)
            else:
                record_class = RecordOperation
            return record_class(
                identifier=identifier,
                fields=fields,
                table=table,
                on_missing=on_missing,
            )
        if RESERVED_ON_MISSING_FIELD in fields:
            msg = (
                f"{RESERVED_ON_MISSING_FIELD} is only supported in record sections: "
                f"{section_name!r}"
            )
            raise InvalidSectionError(msg)
        return operation_class(identifier=identifier, fields=fields, table=table)

    def _extract_fields(
        self, section_name: str
    ) -> tuple[dict[str, str | None], str | None]:
        """Extract fields and table attribute from a section.

        Args:
            section_name: Section name to extract fields from

        Returns:
            Tuple of (fields_dict, table_name)
            - fields_dict: Regular fields (excludes _table)
            - table_name: Value of _table attribute, or None if not specified
        """
        fields: dict[str, str | None] = {}
        table: str | None = None

        for key, raw_value in self._parser.items(section_name):
            # None or blank value means empty assignment (e.g., "field =")
            value = (raw_value or "").strip() or None

            # Handle special _table attribute
            if key == RESERVED_TABLE_FIELD:
                if value is None:
                    msg = (
                        f"_table attribute cannot be empty in section: {section_name!r}"
                    )
                    raise InvalidSectionError(msg)
                table = value
                continue

            # Store regular fields. None is used to unset parameters
            fields[key] = value

        return fields, table


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
