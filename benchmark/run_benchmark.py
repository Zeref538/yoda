"""Run the full benchmark: generate → corrupt → profile → plan → execute → score.

Usage:  python -m benchmark.run_benchmark [--planner rule_based]

Writes results to benchmark/results/<planner>/ :
- per-dataset audit logs and score JSONs
- results.md — the summary table for the README
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmark.corruptor import corrupt
from benchmark.datasets import DATASETS
from benchmark.scorer import score
from yoda.executor import execute
from yoda.planner import RuleBasedPlanner
from yoda.profiler import profile

RESULTS_DIR = Path(__file__).parent / "results"


def get_planner(name: str):
    if name == "rule_based":
        return RuleBasedPlanner()
    raise SystemExit(f"unknown planner: {name} (LLM planners land in Phase 2)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planner", default="rule_based")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    planner = get_planner(args.planner)
    out_dir = RESULTS_DIR / args.planner
    out_dir.mkdir(parents=True, exist_ok=True)

    all_scores = []
    for name, gen in DATASETS.items():
        clean = gen()
        dirty, manifest = corrupt(clean, name, seed=args.seed)
        prof = profile(dirty)
        plan = planner.plan(prof)
        cleaned, _audit = execute(dirty, plan, audit_path=out_dir / f"{name}_audit.jsonl")
        result = score(clean, cleaned, manifest, plan)
        all_scores.append(result)
        (out_dir / f"{name}_score.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8")
        o = result["overall"]
        print(f"{name:16s}  det {o['detection_rate']:.0%}  fix {o['fix_rate']:.0%}  "
              f"false-fix {o['false_fix_rate']:.2%}  ({o['n_errors']} errors)")

    write_markdown(all_scores, out_dir / "results.md", args.planner)
    print(f"\nWrote {out_dir / 'results.md'}")


def write_markdown(scores: list[dict], path: Path, planner: str) -> None:
    lines = [f"# Benchmark results — planner: `{planner}`", ""]
    lines += ["| dataset | errors | detection | fix | false-fix |",
              "|---|---:|---:|---:|---:|"]
    tot_n = tot_det = tot_fix = tot_false = tot_cells = 0
    for s in scores:
        o = s["overall"]
        lines.append(f"| {s['dataset']} | {o['n_errors']} | {o['detection_rate']:.1%} "
                     f"| {o['fix_rate']:.1%} | {o['false_fix_rate']:.2%} |")
        tot_n += o["n_errors"]
        tot_det += round(o["detection_rate"] * o["n_errors"])
        tot_fix += round(o["fix_rate"] * o["n_errors"])
        tot_false += o["n_false_fixes"]
        tot_cells += o["n_clean_cells_checked"]
    lines.append(f"| **overall** | **{tot_n}** | **{tot_det / tot_n:.1%}** "
                 f"| **{tot_fix / tot_n:.1%}** | **{tot_false / tot_cells:.2%}** |")

    lines += ["", "## Per error type (all datasets pooled)", "",
              "| error type | n | detection | fix |", "|---|---:|---:|---:|"]
    pooled: dict[str, dict] = {}
    for s in scores:
        for etype, t in s["per_type"].items():
            p = pooled.setdefault(etype, {"n": 0, "detected": 0, "fixed": 0})
            for k in ("n", "detected", "fixed"):
                p[k] += t[k]
    for etype, p in sorted(pooled.items()):
        lines.append(f"| {etype} | {p['n']} | {p['detected'] / p['n']:.1%} "
                     f"| {p['fixed'] / p['n']:.1%} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
