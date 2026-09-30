"""Build the case study page (docs/index.html) from committed result files.

Every number on the page comes from DATA, and DATA comes from here:
benchmark/results/** and the real profiler run on docs/demo/sample_messy.csv.
Nothing is typed into the template.

    python docs/case/build.py
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from yoda.profiler import profile  # noqa: E402

RES = ROOT / "benchmark" / "results"
ORDER = ["titanic_style", "retail_orders", "ph_customers", "employees",
         "clinic_patients", "inventory"]


def run(folder: str) -> dict:
    """Pool one benchmark run the same way run_benchmark.write_markdown does."""
    scores = [json.loads((RES / folder / f"{d}_score.json").read_text(encoding="utf-8"))
              for d in ORDER]
    n = sum(s["overall"]["n_errors"] for s in scores)
    det = sum(round(s["overall"]["detection_rate"] * s["overall"]["n_errors"]) for s in scores)
    fix = sum(round(s["overall"]["fix_rate"] * s["overall"]["n_errors"]) for s in scores)
    false = sum(s["overall"]["n_false_fixes"] for s in scores)
    cells = sum(s["overall"]["n_clean_cells_checked"] for s in scores)
    types: dict[str, dict] = {}
    for s in scores:
        for t, v in s["per_type"].items():
            p = types.setdefault(t, {"n": 0, "detected": 0, "fixed": 0})
            for k in p:
                p[k] += v[k]
    fell = [s["dataset"] for s in scores
            if s.get("planner_outcome", {}).get("source") == "fallback_rule_based"]
    return {"n": n, "detection": det / n, "fix": fix / n, "false_fix": false / cells,
            "false_fixes": false, "cells": cells, "types": types, "fell_back": fell,
            "datasets": {s["dataset"]: s["overall"] for s in scores}}


def instructions(model: str) -> dict:
    rows = json.loads((RES / "instructions" / f"{model}.json").read_text(encoding="utf-8"))
    kinds: dict[str, list[int]] = {}
    misses = []
    for r in rows:
        k = kinds.setdefault(r["case"]["kind"], [0, 0])
        k[1] += 1
        if r["result"]["pass"]:
            k[0] += 1
        else:
            misses.append({"kind": r["case"]["kind"], "ask": r["case"]["instruction"],
                           "got": [s["tool"] for s in r["steps"]][:4]})
    return {"passed": sum(v[0] for v in kinds.values()), "n": len(rows),
            "kinds": kinds, "misses": misses}


def sees() -> dict:
    """What the model is shown vs what the file holds, from a real profiler run."""
    df = pd.read_csv(ROOT / "docs/demo/sample_messy.csv", dtype=str, keep_default_na=False)
    prof = profile(df)
    cols = ["Customer Name", "Phone", "Monthly Fee"]
    return {"raw": df[cols].head(3).to_dict("records"),
            "profile": {c: prof["columns"][c] for c in cols},
            "rows": prof["n_rows"]}


def main() -> None:
    old = run("qwen3.5_4b_v3_ctx_default")  # the withdrawn run, kept as evidence
    data = {
        "baseline": run("rule_based"),
        "v1": run("qwen3.5_4b_v1"),
        "v2": run("qwen3.5_4b_v2"),
        "small": run("qwen3.5_2b"),
        "v3": run("qwen3.5_4b"),
        "v3_old": {"fell_back": old["fell_back"], "n_sets": len(ORDER),
                   "real": {d: old["datasets"][d] for d in ORDER if d not in old["fell_back"]}},
        "ins4": instructions("qwen3.5_4b"),
        "ins2": instructions("qwen3.5_2b"),
        "ins4_runs": [instructions(f"attempt/baseline_run{i}")["passed"] for i in (1, 2, 3)],
        "sees": sees(),
        "built": datetime.date.today().isoformat(),
    }
    tpl = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    assert tpl.count("/*DATA*/") == 1
    out = tpl.replace("/*DATA*/", "const DATA = " + json.dumps(data, ensure_ascii=False) + ";")
    (ROOT / "docs" / "index.html").write_text(out, encoding="utf-8")
    print("wrote docs/index.html", len(out), "bytes")


if __name__ == "__main__":
    main()
