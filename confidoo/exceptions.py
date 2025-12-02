# Copyright 2025 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Custom exceptions for Confidoo."""


class ConfidooError(Exception):
    """Base exception for all Confidoo errors."""


class ConfigParseError(ConfidooError):
    """Raised when configuration parsing fails."""


class InvalidSectionError(ConfigParseError):
    """Raised when a section has invalid syntax."""


class DatabaseError(ConfidooError):
    """Base exception for database errors."""


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""


class NotOdooDatabaseError(DatabaseError):
    """Raised when database is not an Odoo database."""


class OdooVersionError(DatabaseError):
    """Raised when Odoo version cannot be determined."""


class XmlIdNotFoundError(DatabaseError):
    """Raised when XMLID cannot be resolved."""


class TransactionError(DatabaseError):
    """Raised when transaction operations fail."""
