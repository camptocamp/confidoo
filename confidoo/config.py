# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Configuration parser for Confidoo.

This module provides data models and parsing logic for Confidoo INI configuration files.
"""

from __future__ import annotations

import re
from configparser import ConfigParser, DuplicateOptionError
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from .exceptions import ConfigParseError, InvalidSectionError

if TYPE_CHECKING:
    from re import Match, Pattern
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


class _SectionOccurrenceMatch:
    """Section header match whose ``header`` group is a unique internal name.

    Wraps the real :class:`re.Match` produced by ``ConfigParser.SECTCRE`` and
    only overrides the ``header`` group, which is what ``ConfigParser`` uses as
    the section name.
    """

    __slots__ = ("_match", "_header")

    def __init__(self, match: Match[str], header: str) -> None:
        self._match = match
        self._header = header

    def group(self, *groups: int | str) -> Any:
        if len(groups) == 1 and groups[0] == "header":
            return self._header
        return self._match.group(*groups)  # pragma: no cover

    def __getattr__(self, name: str) -> Any:  # pragma: no cover
        return getattr(self._match, name)


class _SectionOccurrenceRegex:
    """Stand-in for ``ConfigParser.SECTCRE`` that gives each header occurrence
    a unique internal name.

    ``ConfigParser`` only calls ``SECTCRE.match()`` on lines it has already
    decided are not continuation lines, so section headers are recognised
    exactly as ``ConfigParser`` itself would recognise them. Values and
    continuation lines containing brackets are never touched.
    """

    __slots__ = ("_pattern", "_parser")

    def __init__(self, pattern: Pattern[str], parser: _OrderedSectionsParser) -> None:
        self._pattern = pattern
        self._parser = parser

    def match(
        self, string: str, *args: Any
    ) -> _SectionOccurrenceMatch | Match[str] | None:
        match = self._pattern.match(string, *args)
        if match is None:
            return None
        header = match.group("header")
        # Leave [DEFAULT] handling untouched
        if header == self._parser.default_section:
            return match
        return _SectionOccurrenceMatch(match, self._parser._register_section(header))

    def __getattr__(self, name: str) -> Any:  # pragma: no cover
        return getattr(self._pattern, name)


class _OrderedSectionsParser(ConfigParser):
    """``ConfigParser`` that keeps every occurrence of a section separately.

    The stock ``ConfigParser`` either rejects repeated sections (``strict=True``)
    or merges them into a single section (``strict=False``), which would lose
    the file order and silently override keys. Instead, while reading, each
    section header occurrence is stored under a unique internal name, and the
    real name can be recovered with :meth:`real_section_name`.

    Since every occurrence is its own internal section, ``strict`` mode still
    rejects duplicate keys within a single occurrence.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._real_section_names: dict[str, str] = {}

    def _register_section(self, real_name: str) -> str:
        """Register a new occurrence of a section and return its internal name."""
        internal_name = f"{real_name}\x00{len(self._real_section_names)}"
        self._real_section_names[internal_name] = real_name
        return internal_name

    def real_section_name(self, section: str) -> str:
        """Return the section name as written in the configuration file."""
        return self._real_section_names.get(section, section)

    def clear(self) -> None:
        super().clear()
        self._real_section_names = {}

    def _read(self, fp: Any, fpname: str) -> None:
        # Only hook the section regex while reading, so that any other usage of
        # SECTCRE (e.g. key validation when writing) keeps the stock behaviour.
        sectcre = _SectionOccurrenceRegex(type(self).SECTCRE, self)
        self.SECTCRE = sectcre  # ty: ignore[invalid-assignment]
        try:
            super()._read(fp, fpname)  # ty: ignore[unresolved-attribute]
        except DuplicateOptionError as e:
            # Report the real section name instead of the internal one
            raise DuplicateOptionError(
                self.real_section_name(e.section), e.option, e.source, e.lineno
            ) from None
        finally:
            del self.SECTCRE


class ConfidooConfigParser:
    """Parser for Confidoo INI configuration files.

    Parses INI files with special section syntax:
    - [model:model_name] - Model-wide settings
    - [record:xml_id] - Record-specific settings
    - [config:set_param] - System parameter settings

    Preserves section order as they appear in the file. Sections may be
    repeated: each occurrence becomes its own operation, in file order.
    """

    def __init__(self) -> None:
        """Initialize the parser."""
        self._parser = _OrderedSectionsParser(
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
        ConfigParser maintains insertion order since Python 3.7, and repeated
        sections are kept as separate (internally renamed) sections.
        """
        config = ParsedConfig()

        for internal_name in self._parser.sections():
            operation = self._parse_section(internal_name)
            config.add_operation(operation)

        return config

    def _parse_section(self, internal_name: str) -> ConfigOperation:
        """Parse a single section occurrence.

        Args:
            internal_name: Internal (unique) name of the section occurrence

        Returns:
            Appropriate ConfigOperation subclass instance

        Raises:
            InvalidSectionError: If section name doesn't match expected pattern
        """
        section_name = self._parser.real_section_name(internal_name)
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
        fields, table = self._extract_fields(internal_name, section_name)

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
        self, internal_name: str, section_name: str
    ) -> tuple[dict[str, str | None], str | None]:
        """Extract fields and table attribute from a section occurrence.

        Args:
            internal_name: Internal (unique) name of the section occurrence
            section_name: Section name as written in the file (for error messages)

        Returns:
            Tuple of (fields_dict, table_name)
            - fields_dict: Regular fields (excludes _table)
            - table_name: Value of _table attribute, or None if not specified
        """
        fields: dict[str, str | None] = {}
        table: str | None = None

        for key, value in self._parser.items(internal_name):
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
