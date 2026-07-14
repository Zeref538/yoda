"""YODA command-line interface."""

from __future__ import annotations

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
    model: str = typer.Option("qwen2.5:7b-instruct", help="Ollama model for the planner"),
    yes: bool = typer.Option(False, "--yes", help="Auto-approve the plan (benchmark runs)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan and report only; touch nothing"),
) -> None:
    """Profile, plan, approve, execute, verify. Implemented across Phases 1-3."""
    console.print("[yellow]Not implemented yet — Phase 1 in progress.[/yellow]")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
