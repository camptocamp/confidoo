# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


from unittest.mock import patch

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor

# Capture the real psycopg2.connect at import time, before any test can patch it.
_real_psycopg2_connect = psycopg2.connect


class MockSharedConnection:
    """Wrapper that intercepts commit() and close() for test isolation.

    This wrapper delegates everything to the real connection except:
    - commit(): no-op to keep changes in transaction
    - close(): no-op to keep connection alive for test verification
    """

    def __init__(self, real_conn):
        # Use object.__setattr__ to avoid triggering __setattr__
        object.__setattr__(self, "_real_conn", real_conn)

    def commit(self):
        """No-op commit - don't actually commit, keep changes in transaction."""
        pass

    def close(self):
        """No-op close to keep connection alive for test verification."""
        pass

    def __getattr__(self, name):
        """Delegate all other attributes to the real connection."""
        return getattr(self._real_conn, name)

    def __setattr__(self, name, value):
        """Delegate attribute setting to the real connection."""
        if name == "_real_conn":
            object.__setattr__(self, name, value)
        else:
            setattr(self._real_conn, name, value)

    def __enter__(self):
        """Support context manager protocol."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Support context manager protocol."""
        if exc_type is not None:
            # Exception occurred - rollback
            self._real_conn.rollback()
        # Note: if no exception, we don't commit either - changes stay in transaction
        # Don't close the connection - keep it alive for test verification
        return False


@pytest.fixture(scope="session")
def db_params(docker_ip, docker_services):
    """Return raw database connection parameters (no mocking).

    Use for tests that need real independent connections (e.g., concurrency tests).
    """
    port = docker_services.port_for("db", 5432)
    return {
        "host": docker_ip,
        "port": port,
        "database": "odoo",
        "user": "odoo",
        "password": "odoo",
    }


@pytest.fixture(scope="session")
def real_db_connect():
    """Return the real psycopg2.connect, bypassing any active test mock.

    Captured at import time before any fixture can patch psycopg2.connect.
    """
    return _real_psycopg2_connect


@pytest.fixture(scope="session")
def odoo_db(db_params):
    """Return database connection with parameters after Odoo initialization.

    Docker healthchecks ensure Odoo is ready before this fixture runs.
    Returns a tuple of (connection, db_params) where the connection has commit()
    replaced with rollback() to prevent database pollution between tests.

    All calls to psycopg2.connect() will return the same shared connection,
    ensuring Confidoo and test code see the same transaction.
    """
    # Create the real connection with RealDictCursor (same as Confidoo uses)
    # This ensures cursors return dicts instead of tuples
    real_conn = _real_psycopg2_connect(**db_params, cursor_factory=RealDictCursor)

    # Wrap it to intercept commit
    shared_conn = MockSharedConnection(real_conn)

    def mock_connect(*_args, **_kwargs):
        """Mock connect that always returns the same shared connection wrapper."""
        # Ignore all arguments and always return the shared connection
        return shared_conn

    # Patch psycopg2.connect to use our mock
    with patch("psycopg2.connect", side_effect=mock_connect):
        with shared_conn.cursor() as cursor:
            yield (cursor, db_params)

    # Cleanup: rollback and close
    shared_conn._real_conn.rollback()
    shared_conn._real_conn.close()
