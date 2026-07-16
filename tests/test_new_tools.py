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
drop_rows_where = TOOLS["drop_rows_where"]
scale_numeric = TOOLS["scale_numeric"]
format_text = TOOLS["format_text"]
round_numbers = TOOLS["round_numbers"]
flag_outliers = TOOLS["flag_outliers"]


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


def test_drop_rows_where_conditions():
    df = pd.DataFrame({"status": ["Active", "inactive", "Active", None],
                       "age": ["25", "200", "40", "30"]})
    out, s = drop_rows_where(df, "status", {"equals": "inactive"})
    assert s["rows_affected"] == 1 and len(out) == 3
    out, s = drop_rows_where(df, "status", {"equals": "ACTIVE",
                                            "match_case": False})
    assert s["rows_affected"] == 2
    out, s = drop_rows_where(df, "status", {"is_null": True})
    assert s["rows_affected"] == 1
    out, s = drop_rows_where(df, "age", {"min": 0, "max": 120})
    assert s["rows_affected"] == 1 and "200" not in out["age"].values
    out, s = drop_rows_where(df, "status", {"equals": "Active", "keep": True})
    assert len(out) == 2 and set(out["status"]) == {"Active"}
    out, s = drop_rows_where(df, "status", {"contains": "activ",
                                            "match_case": False})
    assert s["rows_affected"] == 3
    with pytest.raises(ValueError):
        drop_rows_where(df, "status", {})


def test_scale_numeric_minmax_and_zscore():
    df = pd.DataFrame({"v": [10.0, 20.0, 30.0, None]})
    out, s = scale_numeric(df, "v", {"method": "minmax"})
    assert list(out["v"].dropna()) == [0.0, 0.5, 1.0]
    assert s["min"] == 10.0 and s["max"] == 30.0
    out, s = scale_numeric(df, "v", {"method": "zscore"})
    assert abs(out["v"].dropna().mean()) < 1e-9
    with pytest.raises(ValueError):
        scale_numeric(pd.DataFrame({"v": [5, 5, 5]}), "v")


def test_format_text_cases():
    df = pd.DataFrame({"n": ["ana CRUZ", "BEN reyes", None]})
    out, s = format_text(df, "n", {"case": "title"})
    assert list(out["n"].dropna()) == ["Ana Cruz", "Ben Reyes"]
    assert s["rows_affected"] == 2
    out, _ = format_text(df, "n", {"case": "upper"})
    assert out["n"][0] == "ANA CRUZ"
    with pytest.raises(ValueError):
        format_text(df, "n", {"case": "spongebob"})


def test_round_numbers_preserves_text():
    df = pd.DataFrame({"p": [1.239, 2.5, "n/a", None]})
    out, s = round_numbers(df, "p", {"decimals": 1})
    assert out["p"][0] == 1.2 and out["p"][2] == "n/a"
    assert s["rows_affected"] == 1        # 2.5 already at 1 decimal


def test_replace_values_contains_substring():
    df = pd.DataFrame({"c": ["plan a x", "a-team", "beta", None]})
    out, s = replace_values(df, "c", {"find": "a", "replace": "b",
                                      "contains": True})
    assert list(out["c"].dropna()) == ["plbn b x", "b-tebm", "betb"]
    assert s["rows_affected"] == 3


def test_flag_outliers_drop_action():
    df = pd.DataFrame({"v": [10, 11, 12, 11, 10, 999]})
    out, s = flag_outliers(df, "v", {"method": "iqr", "action": "drop"})
    assert s["rows_affected"] == 1 and 999 not in out["v"].values
    assert "v_outlier" not in out.columns


def test_drop_blank_columns_multi():
    df = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
    out, s = drop_blank_columns(df, None, {"columns": ["a", "c"]})
    assert list(out.columns) == ["b"]
    with pytest.raises(ValueError):
        drop_blank_columns(df, None, {"columns": ["nope"]})


def test_instruction_only_tools_gated():
    prof = profile(pd.DataFrame({"v": [1.0, 2.0, 3.0]}))
    for step in [
        {"tool": "drop_rows_where", "col": "v", "params": {"min": 0},
         "reason": "r"},
        {"tool": "scale_numeric", "col": "v", "params": {}, "reason": "r"},
        {"tool": "format_text", "col": "v", "params": {}, "reason": "r"},
        {"tool": "round_numbers", "col": "v", "params": {}, "reason": "r"},
        {"tool": "flag_outliers", "col": "v",
         "params": {"action": "drop"}, "reason": "r"},
    ]:
        plan = {"steps": [step]}
        with pytest.raises(PlanValidationError):
            validate_plan(plan, prof)                        # autonomous: no
        assert validate_plan(plan, prof, allow_impute_fill=True)  # asked: yes


def test_executor_resolves_name_form_drift():
    """A plan that says 'full_name' must still work when the data has
    'Full Name' (rename_columns skipped or ordered later)."""
    from yoda.executor import execute
    df = pd.DataFrame({"Full Name": [" ana ", "ben"], "Age": [1, 2]})
    cleaned, audit = execute(df, [
        {"tool": "trim_whitespace", "col": "full_name", "params": {},
         "reason": "r"}])
    assert audit[0]["status"] == "ok"
    assert audit[0]["col_resolved_to"] == "Full Name"
    assert cleaned["Full Name"][0] == "ana"
    # ambiguous or truly missing names still fail loudly
    df2 = pd.DataFrame({"a b": [1], "a_b": [2]})
    _, audit2 = execute(df2, [{"tool": "trim_whitespace", "col": "a_b",
                               "params": {}, "reason": "r"}])
    assert audit2[0]["status"] == "ok"          # exact match wins
    _, audit3 = execute(df, [{"tool": "trim_whitespace", "col": "ghost",
                              "params": {}, "reason": "r"}])
    assert audit3[0]["status"] == "error"


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
