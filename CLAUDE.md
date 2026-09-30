# YODA: Your Offline Data Agent

Privacy-first, fully local data-cleaning agent for CSV / Excel / SQLite. The LLM
never sees a raw row, and nothing leaves the machine. What shipped and the
honest numbers: [README.md](README.md). The original build plan, now historical:
[docs/ORIGINAL_PLAN.md](docs/ORIGINAL_PLAN.md).

Project-only rules. The global rules in `~/.claude/CLAUDE.md` also apply and are
not repeated here.

## The invariant that makes the pitch true

Raw cell values flow only profiler → executor. **Anything sent to the LLM goes
through the redactor first.** `tests/test_redactor.py::test_profile_contains_no_raw_pii`
serializes the whole profile and asserts no seeded secret appears. It covers the
profile, not the final prompt; any new path into the prompt needs its own test. "How do you know the LLM didn't corrupt
the data?" → "It can't. It never touches it."

- AI plans, deterministic pandas executes. Plans are strict JSON checked against
  a schema; invalid → re-prompt (max 3) → rule-based fallback.
- Every change is human-approved and audit-logged. Destructive ops stay
  recoverable: the executor keeps the original frame.
- The architecture is locked. Don't redesign it without asking John.

## Project rules

- Git identity for every commit here (so contributions count):
  `git -c user.email="238805789+Zeref538@users.noreply.github.com" -c user.name="Zeref538" commit ...`
- Before a big step (new benchmark run, model change, publishing), show John the
  results and wait for his sign-off.
- Honest metrics only: no cherry-picked runs. A failure goes in the README as a
  finding. **The rule-based baseline is always reported** next to the agent.
- Default model is **`qwen3.5:4b`** via Ollama (the README's numbers use it). A
  model change goes through the benchmark, never a hunch.
- Benchmark results under `benchmark/results/` are evidence: never edit or
  delete one by hand.

## Commands

```bash
pip install -e ".[web]"            # dev install
python -m pytest -q                # before every merge
ruff check .                       # CI runs the newest ruff
yoda clean data.csv                # CLI; add --planner rule_based without Ollama
yoda web                           # local UI at http://127.0.0.1:8000
python -m benchmark.run_benchmark --help   # ground-truth benchmark (runs locally; CI has no Ollama)
```
