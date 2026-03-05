# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Tests for Confidoo API (programmatic usage)."""

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


def test_advisory_lock_prevents_concurrent_apply(db_params, real_db_connect):
    """Session A acquires the lock and applies its config; session B waits.

    This verifies that concurrent Confidoo callers serialize correctly:
    - Session A (thread) acquires the advisory lock and begins applying.
    - Session B (thread) calls apply_config() and is blocked while A holds the lock.
    - After A commits and releases the lock, B proceeds and applies its config.
    - The database state reflects both applies, each applied exactly once and
      without any concurrent interleaving.
    """
    import threading
    import time
    from unittest.mock import patch

    # How long to wait for threads and events to complete/occur.
    THREAD_TIMEOUT = 10
    # How long to wait after starting B before asserting it is blocked.
    # A single pg_advisory_xact_lock call over a local TCP connection takes
    # well under 100 ms, so 2 seconds is more than enough margin for CI.
    BLOCK_SETTLE_SECONDS = 2

    PARAM_A = "confidoo.test.session_a"
    PARAM_B = "confidoo.test.session_b"

    config_a = dedent(f"""
        [config:set_param]
        {PARAM_A} = set_by_a
    """)
    config_b = dedent(f"""
        [config:set_param]
        {PARAM_B} = set_by_b
    """)

    # Delete any leftover keys from previous test runs.
    cleanup_conn = real_db_connect(**db_params)
    cleanup_cr = cleanup_conn.cursor()
    cleanup_cr.execute(
        "DELETE FROM ir_config_parameter WHERE key = ANY(%s)",
        ([PARAM_A, PARAM_B],),
    )
    cleanup_conn.commit()
    cleanup_cr.close()
    cleanup_conn.close()

    # Create session A's Confidoo instance and inject a delay *inside* the
    # locked section so session B is guaranteed to block.
    instance_a = Confidoo(
        database=db_params["database"],
        user=db_params["user"],
        password=db_params["password"],
        host=db_params["host"],
        port=db_params["port"],
        config_content=config_a,
    )
    original_apply_op = instance_a._apply_operation
    op_started = threading.Event()
    op_can_continue = threading.Event()

    def slow_apply_op(operation):
        # Signal the main thread that we are inside the locked section.
        op_started.set()
        # Block until the main thread tells us to proceed.
        op_can_continue.wait(timeout=THREAD_TIMEOUT)
        return original_apply_op(operation)

    # Patch the instance (not the class) so only session A is slowed down.
    instance_a._apply_operation = slow_apply_op

    a_finished = threading.Event()
    b_finished = threading.Event()
    a_errors: list = []
    b_errors: list = []

    def run_session_a():
        try:
            with instance_a.connect():
                instance_a.apply()
        except Exception as exc:
            a_errors.append(exc)
        finally:
            a_finished.set()

    def run_session_b():
        try:
            Confidoo.apply_config(
                database=db_params["database"],
                user=db_params["user"],
                password=db_params["password"],
                host=db_params["host"],
                port=db_params["port"],
                config_content=config_b,
            )
        except Exception as exc:
            b_errors.append(exc)
        finally:
            b_finished.set()

    # Both threads must run while psycopg2.connect is the *real* function
    # (the odoo_db fixture may have replaced it with a shared-connection mock).
    with patch("psycopg2.connect", real_db_connect):
        # Start A and wait until it has the lock and is inside slow_apply_op.
        thread_a = threading.Thread(target=run_session_a, daemon=True)
        thread_a.start()
        assert op_started.wait(timeout=THREAD_TIMEOUT), (
            "Session A never entered the locked section"
        )

        # Now start B — it will try to acquire the same advisory lock and block.
        thread_b = threading.Thread(target=run_session_b, daemon=True)
        thread_b.start()
        # Allow B enough time to connect and attempt pg_advisory_xact_lock.
        time.sleep(BLOCK_SETTLE_SECONDS)

        # Session B must still be blocked (A holds the lock).
        assert not b_finished.is_set(), (
            "Session B should be blocked waiting for A's advisory lock"
        )
        # Session A is still in progress (inside the slow operation).
        assert not a_finished.is_set(), "Session A should still be running"

        # Check that B has not written anything to the database yet.
        check_conn = real_db_connect(**db_params)
        check_cr = check_conn.cursor()
        check_cr.execute(
            "SELECT value FROM ir_config_parameter WHERE key = %s", (PARAM_B,)
        )
        assert check_cr.fetchone() is None, (
            "Session B must not write to the database while A holds the lock"
        )
        check_cr.close()
        check_conn.close()

        # Release session A — it commits its transaction and releases the lock.
        op_can_continue.set()
        assert a_finished.wait(timeout=THREAD_TIMEOUT), (
            "Session A did not complete in time"
        )
        assert not a_errors, f"Session A raised: {a_errors}"

        # Session B should now acquire the lock and complete.
        assert b_finished.wait(timeout=THREAD_TIMEOUT), (
            "Session B did not complete in time"
        )
        assert not b_errors, f"Session B raised: {b_errors}"

    # Verify the final database state: each config applied exactly once.
    from psycopg2.extras import RealDictCursor

    verify_conn = real_db_connect(**db_params, cursor_factory=RealDictCursor)
    verify_cr = verify_conn.cursor()
    verify_cr.execute(
        "SELECT key, value FROM ir_config_parameter WHERE key = ANY(%s)",
        ([PARAM_A, PARAM_B],),
    )
    rows = {row["key"]: row["value"] for row in verify_cr.fetchall()}
    assert rows == {PARAM_A: "set_by_a", PARAM_B: "set_by_b"}, (
        f"Unexpected database state: {rows}"
    )
    verify_cr.close()
    verify_conn.close()

    # Cleanup: remove the test keys.
    cleanup_conn = real_db_connect(**db_params)
    cleanup_cr = cleanup_conn.cursor()
    cleanup_cr.execute(
        "DELETE FROM ir_config_parameter WHERE key = ANY(%s)",
        ([PARAM_A, PARAM_B],),
    )
    cleanup_conn.commit()
    cleanup_cr.close()
    cleanup_conn.close()

    thread_a.join(timeout=THREAD_TIMEOUT)
    thread_b.join(timeout=THREAD_TIMEOUT)
