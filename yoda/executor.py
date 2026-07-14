"""Executor: applies an approved plan deterministically. Pure pandas, no AI.

Keeps the original dataframe for recoverability and writes an audit log
(JSONL): step, column, rows_affected, redacted before/after examples, timing.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from yoda.redactor import redact_sample
from yoda.tools import TOOLS


def _examples(before: pd.DataFrame, after: pd.DataFrame, col: str | None, n: int = 3) -> list:
    """Redacted before→after examples for changed cells in `col`."""
    if not col or col not in before.columns or col not in after.columns:
        return []
    if len(before) != len(after):
        return []
    b, a = before[col], after[col]
    changed = (b.astype(str) != a.astype(str)) & ~(b.isna() & a.isna())
    out = []
    for idx in before.index[changed][:n]:
        out.append({"before": redact_sample(b[idx], col), "after": redact_sample(a[idx], col)})
    return out


def execute(
    df: pd.DataFrame,
    plan: list[dict],
    audit_path: str | Path | None = None,
    on_step=None,
) -> tuple[pd.DataFrame, list[dict]]:
    """Run each plan step via the tools registry.

    Returns (cleaned_df, audit_entries). The input df is never mutated.
    Unknown tools or failing steps are logged and skipped, never fatal.
    `on_step(entry)` is called after each step (for live CLI progress).
    """
    current = df.copy()
    audit: list[dict] = []

    for i, step in enumerate(plan):
        tool_name = step.get("tool")
        col = step.get("col")
        params = step.get("params") or {}
        entry: dict = {"step": i, "tool": tool_name, "col": col,
                       "params": params, "reason": step.get("reason", "")}
        fn = TOOLS.get(tool_name)
        if fn is None:
            entry.update(status="skipped", error=f"unknown tool: {tool_name}")
            audit.append(entry)
            continue
        t0 = time.perf_counter()
        try:
            new_df, stats = fn(current, col, params)
            entry.update(status="ok", **stats,
                         examples=_examples(current, new_df, col),
                         duration_ms=round((time.perf_counter() - t0) * 1000, 1))
            current = new_df
        except Exception as exc:  # a bad step must never destroy the run
            entry.update(status="error", error=f"{type(exc).__name__}: {exc}",
                         duration_ms=round((time.perf_counter() - t0) * 1000, 1))
        audit.append(entry)
        if on_step:
            on_step(entry)

    if audit_path:
        with open(audit_path, "w", encoding="utf-8") as f:
            for entry in audit:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    return current, audit
