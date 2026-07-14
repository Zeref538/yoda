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


def test_manual_edits_and_undo(uploaded):
    # edit a cell
    r = client.post("/api/edit", json={"op": "cell", "rid": 0,
                                       "col": "city", "value": "Taguig"})
    assert r.status_code == 200
    assert r.json()["grid"]["changed"] == {"city": [0]}

    # rename + delete column
    assert client.post("/api/edit", json={"op": "rename_col", "col": "segment",
                                          "new": "tier"}).status_code == 200
    d = client.post("/api/edit", json={"op": "delete_col", "col": "tier"}).json()
    assert "tier" not in d["grid"]["columns"]

    # delete rows
    d = client.post("/api/edit", json={"op": "delete_rows", "rids": [0, 1]}).json()
    assert d["n_rows"] == 108 and set(d["grid"]["removed_rids"]) == {0, 1}

    # clear cells
    d = client.post("/api/edit", json={"op": "clear_cells",
                                       "cells": [{"rid": 2, "col": "email"}]}).json()
    assert d["grid"]["changed"] == {"email": [2]}

    # undo everything back to the original upload
    for _ in range(5):
        d = client.post("/api/undo").json()
    assert d["n_rows"] == 110 and d["undo_depth"] == 0
    assert client.post("/api/undo").status_code == 400


def test_history_revert_and_versions(uploaded):
    client.post("/api/edit", json={"op": "delete_rows", "rids": [0, 1, 2]})
    client.post("/api/version", json={"name": "trimmed"})
    client.post("/api/edit", json={"op": "delete_col", "col": "city"})

    h = client.get("/api/history").json()
    assert [e["kind"] for e in h["timeline"]] == ["upload", "manual", "manual"]
    assert h["versions"][0]["name"] == "trimmed"

    # revert to the original upload (id 0) — non-destructive, appends an entry
    d = client.post("/api/revert", json={"id": 0}).json()
    assert d["n_rows"] == 110
    assert "city" in d["grid"]["columns"]
    assert d["timeline"][-1]["kind"] == "revert"

    # restore the saved version
    d = client.post("/api/version/restore", json={"name": "trimmed"}).json()
    assert d["n_rows"] == 107

    # download a specific version
    assert client.get("/api/download?version=trimmed").status_code == 200
    assert client.get("/api/download?version=nope").status_code == 400
    assert client.post("/api/revert", json={"id": 999}).status_code == 400


def test_edit_rejects_bad_targets(uploaded):
    assert client.post("/api/edit", json={"op": "cell", "rid": 0, "col": "ghost",
                                          "value": "x"}).status_code == 400
    assert client.post("/api/edit", json={"op": "rename_col", "col": "city",
                                          "new": "email"}).status_code == 400
    assert client.post("/api/edit", json={"op": "nope"}).status_code == 400


def test_upload_required_first():
    S.clear()
    assert client.post("/api/plan", json={}).status_code == 400
    assert client.post("/api/execute", json={"steps": []}).status_code == 400
