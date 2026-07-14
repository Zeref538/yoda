"""YODA command-line interface."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from yoda import __version__

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

    df = load(path, table=table)
    console.print(f"Loaded [bold]{path}[/bold]: {len(df)} rows × {len(df.columns)} cols")

    with console.status("Profiling (pure pandas, no AI)..."):
        prof = profile(df)

    if planner == "rule_based":
        plan = RuleBasedPlanner().plan(prof)
        console.print("[dim]Planner: rule-based baseline (no LLM).[/dim]")
    else:
        p = LLMPlanner(model=model)
        with console.status(f"Planning with {model} (profile only — no raw rows)..."):
            plan = p.plan(prof)
        src = p.last_outcome.get("source")
        if src == "fallback_rule_based":
            console.print("[yellow]LLM plan invalid/unavailable after retries — "
                          "fell back to the rule-based plan.[/yellow]")
            for e in p.last_outcome.get("errors", []):
                console.print(f"[dim]  {e}[/dim]")
        else:
            console.print(f"[dim]Planner: {model}, "
                          f"{p.last_outcome.get('attempts')} attempt(s).[/dim]")

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
    out_path = save(cleaned, path, table=table)

    console.print(f"\n[green]Done.[/green] {len(df)} → {len(cleaned)} rows")
    for entry in audit:
        status = entry.get("status")
        color = {"ok": "green", "skipped": "yellow", "error": "red"}.get(status, "white")
        console.print(f"  [{color}]{status}[/{color}] {entry['tool']}"
                      f"({entry.get('col') or ''}) — "
                      f"{entry.get('rows_affected', 0)} rows affected")
    console.print(f"Cleaned file: [bold]{out_path}[/bold]")
    console.print(f"Audit log:    [bold]{audit_path}[/bold]")


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
