"""GSTIN (Indian GST number) format and checksum validation.

A GSTIN has 15 characters: 2-digit state code, 10-character PAN, entity
number, the letter Z, and a check character computed from the first 14.
"""
from __future__ import annotations

import re

_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_FORMAT = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
STATES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
    "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
    "97": "Other Territory", "99": "Centre Jurisdiction",
}


def check_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = _CHARS.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return _CHARS[(36 - total % 36) % 36]


def clean(gstin: str | None) -> str:
    return re.sub(r"[\s-]", "", (gstin or "").upper())


def problem(gstin: str | None) -> str | None:
    """None if the GSTIN is valid, otherwise a short explanation."""
    value = clean(gstin)
    if not value:
        return "missing"
    if len(value) != 15:
        return f"has {len(value)} characters instead of 15"
    if not _FORMAT.match(value):
        return "is not in the GSTIN format"
    if value[:2] not in STATES:
        return f"has an unknown state code {value[:2]}"
    if check_char(value[:14]) != value[14]:
        return "has a wrong check digit (probably misread or mistyped)"
    return None


def state_of(gstin: str | None) -> str | None:
    value = clean(gstin)
    return value[:2] if len(value) == 15 and value[:2] in STATES else None


def make(state: str, pan: str, entity: str = "1") -> str:
    """Build a GSTIN with a correct check character (used for the fictional samples)."""
    first14 = f"{state}{pan}{entity}Z"
    return first14 + check_char(first14)
