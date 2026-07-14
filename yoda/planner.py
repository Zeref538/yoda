"""Planner: proposes a cleaning plan from the profile only.

Two implementations share one interface:
- RuleBasedPlanner (Phase 1): deterministic heuristics — the mandatory baseline.
- LLMPlanner (Phase 2): local model via Ollama, strict-JSON output validated
  against a JSON Schema, max 3 retries, falls back to the rule-based plan.
"""

from __future__ import annotations


class RuleBasedPlanner:
    """Baseline heuristic planner. Implemented in Phase 1."""

    def plan(self, profile: dict) -> list[dict]:
        raise NotImplementedError("Phase 1")


class LLMPlanner:
    """Ollama-backed planner. Implemented in Phase 2."""

    def __init__(self, model: str = "qwen2.5:7b-instruct") -> None:
        self.model = model

    def plan(self, profile: dict) -> list[dict]:
        raise NotImplementedError("Phase 2")
