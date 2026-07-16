"""Instruction-following benchmark: does the planner route plain-language
asks to the right tool, column, and params?

Every case is labeled with the step(s) a correct plan must contain. Cases
cover verbatim tool asks, paraphrases, typos, column-scoped requests, and
should-refuse asks (vague/off-topic -> expect an empty plan). Extra steps
beyond the expected ones are allowed (the profile is genuinely dirty) but
counted, since an obedient agent should stay close to what was asked.

Usage:  python -m benchmark.run_instructions [--model qwen3.5:4b]

Writes benchmark/results/instructions/<model>.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from yoda.planner import LLMPlanner
from yoda.profiler import profile

RESULTS_DIR = Path(__file__).parent / "results" / "instructions"


def fixture() -> pd.DataFrame:
    """Small table whose dirt matches what the instructions talk about."""
    df = pd.DataFrame({
        "department": ["Sales", "HR", "Sales", "IT", "HR", "Sales", "IT", "HR"],
        "city": ["Manila", "Cebu", "Davao", "Cebu", "Manila", "Davao", "Cebu", "Manila"],
        "status": ["Active", "active", "ACTIVE", "Inactive", "active", "Active",
                   "INACTIVE", "Active"],
        "name": [" Ana Cruz", "Ben  Reyes ", "Carla Lim", None, "Dan Yu ", "Eva Tan",
                 "Fe Sy", "Gio Uy"],
        "birthday": ["1990-01-05", "02/14/1991", "March 3, 1992", "1993-04-01",
                     "05/06/1994", "1995-07-08", "06/07/1996", "1997-09-10"],
        "phone": ["09171234567", "+639181234567", "0917 123 4567", "09191234567",
                  "63-917-123-4567", "09201234567", "09211234567", "09221234567"],
        "price": ["₱1,200.00", "PHP 1500", "₱980.50", "PHP 2000", "₱1,100.00",
                  "₱750.00", "PHP 1250", "₱990.00"],
        "qty": ["10", "5", "8", "12", "3", "7", "9", "4"],
        "age": [25.0, 31.0, None, 45.0, 29.0, None, 38.0, 27.0],
        "note": [None, None, None, None, None, None, None, None],
    })
    dup = df.iloc[[0]]                                   # 1 exact duplicate row
    out = pd.concat([df, dup], ignore_index=True)
    out.loc[len(out)] = {c: None for c in out.columns}   # 1 fully blank row
    return out


# expect: list of {tool, col (optional), params (optional subset)}.
# expect_empty: the correct answer is to propose nothing.
CASES: list[dict] = [
    # --- blank rows / columns -------------------------------------------
    {"id": "blank_rows_verbatim", "kind": "verbatim",
     "instruction": "remove blank rows",
     "expect": [{"tool": "drop_blank_rows"}]},
    {"id": "blank_rows_paraphrase", "kind": "paraphrase",
     "instruction": "get rid of the completely empty lines in this table",
     "expect": [{"tool": "drop_blank_rows"}]},
    {"id": "blank_rows_typo", "kind": "typo",
     "instruction": "remvoe the blnak rows plz",
     "expect": [{"tool": "drop_blank_rows"}]},
    {"id": "blank_cols_verbatim", "kind": "verbatim",
     "instruction": "remove empty columns",
     "expect": [{"tool": "drop_blank_columns"}]},
    {"id": "drop_named_col", "kind": "scoped",
     "instruction": "delete the note column, I don't need it",
     "expect": [{"tool": "drop_blank_columns", "col": "note"}]},
    # --- replace values --------------------------------------------------
    {"id": "replace_verbatim", "kind": "verbatim",
     "instruction": "replace 'Sales' with 'SLS' in department",
     "expect": [{"tool": "replace_values", "col": "department",
                 "params": {"find": "Sales", "replace": "SLS"}}]},
    {"id": "replace_paraphrase", "kind": "paraphrase",
     "instruction": "in the city column change Manila to MNL",
     "expect": [{"tool": "replace_values", "col": "city",
                 "params": {"find": "Manila", "replace": "MNL"}}]},
    # --- encode categories -----------------------------------------------
    {"id": "encode_users_exact", "kind": "verbatim",
     "instruction": "change the department to 1,2,3,4 depending on their unique value",
     "expect": [{"tool": "encode_categories", "col": "department"}]},
    {"id": "encode_paraphrase1", "kind": "paraphrase",
     "instruction": "turn the city column into numbers",
     "expect": [{"tool": "encode_categories", "col": "city"}]},
    {"id": "encode_paraphrase2", "kind": "paraphrase",
     "instruction": "give each department a code number",
     "expect": [{"tool": "encode_categories", "col": "department"}]},
    {"id": "encode_typo", "kind": "typo",
     "instruction": "chnage city to nubmers based on unique vlaue",
     "expect": [{"tool": "encode_categories", "col": "city"}]},
    # --- duplicates -------------------------------------------------------
    {"id": "dedupe_verbatim", "kind": "verbatim",
     "instruction": "remove duplicates",
     "expect": [{"tool": "drop_duplicates"}]},
    {"id": "dedupe_paraphrase", "kind": "paraphrase",
     "instruction": "some rows appear twice, keep only one of each",
     "expect": [{"tool": "drop_duplicates"}]},
    # --- dates ------------------------------------------------------------
    {"id": "dates_verbatim", "kind": "verbatim",
     "instruction": "fix the dates in birthday",
     "expect": [{"tool": "normalize_dates", "col": "birthday"}]},
    {"id": "dates_paraphrase", "kind": "paraphrase",
     "instruction": "the birthday column has several different date styles, make them consistent",
     "expect": [{"tool": "normalize_dates", "col": "birthday"}]},
    # --- phones / currency -------------------------------------------------
    {"id": "phone_paraphrase", "kind": "paraphrase",
     "instruction": "standardize the phone numbers to one format",
     "expect": [{"tool": "normalize_phone", "col": "phone"}]},
    {"id": "currency_paraphrase", "kind": "paraphrase",
     "instruction": "the price column has peso signs and commas, clean it into plain numbers",
     "expect": [{"tool": "normalize_currency", "col": "price"}]},
    # --- categories / casing -----------------------------------------------
    {"id": "casing_verbatim", "kind": "verbatim",
     "instruction": "make the status casing consistent",
     "expect": [{"tool": "standardize_categories", "col": "status"}]},
    {"id": "casing_paraphrase", "kind": "paraphrase",
     "instruction": "Active, active and ACTIVE should be one category in status",
     "expect": [{"tool": "standardize_categories", "col": "status"}]},
    # --- dtypes -------------------------------------------------------------
    {"id": "dtype_paraphrase", "kind": "paraphrase",
     "instruction": "qty is stored as text, make it an actual number",
     "expect": [{"tool": "fix_dtypes", "col": "qty",
                 "params": {"target": "numeric"}}]},
    # --- missing values ------------------------------------------------------
    {"id": "impute_mean", "kind": "verbatim",
     "instruction": "fill missing age with the average",
     "expect": [{"tool": "impute_missing", "col": "age",
                 "params": {"strategy": "mean"}}]},
    {"id": "impute_flag", "kind": "paraphrase",
     "instruction": "mark which rows are missing an age, don't fill anything",
     "expect": [{"tool": "impute_missing", "col": "age",
                 "params": {"strategy": "flag_only"}}]},
    # --- outliers / validation -----------------------------------------------
    {"id": "outliers_paraphrase", "kind": "paraphrase",
     "instruction": "flag any unusual values in age",
     "expect": [{"tool": "flag_outliers", "col": "age"}]},
    {"id": "rule_scoped", "kind": "scoped",
     "instruction": "flag ages outside 0 to 120",
     "expect": [{"tool": "validate_rule", "col": "age",
                 "params": {"min": 0, "max": 120}}]},
    # --- whitespace / renames ---------------------------------------------
    {"id": "trim_paraphrase", "kind": "paraphrase",
     "instruction": "strip the extra spaces from the name column",
     "expect": [{"tool": "trim_whitespace", "col": "name"}]},
    # --- conditional row deletion -------------------------------------------
    {"id": "drop_where_equals", "kind": "verbatim",
     "instruction": "delete rows where status is Inactive",
     "expect": [{"tool": "drop_rows_where", "col": "status",
                 "params": {"equals": "Inactive"}}]},
    {"id": "drop_where_paraphrase", "kind": "paraphrase",
     "instruction": "get rid of every customer whose department is HR",
     "expect": [{"tool": "drop_rows_where", "col": "department",
                 "params": {"equals": "HR"}}]},
    {"id": "drop_where_null", "kind": "paraphrase",
     "instruction": "remove the rows that have no age",
     "expect": [{"tool": "drop_rows_where", "col": "age",
                 "params": {"is_null": True}}]},
    {"id": "keep_only", "kind": "scoped",
     "instruction": "keep only the rows where department is Sales",
     "expect": [{"tool": "drop_rows_where", "col": "department",
                 "params": {"equals": "Sales", "keep": True}}]},
    # --- transforms ------------------------------------------------------------
    {"id": "scale_minmax", "kind": "verbatim",
     "instruction": "normalize age between 0 and 1",
     "expect": [{"tool": "scale_numeric", "col": "age",
                 "params": {"method": "minmax"}}]},
    {"id": "scale_zscore", "kind": "paraphrase",
     "instruction": "standardize the age column to z-scores",
     "expect": [{"tool": "scale_numeric", "col": "age",
                 "params": {"method": "zscore"}}]},
    {"id": "case_upper", "kind": "paraphrase",
     "instruction": "make all the city names uppercase",
     "expect": [{"tool": "format_text", "col": "city",
                 "params": {"case": "upper"}}]},
    {"id": "round_two", "kind": "verbatim",
     "instruction": "round age to 0 decimals",
     "expect": [{"tool": "round_numbers", "col": "age",
                 "params": {"decimals": 0}}]},
    {"id": "replace_every", "kind": "paraphrase",
     "instruction": "replace every occurrence of 'Cruz' with 'Crus' in name",
     "expect": [{"tool": "replace_values", "col": "name",
                 "params": {"find": "Cruz", "replace": "Crus"}}]},
    {"id": "drop_outliers", "kind": "verbatim",
     "instruction": "remove the outliers in age",
     "expect": [{"tool": "flag_outliers", "col": "age",
                 "params": {"action": "drop"}}]},
    {"id": "drop_two_columns", "kind": "scoped",
     "instruction": "drop the note and phone columns, I don't need them",
     # either one multi-column step or two single-column steps is correct
     "expect_any": [
         [{"tool": "drop_blank_columns",
           "params": {"columns": ["note", "phone"]}}],
         [{"tool": "drop_blank_columns",
           "params": {"columns": ["phone", "note"]}}],
         [{"tool": "drop_blank_columns", "col": "note"},
          {"tool": "drop_blank_columns", "col": "phone"}],
         [{"tool": "drop_blank_columns", "params": {"columns": ["note"]}},
          {"tool": "drop_blank_columns", "params": {"columns": ["phone"]}}],
     ]},
    # --- should refuse -------------------------------------------------------
    {"id": "refuse_vague", "kind": "refusal",
     "instruction": "make the data look better for my boss",
     "expect_empty": True},
    {"id": "refuse_offtopic", "kind": "refusal",
     "instruction": "what's the weather in Manila today?",
     "expect_empty": True},
    {"id": "refuse_destructive", "kind": "refusal",
     "instruction": "delete everything",
     "expect_empty": True},
]


def step_matches(expected: dict, step: dict) -> bool:
    if step["tool"] != expected["tool"]:
        return False
    if "col" in expected and step.get("col") != expected["col"]:
        return False
    sp = step.get("params", {})
    for k, v in expected.get("params", {}).items():
        got = sp.get(k)
        if got == v:
            continue
        # A case-insensitive match (match_case=false) satisfies a value
        # expectation for text-matching params — same rows are hit.
        if (k in ("equals", "find", "contains") and sp.get("match_case") is False
                and str(got).lower() == str(v).lower()):
            continue
        return False
    return True


def score_case(case: dict, steps: list[dict]) -> dict:
    if case.get("expect_empty"):
        return {"pass": len(steps) == 0, "extra_steps": len(steps)}
    # expect_any: several equally-correct plan shapes; best one wins.
    alternatives = case.get("expect_any") or [case["expect"]]
    best = {"pass": False, "extra_steps": len(steps)}
    for expect in alternatives:
        matched = all(any(step_matches(e, s) for s in steps) for e in expect)
        extras = sum(1 for s in steps
                     if not any(step_matches(e, s) for e in expect))
        if matched and (not best["pass"] or extras < best["extra_steps"]):
            best = {"pass": True, "extra_steps": extras}
        elif not best["pass"]:
            best["extra_steps"] = min(best["extra_steps"], extras)
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.5:4b")
    args = ap.parse_args()

    prof = profile(fixture())
    planner = LLMPlanner(model=args.model)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    label = args.model.replace(":", "_")

    rows, n_pass, extra_total = [], 0, 0
    by_kind: dict[str, dict] = {}
    for case in CASES:
        steps = planner.plan(prof, instruction=case["instruction"])
        outcome = planner.last_outcome
        if outcome["source"] != "llm":
            # Fallback plans don't measure the model; count as fail.
            result = {"pass": False, "extra_steps": 0}
        else:
            result = score_case(case, steps)
        n_pass += result["pass"]
        extra_total += result["extra_steps"]
        k = by_kind.setdefault(case["kind"], {"n": 0, "pass": 0})
        k["n"] += 1
        k["pass"] += result["pass"]
        rows.append({"case": case, "steps": steps, "result": result,
                     "outcome": outcome})
        mark = "PASS" if result["pass"] else "FAIL"
        print(f"{mark}  {case['id']:24s} ({case['kind']}) "
              f"extras={result['extra_steps']} attempts={outcome.get('attempts')}")

    n = len(CASES)
    print(f"\n{args.model}: {n_pass}/{n} routed correctly "
          f"({n_pass / n:.1%}), {extra_total} extra steps total")

    lines = [f"# Instruction-following benchmark — `{args.model}`", "",
             f"**{n_pass}/{n} instructions routed to the correct tool/column/params "
             f"({n_pass / n:.1%})** — {extra_total} unrequested extra steps across all cases.",
             "", "| kind | cases | pass |", "|---|---:|---:|"]
    for kind, k in sorted(by_kind.items()):
        lines.append(f"| {kind} | {k['n']} | {k['pass']}/{k['n']} |")
    lines += ["", "| case | kind | instruction | pass | extras |",
              "|---|---|---|---|---:|"]
    for r in rows:
        c = r["case"]
        lines.append(f"| {c['id']} | {c['kind']} | {c['instruction']} "
                     f"| {'yes' if r['result']['pass'] else 'NO'} "
                     f"| {r['result']['extra_steps']} |")
    (RESULTS_DIR / f"{label}.md").write_text("\n".join(lines) + "\n",
                                             encoding="utf-8")
    (RESULTS_DIR / f"{label}.json").write_text(
        json.dumps(rows, indent=1, default=str), encoding="utf-8")
    print(f"Wrote {RESULTS_DIR / (label + '.md')}")


if __name__ == "__main__":
    main()
