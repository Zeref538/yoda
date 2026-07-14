"""Web UI API tests: upload → plan (rule-based) → execute → report → download."""

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from benchmark.corruptor import corrupt  # noqa: E402
from benchmark.datasets import ph_customers  # noqa: E402
from yoda.web import S, app  # noqa: E402

client = TestClient(app)


@pytest.fixture()
def uploaded():
    clean = ph_customers(n=100, seed=5)
    dirty, _ = corrupt(clean, "ph_customers", seed=5)
    r = client.post("/api/upload",
                    files={"file": ("cust.csv", dirty.to_csv(index=False), "text/csv")})
    assert r.status_code == 200
    return r.json()


def test_upload_profiles_and_lists_issues(uploaded):
    assert uploaded["n_rows"] == 110  # 100 + 10 duplicates
    assert any(i["issue"] == "duplicate rows" for i in uploaded["issues"])


def test_upload_rejects_unknown_type():
    r = client.post("/api/upload", files={"file": ("x.txt", b"hi", "text/plain")})
    assert r.status_code == 400


def test_full_flow_rule_based(uploaded):
    r = client.post("/api/plan", json={"planner": "rule_based"})
    steps = r.json()["steps"]
    assert steps

    r = client.post("/api/execute", json={"steps": steps})
    assert r.status_code == 200
    d = r.json()
    assert d["n_rows_after"] == 100
    assert all(e["status"] == "ok" for e in d["audit"])
    assert not any(v["verdict"] in ("unresolved", "new_issue") for v in d["verdicts"]) \
        or d["followup"]

    assert "# YODA cleaning report" in client.get("/api/report").text
    assert client.get("/api/download").status_code == 200


def test_execute_rejects_invalid_plan(uploaded):
    client.post("/api/plan", json={"planner": "rule_based"})
    r = client.post("/api/execute", json={"steps": [
        {"tool": "trim_whitespace", "col": "ghost", "params": {}, "reason": "x"}]})
    assert r.status_code == 400


def test_upload_required_first():
    S.clear()
    assert client.post("/api/plan", json={}).status_code == 400
    assert client.post("/api/execute", json={"steps": []}).status_code == 400
