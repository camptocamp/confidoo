# Copyright 2026 Camptocamp SA (https://www.camptocamp.com).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Tests for the XML ID helpers."""

import pytest

from confidoo.utils.xmlid import split_xmlid


@pytest.mark.parametrize(
    ("xmlid", "expected"),
    [
        ("base.user_admin", ("base", "user_admin")),
        ("my_module.a.b", ("my_module", "a.b")),
    ],
)
def test_split_xmlid(xmlid, expected):
    """Test a full XML ID is split on its first dot."""
    assert split_xmlid(xmlid) == expected


@pytest.mark.parametrize("xmlid", ["user_admin", "base.", ".user_admin", "a b.c", ""])
def test_split_xmlid_invalid(xmlid):
    """Test an XML ID not in 'module.name' format is rejected."""
    with pytest.raises(ValueError, match="Invalid XMLID format"):
        split_xmlid(xmlid)
