"""Recipes (save/load/replay) and watch-folder mode."""

import json

import pytest

from benchmark.corruptor import corrupt
from benchmark.datasets import ph_customers
from yoda.recipe import load_recipe, save_recipe
from yoda.watch import scan_once

STEPS = [
    {"tool": "drop_duplicates", "col": None, "params": {}, "reason": "dupes"},
    {"tool": "normalize_phone", "col": "phone", "params": {}, "reason": "formats"},
    {"tool": "normalize_dates", "col": "signup_date", "params": {}, "reason": "formats"},
    {"tool": "trim_whitespace", "col": "full_name", "params": {}, "reason": "ws"},
]


def _dirty(n=80, seed=3):
    clean = ph_customers(n=n, seed=seed)
    dirty, _ = corrupt(clean, "ph_customers", seed=seed)
    return dirty


def test_recipe_roundtrip(tmp_path):
    p = save_recipe(STEPS, tmp_path / "r.json", source="x.csv")
    loaded = load_recipe(p)
    assert loaded == STEPS
    meta = json.loads(p.read_text(encoding="utf-8"))
    assert meta["yoda_recipe"] == 1 and meta["source"] == "x.csv"


def test_recipe_rejects_garbage(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"steps": [{"tool": "rm_rf", "col": None,
                                          "params": {}, "reason": "?"}]}))
    with pytest.raises(Exception):
        load_recipe(bad)


def test_watch_cleans_matching_file(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _dirty().to_csv(inbox / "batch1.csv", index=False)
    results = scan_once(inbox, STEPS, tmp_path / "out", tmp_path / "q", set())
    assert len(results) == 1
    # phone/date/name dirt is fixed by the recipe, but nulls/casing/currency
    # aren't in it — those verdicts stay open, so the file is quarantined
    # rather than silently shipped. That's the designed behavior.
    r = results[0]
    assert r["status"] in ("cleaned", "quarantined")
    if r["status"] == "quarantined":
        assert (tmp_path / "q" / "batch1_REASON.txt").exists()
        assert (tmp_path / "q" / "batch1_attempt.csv").exists()
    else:
        assert (tmp_path / "out" / "batch1_cleaned.csv").exists()


def test_watch_full_recipe_ships_clean_file(tmp_path):
    """A recipe covering all the dirt should land in out/, not quarantine."""
    full = STEPS + [
        {"tool": "normalize_currency", "col": "monthly_spend", "params": {},
         "reason": "currency"},
        {"tool": "standardize_categories", "col": "city", "params": {}, "reason": "case"},
        {"tool": "standardize_categories", "col": "segment", "params": {}, "reason": "case"},
        {"tool": "impute_missing", "col": "email",
         "params": {"strategy": "flag_only"}, "reason": "nulls"},
        {"tool": "impute_missing", "col": "monthly_spend",
         "params": {"strategy": "flag_only"}, "reason": "nulls"},
        {"tool": "trim_whitespace", "col": "email", "params": {}, "reason": "ws"},
    ]
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _dirty().to_csv(inbox / "weekly.csv", index=False)
    results = scan_once(inbox, full, tmp_path / "out", tmp_path / "q", set())
    assert results[0]["status"] == "cleaned", results[0]
    assert (tmp_path / "out" / "weekly_cleaned.csv").exists()
    assert (tmp_path / "out" / "weekly_report.md").exists()
    assert (tmp_path / "out" / "weekly_audit.jsonl").exists()


def test_watch_quarantines_wrong_schema(tmp_path):
    import pandas as pd
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pd.DataFrame({"totally": [1], "different": [2]}).to_csv(
        inbox / "wrong.csv", index=False)
    results = scan_once(inbox, STEPS, tmp_path / "out", tmp_path / "q", set())
    assert results[0]["status"] == "quarantined"
    assert "recipe does not fit" in results[0]["reason"]


def test_watch_skips_seen_and_output_files(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _dirty().to_csv(inbox / "a.csv", index=False)
    _dirty().to_csv(inbox / "a_cleaned.csv", index=False)  # output-style name
    seen = set()
    first = scan_once(inbox, STEPS, tmp_path / "out", tmp_path / "q", seen)
    assert len(first) == 1
    assert scan_once(inbox, STEPS, tmp_path / "out", tmp_path / "q", seen) == []
