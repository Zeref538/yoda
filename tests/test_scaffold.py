"""Phase 0 smoke tests: the package imports and the CLI wires up."""

from typer.testing import CliRunner

import yoda
from yoda.cli import app


def test_version_string():
    assert yoda.__version__


def test_cli_version_command():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "YODA" in result.output


def test_cli_clean_is_stubbed():
    result = CliRunner().invoke(app, ["clean", "nonexistent.csv"])
    assert result.exit_code == 1
