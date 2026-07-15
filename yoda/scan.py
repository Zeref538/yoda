"""PII scanner: report where personal data lives in a file, touch nothing.

Reuses the redactor's detection patterns. Output is a per-column inventory:
what kinds of PII appear, how many cells, and a coarse risk level — the
artifact a compliance review asks for before data leaves a team.
"""

from __future__ import annotations

import pandas as pd

from yoda.redactor import _EMAIL_RE, _NAME_RE, _PHONE_RE, is_sensitive_column

_SCAN_SAMPLE = 50_000

# (kind, regex) — order matters only for readability.
_DETECTORS = [
    ("email", _EMAIL_RE),
    ("ph_phone", _PHONE_RE),
    ("person_name", _NAME_RE),
]


def scan(df: pd.DataFrame) -> dict:
    """Return {'columns': [...], 'summary': {...}} — counts only, no values."""
    findings = []
    for col in df.columns:
        s = df[col].dropna()
        if s.empty:
            continue
        as_str = s.astype(str)
        if len(as_str) > _SCAN_SAMPLE:
            det = as_str.sample(_SCAN_SAMPLE, random_state=0)
            scale = len(as_str) / len(det)
        else:
            det, scale = as_str, 1.0

        kinds: dict[str, int] = {}
        for kind, rx in _DETECTORS:
            # rx patterns contain groups, so str.contains would warn; a plain
            # search over the (sample-capped) values is just as fast here.
            n = int(det.map(lambda v: rx.search(v) is not None).sum())
            if n:
                kinds[kind] = max(1, round(n * scale))
        name_flag = is_sensitive_column(str(col))
        if not kinds and not name_flag:
            continue

        n_cells = len(s)
        top = max(kinds.values(), default=0)
        risk = ("high" if ("email" in kinds or "ph_phone" in kinds)
                and top > 0.5 * n_cells
                else "high" if name_flag and kinds
                else "medium" if kinds
                else "low")
        findings.append({
            "col": str(col),
            "n_cells": n_cells,
            "detected": kinds,
            "sensitive_name": name_flag,
            "risk": risk,
            "sampled": scale > 1.0,
        })

    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (order[f["risk"]], f["col"]))
    return {
        "columns": findings,
        "summary": {
            "n_columns_scanned": len(df.columns),
            "n_columns_with_pii": len(findings),
            "highest_risk": findings[0]["risk"] if findings else "none",
        },
    }


def scan_markdown(result: dict, source: str) -> str:
    lines = [
        "# YODA PII scan",
        "",
        f"- **Source:** `{source}`",
        f"- **Columns scanned:** {result['summary']['n_columns_scanned']}"
        f" · **with PII:** {result['summary']['n_columns_with_pii']}"
        f" · **highest risk:** {result['summary']['highest_risk']}",
        "",
        "| column | risk | detected | cells | notes |",
        "|---|---|---|---:|---|",
    ]
    for f in result["columns"]:
        det = ", ".join(f"{k}×{v}" for k, v in f["detected"].items()) or "—"
        notes = []
        if f["sensitive_name"]:
            notes.append("PII-suggestive column name")
        if f["sampled"]:
            notes.append("counts estimated from a 50k sample")
        lines.append(f"| {f['col']} | {f['risk']} | {det} | {f['n_cells']} "
                     f"| {'; '.join(notes)} |")
    lines += ["", "_Counts only — no cell values appear in this report. "
                  "Nothing left this machine._", ""]
    return "\n".join(lines)
