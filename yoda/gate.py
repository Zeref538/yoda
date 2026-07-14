"""Human gate: show the proposed plan, let the user approve / edit / reject
each step. `--yes` approves everything (benchmark runs)."""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table


def render_plan(plan: list[dict], console: Console, title: str = "Proposed cleaning plan"):
    t = Table(title=title, show_lines=False)
    t.add_column("#", justify="right", style="dim")
    t.add_column("tool", style="cyan")
    t.add_column("column", style="magenta")
    t.add_column("params")
    t.add_column("reason", max_width=50)
    for i, s in enumerate(plan):
        t.add_row(str(i + 1), s["tool"], str(s.get("col") or "—"),
                  json.dumps(s.get("params") or {}), s.get("reason", ""))
    console.print(t)


def approve_plan(plan: list[dict], console: Console, auto_yes: bool = False) -> list[dict]:
    """Return the approved subset (possibly edited). Empty list = run nothing."""
    render_plan(plan, console)
    if auto_yes:
        console.print(f"[green]--yes: all {len(plan)} steps approved.[/green]")
        return plan

    approved: list[dict] = []
    console.print("\nFor each step: [green]y[/green] approve · [red]n[/red] skip · "
                  "[yellow]e[/yellow] edit params (JSON) · [cyan]a[/cyan] approve all rest\n")
    approve_rest = False
    for i, step in enumerate(plan):
        if approve_rest:
            approved.append(step)
            continue
        choice = typer.prompt(
            f"step {i + 1}/{len(plan)}: {step['tool']}({step.get('col') or ''})",
            default="y").strip().lower()
        if choice == "a":
            approve_rest = True
            approved.append(step)
        elif choice == "y":
            approved.append(step)
        elif choice == "e":
            raw = typer.prompt("new params JSON", default=json.dumps(step["params"]))
            try:
                step = {**step, "params": json.loads(raw)}
                approved.append(step)
            except json.JSONDecodeError:
                console.print("[red]invalid JSON — step skipped[/red]")
        else:
            console.print(f"[dim]skipped step {i + 1}[/dim]")
    return approved
