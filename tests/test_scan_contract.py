"""PII scanner, data contracts, parquet io, multi-table sqlite helpers."""

import json
import sqlite3

import pandas as pd
import pytest

from yoda.contract import load_contract, validate
from yoda.io import list_tables, load, save
from yoda.scan import scan, scan_markdown

PII_DF = pd.DataFrame({
    "customer_id": [1, 2, 3],
    "full_name": ["Juan Dela Cruz", "Maria Santos", "Jose Rizal"],
    "email": ["juan@gmail.com", "maria@yahoo.com", "jose@up.edu.ph"],
    "phone": ["+639171234821", "09285554821", "0917 555 1234"],
    "amount": [10.0, 20.0, 30.0],
})


def test_scan_finds_pii_and_ranks_risk():
    r = scan(PII_DF)
    cols = {f["col"]: f for f in r["columns"]}
    assert "email" in cols and cols["email"]["detected"].get("email") == 3
    assert "phone" in cols and cols["phone"]["risk"] == "high"
    assert "amount" not in cols  # clean numeric column not reported
    assert r["summary"]["highest_risk"] == "high"


def test_scan_report_contains_no_values():
    md = scan_markdown(scan(PII_DF), "x.csv")
    for secret in ["juan@gmail.com", "+639171234821", "Juan Dela Cruz"]:
        assert secret not in md


def test_contract_pass_and_fail(tmp_path):
    c = {"columns": {"age": {"min": 0, "max": 120, "not_null": True},
                     "seg": {"allowed": ["A", "B"]},
                     "id": {"unique": True, "required": True}},
         "table": {"min_rows": 2, "no_duplicate_rows": True}}
    p = tmp_path / "c.json"
    p.write_text(json.dumps(c))
    contract = load_contract(p)

    good = pd.DataFrame({"age": [30, 40], "seg": ["A", "B"], "id": [1, 2]})
    assert validate(good, contract)["passed"]

    bad = pd.DataFrame({"age": [30, 999, None], "seg": ["A", "C", "A"],
                        "id": [1, 1, 2]})
    r = validate(bad, contract)
    assert not r["passed"]
    failed = {(x["rule"], x["col"]) for x in r["results"] if not x["passed"]}
    assert ("range", "age") in failed and ("allowed", "seg") in failed
    assert ("unique", "id") in failed and ("not_null", "age") in failed


def test_contract_yaml_and_missing_column(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("columns:\n  ghost: {not_null: true}\n")
    r = validate(pd.DataFrame({"a": [1]}), load_contract(p))
    assert not r["passed"]
    assert r["results"][0]["rule"] == "column_exists"


def test_contract_rejects_unknown_rule(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"columns": {"a": {"explode": True}}}))
    with pytest.raises(ValueError):
        load_contract(p)


def test_parquet_roundtrip(tmp_path):
    pytest.importorskip("pyarrow")
    src = tmp_path / "d.parquet"
    PII_DF.to_parquet(src, index=False)
    df = load(src)
    assert len(df) == 3
    out = save(df, src)
    assert out.name == "d_cleaned.parquet" and load(out).shape == df.shape


def test_list_tables(tmp_path):
    db = tmp_path / "x.sqlite"
    with sqlite3.connect(db) as c:
        pd.DataFrame({"a": [1]}).to_sql("t1", c, index=False)
        pd.DataFrame({"b": [2]}).to_sql("t2", c, index=False)
    assert list_tables(db) == ["t1", "t2"]


def test_watch_contract_quarantines_violations(tmp_path):
    from yoda.watch import scan_once
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    pd.DataFrame({"age": [30, 999], "name": ["a", "b"]}).to_csv(
        inbox / "f.csv", index=False)
    contract = {"columns": {"age": {"min": 0, "max": 120}}}
    steps = [{"tool": "trim_whitespace", "col": "name", "params": {},
              "reason": "x"}]
    results = scan_once(inbox, steps, tmp_path / "o", tmp_path / "q", set(),
                        contract=contract)
    assert results[0]["status"] == "quarantined"
    assert "contract violations" in results[0]["reason"]
