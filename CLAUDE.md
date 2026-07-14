# YODA — Your Offline Data Agent

> Privacy-first, fully local data-cleaning agent. An agentic AI that cleans messy tabular data
> (CSV / Excel / SQLite) where **the LLM never sees a single raw row** and
> **nothing ever leaves the machine**. Demo runs with Wi-Fi off.

Owner: John Andrei Martinez (GitHub **Zeref538**) — BS CS student, AI/ML portfolio.
This is a portfolio project: the goal is a repo + demo + honest eval table that
impresses both AI-engineer and data-analyst recruiters.

## The pitch (memorize this)

Every company wants AI on their data; almost none want their data leaving the
building. YODA solves data cleaning — 60–80% of every data job — with an agent
architecture where:

1. **Everything runs locally** (Ollama, small open model — no API, no internet).
2. **The LLM only ever sees metadata** (schema + statistical profile + redacted
   samples), never actual rows. *AI plans; deterministic pandas executes.*
3. Every change is **human-approved** and **audit-logged** (before/after counts).
4. Quality is proven by a **corruption benchmark with ground truth** — including
   a published **false-fix rate** (things it "fixed" that weren't broken).

If asked "how do you know the LLM didn't corrupt the data?" → "It can't. It
never touches it."

## Non-negotiable working rules

- Git identity for ALL commits in this repo:
  `git -c user.email="238805789+Zeref538@users.noreply.github.com" -c user.name="Zeref538" commit ...`
- **NEVER** add `Co-Authored-By: Claude` (or any AI co-author trailer).
- Commit + push after every meaningful change batch.
- **Phase gates**: finish a phase, show John the results (metrics/output), and
  WAIT for his sign-off before starting the next phase. No skipping ahead.
- Honest metrics only. Never cherry-pick runs. If the model fails at something,
  that goes in the README as a finding, not swept under the rug.
- Python: use whatever is on the machine (3.14 — note: no xgboost/lightgbm
  wheels; irrelevant here, we're pandas + sklearn-optional).
- Keep John in the loop: plan first, short updates, plain language.

## Architecture (locked — do not redesign without asking)

```
dirty file (CSV/XLSX/SQLite)
        │
        ▼
┌─ PROFILER (pure pandas, no AI) ────────────────────────────┐
│ emits PROFILE JSON only:                                   │
│  • columns, dtypes, row count                              │
│  • per column: % null, n_unique, min/max/mean/std          │
│  • detected patterns (date formats seen, phone formats,    │
│    casing variants of categories, currency symbols)        │
│  • duplicate stats (full-row and key-candidate)            │
│  • outlier flags (IQR / z-score)                           │
│  • REDACTED samples: "09**-***-4821", "j***@g***.com"      │
│    (regex-based PII masking: emails, PH phones, names cols)│
└────────────────────────────────────────────────────────────┘
        │ profile only
        ▼
┌─ PLANNER AGENT (local LLM via Ollama) ─────────────────────┐
│ loop: think → propose CLEANING PLAN as strict JSON:        │
│  [{"tool":"normalize_dates","col":"birthday",              │
│    "params":{"format":"ISO"},"reason":"3 formats found"},…]│
│ Validated against a JSON Schema. Invalid → re-prompt       │
│ (max 3 retries) → else fall back to rule-based plan.       │
└────────────────────────────────────────────────────────────┘
        │ plan
        ▼
  HUMAN GATE — show plan in CLI table; user approves /
  edits / rejects each step (or --yes for benchmark runs)
        │ approved plan
        ▼
┌─ EXECUTOR (pure pandas, deterministic, no AI) ─────────────┐
│ runs each tool; writes AUDIT LOG (JSONL): step, col,       │
│ rows_affected, before→after examples (redacted), timing    │
└────────────────────────────────────────────────────────────┘
        │ cleaned df
        ▼
┌─ VERIFIER ─────────────────────────────────────────────────┐
│ re-profile → diff vs original profile → agent reviews:     │
│ "resolved / partially resolved / new issue introduced" →   │
│ may propose ONE follow-up plan round (max 2 total rounds)  │
└────────────────────────────────────────────────────────────┘
        ▼
 clean file + audit_log.jsonl + report.md (human-readable)
```

**Key invariant:** raw cell values may only flow through profiler → executor.
Anything sent to the LLM must pass through the redactor. Add a unit test that
asserts the prompt-builder output contains no unredacted values from a seeded
PII fixture.

## Model & stack

- **LLM**: Ollama, default `qwen2.5:7b-instruct` (good JSON compliance);
  configurable via `--model`. Document RAM needs. Use Ollama's
  `format: "json"` / structured output.
- **Data**: pandas. **CLI**: `typer` + `rich` (pretty plan tables, diffs).
- Package as `yoda` with `pyproject.toml` (distribution name `yoda-agent` to
  avoid PyPI collisions); entry point `yoda clean data.csv`.
- Tests: pytest. CI: GitHub Actions (lint + unit tests; benchmark runs locally
  since CI has no GPU/Ollama — but include a mocked-LLM test of the full loop).

## Cleaning tools (the agent's toolbox — each a pure function + unit tests)

| tool | what it does |
|---|---|
| `drop_duplicates` | full-row or key-based dedupe |
| `normalize_dates` | mixed formats → ISO 8601 (dateutil + explicit format hints) |
| `normalize_phone` | PH-aware: `0917…` / `+63917…` / `63-917…` → E.164 |
| `normalize_currency` | `₱1,200.00` / `PHP 1200` / `1200` → float + currency col |
| `standardize_categories` | `Male/male/M/MALE` → canonical (agent supplies mapping, executor applies) |
| `fix_dtypes` | numeric-as-string, bool-as-string coercion with fail counts |
| `impute_missing` | mean / median / mode / constant / **flag-only** (never silent-default) |
| `flag_outliers` | IQR or z-score → adds `_outlier` bool col (flag, don't delete) |
| `trim_whitespace` | strip/collapse whitespace, unify unicode (NFC) |
| `validate_rule` | declarative check, e.g. `age in [0,120]` → violation flags |
| `rename_columns` | snake_case normalization |

Design rule: destructive ops (drop rows, overwrite values) always recoverable —
executor keeps original df; report shows exact diff counts.

## The benchmark (Phase 1 — built BEFORE any AI, this is the moat)

1. Take 6–8 clean public datasets (mix: Titanic, a retail/orders set, a PH-flavored
   synthetic customer table with names/phones/addresses via Faker, etc.).
2. `corruptor.py`: programmatically inject **labeled** dirt — duplicates,
   mixed date formats, category casing chaos, nulls, dtype corruption, outliers,
   whitespace, phone-format chaos. Emit `corruption_manifest.json` (ground truth:
   every injected error, its type, location).
3. Scorer compares YODA output vs manifest and reports per error type:
   - **detection rate** (found in plan)
   - **fix rate** (correctly repaired)
   - **false-fix rate** (changed something that wasn't corrupted)
   - rows perfectly restored vs original clean file
4. Results table goes in README, per model (qwen2.5:7b vs llama3.1:8b vs
   rule-based baseline). **The rule-based baseline is mandatory** — the story
   "agent beats heuristics on ambiguous dirt, ties on mechanical dirt" is the
   honest, credible finding.

## Employer-appeal features (build in this order of value)

1. Benchmark + false-fix rate + baseline comparison (above) — the #1 differentiator.
2. Audit log + `report.md` generation — compliance mindset.
3. PII redaction layer with a test proving no leakage into prompts.
4. Human-in-the-loop plan approval UI in the CLI (rich table, per-step y/n/edit).
5. **Failure-analysis section in README**: where the 7B model failed, how schema
   constraints fixed it (recruiters love this more than the successes).
6. `--dry-run` mode (plan + report, touch nothing).
7. SQLite support (`yoda clean db.sqlite --table customers`) — "works on databases,
   not just CSVs" matches John's original idea.
8. Optional (Phase 5, only if John wants): tiny local web UI (FastAPI + React)
   showing profile → plan → diff visually, for the demo video.
9. Demo video/GIF: run with Wi-Fi visibly OFF.

## Phases (gate after each)

- **Phase 0 — scaffold**: repo init, pyproject, package layout
  (`yoda/{profiler,redactor,planner,executor,verifier,tools,report}.py`),
  CI, this file. Gate: John says go.
- **Phase 1 — truth first**: profiler + redactor + corruptor + scorer +
  rule-based baseline planner (no LLM). Gate: baseline benchmark table.
- **Phase 2 — the agent**: Ollama planner, JSON-schema validation, retries,
  fallback; human gate; executor + audit log. Gate: agent benchmark vs baseline.
- **Phase 3 — verifier loop + report.md** + failure analysis. Gate: final
  metrics table + example report reviewed by John.
- **Phase 4 — polish**: README (metrics front and center), demo GIF, SQLite,
  `--dry-run`, publish repo public, add card to portfolio site
  (portfolio repo has its own conventions: rebuild RAG index after data.js edits).
- **Phase 5 (optional)** — local web UI.

## Portfolio card (draft for later)

- Title: **YODA — Your Offline Data Agent** · tags: `Python, Agentic AI, Ollama, Pandas, Privacy`
- Metric: whatever the honest headline is, e.g. "94% fix rate, 1.8% false-fix, 100% local"
- Description: "Privacy-first data-cleaning agent — a local LLM plans repairs
  from metadata only (raw rows never reach the model), deterministic pandas
  executes with a full audit trail. Benchmarked against ground-truth corruption."
