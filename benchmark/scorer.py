"""Scorer: compares YODA's output against the corruption manifest.

Per error type it reports:
- detection rate  — the plan contains the right tool for the corrupted column
- fix rate        — the corrupted cell was correctly repaired (or, for
                    nulls/outliers, correctly flagged — those aren't restorable)
- false-fix rate  — cells that were NOT corrupted but got changed anyway

Rows are aligned between clean and cleaned output via the dataset's key
column, which the corruptor never touches.
"""

from __future__ import annotations

import math

import pandas as pd

EXPECTED_TOOL = {
    "duplicate": "drop_duplicates",
    "mixed_date_format": "normalize_dates",
    "phone_format": "normalize_phone",
    "currency_format": "normalize_currency",
    "category_casing": "standardize_categories",
    "dtype_corruption": "fix_dtypes",
    "outlier": "flag_outliers",
    "whitespace": "trim_whitespace",
    "null": "impute_missing",
}
# Error types where the truth is unrecoverable: success = a correct flag.
FLAG_TYPES = {"null": "_missing", "outlier": "_outlier"}


def _eq(a, b) -> bool:
    a_na, b_na = pd.isna(a), pd.isna(b)
    if a_na or b_na:
        return bool(a_na and b_na)
    try:
        return math.isclose(float(a), float(b), rel_tol=1e-9)
    except (TypeError, ValueError):
        return str(a) == str(b)


def score(clean: pd.DataFrame, output: pd.DataFrame,
          manifest: dict, plan: list[dict]) -> dict:
    key = manifest["key"]
    clean_by_key = clean.set_index(clean[key].astype(str))
    out_dedup = output.drop_duplicates(subset=[key], keep="first")
    out_by_key = out_dedup.set_index(out_dedup[key].astype(str))
    key_counts = output[key].astype(str).value_counts()

    planned = {(s["tool"], s.get("col")) for s in plan}
    planned_tools = {s["tool"] for s in plan}

    corrupted_cells = {(e["col"], e["key"]) for e in manifest["errors"]
                       if e["type"] != "duplicate"}

    per_type: dict[str, dict] = {}
    for err in manifest["errors"]:
        etype, col, k = err["type"], err["col"], err["key"]
        t = per_type.setdefault(etype, {"n": 0, "detected": 0, "fixed": 0})
        t["n"] += 1

        expected = EXPECTED_TOOL[etype]
        detected = (expected, col) in planned or (
            etype == "duplicate" and "drop_duplicates" in planned_tools)
        t["detected"] += detected

        if k not in out_by_key.index:
            continue
        row = out_by_key.loc[k]
        if etype == "duplicate":
            t["fixed"] += int(key_counts.get(k, 0) == 1)
        elif etype in FLAG_TYPES:
            flag_col = col + FLAG_TYPES[etype]
            t["fixed"] += int(bool(row.get(flag_col, False)))
        else:
            if col in out_by_key.columns and k in clean_by_key.index:
                t["fixed"] += int(_eq(row[col], clean_by_key.loc[k, col]))

    # False fixes: uncorrupted cells (original columns only) that changed.
    n_clean_cells = n_false = 0
    shared_cols = [c for c in clean.columns if c in out_by_key.columns and c != key]
    for col in shared_cols:
        for k in clean_by_key.index:
            if (col, k) in corrupted_cells or k not in out_by_key.index:
                continue
            n_clean_cells += 1
            if not _eq(clean_by_key.loc[k, col], out_by_key.loc[k, col]):
                n_false += 1

    total_n = sum(t["n"] for t in per_type.values())
    return {
        "dataset": manifest["dataset"],
        "per_type": {
            etype: {
                **t,
                "detection_rate": round(t["detected"] / t["n"], 4),
                "fix_rate": round(t["fixed"] / t["n"], 4),
            }
            for etype, t in sorted(per_type.items())
        },
        "overall": {
            "n_errors": total_n,
            "detection_rate": round(
                sum(t["detected"] for t in per_type.values()) / total_n, 4),
            "fix_rate": round(sum(t["fixed"] for t in per_type.values()) / total_n, 4),
            "false_fix_rate": round(n_false / n_clean_cells, 4) if n_clean_cells else 0.0,
            "n_clean_cells_checked": n_clean_cells,
            "n_false_fixes": n_false,
        },
    }
