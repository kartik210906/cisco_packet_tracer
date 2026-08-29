"""
comparator.py
=============
Compares the AI's diagnosis against the independent Python rule
checker's finding and returns one of MATCH / CONFLICT / UNVERIFIED.

This module never hides disagreement — CONFLICT must always be shown
to the human reviewer.
"""

import re

MATCH = "MATCH"
CONFLICT = "CONFLICT"
UNVERIFIED = "UNVERIFIED"

# A small synonym map so that "Interface Down" (AI) and
# "Interface administratively down" (Python) are recognized as the
# same underlying fault category rather than a false conflict.
_CATEGORY_KEYWORDS = {
    "interface_down": ["administratively down", "interface down", "down/down",
                        "line protocol down", "port down"],
    "duplicate_ip": ["duplicate ip"],
    "subnet_mask": ["subnet mask", "wrong mask", "mask mismatch"],
    "gateway": ["gateway", "default gateway"],
    "vlan": ["vlan"],
    "route": ["route", "routing"],
    "dns": ["dns"],
    "dhcp": ["dhcp"],
    "acl": ["access list", "access-list", "access control list", "acl"],
    "nat": ["nat", "network address translation"],
    "wireless": ["ssid", "wireless", "wifi", "wpa", "authentication key"],
}


def _categorize(text: str):
    text = (text or "").lower()
    categories = set()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            categories.add(category)
    return categories


def compare(ai_root_cause: str, python_finding: str, python_status: str) -> str:
    """
    Compare the AI's root cause text against the Python checker's
    finding text and status.

    Returns MATCH, CONFLICT, or UNVERIFIED.
    """
    if python_status == "UNVERIFIED":
        return UNVERIFIED

    ai_categories = _categorize(ai_root_cause)
    python_categories = _categorize(python_finding)

    if python_status == "NO_ISSUE_FOUND":
        # Python found nothing wrong. If the AI also found nothing
        # meaningful (empty/uncertain), treat as MATCH; otherwise the
        # AI claims a fault Python could not confirm -> CONFLICT.
        if not ai_categories:
            return MATCH
        return CONFLICT

    # python_status == ISSUE_FOUND
    if not ai_categories or not python_categories:
        # Not enough signal in one side's text to compare categories;
        # be conservative and call it UNVERIFIED rather than assume.
        return UNVERIFIED

    if ai_categories & python_categories:
        return MATCH

    return CONFLICT
