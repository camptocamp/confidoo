# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Tests for Confidoo API (programmatic usage)."""

import logging
from pathlib import Path
from textwrap import dedent

import pytest
from psycopg2 import errorcodes, errors

from confidoo.exceptions import (
    InvalidSectionError,
    XmlIdNotFoundError,
)
from confidoo.main import Confidoo


def test_apply_with_config_content(odoo_db):
    """Test applying configuration using config_content parameter."""
    config_file = Path(__file__).parent / "fixtures" / "test-config-01.ini"
    config_content = config_file.read_text()
    cursor, db_params = odoo_db

    # Apply configuration using Confidoo class
    Confidoo.apply_config(
        database=db_params["database"],
        user=db_params["user"],
        password=db_params["password"],
        host=db_params["host"],
        port=db_params["port"],
        config_content=config_content,
    )

    # 1. Verify base.partner_admin was updated
    cursor.execute(
        """
        SELECT p.name, p.email
        FROM res_partner p
        JOIN ir_model_data imd ON imd.res_id = p.id
        WHERE imd.module = 'base'
        AND imd.name = 'partner_admin'
        AND imd.model = 'res.partner'
        """
    )
    partner_data = cursor.fetchone()
    assert partner_data is not None, "base.partner_admin record not found"
    assert partner_data["name"] == '"Confidoo"'
    assert partner_data["email"] == '"admin@confidoo.com"'

    # 2. Verify config parameters were set
    cursor.execute(
        """
        SELECT key, value FROM ir_config_parameter
        WHERE key IN ('ribbon.name', 'database.uuid')
        ORDER BY key
        """
    )
    config_params = cursor.fetchall()
    assert len(config_params) == 2
    assert config_params[0]["key"] == "database.uuid"
    assert config_params[0]["value"] == '"0000-0000-0000-0000"'
    assert config_params[1]["key"] == "ribbon.name"
    assert config_params[1]["value"] == '"Test"'

    # 3. Verify config parameters were deleted
    cursor.execute(
        """
        SELECT key FROM ir_config_parameter
        WHERE key IN ('database.expiration_reason', 'database.expiration_date')
        """
    )
    deleted_params = cursor.fetchall()
    assert len(deleted_params) == 0

    # 4. Verify ir.cron records were updated
    cursor.execute(
        """
        SELECT active FROM ir_cron
        """
    )
    ir_cron = cursor.fetchall()
    assert len(ir_cron) > 0
    assert all(not cron["active"] for cron in ir_cron)


def test_apply_with_config_file(odoo_db):
    """Test applying configuration using config_path parameter."""
    config_file = Path(__file__).parent / "fixtures" / "test-config-01.ini"
    cursor, db_params = odoo_db

    # Apply configuration using Confidoo class
    Confidoo.apply_config(
        database=db_params["database"],
        user=db_params["user"],
        password=db_params["password"],
        host=db_params["host"],
        port=db_params["port"],
        config_path=config_file,
    )

    # Verify base.partner_admin was updated
    cursor.execute(
        """
        SELECT p.name, p.email
        FROM res_partner p
        JOIN ir_model_data imd ON imd.res_id = p.id
        WHERE imd.module = 'base'
        AND imd.name = 'partner_admin'
        AND imd.model = 'res.partner'
        """
    )
    partner_data = cursor.fetchone()
    assert partner_data is not None, "base.partner_admin record not found"
    assert partner_data["name"] == '"Confidoo"'
    assert partner_data["email"] == '"admin@confidoo.com"'


def test_apply_with_context_manager(odoo_db):
    """Test applying configuration using context manager pattern."""
    config_content = dedent(
        """
        [model:ir.cron]
        active = False
        """
    )
    cursor, db_params = odoo_db

    # Use context manager pattern
    confidoo = Confidoo(
        database=db_params["database"],
        user=db_params["user"],
        password=db_params["password"],
        host=db_params["host"],
        port=db_params["port"],
        config_content=config_content,
    )

    with confidoo.connect():
        confidoo.apply()

    # Verify ir.cron records were updated
    cursor.execute("SELECT active FROM ir_cron")
    ir_cron = cursor.fetchall()
    assert len(ir_cron) > 0
    assert all(not cron["active"] for cron in ir_cron)


def test_apply_with_separate_load(odoo_db):
    """Test applying configuration with separate load_config call."""
    config_content = dedent(
        """
        [model:ir.cron]
        active = False
        """
    )
    cursor, db_params = odoo_db

    # Create instance without config
    confidoo = Confidoo(
        database=db_params["database"],
        user=db_params["user"],
        password=db_params["password"],
        host=db_params["host"],
        port=db_params["port"],
    )

    # Load config separately
    confidoo.load_config(config_content)

    # Apply
    with confidoo.connect():
        confidoo.apply()

    # Verify ir.cron records were updated
    cursor.execute("SELECT active FROM ir_cron")
    ir_cron = cursor.fetchall()
    assert len(ir_cron) > 0
    assert all(not cron["active"] for cron in ir_cron)


def test_apply_with_invalid_config(odoo_db):
    """Test error handling with invalid configuration."""
    __, db_params = odoo_db

    # Invalid section syntax
    with pytest.raises(InvalidSectionError, match="Invalid section name"):
        Confidoo.apply_config(
            database=db_params["database"],
            user=db_params["user"],
            password=db_params["password"],
            host=db_params["host"],
            port=db_params["port"],
            config_content="[invalid_section]\nfield = value\n",
        )


