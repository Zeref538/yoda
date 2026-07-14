"""Profiler → rule-based planner → executor → scorer, end to end (no LLM)."""

import json

import pandas as pd

from benchmark.corruptor import corrupt
from benchmark.datasets import ph_customers
from benchmark.scorer import score
from yoda.executor import execute
from yoda.planner import RuleBasedPlanner
from yoda.profiler import profile


def test_profile_is_json_serializable_and_detects_signals():
    df = pd.DataFrame({
        "Order Date": ["2021-01-01", "03/04/2021", "2021-01-05",
                       "2021-02-01", "2021-02-02", "2021-02-03"],
        "amount": ["₱1,200.00", "PHP 500", "₱99.00", "₱1.00", "PHP 2", "₱3.00"],
        "sex": ["Male", "male", "MALE", "Female", "female", "Male"],
        "age": [30, 31, 29, 32, 30, 3000],
    })
    prof = profile(df)
    json.dumps(prof)  # must not raise
    assert prof["n_rows"] == 6
    assert len(prof["columns"]["Order Date"]["date_formats_seen"]) == 2
    assert prof["columns"]["Order Date"]["non_snake_case_name"]
    assert prof["columns"]["amount"]["currency_like_values"] == 6
    assert prof["columns"]["sex"]["casing_variants"]["folded_unique"] == 2
    assert prof["columns"]["age"]["iqr_outliers"] == 1


def test_executor_writes_audit_log(tmp_path):
    df = pd.DataFrame({"d": ["03/04/2021", "2021-01-01"], "x": [1, 1]})
    plan = [{"tool": "normalize_dates", "col": "d", "params": {}, "reason": "test"},
            {"tool": "bogus_tool", "col": "x", "params": {}, "reason": "test"}]
    audit_path = tmp_path / "audit.jsonl"
    cleaned, audit = execute(df, plan, audit_path)
    assert cleaned["d"].tolist() == ["2021-03-04", "2021-01-01"]
    entries = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert entries[0]["status"] == "ok" and entries[0]["rows_affected"] == 1
    assert entries[1]["status"] == "skipped"
    pd.testing.assert_frame_equal(df, pd.DataFrame({"d": ["03/04/2021", "2021-01-01"],
                                                    "x": [1, 1]}))


def test_full_pipeline_on_corrupted_dataset(tmp_path):
    clean = ph_customers(n=200, seed=7)
    dirty, manifest = corrupt(clean, "ph_customers", seed=7)
    plan = RuleBasedPlanner().plan(profile(dirty))
    assert plan, "planner produced an empty plan on corrupted data"
    cleaned, _ = execute(dirty, plan, tmp_path / "audit.jsonl")
    result = score(clean, cleaned, manifest, plan)
    o = result["overall"]
    assert o["detection_rate"] > 0.7
    assert o["fix_rate"] > 0.5
    assert o["false_fix_rate"] < 0.05
