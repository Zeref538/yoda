"""Report: human-readable report.md from the audit log and verifier output.

Everything in the report is already redacted (audit examples pass through
the redactor at execution time; profiles contain only masked samples).
"""

from __future__ import annotations

import json
from datetime import datetime


def build_report(
    source: str,
    before_profile: dict,
    after_profile: dict,
    rounds: list[dict],
    verdicts: list[dict],
) -> str:
    """Render report.md. `rounds` is a list of {"plan": [...], "audit": [...]}."""
    lines = [
        "# YODA cleaning report",
        "",
        f"- **Source:** `{source}`",
        f"- **Generated:** {datetime.now().isoformat(timespec='seconds')}",
        f"- **Rows:** {before_profile['n_rows']} → {after_profile['n_rows']}"
        f" · **Columns:** {before_profile['n_cols']} → {after_profile['n_cols']}",
        f"- **Rounds:** {len(rounds)} (max 2)",
        "",
    ]

    for r, round_ in enumerate(rounds, 1):
        lines += [f"## Round {r} — executed steps", "",
                  "| # | tool | column | rows affected | status | detail |",
                  "|---:|---|---|---:|---|---|"]
        for e in round_["audit"]:
            detail = e.get("error", "") or "; ".join(
                f"{x['before']} → {x['after']}" for x in e.get("examples", [])[:2])
            lines.append(
                f"| {e['step'] + 1} | {e['tool']} | {e.get('col') or '—'} "
                f"| {e.get('rows_affected', 0)} | {e.get('status')} "
                f"| {detail} |")
        lines.append("")

    lines += ["## Verification (profile diff)", "",
              "| issue | column | before | after | verdict |",
              "|---|---|---:|---:|---|"]
    icon = {"resolved": "✅ resolved", "flagged": "🚩 flagged",
            "partially_resolved": "🟡 partially resolved",
            "unresolved": "❌ unresolved", "new_issue": "⚠️ new issue"}
    for v in sorted(verdicts, key=lambda v: (v["verdict"], str(v["col"]))):
        lines.append(f"| {v['issue']} | {v['col'] or '—'} | {v['before']} "
                     f"| {v['after']} | {icon.get(v['verdict'], v['verdict'])} |")

    n_open = sum(v["verdict"] in ("unresolved", "new_issue") for v in verdicts)
    lines += ["",
              "**Summary:** " + (
                  "all detected issues resolved or flagged."
                  if n_open == 0 else
                  f"{n_open} issue(s) remain open — see table above."),
              "",
              "_All sample values in this report are redacted; raw data never "
              "left this machine and was never shown to the language model._",
              ""]
    return "\n".join(lines)


def write_report(path, **kwargs) -> None:
    from pathlib import Path
    Path(path).write_text(build_report(**kwargs), encoding="utf-8")


def load_audit(audit_path) -> list[dict]:
    with open(audit_path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
