"""Parser for declarative Odoo configuration files.

The configuration file uses an INI-style format with specific section types:

- [model:model_name] - Settings applied to all records of a model
- [record:xml_id] - Settings applied to a specific record by XML ID
- [config:set_param] - Odoo config parameters (ir.config_parameter)
"""

import configparser
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Section type patterns
MODEL_PATTERN = re.compile(r"^model:(.+)$")
RECORD_PATTERN = re.compile(r"^record:(.+)$")
CONFIG_PATTERN = re.compile(r"^config:set_param$")


@dataclass
class ModelConfig:
    """Configuration for all records of a model."""

    model_name: str
    field_values: Dict[str, str] = field(default_factory=dict)


@dataclass
class RecordConfig:
    """Configuration for a specific record by XML ID."""

    xml_id: str
    field_values: Dict[str, str] = field(default_factory=dict)


@dataclass
class ConfigParam:
    """Configuration parameter (ir.config_parameter)."""

    key: str
    value: str


@dataclass
class ParsedConfig:
    """Parsed configuration containing all settings."""

    models: List[ModelConfig] = field(default_factory=list)
    records: List[RecordConfig] = field(default_factory=list)
    config_params: List[ConfigParam] = field(default_factory=list)


def parse_config(config_text: str) -> ParsedConfig:
    """Parse a configuration string into structured settings.

    Args:
        config_text: The configuration text in INI-style format.

    Returns:
        ParsedConfig object containing all parsed settings.

    Raises:
        ValueError: If the configuration contains invalid sections.
    """
    parser = configparser.ConfigParser()
    parser.read_string(config_text)

    result = ParsedConfig()

    for section in parser.sections():
        items = dict(parser.items(section))

        # Check for model section
        model_match = MODEL_PATTERN.match(section)
        if model_match:
            model_name = model_match.group(1)
            result.models.append(ModelConfig(model_name=model_name, field_values=items))
            continue

        # Check for record section
        record_match = RECORD_PATTERN.match(section)
        if record_match:
            xml_id = record_match.group(1)
            result.records.append(RecordConfig(xml_id=xml_id, field_values=items))
            continue

        # Check for config section
        config_match = CONFIG_PATTERN.match(section)
        if config_match:
            for key, value in items.items():
                result.config_params.append(ConfigParam(key=key, value=value))
            continue

        # Unknown section type
        raise ValueError(f"Unknown section type: [{section}]")

    return result


def parse_config_file(file_path: str) -> ParsedConfig:
    """Parse a configuration file.

    Args:
        file_path: Path to the configuration file.

    Returns:
        ParsedConfig object containing all parsed settings.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return parse_config(f.read())
