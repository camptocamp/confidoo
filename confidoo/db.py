# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Database connection and utilities for Confidoo.

This module provides database connection management with transactional support
and Odoo-specific utility methods.
"""

from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError as e:  # pragma: no cover
    msg = (
        "psycopg2 is required but not installed.\n\n"
        "Installation options:\n"
        "1. For source version (if you have PostgreSQL development libraries):\n"
        "   pip install confidoo[psycopg2]\n"
        "   uv pip install confidoo[psycopg2]\n\n"
        "2. For binary version (easier, no dev libs needed):\n"
        "   pip install confidoo[psycopg2-binary]\n"
        "   uv pip install confidoo[psycopg2-binary]\n"
    )
    raise ImportError(msg) from e

from .exceptions import (
    DatabaseConnectionError,
    NotOdooDatabaseError,
    OdooVersionError,
    XmlIdNotFoundError,
)

if TYPE_CHECKING:
    from psycopg2.extensions import connection as Connection
    from psycopg2.extensions import cursor as Cursor

logger = logging.getLogger(__name__)


@dataclass
class ConnectionParams:
    """Database connection parameters."""

    database: str
    user: str
    password: str
    host: str = "localhost"
    port: int = 5432

    def to_dsn(self) -> str:
        """Convert to psycopg2 connection string.

        Returns:
            PostgreSQL connection string (DSN)
        """
        return (
            f"dbname={self.database} "
            f"user={self.user} "
            f"password={self.password} "
            f"host={self.host} "
            f"port={self.port}"
        )

    def __str__(self) -> str:
        return f"{self.database} ({self.user}@{self.host}:{self.port})"


class OdooDatabase:
    """Manages connection to an Odoo PostgreSQL database.

    Provides context manager support for automatic transaction management.
    All operations within the context are part of a single transaction.

    Example:
        >>> params = ConnectionParams(database="odoo", user="odoo", password="odoo")
        >>> with OdooDatabase(params) as db:
        ...     print(f"Odoo version: {db.odoo_version}")
        ...     model, res_id = db.resolve_xmlid("base.user_admin")
        Odoo version: 18.0
    """

    def __init__(self, params: ConnectionParams) -> None:
        """Initialize database connection handler.

        Args:
            params: Database connection parameters
        """
        self.params = params
        self._conn: Connection | None = None
        self._cr: Cursor | None = None
        self.odoo_version: float | None = None

    @property
    def cr(self) -> Cursor:
        """Get the database cursor.

        Returns:
            Active database cursor for executing queries

        Raises:
            RuntimeError: If called outside context manager
        """
        if not self._cr:  # pragma: no cover
            msg = "Database connection not active. Use within context manager."
            raise RuntimeError(msg)
        return self._cr

    def __enter__(self) -> OdooDatabase:
        """Establish connection and verify Odoo database.

        Returns:
            Self instance with active database connection

        Raises:
            DatabaseConnectionError: If connection fails
            NotOdooDatabaseError: If database is not an Odoo database
            OdooVersionError: If Odoo version cannot be determined
        """
        try:
            logger.info("Connecting to database %s...", self.params)

            # Connect to PostgreSQL with dict cursor factory
            self._conn = psycopg2.connect(
                self.params.to_dsn(),
                cursor_factory=RealDictCursor,
            )

            # Create cursor for operations
            self._cr = self._conn.cursor()

            # Verify this is an Odoo database
            self._check_odoo_database()

            # Get and store Odoo version
            self.odoo_version = self._get_odoo_version()

            logger.info("Connected to an Odoo %s database", self.odoo_version)

            return self

        except psycopg2.Error as e:
            # Close connection if partially established
            if self._conn:
                self._conn.close()
            msg = f"Failed to connect to database: {e}"
            raise DatabaseConnectionError(msg) from e

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        """Close connection, committing or rolling back as appropriate.

        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred

        Returns:
            False to propagate any exception that occurred
        """
        if not self._conn:  # pragma: no cover
            return False

        try:
            if exc_type is None:
                # No exception - commit transaction
                self._conn.commit()
            else:
                # Exception occurred - rollback transaction
                self._conn.rollback()
        finally:
            # Always close cursor and connection
            if self._cr:
                self._cr.close()
            self._conn.close()

        # Don't suppress exceptions
        return False

    def _check_odoo_database(self) -> None:
        """Verify this is an Odoo database.

        Checks if the ir_module_module table exists in the public schema.

        Raises:
            NotOdooDatabaseError: If ir_module_module table doesn't exist
        """
        query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'ir_module_module'
            ) AS table_exists
        """

        self.cr.execute(query)
        result = self.cr.fetchone()

        if not result or not result["table_exists"]:
            msg = (
                f"Database '{self.params.database}' is not an Odoo database. "
                f"Table 'ir_module_module' not found."
            )
            raise NotOdooDatabaseError(msg)

    def _get_odoo_version(self) -> float:
        """Extract Odoo major version from base module.

        Queries the ir_module_module table for the 'base' module version
        and extracts the major version (e.g., '18.0.1.3' -> 18.0).

        Returns:
            Major version as float (e.g., 18.0, 17.0)

        Raises:
            OdooVersionError: If version cannot be determined
        """
        query = """
            SELECT latest_version
            FROM ir_module_module
            WHERE name = 'base'
        """

        self.cr.execute(query)
        result = self.cr.fetchone()

        if not result or not result["latest_version"]:
            msg = (
                "Cannot determine Odoo version. "
                "The 'base' module version is not available."
            )
            raise OdooVersionError(msg)

        version_str = result["latest_version"]

        # Extract major version (e.g., '18.0.1.3' -> 18.0)
        try:
            parts = version_str.split(".")
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0
            return float(f"{major}.{minor}")
        except (ValueError, IndexError) as e:
            msg = f"Invalid version format: {version_str}"
            raise OdooVersionError(msg) from e

    @contextmanager
    def advisory_lock(self, name: str):
        """Acquire a PostgreSQL advisory lock for the current transaction.

        Converts the name to a stable integer lock ID using SHA-256 hashing.
        Blocks until the lock is available, preventing concurrent runs with the
        same lock name on the same database.  The lock is automatically released
        when the surrounding transaction commits or rolls back.

        Args:
            name: Human-readable lock name (e.g. "confidoo/mydb")

        Yields:
            None

        Example:
            >>> with db.advisory_lock("confidoo/mydb"):
            ...     # exclusive section
            ...     pass
        """
        h = hashlib.sha256()
        h.update(name.encode("utf-8"))
        # Use 14 hex chars (56 bits) to stay well within PostgreSQL bigint's
        # positive range (max 2^63-1 for a signed 64-bit integer).
        lock_id = int(h.hexdigest()[:14], 16)
        self.cr.execute("SELECT pg_advisory_xact_lock(%s::bigint)", (lock_id,))
        yield

    def resolve_xmlid(self, xmlid: str) -> tuple[str, int]:
        """Resolve XMLID to (model, res_id).

        Similar to Odoo's ref() method but using direct SQL queries.

        Args:
            xmlid: Full XML ID in 'module.name' format

        Returns:
            Tuple of (model_name, res_id)

        Raises:
            ValueError: If XMLID format is invalid
            XmlIdNotFoundError: If XMLID doesn't exist in database

        Example:
            >>> db.resolve_xmlid('base.user_admin')
            ('res.users', 2)
        """
        # Parse module.name format
        if "." not in xmlid:
            msg = f"Invalid XMLID format: {xmlid}. Expected 'module.name'"
            raise ValueError(msg)

        module, name = xmlid.split(".", 1)

        query = """
            SELECT model, res_id
            FROM ir_model_data
            WHERE module = %s AND name = %s
        """

        self.cr.execute(query, (module, name))
        result = self.cr.fetchone()

        if not result:
            msg = (
                f"XMLID not found: {xmlid}. "
                f"Ensure the record exists in the database."
            )
            raise XmlIdNotFoundError(msg)

        return result["model"], result["res_id"]

    def resolve_table_name(self, model: str) -> str:
        """Resolve table name from model or custom table attribute.

        Args:
            model: Odoo model name (e.g., 'ir.mail_server')

        Returns:
            Table name to use in SQL queries

        Example:
            >>> db.resolve_table_name('ir.mail_server')
            'ir_mail_server'
        """
        return model.replace(".", "_")
