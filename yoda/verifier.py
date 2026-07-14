"""Verifier: re-profiles the cleaned data and diffs against the original.

Classifies each planned issue as resolved / partially resolved / new issue
introduced; may propose one follow-up plan round (max 2 rounds total).
"""

from __future__ import annotations


def verify(before_profile: dict, after_profile: dict, plan: list[dict]) -> dict:
    """Implemented in Phase 3."""
    raise NotImplementedError("Phase 3")
