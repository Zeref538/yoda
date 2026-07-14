"""Planner: proposes a cleaning plan from the profile only.

Two implementations share one interface:
- RuleBasedPlanner (Phase 1): deterministic heuristics — the mandatory baseline.
- LLMPlanner (Phase 2): local model via Ollama, strict-JSON output validated
  against a JSON Schema, max 3 retries, falls back to the rule-based plan.

A plan is a list of steps:
    {"tool": "normalize_dates", "col": "birthday",
     "params": {...}, "reason": "3 date formats found"}
"""

from __future__ import annotations

import re


class RuleBasedPlanner:
    """Baseline heuristic planner: maps profile signals to tool calls."""

    def plan(self, profile: dict) -> list[dict]:
        steps: list[dict] = []
        cols: dict = profile["columns"]

        if any(info.get("non_snake_case_name") for info in cols.values()):
            steps.append({"tool": "rename_columns", "col": None, "params": {},
                          "reason": "non-snake_case column names"})

        if profile["duplicates"]["full_row"] > 0:
            steps.append({"tool": "drop_duplicates", "col": None, "params": {},
                          "reason": f"{profile['duplicates']['full_row']} full-row duplicates"})

        for name, info in cols.items():
            target = self._renamed(name) if any(
                i.get("non_snake_case_name") for i in cols.values()) else name

            if info.get("whitespace_issues") or info.get("non_nfc_values"):
                steps.append({"tool": "trim_whitespace", "col": target, "params": {},
                              "reason": f"{info.get('whitespace_issues', 0)} whitespace / "
                                        f"{info.get('non_nfc_values', 0)} unicode issues"})

            fmts = info.get("date_formats_seen", {})
            if len(fmts) >= 2 or (len(fmts) == 1 and "ISO (YYYY-MM-DD)" not in fmts):
                steps.append({"tool": "normalize_dates", "col": target, "params": {},
                              "reason": f"{len(fmts)} date formats: {sorted(fmts)}"})

            pfmts = info.get("phone_formats_seen", {})
            if pfmts and set(pfmts) != {"intl (+639XXXXXXXXX)"}:
                steps.append({"tool": "normalize_phone", "col": target, "params": {},
                              "reason": f"phone formats: {sorted(pfmts)}"})

            if info.get("currency_like_values"):
                steps.append({"tool": "normalize_currency", "col": target, "params": {},
                              "reason": f"{info['currency_like_values']} currency-style values"})
            elif info.get("bool_as_string"):
                steps.append({"tool": "fix_dtypes", "col": target,
                              "params": {"target": "bool"},
                              "reason": "boolean values stored as strings"})
            elif info.get("numeric_as_string") and not info.get("phone_formats_seen") \
                    and not info.get("casing_variants"):
                steps.append({"tool": "fix_dtypes", "col": target,
                              "params": {"target": "numeric"},
                              "reason": f"{info['numeric_as_string']} numeric values as strings"})

            if info.get("casing_variants"):
                cv = info["casing_variants"]
                steps.append({"tool": "standardize_categories", "col": target, "params": {},
                              "reason": f"{cv['raw_unique']} raw variants fold to "
                                        f"{cv['folded_unique']} categories"})

            if info.get("null_pct", 0) > 0 and info.get("null_pct", 0) < 50:
                steps.append({"tool": "impute_missing", "col": target,
                              "params": {"strategy": "flag_only"},
                              "reason": f"{info['null_pct']}% nulls (flag, never silent-fill)"})

            if info.get("iqr_outliers"):
                steps.append({"tool": "flag_outliers", "col": target,
                              "params": {"method": "iqr"},
                              "reason": f"{info['iqr_outliers']} IQR outliers (flag, don't delete)"})
        return steps

    @staticmethod
    def _renamed(name: str) -> str:
        s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name))
        s = re.sub(r"[^\w]+", "_", s)
        return re.sub(r"_+", "_", s).strip("_").lower()


class LLMPlanner:
    """Ollama-backed planner. Implemented in Phase 2."""

    def __init__(self, model: str = "qwen2.5:7b-instruct") -> None:
        self.model = model

    def plan(self, profile: dict) -> list[dict]:
        raise NotImplementedError("Phase 2")