def test_apply_nonexistent_model(odoo_db):
    """Test error handling when applying to non-existent model/table."""
    config_file = (
        Path(__file__).parent / "fixtures" / "test-config-nonexistent-model.ini"
    )
    __, db_params = odoo_db

    # psycopg2 errors propagate directly, not wrapped in DatabaseError
    with pytest.raises(errors.lookup(errorcodes.UNDEFINED_TABLE)) as exc_info:
        Confidoo.apply_config(
            database=db_params["database"],
            user=db_params["user"],
            password=db_params["password"],
            host=db_params["host"],
            port=db_params["port"],
            config_path=config_file,
        )

    # Verify error mentions the table
    error_msg = str(exc_info.value).lower()
    assert (
        "nonexistent_model" in error_msg or "does not exist" in error_msg
    ), f"Error message should mention table: {error_msg}"


def test_apply_nonexistent_xmlid(odoo_db):
    """Test error handling when applying to non-existent XMLID."""
    config_file = (
        Path(__file__).parent / "fixtures" / "test-config-nonexistent-xmlid.ini"
    )
    __, db_params = odoo_db

    with pytest.raises(XmlIdNotFoundError):
        Confidoo.apply_config(
            database=db_params["database"],
            user=db_params["user"],
            password=db_params["password"],
            host=db_params["host"],
            port=db_params["port"],
            config_path=config_file,
        )


def test_apply_empty_identifier(odoo_db):
    """Test error handling when section has empty identifier."""
    __, db_params = odoo_db

    with pytest.raises(InvalidSectionError):
        Confidoo.apply_config(
            database=db_params["database"],
            user=db_params["user"],
            password=db_params["password"],
            host=db_params["host"],
            port=db_params["port"],
            config_content="[model:]\nfield = value\n",
        )


def test_multiple_config_sources_error():
    """Test that providing multiple config sources raises ValueError."""
    with pytest.raises(ValueError, match="Only one of config_content"):
        Confidoo(
            database="testdb",
            user="testuser",
            password="testpass",
            config_content="[model:ir.cron]\nactive = False\n",
            config_path="/path/to/config.ini",
        )


def test_apply_without_config_raises_runtime_error(odoo_db):
    """Test that calling apply() without loading config raises RuntimeError."""
    __, db_params = odoo_db

    confidoo = Confidoo(
        database=db_params["database"],
        user=db_params["user"],
        password=db_params["password"],
        host=db_params["host"],
        port=db_params["port"],
    )

    with confidoo.connect():
        with pytest.raises(RuntimeError, match="No configuration loaded"):
            confidoo.apply()


def test_apply_without_connection_raises_runtime_error():
    """Test that accessing db property without connection raises RuntimeError."""
    confidoo = Confidoo(
        database="testdb",
        user="testuser",
        password="testpass",
        config_content="[model:ir.cron]\nactive = False\n",
    )

    # Accessing db property without connection should raise RuntimeError
    with pytest.raises(RuntimeError, match="No active database connection"):
        _ = confidoo.db


def test_apply_stale_xmlid_warns(odoo_db, caplog):
    """Test that a stale XMLID (pointing to a deleted row) logs a warning."""
    cursor, db_params = odoo_db
    cursor.execute(
        """
        INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
        VALUES ('confidoo_test', 'stale_partner', 'res.partner', 2147483647, true)
        """
    )

    with caplog.at_level(logging.INFO, logger="confidoo.main"):
        Confidoo.apply_config(
            database=db_params["database"],
            user=db_params["user"],
            password=db_params["password"],
            host=db_params["host"],
            port=db_params["port"],
            config_content="[record:confidoo_test.stale_partner]\nname = Ghost\n",
        )

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "confidoo_test.stale_partner" in message
    assert "res.partner,2147483647" in message
    assert "res_partner" in message
    assert not any(r.getMessage() == "✓ Updated" for r in caplog.records)


@pytest.mark.parametrize("config_content", ["", "\n", "   \n\t\n"])
def test_apply_empty_config_warns(odoo_db, caplog, config_content):
    """Test that applying an empty config logs a warning instead of failing."""
    __, db_params = odoo_db

    with caplog.at_level(logging.WARNING, logger="confidoo.main"):
        Confidoo.apply_config(
            database=db_params["database"],
            user=db_params["user"],
            password=db_params["password"],
            host=db_params["host"],
            port=db_params["port"],
            config_content=config_content,
        )

    assert any(
        record.levelno == logging.WARNING and "Nothing to apply" in record.message
        for record in caplog.records
    ), caplog.text


@pytest.mark.parametrize(
    ("config_name", "active"),
    [
        ("test-config-cron-inactive.ini", False),
        ("test-config-cron-active.ini", True),
    ],
)
def test_toggle_cron_active_by_xmlid(odoo_db, config_name, active):
    """Test activating / deactivating a standard ir.cron record by its XMLID."""
    config_file = Path(__file__).parent / "fixtures" / config_name
    cursor, db_params = odoo_db
    query = """
        SELECT c.id, c.active
        FROM ir_cron c
        JOIN ir_model_data imd ON imd.res_id = c.id
        WHERE imd.module = 'base'
        AND imd.name = 'autovacuum_job'
        AND imd.model = 'ir.cron'
    """

    # Start from the opposite state, so the change is actually observable
    cursor.execute(query)
    cron = cursor.fetchone()
    assert cron is not None, "base.autovacuum_job record not found"
    cursor.execute(
        "UPDATE ir_cron SET active = %s WHERE id = %s", (not active, cron["id"])
    )

    Confidoo.apply_config(
        database=db_params["database"],
        user=db_params["user"],
        password=db_params["password"],
        host=db_params["host"],
        port=db_params["port"],
        config_path=config_file,
    )

    cursor.execute(query)
    assert cursor.fetchone()["active"] is active
