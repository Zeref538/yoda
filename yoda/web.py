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


@app.get("/api/models")
def models():
    """Installed Ollama models for the model dropdown (empty list if down)."""
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            tags = json.loads(r.read())
        return {"models": [m["name"] for m in tags.get("models", [])]}
    except OSError:
        return {"models": []}


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
             planner=None, new_prof=prof, verdicts=[], versions={})
    _snapshot("original upload", "upload")
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
    _snapshot(f"AI round {len(S['rounds'])}: {len(steps)} step(s)", "ai")
    return {
        "audit": json.loads(json.dumps(audit, default=str)),
        "verdicts": verdicts,
        "followup": followup,
        "round": len(S["rounds"]),
        "n_rows_before": len(S["df"]), "n_rows_after": len(cleaned),
        "grid": _grid(cleaned, changed, new_cols, removed),
        "undo_depth": len(S["timeline"]) - 1,
    }


def _snapshot(label: str, kind: str):
    """Append the current dataframe to the timeline (single undo/history
    source of truth). Entry 0 — the original upload — is never dropped."""
    tl = S.setdefault("timeline", [])
    tl.append({"id": (tl[-1]["id"] + 1) if tl else 0, "label": label,
               "kind": kind, "ts": pd.Timestamp.now().isoformat(timespec="seconds"),
               "df": S["cleaned"].copy(), "rounds_len": len(S.get("rounds", [])),
               "n_rows": len(S["cleaned"])})
    if len(tl) > 40:  # cap memory, keep the original
        del tl[1:len(tl) - 39]


def _timeline_meta():
    return [{k: e[k] for k in ("id", "label", "kind", "ts", "n_rows")}
            for e in S.get("timeline", [])]


def _log_manual(entry: dict):
    """Manual edits land in one rolling 'manual edits' round for the report."""
    rounds = S.setdefault("rounds", [])
    if not rounds or not rounds[-1].get("manual"):
        rounds.append({"plan": [], "audit": [], "manual": True})
    entry.setdefault("status", "ok")
    entry["step"] = len(rounds[-1]["audit"])
    rounds[-1]["audit"].append(entry)


def _parse_value(series: pd.Series, value: str):
    if value == "":
        return pd.NA
    if pd.api.types.is_numeric_dtype(series):
        try:
            return float(value) if "." in value else int(value)
        except ValueError:
            pass  # falls through: column becomes object, like Excel would
    return value


@app.post("/api/edit")
def edit(body: dict):
    """Direct user edits — Excel-style, no AI, no approval gate needed
    (the user IS the action). Everything is undoable and audit-logged."""
    if S.get("cleaned") is None:
        raise HTTPException(400, "upload a file first")
    df = S["cleaned"]
    op = body.get("op")
    changed: dict[str, list] = {}
    removed: list = []
    label = {"cell": "edited a cell", "clear_cells": "cleared cells",
             "delete_rows": "deleted rows", "delete_col": "deleted a column",
             "rename_col": "renamed a column"}.get(op, op)

    try:
        if op == "cell":
            rid, col, val = body["rid"], body["col"], str(body.get("value", ""))
            if col not in df.columns or rid not in df.index:
                raise KeyError(f"{col}[{rid}]")
            out = df.copy()
            if pd.api.types.is_numeric_dtype(out[col]) and not isinstance(
                    _parse_value(out[col], val), (int, float)):
                out[col] = out[col].astype(object)
            out.at[rid, col] = _parse_value(out[col], val)
            changed = {col: [int(rid)]}
            _log_manual({"tool": "manual_edit_cell", "col": col,
                         "rows_affected": 1, "reason": "user edited a cell"})
        elif op == "clear_cells":
            out = df.copy()
            n = 0
            for c in body["cells"]:
                rid, col = c["rid"], c["col"]
                if col in out.columns and rid in out.index:
                    if not pd.api.types.is_object_dtype(out[col]) and not \
                            pd.api.types.is_float_dtype(out[col]):
                        out[col] = out[col].astype(object)
                    out.at[rid, col] = pd.NA
                    changed.setdefault(col, []).append(int(rid))
                    n += 1
            _log_manual({"tool": "manual_clear_cells", "col": None,
                         "rows_affected": n, "reason": "user cleared cells"})
        elif op == "delete_rows":
            rids = [r for r in body["rids"] if r in df.index]
            out = df.drop(index=rids)
            removed = rids
            _log_manual({"tool": "manual_delete_rows", "col": None,
                         "rows_affected": len(rids), "reason": "user deleted rows"})
        elif op == "delete_col":
            col = body["col"]
            if col not in df.columns:
                raise KeyError(col)
            out = df.drop(columns=[col])
            _log_manual({"tool": "manual_delete_column", "col": col,
                         "rows_affected": len(df), "reason": "user deleted a column"})
        elif op == "rename_col":
            old, new = body["col"], str(body["new"]).strip()
            if old not in df.columns:
                raise KeyError(old)
            if not new or new in df.columns:
                raise HTTPException(400, f"invalid or duplicate name: '{new}'")
            out = df.rename(columns={old: new})
            _log_manual({"tool": "manual_rename_column", "col": old,
                         "rows_affected": 0,
                         "reason": f"user renamed column to '{new}'"})
        else:
            raise HTTPException(400, f"unknown edit op: {op}")
    except KeyError as exc:
        raise HTTPException(400, f"not found: {exc}")

    S["cleaned"] = out
    _snapshot(label, "manual")
    return {"grid": _grid(out, changed, [], removed),
            "n_rows": len(out), "undo_depth": len(S["timeline"]) - 1}


