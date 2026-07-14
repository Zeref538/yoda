"""Redactor: PII masking for anything destined for the LLM.

Key invariant: no unredacted cell value may appear in any prompt. Every
sample string that leaves the profiler passes through :func:`redact`.
Masking is deliberately aggressive — when in doubt, hide characters.
"""

from __future__ import annotations

import re

# Order matters: emails before phones (emails can contain digits).
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# PH-flavored phone numbers: 0917..., +63917..., 63-917-..., with optional
# separators. Broad on purpose; we only use this for masking, never parsing.
_PHONE_RE = re.compile(r"(?:\+?63|0)[\s.-]?9\d{2}[\s.-]?\d{3}[\s.-]?\d{4}")
_LONG_DIGITS_RE = re.compile(r"\d{7,}")
# Name-like: capitalized word pairs ("Juan Dela Cruz", "Maria Santos").
_NAME_RE = re.compile(r"\b([A-Z][a-z]+)(\s+(?:[A-Z][a-z]+|[A-Z]\.)){1,3}\b")

# Column names that get whole-value masking regardless of content.
_SENSITIVE_COL_RE = re.compile(
    r"(name|email|phone|mobile|contact|address|street|birth|dob|ssn|tin|passport|id_?number)",
    re.IGNORECASE,
)


def _mask_email(m: re.Match) -> str:
    local, _, domain = m.group(0).partition("@")
    return f"{local[0]}***@{domain[0]}***.{domain.rsplit('.', 1)[-1]}"


def _mask_phone(m: re.Match) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    return f"{digits[:2]}**-***-{digits[-4:]}"


def _mask_name(m: re.Match) -> str:
    words = m.group(0).split()
    return " ".join(w[0] + "*" * (len(w) - 1) for w in words)


def redact(value: object) -> str:
    """Mask emails, PH phone numbers, long digit runs, and name-like strings."""
    s = str(value)
    s = _EMAIL_RE.sub(_mask_email, s)
    s = _PHONE_RE.sub(_mask_phone, s)
    s = _LONG_DIGITS_RE.sub(lambda m: m.group(0)[:2] + "*" * (len(m.group(0)) - 2), s)
    s = _NAME_RE.sub(_mask_name, s)
    return s


def is_sensitive_column(col_name: str) -> bool:
    """True when a column name implies PII; its samples get fully masked."""
    return bool(_SENSITIVE_COL_RE.search(col_name))


def redact_sample(value: object, col_name: str = "") -> str:
    """Redact one sample value, applying whole-value masking for PII columns."""
    s = str(value)
    if is_sensitive_column(col_name):
        # Preserve only shape: first char, length class, last char.
        if len(s) <= 2:
            return "*" * len(s)
        return f"{s[0]}{'*' * min(len(s) - 2, 8)}{s[-1]}"
    return redact(s)
