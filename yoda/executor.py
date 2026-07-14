"""Executor: applies an approved plan deterministically. Pure pandas, no AI.

Keeps the original dataframe for recoverability and writes an audit log
(JSONL): step, column, rows_affected, redacted before/after examples, timing.
"""

from __future__ import annotations

import pandas as pd


def execute(df: pd.DataFrame, plan: list[dict], audit_path: str) -> pd.DataFrame:
    """Run each plan step via the tools registry. Implemented in Phase 2."""
    raise NotImplementedError("Phase 2")
