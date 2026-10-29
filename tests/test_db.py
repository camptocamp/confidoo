# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Tests for database connection parameters and handling."""

from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from confidoo.db import ConnectionParams, OdooDatabase
from confidoo.exceptions import (
    DatabaseConnectionError,
    NotOdooDatabaseError,
    OdooVersionError,
)


@pytest.mark.parametrize(
    "password",
    ["p@ss word", "it's", "back\\slash", "a=b", "x sslmode=disable", ""],
)
def test_connection_params_to_kwargs(password):
    """Test that special characters are passed through verbatim."""
    params = ConnectionParams(
        database="odoo",
        user="odoo",
        password=password,
        host="db.example.com",
        port=5433,
    )
    assert params.to_kwargs() == {
        "dbname": "odoo",
        "user": "odoo",
        "password": password,
        "host": "db.example.com",
        "port": 5433,
    }


def test_connect_uses_keyword_arguments():
    """Test that psycopg2.connect() receives keyword arguments, not a DSN."""
    params = ConnectionParams(database="odoo", user="odoo", password="p@ss word")
    with (
        patch(
            "psycopg2.connect", side_effect=psycopg2.OperationalError("boom")
        ) as mock_connect,
        pytest.raises(DatabaseConnectionError),
    ):
        OdooDatabase(params).__enter__()
    args, kwargs = mock_connect.call_args
    assert args == ()
    assert kwargs["password"] == "p@ss word"
    assert kwargs["host"] == "localhost"
    assert kwargs["port"] == 5432


def _make_db():
    params = ConnectionParams(database="db", user="user", password="password")
    return OdooDatabase(params)


@pytest.mark.parametrize(
    ("fetchone", "expected_error"),
    [
        # _check_odoo_database fails: not an Odoo database
        ([{"table_exists": False}], NotOdooDatabaseError),
        # _get_odoo_version fails: no base module version
        ([{"table_exists": True}, {"latest_version": None}], OdooVersionError),
        # Any psycopg2 error during the checks gets wrapped
        (psycopg2.OperationalError("boom"), DatabaseConnectionError),
    ],
)
def test_enter_closes_connection_on_error(fetchone, expected_error):
    """Test that a failing __enter__ closes the cursor and connection."""
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.side_effect = fetchone
    db = _make_db()

    with patch("psycopg2.connect", return_value=conn):
        with pytest.raises(expected_error):
            with db:
                pytest.fail("__enter__ should have raised")  # pragma: no cover

    cursor.close.assert_called_once()
    conn.close.assert_called_once()
    assert db._cr is None
    assert db._conn is None


def test_enter_cleanup_errors_do_not_mask_original():
    """Test that errors while closing don't hide the original exception."""
    conn = MagicMock()
    conn.close.side_effect = psycopg2.InterfaceError("already closed")
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = {"table_exists": False}
    cursor.close.side_effect = psycopg2.InterfaceError("already closed")
    db = _make_db()

    with patch("psycopg2.connect", return_value=conn):
        with pytest.raises(NotOdooDatabaseError):
            db.__enter__()

    assert db._cr is None
    assert db._conn is None
