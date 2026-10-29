# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Tests for database connection parameters."""

from unittest.mock import patch

import psycopg2
import pytest

from confidoo.db import ConnectionParams, OdooDatabase
from confidoo.exceptions import DatabaseConnectionError


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
