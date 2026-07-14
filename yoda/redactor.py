"""Redactor: PII masking for anything destined for the LLM.

Key invariant: no unredacted cell value may appear in any prompt. A unit
test seeds PII fixtures and asserts the prompt-builder output is clean.
"""

from __future__ import annotations


def redact(value: str) -> str:
    """Mask emails, PH phone numbers, and name-like strings. Phase 1."""
    raise NotImplementedError("Phase 1")
