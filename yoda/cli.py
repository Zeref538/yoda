"""YODA command-line interface."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from yoda import __version__

# Windows consoles often default to cp1252, which can't encode ₱ / -> found
# in profiles and reports. Degrade gracefully instead of crashing.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")

app = typer.Typer(help="YODA - Your Offline Data Agent. Cleans tabular data 100% locally.")
console = Console()

_STATUS_STYLE = {"ok": "green", "skipped": "yellow", "error": "red"}
_VERDICT_STYLE = {
    "resolved": "[green]resolved[/green]",
    "flagged": "[cyan]flagged[/cyan]",
    "partially_resolved": "[yellow]partially resolved[/yellow]",
    "unresolved": "[red]unresolved[/red]",
    "new_issue": "[red]new issue[/red]",
}


def _banner(subtitle: str) -> None:
    console.print(Panel.fit(
        f"[bold cyan]YODA[/bold cyan] - Your Offline Data Agent  [dim]v{__version__}[/dim]\n"
        f"[dim]{subtitle}[/dim]",
        border_style="cyan"))


def _issue_summary(prof: dict) -> Table | None:
    """One row per detected issue signal - what the planner will act on."""
    rows = []
    dup = prof["duplicates"]["full_row"]
    if dup:
        rows.append(("duplicate rows", "whole table", str(dup)))
    for col, c in prof["columns"].items():
        if c.get("date_formats_seen") and (
                set(c["date_formats_seen"]) - {"ISO (YYYY-MM-DD)"}):
            rows.append(("mixed date formats", col, str(len(c["date_formats_seen"]))))
        if c.get("phone_formats_seen") and (
                set(c["phone_formats_seen"]) - {"intl (+639XXXXXXXXX)"}):
            rows.append(("phone format chaos", col, str(len(c["phone_formats_seen"]))))
        if c.get("currency_like_values"):
            rows.append(("currency strings", col, str(c["currency_like_values"])))
        elif c.get("bool_as_string"):
            rows.append(("bools as strings", col, str(c["bool_as_string"])))
        elif c.get("numeric_as_string"):
            rows.append(("numbers as strings", col, str(c["numeric_as_string"])))
        if c.get("casing_variants"):
            cv = c["casing_variants"]
            rows.append(("category casing variants", col,
                         f"{cv['raw_unique']} -> {cv['folded_unique']}"))
        if c.get("whitespace_issues") or c.get("non_nfc_values"):
            rows.append(("whitespace / unicode", col,
                         str(c.get("whitespace_issues", 0) + c.get("non_nfc_values", 0))))
        if c.get("null_pct"):
            rows.append(("missing values", col, f"{c['null_pct']}%"))
        if c.get("iqr_outliers"):
            rows.append(("statistical outliers", col, str(c["iqr_outliers"])))
    if not rows:
        return None
    t = Table(title="Issues detected by the profiler (no AI involved yet)",
              title_style="bold", border_style="dim")
    t.add_column("issue", style="yellow")
    t.add_column("column", style="magenta")
    t.add_column("count", justify="right")
    for r in rows:
        t.add_row(*r)
    return t


def _print_step(entry: dict) -> None:
    status = entry.get("status", "?")
    style = _STATUS_STYLE.get(status, "white")
    detail = (f"[red]{entry['error']}[/red]" if entry.get("error")
              else f"{entry.get('rows_affected', 0)} rows affected"
                   + (f", [yellow]{entry['parse_failures']} unparseable[/yellow]"
                      if entry.get("parse_failures") else ""))
    console.print(f"  [{style}]{'OK ' if status == 'ok' else status:<7}[/{style}] "
                  f"[cyan]{entry['tool']}[/cyan]"
                  f"([magenta]{entry.get('col') or ''}[/magenta]) {detail}")


def _verification_table(verdicts: list[dict]) -> Table:
    t = Table(title="Verification (profile re-check)", title_style="bold",
              border_style="dim")
    t.add_column("issue", style="yellow")
    t.add_column("column", style="magenta")
    t.add_column("before", justify="right")
    t.add_column("after", justify="right")
    t.add_column("verdict")
    order = {"unresolved": 0, "new_issue": 0, "partially_resolved": 1,
             "flagged": 2, "resolved": 3}
    for v in sorted(verdicts, key=lambda v: (order.get(v["verdict"], 9), str(v["col"]))):
        t.add_row(v["issue"], v["col"] or "whole table", str(v["before"]),
                  str(v["after"]), _VERDICT_STYLE.get(v["verdict"], v["verdict"]))
    return t


@app.command()
def version() -> None:
    """Print the YODA version."""
    console.print(f"YODA - Your Offline Data Agent v{__version__}")


@app.command()
def clean(
    path: str = typer.Argument(..., help="CSV/XLSX/SQLite file to clean"),
    table: str = typer.Option(None, help="Table name (SQLite inputs)"),
    model: str = typer.Option("qwen3.5:4b", help="Ollama model for the planner"),
    planner: str = typer.Option("llm", help="'llm' or 'rule_based' (no-AI baseline)"),
    yes: bool = typer.Option(False, "--yes", help="Auto-approve the plan (benchmark runs)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan and report only; touch nothing"),
    recipe: str = typer.Option(None, help="Replay a saved recipe instead of planning"),
    save_recipe: str = typer.Option(None, help="Save the approved plan as a recipe JSON"),
    all_tables: bool = typer.Option(False, "--all-tables",
                                    help="SQLite: clean every table in the database"),
) -> None:
    """Profile -> plan (local LLM) -> human approval -> execute -> verify -> report."""
    # Imports here keep `yoda version` fast and dependency-light.
    from yoda.executor import execute
    from yoda.gate import approve_plan, render_plan
    from yoda.io import load, save
    from yoda.planner import LLMPlanner, RuleBasedPlanner
    from yoda.profiler import profile
    from yoda.report import write_report
    from yoda.verifier import diff_profiles, follow_up_plan

    _banner("100% local - raw rows never reach the model - nothing leaves this machine")

    if all_tables:
        from yoda.io import list_tables
        if Path(path).suffix.lower() not in (".sqlite", ".db", ".sqlite3"):
            console.print("[red]--all-tables only applies to SQLite inputs.[/red]")
            raise typer.Exit(code=1)
        tables = list_tables(path)
        console.print(f"Database has {len(tables)} table(s): {', '.join(tables)}\n")
        for t in tables:
            console.print(f"[bold cyan]=== table: {t} ===[/bold cyan]")
            try:
                clean(path=path, table=t, model=model, planner=planner, yes=yes,
                      dry_run=dry_run, recipe=recipe, save_recipe=None,
                      all_tables=False)
            except typer.Exit as exc:
                if exc.exit_code not in (0, None):
                    console.print(f"[yellow]table {t}: skipped ({exc.exit_code})[/yellow]")
        raise typer.Exit()

    try:
        df = load(path, table=table)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Could not load {path}: {exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"Loaded [bold]{path}[/bold]: "
                  f"[bold]{len(df)}[/bold] rows x [bold]{len(df.columns)}[/bold] columns\n")

    with console.status("[cyan]Step 1/5[/cyan] Profiling (pure pandas, no AI)..."):
        prof = profile(df)
    summary = _issue_summary(prof)
    if summary is None:
        console.print("[green]Profiler found no issues - nothing to clean.[/green]")
        raise typer.Exit()
    console.print(summary)
    console.print()

    if recipe:
        from yoda.recipe import load_recipe
        planner_obj = RuleBasedPlanner()  # verifier follow-ups stay deterministic
        plan = load_recipe(recipe)
        console.print(f"[dim]Step 2/5 Plan loaded from recipe [bold]{recipe}[/bold] "
                      "(previously human-approved).[/dim]\n")
    elif planner == "rule_based":
        planner_obj = RuleBasedPlanner()
        plan = planner_obj.plan(prof)
        console.print("[dim]Step 2/5 Planner: rule-based baseline (no LLM).[/dim]\n")
    else:
        planner_obj = LLMPlanner(model=model)
        with console.status(f"[cyan]Step 2/5[/cyan] Planning with [bold]{model}[/bold] "
                            "(sees the profile above, never your data)..."):
            plan = planner_obj.plan(prof)
        src = planner_obj.last_outcome.get("source")
        if src == "fallback_rule_based":
            console.print("[yellow]LLM plan invalid or Ollama unavailable after retries - "
                          "fell back to the deterministic rule-based plan.[/yellow]")
            for e in planner_obj.last_outcome.get("errors", []):
                console.print(f"[dim]  {e}[/dim]")
            console.print("[dim]Tip: is Ollama running? Try `ollama serve` or "
                          f"`ollama pull {model}`.[/dim]\n")
        else:
            console.print(f"[dim]Step 2/5 Plan produced by {model} in "
                          f"{planner_obj.last_outcome.get('attempts')} attempt(s), "
                          "validated against the JSON schema.[/dim]\n")

    if not plan:
        console.print("[green]Planner proposed no steps - nothing to clean.[/green]")
        raise typer.Exit()

    if dry_run:
        render_plan(plan, console, title="Cleaning plan (dry run - nothing was executed)")
        console.print("[dim]Re-run without --dry-run to apply.[/dim]")
        raise typer.Exit()

    console.print("[cyan]Step 3/5[/cyan] Your approval - nothing runs without it:")
    approved = approve_plan(plan, console, auto_yes=yes or bool(recipe))
    if not approved:
        console.print("[yellow]No steps approved - exiting without touching anything.[/yellow]")
        raise typer.Exit()
    if save_recipe:
        from yoda.recipe import save_recipe as _save
        _save(approved, save_recipe, source=path)
        console.print(f"[dim]Recipe saved to [bold]{save_recipe}[/bold] - replay with "
                      f"`yoda clean other.csv --recipe {save_recipe}`.[/dim]")

    src_path = Path(path)
    tag = f"_{table}" if table else ""
    audit_path = src_path.with_name(src_path.stem + tag + "_audit.jsonl")
    console.print(f"\n[cyan]Step 4/5[/cyan] Executing {len(approved)} step(s) "
                  "(deterministic pandas):")
    cleaned, audit = execute(df, approved, audit_path=audit_path, on_step=_print_step)
    rounds = [{"plan": approved, "audit": audit}]

    # Verifier loop: re-profile, diff, at most ONE follow-up round.
    with console.status("[cyan]Step 5/5[/cyan] Verifying (re-profile + diff)..."):
        new_prof = profile(cleaned)
        verdicts = diff_profiles(prof, new_prof)
    followup = follow_up_plan(verdicts, planner_obj, new_prof)
    if followup:
        console.print(f"\n[yellow]Verifier: {len(followup)} issue(s) survived round 1 - "
                      "proposing a follow-up round.[/yellow]")
        approved2 = approve_plan(followup, console, auto_yes=yes)
        if approved2:
            audit_path2 = src_path.with_name(src_path.stem + tag + "_audit_round2.jsonl")
            console.print("\nExecuting follow-up round:")
            cleaned, audit2 = execute(cleaned, approved2, audit_path=audit_path2,
                                      on_step=_print_step)
            rounds.append({"plan": approved2, "audit": audit2})
            new_prof = profile(cleaned)
            verdicts = diff_profiles(prof, new_prof)

    out_path = save(cleaned, path, table=table)
    report_path = src_path.with_name(src_path.stem + tag + "_report.md")
    write_report(report_path, source=str(path), before_profile=prof,
                 after_profile=new_prof, rounds=rounds, verdicts=verdicts)

    console.print()
    console.print(_verification_table(verdicts))

    n_open = sum(v["verdict"] in ("unresolved", "new_issue") for v in verdicts)
    n_changed = sum(e.get("rows_affected", 0) for r in rounds for e in r["audit"])
    verdict_line = ("[green]all detected issues resolved or flagged[/green]"
                    if n_open == 0 else
                    f"[yellow]{n_open} issue(s) still open - see report[/yellow]")
    console.print(Panel.fit(
        f"[bold green]Done[/bold green] in {len(rounds)} round(s) - "
        f"{len(df)} -> {len(cleaned)} rows, {n_changed} cell/row changes\n"
        f"Verifier: {verdict_line}\n\n"
        f"Cleaned data  [bold]{out_path}[/bold]\n"
        f"Audit log     [bold]{audit_path}[/bold]\n"
        f"Report        [bold]{report_path}[/bold]\n\n"
        f"[dim]Your original file was not modified.[/dim]",
        border_style="green", title="Results"))


@app.command()
def scan(
    path: str = typer.Argument(..., help="File to scan for PII"),
    table: str = typer.Option(None, help="Table name (SQLite inputs)"),
    out: str = typer.Option(None, help="Also write a markdown report here"),
) -> None:
    """Report where PII lives (emails, PH phones, names) - touches nothing."""
    from yoda.io import load
    from yoda.scan import scan as _scan, scan_markdown

    df = load(path, table=table)
    result = _scan(df)
    t = Table(title="PII scan (counts only - values never shown)",
              title_style="bold", border_style="dim")
    for c in ("column", "risk", "detected", "cells", "notes"):
        t.add_column(c)
    risk_style = {"high": "red", "medium": "yellow", "low": "green"}
    for f in result["columns"]:
        det = ", ".join(f"{k} x{v}" for k, v in f["detected"].items()) or "-"
        notes = "PII-suggestive name" if f["sensitive_name"] else ""
        t.add_row(f["col"], f"[{risk_style[f['risk']]}]{f['risk']}[/]",
                  det, str(f["n_cells"]), notes)
    console.print(t)
    s = result["summary"]
    console.print(f"\n{s['n_columns_with_pii']}/{s['n_columns_scanned']} columns "
                  f"contain PII - highest risk: [bold]{s['highest_risk']}[/bold]")
    if out:
        Path(out).write_text(scan_markdown(result, path), encoding="utf-8")
        console.print(f"Report written to [bold]{out}[/bold]")
    raise typer.Exit(code=1 if s["highest_risk"] == "high" else 0)


@app.command()
def validate(
    path: str = typer.Argument(..., help="File to validate"),
    contract: str = typer.Option(..., help="Contract file (YAML or JSON)"),
    table: str = typer.Option(None, help="Table name (SQLite inputs)"),
) -> None:
    """Check a file against a data contract; exit 1 on any violation."""
    from yoda.contract import load_contract, validate as _validate
    from yoda.io import load

    result = _validate(load(path, table=table), load_contract(contract))
    t = Table(title=f"Contract: {contract}", title_style="bold", border_style="dim")
    for c in ("rule", "column", "violations", "detail", "verdict"):
        t.add_column(c)
    for r in result["results"]:
        t.add_row(r["rule"], r["col"] or "whole table", str(r["violations"]),
                  r["detail"],
                  "[green]pass[/green]" if r["passed"] else "[red]FAIL[/red]")
    console.print(t)
    if result["passed"]:
        console.print("[green]Contract satisfied.[/green]")
    else:
        console.print(f"[red]{result['n_violations']} violation(s) across "
                      f"{sum(not r['passed'] for r in result['results'])} rule(s).[/red]")
        raise typer.Exit(code=1)


@app.command()
def watch(
    folder: str = typer.Argument(..., help="Folder to watch for new CSV/XLSX files"),
    recipe: str = typer.Option(..., help="Recipe JSON to apply to every new file"),
    out: str = typer.Option(None, help="Output folder (default <folder>/cleaned)"),
    quarantine: str = typer.Option(None, help="Quarantine folder (default <folder>/quarantine)"),
    contract: str = typer.Option(None, help="Also enforce a data contract on the cleaned output"),
    interval: float = typer.Option(5.0, help="Poll interval in seconds"),
    once: bool = typer.Option(False, "--once", help="Process current files, then exit"),
) -> None:
    """Auto-clean every file dropped into a folder using a saved recipe.

    Files that fail recipe validation or leave unresolved issues after
    verification are quarantined with a reason file, never silently shipped.
    """
    from yoda.recipe import load_recipe
    from yoda.watch import run_watch

    steps = load_recipe(recipe)
    contract_data = None
    if contract:
        from yoda.contract import load_contract
        contract_data = load_contract(contract)
    out_dir = out or str(Path(folder) / "cleaned")
    q_dir = quarantine or str(Path(folder) / "quarantine")
    _banner(f"watch mode - {len(steps)}-step recipe - Ctrl+C to stop")
    console.print(f"Watching [bold]{folder}[/bold] -> cleaned: [bold]{out_dir}[/bold] "
                  f"| quarantine: [bold]{q_dir}[/bold]\n")

    def show(r: dict) -> None:
        if r["status"] == "cleaned":
            console.print(f"  [green]cleaned[/green] {r['file']} "
                          f"({r['rows']} rows) -> {r['out']}")
        else:
            console.print(f"  [yellow]quarantined[/yellow] {r['file']} - {r['reason']}")

    try:
        run_watch(folder, steps, out_dir, q_dir, interval=interval,
                  once=once, on_result=show, contract=contract_data)
    except KeyboardInterrupt:
        console.print("\n[dim]watch stopped.[/dim]")


@app.command()
def web(
    port: int = typer.Option(8000, help="Port on 127.0.0.1"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't auto-open a browser"),
) -> None:
    """Launch the local web UI (binds to 127.0.0.1 only - never exposed)."""
    try:
        from yoda.web import serve
    except ImportError:
        console.print("[red]Web UI dependencies missing.[/red] "
                      "Install with: pip install 'yoda-agent[web]'")
        raise typer.Exit(code=1)
    _banner("local web UI - binds to 127.0.0.1 only - Ctrl+C to stop")
    console.print(f"Serving at [bold]http://127.0.0.1:{port}[/bold]")
    serve(port=port, open_browser=not no_browser)


@app.command("profile")
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
