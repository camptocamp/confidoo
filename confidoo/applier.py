"""Apply parsed configuration to Odoo database."""

from typing import Any, Optional

from .parser import ParsedConfig


def apply_config(
    config: ParsedConfig,
    env: Any,
    raise_on_error: bool = True,
) -> None:
    """Apply parsed configuration to an Odoo environment.

    Args:
        config: Parsed configuration from parse_config().
        env: Odoo environment (odoo.api.Environment).
        raise_on_error: If True, raise exceptions on errors.
            If False, log warnings and continue.

    Raises:
        ValueError: If a model, record, or field is not found and raise_on_error is True.
    """
    # Apply model-wide configurations
    for model_config in config.models:
        _apply_model_config(env, model_config.model_name, model_config.field_values, raise_on_error)

    # Apply record-specific configurations
    for record_config in config.records:
        _apply_record_config(env, record_config.xml_id, record_config.field_values, raise_on_error)

    # Apply config parameters
    for param in config.config_params:
        _apply_config_param(env, param.key, param.value, raise_on_error)


def _apply_model_config(
    env: Any,
    model_name: str,
    field_values: dict,
    raise_on_error: bool,
) -> None:
    """Apply configuration to all records of a model."""
    if model_name not in env:
        if raise_on_error:
            raise ValueError(f"Model not found: {model_name}")
        return

    model = env[model_name]

    # Validate fields exist
    for field_name in field_values:
        if field_name not in model._fields:
            if raise_on_error:
                raise ValueError(f"Field '{field_name}' not found in model '{model_name}'")
            return

    # Apply to all records
    records = model.search([])
    if records:
        records.write(field_values)


def _apply_record_config(
    env: Any,
    xml_id: str,
    field_values: dict,
    raise_on_error: bool,
) -> None:
    """Apply configuration to a specific record by XML ID."""
    record = env.ref(xml_id, raise_if_not_found=False)

    if record is None:
        if raise_on_error:
            raise ValueError(f"Record not found: {xml_id}")
        return

    # Validate fields exist
    for field_name in field_values:
        if field_name not in record._fields:
            if raise_on_error:
                raise ValueError(f"Field '{field_name}' not found for record '{xml_id}'")
            return

    record.write(field_values)


def _apply_config_param(
    env: Any,
    key: str,
    value: str,
    raise_on_error: bool,
) -> None:
    """Apply a config parameter using ir.config_parameter."""
    try:
        env["ir.config_parameter"].set_param(key, value)
    except Exception as e:
        if raise_on_error:
            raise ValueError(f"Failed to set config parameter '{key}': {e}") from e
