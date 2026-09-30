"""LLM planner tests with a mocked Ollama — validation, retry, fallback,
and the full clean loop without a real model (CI has no GPU/Ollama)."""

import json

import pandas as pd
import pytest

from yoda.executor import execute
from yoda.planner import (LLMPlanner, PlanValidationError, RuleBasedPlanner,
                          validate_plan)
from yoda.profiler import profile

DF = pd.DataFrame({
    "d": ["03/04/2021", "2021-01-01", "March 4, 2021"] * 4,
    "cat": ["Yes", "Yes", "yes", "No"] * 3,
    "n": [1, 2, 3, 4] * 3,
})
PROF = profile(DF)

GOOD_PLAN = {"steps": [
    {"tool": "normalize_dates", "col": "d", "params": {},
     "reason": "3 date formats seen"},
    {"tool": "standardize_categories", "col": "cat", "params": {},
     "reason": "casing variants"},
]}


def make_planner(replies: list[str], strategy: str = "single") -> LLMPlanner:
    p = LLMPlanner(model="mock", strategy=strategy)
    it = iter(replies)
    p._chat = lambda messages, think=None, **kw: next(it)
    return p


def test_valid_plan_accepted_first_try():
    p = make_planner([json.dumps(GOOD_PLAN)])
    steps = p.plan(PROF)
    assert [s["tool"] for s in steps] == ["normalize_dates", "standardize_categories"]
    assert p.last_outcome["source"] == "llm" and p.last_outcome["attempts"] == 1


def test_invalid_then_valid_uses_retry():
    bad = json.dumps({"steps": [{"tool": "normalize_dates", "col": "nope",
                                 "params": {}, "reason": "x"}]})
    p = make_planner([bad, json.dumps(GOOD_PLAN)])
    steps = p.plan(PROF)
    assert p.last_outcome["attempts"] == 2 and len(steps) == 2


def test_persistent_garbage_falls_back_to_rule_based():
    p = make_planner(["not json"] * 3)
    steps = p.plan(PROF)
    assert p.last_outcome["source"] == "fallback_rule_based"
    assert steps == RuleBasedPlanner().plan(PROF)


def test_ollama_down_falls_back_immediately():
    p = LLMPlanner(model="mock", host="http://localhost:1", timeout=1)
    steps = p.plan(PROF)
    assert p.last_outcome["source"] == "fallback_rule_based"
    assert steps == RuleBasedPlanner().plan(PROF)


def test_validate_rejects_unknown_column():
    with pytest.raises(PlanValidationError):
        validate_plan({"steps": [{"tool": "trim_whitespace", "col": "ghost",
                                  "params": {}, "reason": "x"}]}, PROF)


def test_validate_rejects_silent_imputation():
    with pytest.raises(PlanValidationError):
        validate_plan({"steps": [{"tool": "impute_missing", "col": "n",
                                  "params": {"strategy": "mean"}, "reason": "x"}]}, PROF)


def test_validate_accepts_snake_cased_names_after_rename():
    prof = profile(pd.DataFrame({"Order Date": ["03/04/2021", "2021-01-01"]}))
    plan = {"steps": [
        {"tool": "rename_columns", "col": None, "params": {}, "reason": "x"},
        {"tool": "normalize_dates", "col": "order_date", "params": {}, "reason": "x"},
    ]}
    assert len(validate_plan(plan, prof)) == 2


def test_full_loop_with_mocked_llm(tmp_path):
    """profile → (mocked) LLM plan → execute → audit: the Phase 2 loop."""
    p = make_planner([json.dumps(GOOD_PLAN)])
    plan = p.plan(PROF)
    cleaned, audit = execute(DF, plan, tmp_path / "audit.jsonl")
    assert set(cleaned["d"]) == {"2021-03-04", "2021-01-01"}
    assert set(cleaned["cat"]) <= {"Yes", "No"}
    assert all(e["status"] == "ok" for e in audit)


DATES_ONLY = {"steps": [GOOD_PLAN["steps"][0]]}


def test_vote3_keeps_the_majority_plan():
    """Idea 1: two of three samples agree, so that plan wins over the odd one."""
    p = make_planner([json.dumps(DATES_ONLY), json.dumps(GOOD_PLAN),
                      json.dumps(GOOD_PLAN)], strategy="vote3")
    steps = p.plan(PROF, instruction="fix the dates and the categories")
    assert len(steps) == 2 and p.last_outcome["votes"] == 2


def test_vote3_tie_takes_the_first_sample():
    empty = json.dumps({"steps": []})
    p = make_planner([json.dumps(DATES_ONLY), json.dumps(GOOD_PLAN), empty],
                     strategy="vote3")
    steps = p.plan(PROF, instruction="fix the dates")
    assert [s["tool"] for s in steps] == ["normalize_dates"]


def test_intent_hint_reaches_the_plan_prompt():
    """Idea 2: the tool named by the first call is stated in the second."""
    seen = []
    p = LLMPlanner(model="mock", strategy="intent")
    replies = iter([json.dumps({"tool": "none"}), json.dumps({"steps": []})])
    def fake(messages, think=None, **kw):
        seen.append(messages[-1]["content"])
        return next(replies)
    p._chat = fake
    assert p.plan(PROF, instruction="what's the weather?") == []
    assert "does not ask for any cleaning tool" in seen[1]


def test_strategy_ignored_without_instruction():
    """Autonomous plans (the corruption benchmark) always take one sample."""
    p = make_planner([json.dumps(GOOD_PLAN)], strategy="vote3")
    assert len(p.plan(PROF)) == 2 and "votes" not in p.last_outcome