@app.post("/api/undo")
def undo():
    tl = S.get("timeline", [])
    if len(tl) <= 1:
        raise HTTPException(400, "nothing to undo")
    tl.pop()
    S["cleaned"] = tl[-1]["df"].copy()
    del S["rounds"][tl[-1]["rounds_len"]:]  # drop audit of the undone step
    return {"grid": _grid(S["cleaned"]), "n_rows": len(S["cleaned"]),
            "undo_depth": len(tl) - 1}


@app.get("/api/history")
def history():
    if "timeline" not in S:
        raise HTTPException(400, "upload a file first")
    return {"timeline": _timeline_meta(),
            "versions": [{"name": n, "ts": v["ts"], "n_rows": len(v["df"])}
                         for n, v in S.get("versions", {}).items()]}


@app.post("/api/revert")
def revert(body: dict):
    """Jump to any timeline entry (id 0 = the original upload). The revert is
    itself appended to the timeline, so it's non-destructive and undoable."""
    tl = S.get("timeline", [])
    entry = next((e for e in tl if e["id"] == body.get("id")), None)
    if entry is None:
        raise HTTPException(400, "unknown history entry")
    S["cleaned"] = entry["df"].copy()
    _log_manual({"tool": "revert", "col": None, "rows_affected": len(S["cleaned"]),
                 "reason": f"user reverted to '{entry['label']}'"})
    _snapshot(f"reverted to: {entry['label']}", "revert")
    return {"grid": _grid(S["cleaned"]), "n_rows": len(S["cleaned"]),
            "undo_depth": len(tl) - 1, "timeline": _timeline_meta()}


@app.post("/api/version")
def save_version(body: dict):
    """Save the current state as a named copy; the working data (and the
    original) are untouched. Versions are downloadable and restorable."""
    if S.get("cleaned") is None:
        raise HTTPException(400, "upload a file first")
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "version needs a name")
    S.setdefault("versions", {})[name] = {
        "df": S["cleaned"].copy(),
        "ts": pd.Timestamp.now().isoformat(timespec="seconds")}
    return {"versions": [{"name": n, "ts": v["ts"], "n_rows": len(v["df"])}
                         for n, v in S["versions"].items()]}


@app.post("/api/version/restore")
def restore_version(body: dict):
    v = S.get("versions", {}).get(body.get("name"))
    if v is None:
        raise HTTPException(400, "unknown version")
    S["cleaned"] = v["df"].copy()
    _log_manual({"tool": "restore_version", "col": None,
                 "rows_affected": len(S["cleaned"]),
                 "reason": f"user restored version '{body['name']}'"})
    _snapshot(f"restored version: {body['name']}", "revert")
    return {"grid": _grid(S["cleaned"]), "n_rows": len(S["cleaned"]),
            "undo_depth": len(S["timeline"]) - 1}


@app.get("/api/report")
def report():
    if not S.get("rounds"):
        raise HTTPException(400, "nothing executed yet")
    md = build_report(source=S["name"], before_profile=S["prof"],
                      after_profile=S["new_prof"], rounds=S["rounds"],
                      verdicts=S["verdicts"])
    return Response(md, media_type="text/markdown; charset=utf-8")


@app.get("/api/download")
def download(version: str | None = None):
    if S.get("cleaned") is None:
        raise HTTPException(400, "upload a file first")
    if version is not None:
        v = S.get("versions", {}).get(version)
        if v is None:
            raise HTTPException(400, "unknown version")
        df, tag = v["df"], f"_{version}"
    else:
        df, tag = S["cleaned"], "_cleaned"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tag)
    out = Path(tempfile.gettempdir()) / (Path(S["name"]).stem + safe + ".csv")
    df.to_csv(out, index=False)
    return FileResponse(out, filename=out.name, media_type="text/csv")


def serve(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True) -> None:
    import threading
    import webbrowser

    import uvicorn

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
