"""Verifier: re-profile the cleaned data, diff against the original profile,
and issue a verdict per detected issue: resolved / partially_resolved /
flagged / unresolved / new_issue.

May propose ONE follow-up plan round (max 2 rounds total): the planner is
re-run on the new profile, keeping only steps that target still-open issues.
"""

from __future__ import annotations

from yoda.planner import snake_case

# Signals the profiler emits that represent "issues", and how to measure them.
_SIGNALS = {
    "mixed_date_formats": lambda c: (
        len(c.get("date_formats_seen", {}))
        if set(c.get("date_formats_seen", {})) - {"ISO (YYYY-MM-DD)"} else 0),
    "phone_format_chaos": lambda c: (
        len(c.get("phone_formats_seen", {}))
        if set(c.get("phone_formats_seen", {})) - {"intl (+639XXXXXXXXX)"} else 0),
    "currency_strings": lambda c: c.get("currency_like_values", 0),
    "numeric_as_string": lambda c: c.get("numeric_as_string", 0),
    "bool_as_string": lambda c: c.get("bool_as_string", 0),
    "whitespace": lambda c: c.get("whitespace_issues", 0) + c.get("non_nfc_values", 0),
    "casing_variants": lambda c: (
        c["casing_variants"]["raw_unique"] - c["casing_variants"]["folded_unique"]
        if c.get("casing_variants") else 0),
    "nulls": lambda c: c.get("null_pct", 0),
    "outliers": lambda c: c.get("iqr_outliers", 0),
}
# Issues that are handled by adding a flag column, not by changing values.
_FLAG_HANDLED = {"nulls": "_missing", "outliers": "_outlier"}
_HELPER_SUFFIXES = ("_missing", "_outlier", "_invalid", "_currency")

# Which planner tool addresses which signal (for follow-up filtering).
_SIGNAL_TOOL = {
    "mixed_date_formats": "normalize_dates",
    "phone_format_chaos": "normalize_phone",
    "currency_strings": "normalize_currency",
    "numeric_as_string": "fix_dtypes",
    "bool_as_string": "fix_dtypes",
    "whitespace": "trim_whitespace",
    "casing_variants": "standardize_categories",
    "nulls": "impute_missing",
    "outliers": "flag_outliers",
    "blank_rows": "drop_blank_rows",
}

OPEN_VERDICTS = ("unresolved", "partially_resolved", "new_issue")


def diff_profiles(before: dict, after: dict) -> list[dict]:
    """Compare issue signals column by column. Returns verdict entries."""
    verdicts: list[dict] = []
    after_cols = after["columns"]

    dup_b = before["duplicates"]["full_row"]
    dup_a = after["duplicates"]["full_row"]
    if dup_b or dup_a:
        verdicts.append({
            "issue": "duplicates", "col": None, "before": dup_b, "after": dup_a,
            "verdict": ("resolved" if dup_a == 0 else
                        "new_issue" if dup_b == 0 else
                        "partially_resolved" if dup_a < dup_b else "unresolved"),
        })

    bl_b = before.get("blank_rows", 0)
    bl_a = after.get("blank_rows", 0)
    if bl_b or bl_a:
        verdicts.append({
            "issue": "blank_rows", "col": None, "before": bl_b, "after": bl_a,
            "verdict": ("resolved" if bl_a == 0 else
                        "new_issue" if bl_b == 0 else
                        "partially_resolved" if bl_a < bl_b else "unresolved"),
        })

    for col, cb in before["columns"].items():
        out_name = col if col in after_cols else snake_case(col)
        ca = after_cols.get(out_name, {})
        for signal, measure in _SIGNALS.items():
            b, a = measure(cb), measure(ca)
            if not b and not a:
                continue
            if signal in _FLAG_HANDLED:
                flag = out_name + _FLAG_HANDLED[signal]
                verdict = ("flagged" if flag in after_cols else
                           "resolved" if not a else "unresolved")
            elif a == 0:
                verdict = "resolved"
            elif b == 0:
                verdict = "new_issue"
            elif a < b:
                verdict = "partially_resolved"
            else:
                verdict = "unresolved"
            verdicts.append({"issue": signal, "col": col,
                             "before": b, "after": a, "verdict": verdict})

    # Issue signals in columns that didn't exist before (excluding helper cols)
    known = set(before["columns"]) | {snake_case(c) for c in before["columns"]}
    for col, ca in after_cols.items():
        if col in known or col.endswith(_HELPER_SUFFIXES):
            continue
        for signal, measure in _SIGNALS.items():
            if signal in _FLAG_HANDLED:
                continue
            a = measure(ca)
            if a:
                verdicts.append({"issue": signal, "col": col, "before": 0,
                                 "after": a, "verdict": "new_issue"})
    return verdicts


def follow_up_plan(verdicts: list[dict], planner, new_profile: dict) -> list[dict]:
    """One follow-up round: re-plan on the new profile, keep only steps that
    address issues still open. Caller enforces the 2-round maximum."""
    open_targets = {(_SIGNAL_TOOL[v["issue"]], v["col"] and (
        v["col"] if v["col"] in new_profile["columns"] else snake_case(v["col"])))
        for v in verdicts
        if v["verdict"] in OPEN_VERDICTS and v["issue"] in _SIGNAL_TOOL}
    if not open_targets:
        return []
    full = planner.plan(new_profile)
    return [s for s in full if (s["tool"], s.get("col")) in open_targets]
