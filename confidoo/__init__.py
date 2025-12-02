"""Declarative Odoo configuration."""

from .parser import parse_config
from .applier import apply_config

__version__ = "0.1.0"
__all__ = ["parse_config", "apply_config"]
