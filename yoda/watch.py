"""Watch-folder mode: auto-clean files dropped into a directory with a recipe.

Every new CSV/XLSX gets: recipe validation against its profile → execute →
verify. Files whose verification leaves unresolved/new issues land in the
quarantine folder (with a note) instead of the output folder. Since a recipe
is a previously human-approved plan, no per-file gate is needed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from yoda.executor import execute
from yoda.io import load
from yoda.planner import PlanValidationError, validate_plan
from yoda.profiler import profile
from yoda.report import build_report
from yoda.verifier import OPEN_VERDICTS, diff_profiles

WATCHABLE = {".csv", ".xlsx", ".xls"}


def process_file(path: Path, steps: list[dict], out_dir: Path,
                 quarantine_dir: Path) -> dict:
    """Clean one file with a recipe. Returns a summary dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    df = load(path)
    prof = profile(df)
    try:
        validate_plan({"steps": steps}, prof)
    except (PlanValidationError, Exception) as exc:  # noqa: B014 — jsonschema too
        return _quarantine(path, quarantine_dir,
                           f"recipe does not fit this file: {exc}")

    cleaned, audit = execute(df, steps)
    new_prof = profile(cleaned)
    verdicts = diff_profiles(prof, new_prof)
    n_open = sum(v["verdict"] in OPEN_VERDICTS for v in verdicts)

    report = build_report(source=str(path), before_profile=prof,
                          after_profile=new_prof,
                          rounds=[{"plan": steps, "audit": audit}],
                          verdicts=verdicts)
    if n_open:
        return _quarantine(path, quarantine_dir,
                           f"{n_open} issue(s) unresolved after cleaning",
                           cleaned=cleaned, report=report)

    out_csv = out_dir / (path.stem + "_cleaned.csv")
    cleaned.to_csv(out_csv, index=False)
    (out_dir / (path.stem + "_report.md")).write_text(report, encoding="utf-8")
    with open(out_dir / (path.stem + "_audit.jsonl"), "w", encoding="utf-8") as f:
        for e in audit:
            f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
    return {"file": path.name, "status": "cleaned", "rows": len(cleaned),
            "out": str(out_csv)}


def _quarantine(path: Path, qdir: Path, reason: str, cleaned=None,
                report: str | None = None) -> dict:
    qdir.mkdir(parents=True, exist_ok=True)
    (qdir / (path.stem + "_REASON.txt")).write_text(reason, encoding="utf-8")
    if cleaned is not None:
        cleaned.to_csv(qdir / (path.stem + "_attempt.csv"), index=False)
    if report:
        (qdir / (path.stem + "_report.md")).write_text(report, encoding="utf-8")
    return {"file": path.name, "status": "quarantined", "reason": reason}


def scan_once(folder: Path, steps: list[dict], out_dir: Path,
              quarantine_dir: Path, seen: set[str]) -> list[dict]:
    """One pass over the folder; processes files not seen before."""
    results = []
    for p in sorted(folder.iterdir()):
        if (p.suffix.lower() not in WATCHABLE or p.name in seen
                or p.stem.endswith(("_cleaned", "_attempt"))):
            continue
        seen.add(p.name)
        try:
            results.append(process_file(p, steps, out_dir, quarantine_dir))
        except Exception as exc:  # a broken file must not kill the watcher
            results.append(_quarantine(p, quarantine_dir,
                                       f"failed to process: {exc}"))
    return results


def run_watch(folder: str | Path, steps: list[dict], out_dir: str | Path,
              quarantine_dir: str | Path, interval: float = 5.0,
              once: bool = False, on_result=print) -> None:
    folder, out_dir = Path(folder), Path(out_dir)
    quarantine_dir = Path(quarantine_dir)
    seen: set[str] = set()
    while True:
        for r in scan_once(folder, steps, out_dir, quarantine_dir, seen):
            on_result(r)
        if once:
            return
        time.sleep(interval)
