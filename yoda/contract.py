"""Data contracts: declarative expectations a file must meet.

Contract file (YAML or JSON):

    columns:
      age:      {min: 0, max: 120, not_null: true}
      email:    {regex: "^[^@]+@[^@]+$"}
      segment:  {allowed: [Retail, SME, Enterprise]}
      order_id: {unique: true, required: true}
    table:
      min_rows: 1
      no_duplicate_rows: true

`validate(df, contract)` returns per-rule results with violation counts.
Used by `yoda validate` and by watch mode (--contract quarantines breaches).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

_RULE_KEYS = {"min", "max", "allowed", "not_null", "unique", "regex", "required"}


def load_contract(path: str | Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    if str(path).endswith((".yaml", ".yml")):
        import yaml
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict) or "columns" not in data:
        raise ValueError("contract needs a top-level 'columns' mapping")
    for col, rules in data["columns"].items():
        unknown = set(rules) - _RULE_KEYS
        if unknown:
            raise ValueError(f"unknown rule(s) for '{col}': {sorted(unknown)}")
    return data


def validate(df: pd.DataFrame, contract: dict) -> dict:
    """Evaluate every rule. Returns {'results': [...], 'passed': bool}."""
    results: list[dict] = []

    def add(rule: str, col: str | None, violations: int, detail: str = ""):
        results.append({"rule": rule, "col": col, "violations": int(violations),
                        "passed": violations == 0, "detail": detail})

    table = contract.get("table", {})
    if "min_rows" in table:
        short = max(0, int(table["min_rows"]) - len(df))
        add("min_rows", None, 1 if short else 0,
            f"{len(df)} rows, need >= {table['min_rows']}")
    if table.get("no_duplicate_rows"):
        add("no_duplicate_rows", None, int(df.duplicated().sum()))

    for col, rules in contract["columns"].items():
        if col not in df.columns:
            if rules.get("required", True):
                add("column_exists", col, 1, "column is missing")
            continue
        s = df[col]
        if rules.get("not_null"):
            add("not_null", col, int(s.isna().sum()))
        if rules.get("unique"):
            add("unique", col, int(s.duplicated().sum()))
        if "min" in rules or "max" in rules:
            num = pd.to_numeric(s, errors="coerce")
            bad = pd.Series(False, index=s.index)
            if "min" in rules:
                bad |= num < rules["min"]
            if "max" in rules:
                bad |= num > rules["max"]
            bad |= num.isna() & s.notna()  # non-numeric can't satisfy a range
            add("range", col, int(bad.sum()),
                f"[{rules.get('min', '-inf')}, {rules.get('max', 'inf')}]")
        if "allowed" in rules:
            add("allowed", col,
                int((~s.isin(rules["allowed"]) & s.notna()).sum()),
                f"allowed: {rules['allowed']}")
        if "regex" in rules:
            rx = re.compile(rules["regex"])
            non_null = s.dropna().astype(str)
            add("regex", col,
                int((~non_null.str.match(rx)).sum()), rules["regex"])

    return {"results": results, "passed": all(r["passed"] for r in results),
            "n_violations": sum(r["violations"] for r in results)}
