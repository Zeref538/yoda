"""Local web UI: FastAPI backend serving a single-page spreadsheet frontend.

Binds to 127.0.0.1 only — this is a local tool, not a service. State is a
single in-memory session (one user, one file at a time). The grid shows raw
data because it never leaves this machine; the LLM still only ever receives
the redacted profile (plus the user's own typed instruction).
"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from yoda.executor import execute
from yoda.planner import LLMPlanner, RuleBasedPlanner, validate_plan
from yoda.profiler import profile
from yoda.report import build_report
from yoda.verifier import diff_profiles, follow_up_plan

app = FastAPI(title="YODA — Your Offline Data Agent", docs_url=None, redoc_url=None)

STATIC = Path(__file__).parent / "static"
GRID_MAX_ROWS = 500

# Single-user local session.
S: dict = {}


def _issues(prof: dict) -> list[dict]:
    """Flatten profile signals into UI-friendly issue rows."""
    rows = []
    if prof["duplicates"]["full_row"]:
        rows.append({"issue": "duplicate rows", "col": None,
                     "count": prof["duplicates"]["full_row"]})
    for col, c in prof["columns"].items():
        if c.get("date_formats_seen") and set(c["date_formats_seen"]) - {"ISO (YYYY-MM-DD)"}:
            rows.append({"issue": "mixed date formats", "col": col,
                         "count": len(c["date_formats_seen"])})
        if c.get("phone_formats_seen") and set(c["phone_formats_seen"]) - {"intl (+639XXXXXXXXX)"}:
            rows.append({"issue": "phone format chaos", "col": col,
                         "count": len(c["phone_formats_seen"])})
        if c.get("currency_like_values"):
            rows.append({"issue": "currency strings", "col": col,
                         "count": c["currency_like_values"]})
        elif c.get("bool_as_string"):
            rows.append({"issue": "bools as strings", "col": col,
                         "count": c["bool_as_string"]})
        elif c.get("numeric_as_string"):
            rows.append({"issue": "numbers as strings", "col": col,
                         "count": c["numeric_as_string"]})
        if c.get("casing_variants"):
            cv = c["casing_variants"]
            rows.append({"issue": "category casing variants", "col": col,
                         "count": f"{cv['raw_unique']} -> {cv['folded_unique']}"})
        if c.get("whitespace_issues") or c.get("non_nfc_values"):
            rows.append({"issue": "whitespace / unicode", "col": col,
                         "count": c.get("whitespace_issues", 0) + c.get("non_nfc_values", 0)})
        if c.get("null_pct"):
            rows.append({"issue": "missing values", "col": col,
                         "count": f"{c['null_pct']}%"})
        if c.get("iqr_outliers"):
            rows.append({"issue": "statistical outliers", "col": col,
                         "count": c["iqr_outliers"]})
    return rows


def _grid(df: pd.DataFrame, changed: dict[str, list] | None = None,
          new_cols: list[str] | None = None, removed: list | None = None) -> dict:
    """Grid payload: columns, up to GRID_MAX_ROWS rows keyed by row id,
    plus diff decorations (changed cells / new columns / removed row ids)."""
    view = df.head(GRID_MAX_ROWS)
    rows = []
    for rid, row in view.iterrows():
        cells = ["" if pd.isna(v) else str(v) for v in row]
        rows.append({"rid": int(rid), "cells": cells})
    return {
        "columns": [str(c) for c in df.columns],
        "rows": rows,
        "n_total_rows": len(df),
        "truncated": len(df) > GRID_MAX_ROWS,
        "changed": changed or {},          # {col: [rids]}
        "new_cols": new_cols or [],
        "removed_rids": [int(r) for r in (removed or [])],
    }


def _diff(before: pd.DataFrame, after: pd.DataFrame) -> tuple[dict, list, list]:
    """Cell-level diff aligned on the (preserved) index."""
    shared_rids = before.index.intersection(after.index)
    removed = list(before.index.difference(after.index))
    new_cols = [str(c) for c in after.columns if c not in before.columns]
    changed: dict[str, list] = {}
    for col in before.columns:
        if col not in after.columns:
            continue
        b = before.loc[shared_rids, col]
        a = after.loc[shared_rids, col]
        mask = (b.astype(str) != a.astype(str)) & ~(b.isna() & a.isna())
        rids = [int(r) for r in shared_rids[mask]]
        if rids:
            changed[str(col)] = rids
    return changed, new_cols, removed


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    suffix = Path(file.filename or "data.csv").suffix.lower()
    raw = await file.read()
    try:
        if suffix == ".csv":
            df = pd.read_csv(io.BytesIO(raw))
        elif suffix in (".xlsx", ".xls"):
            df = pd.read_excel(io.BytesIO(raw))
        elif suffix in (".sqlite", ".db", ".sqlite3"):
            from yoda.io import load
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(raw)
            df = load(tmp.name)
        else:
            raise ValueError(f"unsupported file type: {suffix}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    df.index = pd.RangeIndex(len(df))  # stable row ids for diffing
    prof = profile(df)
    S.clear()
    S.update(df=df, cleaned=df, prof=prof, name=file.filename, rounds=[],
             planner=None, new_prof=prof, verdicts=[])
    return {
        "name": file.filename, "n_rows": len(df), "n_cols": len(df.columns),
        "issues": _issues(prof),
        "profile": json.loads(json.dumps(prof, default=str)),
        "grid": _grid(df),
    }


@app.post("/api/plan")
def plan(body: dict):
    if "prof" not in S:
        raise HTTPException(400, "upload a file first")
    prof = profile(S["cleaned"]) if S["rounds"] else S["prof"]
    col = body.get("col")
    instruction = body.get("instruction") or None

    if body.get("planner") == "rule_based":
        S["planner"] = RuleBasedPlanner()
        steps = S["planner"].plan(prof)
        if col:
            steps = [s for s in steps if s.get("col") in (col, None)]
        outcome = {"source": "rule_based"}
    else:
        S["planner"] = LLMPlanner(model=body.get("model", "qwen3.5:4b"))
        steps = S["planner"].plan(prof, instruction=instruction, col=col)
        if col:  # keep the model honest: never leak steps onto other columns
            steps = [s for s in steps if s.get("col") in (col, None)]
        outcome = S["planner"].last_outcome
    S["current_prof"] = prof
    return {"steps": steps, "outcome": outcome}


@app.post("/api/execute")
def run(body: dict):
    if "prof" not in S:
        raise HTTPException(400, "upload a file first")
    steps = body.get("steps", [])
    source = S["cleaned"]
    try:
        validate_plan({"steps": steps}, profile(source))
    except Exception as exc:
        raise HTTPException(400, f"invalid plan: {exc}")

    cleaned, audit = execute(source, steps)
    changed, new_cols, removed = _diff(source, cleaned)
    S["cleaned"] = cleaned
    S["rounds"].append({"plan": steps, "audit": audit})

    new_prof = profile(cleaned)
    verdicts = diff_profiles(S["prof"], new_prof)
    S["verdicts"], S["new_prof"] = verdicts, new_prof
    followup = ([] if len(S["rounds"]) >= 4 or S["planner"] is None
                else follow_up_plan(verdicts, S["planner"], new_prof))
    return {
        "audit": json.loads(json.dumps(audit, default=str)),
        "verdicts": verdicts,
        "followup": followup,
        "round": len(S["rounds"]),
        "n_rows_before": len(S["df"]), "n_rows_after": len(cleaned),
        "grid": _grid(cleaned, changed, new_cols, removed),
    }


@app.get("/api/report")
def report():
    if not S.get("rounds"):
        raise HTTPException(400, "nothing executed yet")
    md = build_report(source=S["name"], before_profile=S["prof"],
                      after_profile=S["new_prof"], rounds=S["rounds"],
                      verdicts=S["verdicts"])
    return Response(md, media_type="text/markdown; charset=utf-8")


@app.get("/api/download")
def download():
    if S.get("cleaned") is None or not S.get("rounds"):
        raise HTTPException(400, "nothing executed yet")
    out = Path(tempfile.gettempdir()) / (Path(S["name"]).stem + "_cleaned.csv")
    S["cleaned"].to_csv(out, index=False)
    return FileResponse(out, filename=out.name, media_type="text/csv")


def serve(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True) -> None:
    import threading
    import webbrowser

    import uvicorn

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
