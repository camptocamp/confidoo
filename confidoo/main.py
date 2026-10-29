# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Main Confidoo class for declarative Odoo configuration.

This module provides the primary API for using Confidoo both as a library
and through the CLI.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from psycopg2 import sql

from .config import (
    ConfigOperation,
    ConfigParamOperation,
    ModelOperation,
    RecordOperation,
    parse_config,
)
from .db import ConnectionParams, OdooDatabase

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .config import ParsedConfig


logger = logging.getLogger(__name__)


class Confidoo:
    """Main class for managing Odoo configuration declaratively.

    Provides both high-level convenience methods and low-level control
    for loading and applying configuration to Odoo databases.

    Example (convenience method):
        >>> Confidoo.apply_config(
        ...     config_content="[model:ir.mail_server]\\nsmtp_host=localhost",
        ...     database="mydb",
        ...     user="odoo",
        ...     password="odoo"
        ... )

    Example (with config in constructor):
        >>> confidoo = Confidoo(
        ...     database="mydb",
        ...     user="odoo",
        ...     password="odoo",
        ...     config_content="[model:ir.mail_server]\\nsmtp_host=localhost"
        ... )
        >>> with confidoo.connect():
        ...     confidoo.apply()

    Example (low-level control):
        >>> confidoo = Confidoo(database="mydb", user="odoo", password="odoo")
        >>> confidoo.load_config("[model:ir.mail_server]\\nsmtp_host=localhost")
        >>> with confidoo.connect() as db:
        ...     confidoo.apply()
    """

    def __init__(
        self,
        database: str,
        user: str,
        password: str,
        host: str = "localhost",
        port: int = 5432,
        config_content: str | None = None,
        config_path: str | Path | None = None,
        config_file: TextIO | None = None,
    ) -> None:
        """Initialize Confidoo with database connection parameters.

        Args:
            database: Database name
            user: Database user
            password: Database password
            host: Database host (default: localhost)
            port: Database port (default: 5432)
            config_content: Optional INI configuration content
            config_path: Optional path to INI configuration file
            config_file: Optional file object with INI configuration

        Raises:
            ValueError: If multiple config sources are provided
            ConfigParseError: If configuration is invalid
            InvalidSectionError: If section syntax is invalid

        Note:
            Only one of config_content, config_path, or config_file
            should be provided. If none are provided, you must call
            load_config() or load_config_file() before apply().
        """
        self._conn_params = ConnectionParams(
            database=database,
            user=user,
            password=password,
            host=host,
            port=port,
        )
        self._config: ParsedConfig | None = None
        self._db: OdooDatabase | None = None

        # Validate that at most one config source is provided
        config_sources = [
            config_content is not None,
            config_path is not None,
            config_file is not None,
        ]
        if sum(config_sources) > 1:
            msg = (
                "Only one of config_content, config_path, or config_file "
                "can be provided"
            )
            raise ValueError(msg)

        # Load config if provided
        if config_content is not None:
            self.load_config(config_content)
        elif config_path is not None:
            self.load_config_file(config_path)
        elif config_file is not None:
            self.load_config(config_file.read())

    @property
    def config(self) -> ParsedConfig:
        """Get the parsed configuration.

        Returns:
            Parsed configuration object

        Raises:
            RuntimeError: If no configuration is loaded
        """
        if self._config is None:  # pragma: no cover
            msg = (
                "No configuration loaded. "
                "Call load_config() or load_config_file() first."
            )
            raise RuntimeError(msg)
        return self._config

    @property
    def db(self) -> OdooDatabase:
        """Get the database connection.

        Returns:
            Active database connection

        Raises:
            RuntimeError: If no active database connection
        """
        if self._db is None:  # pragma: no cover
            msg = (
                "No active database connection. "
                "Call apply() within connect() context."
            )
            raise RuntimeError(msg)
        return self._db

    def load_config(self, content: str) -> None:
        """Load and parse configuration from a string.

        Args:
            content: INI configuration content

        Raises:
            ConfigParseError: If the content is invalid
            InvalidSectionError: If section syntax is invalid
        """
        logger.debug("Loading configuration...")
        self._config = parse_config(content)

    def load_config_file(self, path: str | Path) -> None:
        """Load and parse configuration from a file.

        Args:
            path: Path to INI configuration file

        Raises:
            ConfigParseError: If the content is invalid
            InvalidSectionError: If section syntax is invalid
            FileNotFoundError: If the file doesn't exist
        """
        self.load_config(Path(path).read_text())

    def connect(self) -> OdooDatabase:
        """Establish database connection.

        Returns:
            OdooDatabase context manager for transaction handling

        Example:
            >>> confidoo = Confidoo(database="mydb", user="odoo", password="odoo")
            >>> with confidoo.connect() as db:
            ...     print(f"Connected to Odoo {db.odoo_version}")
        """
        self._db = OdooDatabase(self._conn_params)
        return self._db

    def apply(self) -> None:
        """Apply loaded configuration to the database.

        Must be called within the context of connect().

        Raises:
            RuntimeError: If called without loading config first
            RuntimeError: If called outside connect() context
            DatabaseError: If database operations fail
        """
        # Apply all operations in order
        for operation in self.config:
            self._apply_operation(operation)

    def _apply_operation(self, operation: ConfigOperation) -> None:
        """Apply a single operation to the database.

        Dispatches to appropriate handler based on operation type.

        Args:
            operation: Configuration operation to apply

        Raises:
            ValueError: If operation type is unknown
        """
        logger.info("Applying %s...", operation)
        if isinstance(operation, ModelOperation):
            self._apply_model_operation(operation)
        elif isinstance(operation, RecordOperation):
            self._apply_record_operation(operation)
        elif isinstance(operation, ConfigParamOperation):
            self._apply_config_param_operation(operation)
        else:
            msg = f"Unknown operation type: {type(operation)}"
            raise ValueError(msg)

    @staticmethod
    def _build_set_clause(fields: Mapping[str, str | None]) -> sql.Composed:
        """Build the SET clause of an UPDATE query.

        Field names are quoted with sql.Identifier, and values are left as
        %s placeholders to be passed as query parameters, in the same order.

        Args:
            fields: Mapping of field names to values

        Returns:
            Composed SQL like ``"field1" = %s, "field2" = %s``
        """
        return sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(field)) for field in fields
        )

    def _apply_model_operation(self, operation: ModelOperation) -> None:
        """Apply settings to all records of a model.

        Args:
            operation: Model operation to apply

        Example:
            [model:ir.mail_server]
            smtp_encryption = starttls
            -> UPDATE ir_mail_server SET smtp_encryption = 'starttls'
        """
        if not operation.fields:
            return  # Nothing to update

        # Resolve table name
        table = operation.table or self.db.resolve_table_name(operation.identifier)

        # Build SET clause using sql.Identifier for safe field names
        set_clause = self._build_set_clause(operation.fields)

        # Build values tuple (None for empty values)
        values = tuple(operation.fields.values())

        # Execute UPDATE query with safe identifiers
        query = sql.SQL("UPDATE {} SET {}").format(sql.Identifier(table), set_clause)
        self.db.cr.execute(query, values)
        logger.info("✓ Updated %d row(s)", self.db.cr.rowcount)

    def _apply_record_operation(self, operation: RecordOperation) -> None:
        """Apply settings to a specific record by XMLID.

        Args:
            operation: Record operation to apply

        Example:
            [record:base.user_admin]
            login = administrator
            -> UPDATE res_users SET login = 'administrator' WHERE id = 2
        """
        if not operation.fields:
            return  # Nothing to update

        # Resolve XMLID to model and res_id
        model, res_id = self.db.resolve_xmlid(operation.identifier)

        # Resolve table name (use model from XMLID, not operation identifier)
        table = operation.table or self.db.resolve_table_name(model)

        # Build SET clause using sql.Identifier for safe field names
        set_clause = self._build_set_clause(operation.fields)

        # Build values tuple with res_id at the end for WHERE clause
        values = tuple(operation.fields.values()) + (res_id,)

        # Execute UPDATE query with safe identifiers and WHERE clause
        query = sql.SQL("UPDATE {} SET {} WHERE id = %s").format(
            sql.Identifier(table), set_clause
        )
        self.db.cr.execute(query, values)
        logger.info("✓ Updated")

    def _apply_config_param_operation(self, operation: ConfigParamOperation) -> None:
        """Apply system parameters (INSERT or UPDATE or DELETE).

        System parameters are stored in the ir_config_parameter table.
        - If value is None: DELETE the parameter
        - If value is not None: UPSERT (INSERT ... ON CONFLICT)

        Args:
            operation: Config parameter operation to apply

        Example:
            [config:set_param]
            web.base.url = https://example.com
            mail.catchall.domain =
            -> UPSERT web.base.url
            -> DELETE mail.catchall.domain
        """
        for key, value in operation.fields.items():
            if value is None:
                # Delete parameter
                delete_query = """
                    DELETE FROM ir_config_parameter
                    WHERE key = %s
                """
                self.db.cr.execute(delete_query, (key,))
                logger.info("✓ %s (deleted)", key)
            else:
                # Upsert parameter (PostgreSQL specific)
                # Use INSERT ... ON CONFLICT for upsert
                upsert_query = """
                    INSERT INTO ir_config_parameter (key, value)
                    VALUES (%s, %s)
                    ON CONFLICT (key)
                    DO UPDATE SET value = EXCLUDED.value
                """
                self.db.cr.execute(upsert_query, (key, value))
                logger.info("✓ %s", key)

    @classmethod
    def apply_config(
        cls,
        database: str,
        user: str,
        password: str,
        host: str = "localhost",
        port: int = 5432,
        config_content: str | None = None,
        config_path: str | Path | None = None,
        config_file: TextIO | None = None,
    ) -> None:
        """Convenience method to apply configuration in one call.

        Loads configuration, connects to database, and applies all operations
        within a single transaction.

        Args:
            database: Database name
            user: Database user
            password: Database password
            host: Database host (default: localhost)
            port: Database port (default: 5432)
            config_content: INI configuration content (mutually exclusive)
            config_path: Path to INI configuration file (mutually exclusive)
            config_file: File object with INI configuration (mutually exclusive)

        Raises:
            ValueError: If neither or both config sources are provided
            ConfigParseError: If configuration is invalid
            DatabaseError: If database operations fail

        Example:
            >>> Confidoo.apply_config(
            ...     config_content="[model:ir.mail_server]\\nsmtp_host=localhost",
            ...     database="mydb",
            ...     user="odoo",
            ...     password="odoo"
            ... )
        """
        # Create instance with config already loaded
        confidoo = cls(
            database=database,
            user=user,
            password=password,
            host=host,
            port=port,
            config_content=config_content,
            config_path=config_path,
            config_file=config_file,
        )

        # Connect and apply
        with confidoo.connect():
            confidoo.apply()
