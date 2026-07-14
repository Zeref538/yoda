"""Verifier + report tests: profile diff verdicts, follow-up round, report.md."""

import pandas as pd

from benchmark.corruptor import corrupt
from benchmark.datasets import retail_orders
from yoda.executor import execute
from yoda.planner import RuleBasedPlanner
from yoda.profiler import profile
from yoda.report import build_report
from yoda.verifier import diff_profiles, follow_up_plan


def test_resolved_and_flagged_verdicts():
    dirty = pd.DataFrame({
        "d": ["03/04/2021", "2021-01-01", "March 4, 2021"] * 4,
        "x": [1.0, None, 3.0, 4.0] * 3,
    })
    before = profile(dirty)
    planner = RuleBasedPlanner()
    cleaned, _ = execute(dirty, planner.plan(before))
    verdicts = {(v["issue"], v["col"]): v["verdict"]
                for v in diff_profiles(before, profile(cleaned))}
    assert verdicts[("mixed_date_formats", "d")] == "resolved"
    assert verdicts[("nulls", "x")] == "flagged"


def test_unresolved_issue_triggers_follow_up():
    dirty = pd.DataFrame({"d": ["03/04/2021", "2021-01-01", "March 4, 2021"] * 4})
    before = profile(dirty)
    # Execute an empty plan: nothing fixed, issue stays open.
    cleaned, _ = execute(dirty, [])
    after = profile(cleaned)
    verdicts = diff_profiles(before, after)
    assert any(v["verdict"] == "unresolved" for v in verdicts)
    followup = follow_up_plan(verdicts, RuleBasedPlanner(), after)
    assert [s["tool"] for s in followup] == ["normalize_dates"]


def test_no_follow_up_when_all_resolved():
    dirty = pd.DataFrame({"d": ["03/04/2021", "2021-01-01"] * 6})
    before = profile(dirty)
    planner = RuleBasedPlanner()
    cleaned, _ = execute(dirty, planner.plan(before))
    after = profile(cleaned)
    assert follow_up_plan(diff_profiles(before, after), planner, after) == []


def test_full_round_loop_on_benchmark_dataset():
    clean = retail_orders(n=200, seed=11)
    dirty, _ = corrupt(clean, "retail_orders", seed=11)
    planner = RuleBasedPlanner()
    before = profile(dirty)
    cleaned, audit = execute(dirty, planner.plan(before))
    after = profile(cleaned)
    verdicts = diff_profiles(before, after)
    assert not any(v["verdict"] == "new_issue" for v in verdicts)
    report = build_report(source="retail.csv", before_profile=before,
                          after_profile=after,
                          rounds=[{"plan": [], "audit": audit}],
                          verdicts=verdicts)
    assert "# YODA cleaning report" in report
    assert "Verification" in report


def test_report_is_redacted():
    """Audit examples flow through redact_sample; PII must not survive."""
    dirty = pd.DataFrame({"email": ["  juandc@gmail.com ", "a@b.com  "]})
    before = profile(dirty)
    planner = RuleBasedPlanner()
    cleaned, audit = execute(dirty, planner.plan(before))
    report = build_report(source="x.csv", before_profile=before,
                          after_profile=profile(cleaned),
                          rounds=[{"plan": [], "audit": audit}],
                          verdicts=diff_profiles(before, profile(cleaned)))
    assert "juandc@gmail.com" not in report
