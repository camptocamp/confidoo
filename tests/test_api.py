# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Tests for Confidoo API (programmatic usage)."""

from contextlib import contextmanager
from pathlib import Path
from textwrap import dedent

import psycopg2
import pytest

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
    with pytest.raises(psycopg2.errors.UndefinedTable) as exc_info:
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


def test_advisory_lock_acquired_and_released(odoo_db):
    """Test that an advisory lock is acquired and released during apply."""
    from unittest.mock import patch

    cursor, db_params = odoo_db
    config_content = dedent(
        """
        [model:ir.cron]
        active = False
        """
    )

    advisory_calls = []

    # Intercept cursor.execute to capture advisory lock SQL calls.
    # We patch OdooDatabase.advisory_lock to spy on the SQL actually sent
    # to the database by wrapping the real implementation.
    from confidoo.db import OdooDatabase

    real_advisory_lock = OdooDatabase.advisory_lock

    @contextmanager
    def spy_advisory_lock(self, name):
        # Record acquire call
        advisory_calls.append(("acquire", name))
        try:
            with real_advisory_lock(self, name):
                yield
        finally:
            # Record release call
            advisory_calls.append(("release", name))

    with patch.object(OdooDatabase, "advisory_lock", spy_advisory_lock):
        Confidoo.apply_config(
            database=db_params["database"],
            user=db_params["user"],
            password=db_params["password"],
            host=db_params["host"],
            port=db_params["port"],
            config_content=config_content,
        )

    assert len(advisory_calls) == 2, (
        f"Expected 2 advisory lock calls, got: {advisory_calls}"
    )
    assert advisory_calls[0] == ("acquire", f"confidoo/{db_params['database']}")
    assert advisory_calls[1] == ("release", f"confidoo/{db_params['database']}")
