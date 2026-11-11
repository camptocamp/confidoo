# Copyright 2026 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""XML ID helpers."""

import re

# A full XML ID: module.name, without whitespace
XMLID_PATTERN = re.compile(r"(?P<module>[^.\s]+)\.(?P<name>\S+)")


def split_xmlid(xmlid: str) -> tuple[str, str]:
    """Split a full XML ID into its module and name.

    Args:
        xmlid: Full XML ID in 'module.name' format

    Returns:
        Tuple of (module, name)

    Raises:
        ValueError: If the XML ID isn't in 'module.name' format

    Example:
        >>> split_xmlid("base.user_admin")
        ('base', 'user_admin')
    """
    if not (match := XMLID_PATTERN.fullmatch(xmlid)):
        msg = f"Invalid XMLID format: {xmlid}. Expected 'module.name'"
        raise ValueError(msg)
    return match["module"], match["name"]
