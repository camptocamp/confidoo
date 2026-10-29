# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Database connection and utilities for Confidoo.

This module provides database connection management with transactional support
and Odoo-specific utility methods.
"""

from __future__ import annotations

import contextlib
import logging
import re
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
    XmlIdNotFoundError,
)

if TYPE_CHECKING:
    from psycopg2.extensions import connection as Connection
    from psycopg2.extensions import cursor as Cursor

logger = logging.getLogger(__name__)

# Matches the major.minor prefix of an Odoo module version, optionally prefixed
# with "saas~" (e.g. '18.0.1.3', 'saas~17.2.1.0')
_ODOO_VERSION_RE = re.compile(r"^(?:saas~)?(\d+)(?:\.(\d+))?")


def parse_odoo_version(version: str | None) -> float | None:
    """Parse the Odoo major version from a module version string.

    Args:
        version: Module version string (e.g., '18.0.1.3', 'saas~17.2.1.0')

    Returns:
        Major version as float (e.g., 18.0, 17.2), or None if it can't be parsed

    Example:
        >>> parse_odoo_version("18.0.1.3")
        18.0
        >>> parse_odoo_version("saas~17.2.1.0")
        17.2
        >>> parse_odoo_version("unknown") is None
        True
    """
    if not version:
        return None
    match = _ODOO_VERSION_RE.match(version.strip())
    if not match:
        return None
    major, minor = match.groups()
    return float(f"{major}.{minor or 0}")


@dataclass
class ConnectionParams:
    """Database connection parameters.

    Any parameter left as ``None`` is omitted when connecting, so libpq applies
    its own defaults (``PG*`` environment variables, ``.pgpass``, the current OS
    user, the default Unix socket, etc.).
    """

    database: str
    user: str | None = None
    password: str | None = None
    host: str | None = None
    port: int | None = None

    def to_kwargs(self) -> dict[str, Any]:
        """Convert to keyword arguments for :func:`psycopg2.connect`.

        Passing parameters as keyword arguments lets psycopg2 quote them,
        so values containing spaces, quotes or ``=`` are handled safely.

        Returns:
            Connection keyword arguments, without the ones that are ``None``
        """
        kwargs = {
            "dbname": self.database,
            "user": self.user,
            "password": self.password,
            "host": self.host,
            "port": self.port,
        }
        return {key: value for key, value in kwargs.items() if value is not None}

    def __str__(self) -> str:
        user = f"{self.user}@" if self.user else ""
        host = self.host or "default host"
        port = f":{self.port}" if self.port else ""
        return f"{self.database} ({user}{host}{port})"


class OdooDatabase:
    """Manages connection to an Odoo PostgreSQL database.

    Provides context manager support for automatic transaction management.
    All operations within the context are part of a single transaction.

    Example:
        >>> params = ConnectionParams(database="odoo", user="odoo")
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
        """
        try:
            logger.info("Connecting to database %s...", self.params)

            # Connect to PostgreSQL with dict cursor factory
            self._conn = psycopg2.connect(
                **self.params.to_kwargs(),
                cursor_factory=RealDictCursor,
            )

            # Create cursor for operations
            self._cr = self._conn.cursor()

            # Verify this is an Odoo database
            self._check_odoo_database()

            # Get and store Odoo version
            self.odoo_version = self._get_odoo_version()

            if self.odoo_version is not None:
                logger.info("Connected to an Odoo %s database", self.odoo_version)
            else:
                logger.info("Connected to an Odoo database (unknown version)")

            return self

        except psycopg2.Error as e:
            # Close connection if partially established
            self._close_connection()
            msg = f"Failed to connect to database: {e}"
            raise DatabaseConnectionError(msg) from e

        except BaseException:
            # __exit__ won't run if __enter__ raises, so clean up here
            self._close_connection()
            raise

    def _close_connection(self) -> None:
        """Close the cursor and connection, if open, ignoring errors.

        Cleanup errors are ignored so that they don't mask the original
        exception, or a failed commit.
        """
        cr, conn = self._cr, self._conn
        self._cr = None
        self._conn = None
        if cr:
            with contextlib.suppress(psycopg2.Error):
                cr.close()
        if conn:
            with contextlib.suppress(psycopg2.Error):
                conn.close()

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
            self._close_connection()

        # Don't suppress exceptions
        return False

    def _check_odoo_database(self) -> None:
        """Verify this is an Odoo database.

        Checks if the ir_module_module table exists in the public schema.

        Raises:
            NotOdooDatabaseError: If ir_module_module table doesn't exist
        """
        query = """
            SELECT to_regclass('public.ir_module_module') IS NOT NULL AS table_exists
        """

        self.cr.execute(query)
        result = self.cr.fetchone()

        if not result or not result["table_exists"]:
            msg = (
                f"Database '{self.params.database}' is not an Odoo database. "
                f"Table 'ir_module_module' not found."
            )
            raise NotOdooDatabaseError(msg)

    def _get_odoo_version(self) -> float | None:
        """Extract Odoo major version from base module.

        Queries the ir_module_module table for the 'base' module version
        and extracts the major version (e.g., '18.0.1.3' -> 18.0).

        The version is informational only: if it is missing or can't be parsed,
        a warning is logged and None is returned.

        Returns:
            Major version as float (e.g., 18.0, 17.0), or None if unknown
        """
        query = """
            SELECT latest_version
            FROM ir_module_module
            WHERE name = 'base'
        """

        self.cr.execute(query)
        result = self.cr.fetchone()
        version_str = result["latest_version"] if result else None

        version = parse_odoo_version(version_str)
        if version is None:
            logger.warning(
                "Cannot determine Odoo version from 'base' module version: %r",
                version_str,
            )
        return version

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
