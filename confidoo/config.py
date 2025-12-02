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
from typing import TYPE_CHECKING

from .exceptions import ConfigParseError, InvalidSectionError

if TYPE_CHECKING:
    from typing import TextIO


# Section pattern: [type:identifier]
SECTION_PATTERN = re.compile(r"^(?P<type>model|record|config):(?P<identifier>.+)$")

# Reserved field name for custom table specification
RESERVED_TABLE_FIELD = "_table"


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

    operation_type: OperationType
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

    def __init__(
        self, identifier: str, fields: dict[str, str | None], table: str | None = None
    ) -> None:
        object.__setattr__(self, "operation_type", OperationType.MODEL)
        object.__setattr__(self, "identifier", identifier)
        object.__setattr__(self, "fields", fields)
        object.__setattr__(self, "table", table)
        self.__post_init__()


@dataclass(slots=True, frozen=True)
class RecordOperation(ConfigOperation):
    """Record-specific configuration operation.

    Example: [record:customer_module.sftp_server]
    """

    def __init__(
        self, identifier: str, fields: dict[str, str | None], table: str | None = None
    ) -> None:
        object.__setattr__(self, "operation_type", OperationType.RECORD)
        object.__setattr__(self, "identifier", identifier)
        object.__setattr__(self, "fields", fields)
        object.__setattr__(self, "table", table)
        self.__post_init__()


@dataclass(slots=True, frozen=True)
class ConfigParamOperation(ConfigOperation):
    """System parameter configuration operation.

    Example: [config:set_param]
    """

    def __init__(self, identifier: str, fields: dict[str, str | None]) -> None:
        object.__setattr__(self, "operation_type", OperationType.CONFIG)
        object.__setattr__(self, "identifier", identifier)
        object.__setattr__(self, "fields", fields)
        object.__setattr__(self, "table", None)
        self.__post_init__()


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

        operation_type_str = match.group("type")
        identifier = match.group("identifier").strip()

        if not identifier:
            msg = f"Empty identifier in section: {section_name!r}"
            raise InvalidSectionError(msg)

        # Extract fields and special attributes
        fields, table = self._extract_fields(section_name)

        # Create appropriate operation type
        operation_type = OperationType(operation_type_str)

        if operation_type == OperationType.MODEL:
            return ModelOperation(identifier=identifier, fields=fields, table=table)
        elif operation_type == OperationType.RECORD:
            return RecordOperation(identifier=identifier, fields=fields, table=table)
        elif operation_type == OperationType.CONFIG:
            if table is not None:
                msg = f"Config sections cannot have _table attribute: {section_name!r}"
                raise InvalidSectionError(msg)
            return ConfigParamOperation(identifier=identifier, fields=fields)
        else:
            # Should never happen due to regex and enum validation
            msg = f"Unknown section type: {operation_type_str}"
            raise InvalidSectionError(msg)

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

        for key, value in self._parser.items(section_name):
            # Handle special _table attribute
            if key == RESERVED_TABLE_FIELD:
                if value is None or value.strip() == "":
                    msg = (
                        f"_table attribute cannot be empty in section: {section_name!r}"
                    )
                    raise InvalidSectionError(msg)
                table = value.strip()
                continue

            # Store regular fields
            # None or empty string value means empty assignment (e.g., "field =")
            # This is used to unset parameters
            if value is None or value.strip() == "":
                fields[key] = None
            else:
                fields[key] = value.strip()

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
