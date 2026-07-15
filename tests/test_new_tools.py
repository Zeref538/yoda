"""New cleaning tools: drop_blank_rows, drop_blank_columns, replace_values —
plus profiler blank signals, rule-based planner coverage, and the
allow_impute_fill validation gate."""

import pandas as pd
import pytest

from yoda.planner import (PlanValidationError, RuleBasedPlanner, validate_plan)
from yoda.profiler import profile
from yoda.tools import TOOLS

drop_blank_rows = TOOLS["drop_blank_rows"]
drop_blank_columns = TOOLS["drop_blank_columns"]
replace_values = TOOLS["replace_values"]
encode_categories = TOOLS["encode_categories"]


def blanky_df():
    return pd.DataFrame({
        "a": [1, None, 3, None],
        "b": ["x", "  ", "y", None],
        "empty": [None, None, None, "   "],
    })


def test_drop_blank_rows_all_null_and_whitespace():
    out, stats = drop_blank_rows(blanky_df())
    assert stats["rows_affected"] == 2          # rows 1 and 3 are blank
    assert list(out.index) == [0, 2]            # index preserved


def test_drop_blank_rows_scoped_to_column():
    out, stats = drop_blank_rows(blanky_df(), col="a")
    assert stats["rows_affected"] == 2
    assert out["a"].notna().all()


def test_drop_blank_rows_noop_on_clean():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    out, stats = drop_blank_rows(df)
    assert stats["rows_affected"] == 0
    assert out.equals(df)


def test_drop_blank_columns_detects_empty():
    out, stats = drop_blank_columns(blanky_df())
    assert stats["columns_dropped"] == ["empty"]
    assert list(out.columns) == ["a", "b"]


def test_drop_blank_columns_explicit_col():
    out, stats = drop_blank_columns(blanky_df(), col="b")
    assert stats["columns_dropped"] == ["b"]
    with pytest.raises(ValueError):
        drop_blank_columns(blanky_df(), col="nope")


def test_replace_values_exact_and_case():
    df = pd.DataFrame({"c": ["N/A", "n/a", "ok", None]})
    out, stats = replace_values(df, "c", {"find": "N/A", "replace": ""})
    assert stats["rows_affected"] == 1
    out, stats = replace_values(df, "c", {"find": "N/A", "replace": "",
                                          "match_case": False})
    assert stats["rows_affected"] == 2
    assert out["c"].isna().sum() == 1           # nulls untouched


def test_replace_values_regex_and_errors():
    df = pd.DataFrame({"c": ["id-001", "id-002", "x"]})
    out, stats = replace_values(df, "c", {"find": r"^id-", "replace": "",
                                          "regex": True})
    assert stats["rows_affected"] == 2
    assert list(out["c"]) == ["001", "002", "x"]
    with pytest.raises(ValueError):
        replace_values(df, "c", {})              # missing find
    with pytest.raises(ValueError):
        replace_values(df, "c", {"find": "(", "regex": True})


def test_encode_categories_sorted_in_place():
    df = pd.DataFrame({"dept": ["Sales", "HR", "Sales", "IT", None]})
    out, stats = encode_categories(df, "dept")
    assert stats["mapping"] == {"HR": 1, "IT": 2, "Sales": 3}   # sorted, 1-based
    assert list(out["dept"].dropna()) == [3, 1, 3, 2]
    assert out["dept"].isna().sum() == 1                        # null preserved
    assert stats["n_categories"] == 3


def test_encode_categories_start_and_new_column():
    df = pd.DataFrame({"g": ["b", "a", "b"]})
    out, stats = encode_categories(df, "g", {"start": 0, "new_column": True})
    assert stats["mapping"] == {"a": 0, "b": 1}
    assert list(out["g"]) == ["b", "a", "b"]                    # original kept
    assert list(out["g_code"]) == [1, 0, 1]
    assert stats["target"] == "g_code"


def test_encode_categories_orderings():
    df = pd.DataFrame({"g": ["b", "b", "a", "c", "c", "c"]})
    _, freq = encode_categories(df, "g", {"order": "frequency"})
    assert freq["mapping"]["c"] == 1                            # most frequent -> 1
    _, appear = encode_categories(df, "g", {"order": "appearance"})
    assert appear["mapping"] == {"b": 1, "a": 2, "c": 3}        # order seen


def test_profiler_blank_signals():
    prof = profile(blanky_df())
    assert prof["blank_rows"] == 2
    assert prof["blank_columns"] == ["empty"]
    clean = profile(pd.DataFrame({"a": [1, 2]}))
    assert "blank_rows" not in clean and "blank_columns" not in clean


def test_rule_based_planner_proposes_blank_fixes():
    steps = RuleBasedPlanner().plan(profile(blanky_df()))
    tools = [s["tool"] for s in steps]
    assert "drop_blank_rows" in tools
    assert "drop_blank_columns" in tools


def test_validate_plan_impute_fill_gate():
    prof = profile(pd.DataFrame({"n": [1.0, None, 3.0]}))
    plan = {"steps": [{"tool": "impute_missing", "col": "n",
                       "params": {"strategy": "mean"}, "reason": "user asked"}]}
    with pytest.raises(PlanValidationError):
        validate_plan(plan, prof)                       # autonomous: forbidden
    assert validate_plan(plan, prof, allow_impute_fill=True)  # human ask: ok


def test_validate_plan_new_whole_table_tools():
    prof = profile(blanky_df())
    plan = {"steps": [
        {"tool": "drop_blank_rows", "col": None, "params": {}, "reason": "r"},
        {"tool": "drop_blank_columns", "col": "empty", "params": {}, "reason": "r"},
        {"tool": "replace_values", "col": "b", "params": {"find": "x"},
         "reason": "r"},
    ]}
    assert len(validate_plan(plan, prof)) == 3
    bad = {"steps": [{"tool": "replace_values", "col": "b", "params": {},
                      "reason": "r"}]}
    with pytest.raises(PlanValidationError):
        validate_plan(bad, prof)
