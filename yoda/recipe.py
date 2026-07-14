"""Recipes: save an approved cleaning plan and replay it on new files.

A recipe is the product of a human-approved run — replaying one is applying
a decision the user already made, so recipe runs don't re-gate each step.
Column existence is still validated against the new file's profile before
anything executes.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import jsonschema

from yoda.planner import PLAN_SCHEMA

RECIPE_VERSION = 1


def save_recipe(steps: list[dict], path: str | Path, source: str | None = None) -> Path:
    path = Path(path)
    data = {
        "yoda_recipe": RECIPE_VERSION,
        "created": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "steps": steps,
    }
    jsonschema.validate({"steps": steps}, PLAN_SCHEMA)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_recipe(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    steps = data["steps"] if isinstance(data, dict) else data  # bare lists ok
    jsonschema.validate({"steps": steps}, PLAN_SCHEMA)
    return steps
