"""YODA command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import sys

import typer
from rich.console import Console

from yoda import __version__

# Windows consoles often default to cp1252, which can't encode ₱ / → found
# in profiles and reports. Degrade gracefully instead of crashing.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")

app = typer.Typer(help="YODA — Your Offline Data Agent. Cleans tabular data 100% locally.")
console = Console()


@app.command()
def version() -> None:
    """Print the YODA version."""
    console.print(f"YODA — Your Offline Data Agent v{__version__}")


@app.command()
def clean(
    path: str = typer.Argument(..., help="CSV/XLSX/SQLite file to clean"),
    table: str = typer.Option(None, help="Table name (SQLite inputs)"),
    model: str = typer.Option("qwen3.5:4b", help="Ollama model for the planner"),
    planner: str = typer.Option("llm", help="'llm' or 'rule_based' (no-AI baseline)"),
    yes: bool = typer.Option(False, "--yes", help="Auto-approve the plan (benchmark runs)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan and report only; touch nothing"),
) -> None:
    """Profile → plan (local LLM) → human approval → execute → audit log."""
    # Imports here keep `yoda version` fast and dependency-light.
    from yoda.executor import execute
    from yoda.gate import approve_plan, render_plan
    from yoda.io import load, save
    from yoda.planner import LLMPlanner, RuleBasedPlanner
    from yoda.profiler import profile
    from yoda.report import write_report
    from yoda.verifier import diff_profiles, follow_up_plan

    df = load(path, table=table)
    console.print(f"Loaded [bold]{path}[/bold]: {len(df)} rows x {len(df.columns)} cols")

    with console.status("Profiling (pure pandas, no AI)..."):
        prof = profile(df)

    if planner == "rule_based":
        planner_obj = RuleBasedPlanner()
        plan = planner_obj.plan(prof)
        console.print("[dim]Planner: rule-based baseline (no LLM).[/dim]")
    else:
        planner_obj = LLMPlanner(model=model)
        with console.status(f"Planning with {model} (profile only — no raw rows)..."):
            plan = planner_obj.plan(prof)
        src = planner_obj.last_outcome.get("source")
        if src == "fallback_rule_based":
            console.print("[yellow]LLM plan invalid/unavailable after retries — "
                          "fell back to the rule-based plan.[/yellow]")
            for e in planner_obj.last_outcome.get("errors", []):
                console.print(f"[dim]  {e}[/dim]")
        else:
            console.print(f"[dim]Planner: {model}, "
                          f"{planner_obj.last_outcome.get('attempts')} attempt(s).[/dim]")

    if not plan:
        console.print("[green]No issues found — nothing to clean.[/green]")
        raise typer.Exit()

    if dry_run:
        render_plan(plan, console, title="Cleaning plan (dry run — nothing executed)")
        raise typer.Exit()

    approved = approve_plan(plan, console, auto_yes=yes)
    if not approved:
        console.print("[yellow]No steps approved — exiting without changes.[/yellow]")
        raise typer.Exit()

    src_path = Path(path)
    audit_path = src_path.with_name(src_path.stem + "_audit.jsonl")
    cleaned, audit = execute(df, approved, audit_path=audit_path)
    rounds = [{"plan": approved, "audit": audit}]

    # Verifier loop: re-profile, diff, at most ONE follow-up round.
    with console.status("Verifying (re-profile + diff)..."):
        new_prof = profile(cleaned)
        verdicts = diff_profiles(prof, new_prof)
    followup = follow_up_plan(verdicts, planner_obj, new_prof)
    if followup:
        console.print(f"\n[yellow]Verifier: {len(followup)} issue(s) still open — "
                      "proposing a follow-up round.[/yellow]")
        approved2 = approve_plan(followup, console, auto_yes=yes)
        if approved2:
            audit_path2 = src_path.with_name(src_path.stem + "_audit_round2.jsonl")
            cleaned, audit2 = execute(cleaned, approved2, audit_path=audit_path2)
            rounds.append({"plan": approved2, "audit": audit2})
            new_prof = profile(cleaned)
            verdicts = diff_profiles(prof, new_prof)

    out_path = save(cleaned, path, table=table)
    report_path = src_path.with_name(src_path.stem + "_report.md")
    write_report(report_path, source=str(path), before_profile=prof,
                 after_profile=new_prof, rounds=rounds, verdicts=verdicts)

    console.print(f"\n[green]Done.[/green] {len(df)} -> {len(cleaned)} rows, "
                  f"{len(rounds)} round(s)")
    for round_ in rounds:
        for entry in round_["audit"]:
            status = entry.get("status")
            color = {"ok": "green", "skipped": "yellow", "error": "red"}.get(status, "white")
            console.print(f"  [{color}]{status}[/{color}] {entry['tool']}"
                          f"({entry.get('col') or ''}) — "
                          f"{entry.get('rows_affected', 0)} rows affected")
    n_open = sum(v["verdict"] in ("unresolved", "new_issue") for v in verdicts)
    console.print("Verifier: " + ("[green]all issues resolved or flagged[/green]"
                                  if n_open == 0 else
                                  f"[yellow]{n_open} issue(s) still open[/yellow]"))
    console.print(f"Cleaned file: [bold]{out_path}[/bold]")
    console.print(f"Audit log:    [bold]{audit_path}[/bold]")
    console.print(f"Report:       [bold]{report_path}[/bold]")


@app.command()
def profile_cmd(
    path: str = typer.Argument(..., help="File to profile"),
    table: str = typer.Option(None, help="Table name (SQLite inputs)"),
) -> None:
    """Print the redacted profile JSON (exactly what the LLM would see)."""
    from yoda.io import load
    from yoda.profiler import profile

    console.print_json(json.dumps(profile(load(path, table=table)), default=str))


if __name__ == "__main__":
    app()
