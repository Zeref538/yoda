"""Profiler: pure-pandas metadata extraction. No AI, no raw-row output.

Emits a PROFILE dict (JSON-serializable) with schema, per-column stats,
detected format patterns, duplicate stats, outlier flags, and REDACTED
samples only. This is the sole artifact the planner LLM is allowed to see.
"""

from __future__ import annotations

import pandas as pd


def profile(df: pd.DataFrame) -> dict:
    """Build the metadata profile for a dataframe. Implemented in Phase 1."""
    raise NotImplementedError("Phase 1")
