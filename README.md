# YODA 🧹 — Your Offline Data Agent

> A privacy-first, fully local data-cleaning agent. The LLM never sees a
> single raw row and **nothing leaves your machine**. The demo runs with
> Wi-Fi off.

**Headline result:** on a ground-truth benchmark of **1,589 labeled errors**
across 6 datasets, YODA's agent (qwen3.5:4b, ~3.4 GB, runs on a laptop) reaches
**91.3% detection / 88.9% fix rate with a 0.00% false-fix rate** — it never
"fixed" anything that wasn't broken. A deterministic rule-based baseline scores
100% / 97.3%, and that comparison is the honest core of this project
([full analysis below](#failure-analysis-where-the-small-models-lose)).

## Why

Every company wants AI on their data; almost none want their data leaving the
building. YODA cleans messy tabular data (CSV / Excel / SQLite) with an
architecture where the AI physically cannot corrupt or leak your data:

1. **Everything runs locally** — Ollama + a small open model. No API, no internet.
2. **The LLM only ever sees metadata** — schema, statistical profile, redacted
   samples (`j***@g***.com`, `09**-***-4821`). *AI plans; deterministic pandas
   executes.* A unit test proves no unredacted value can reach a prompt.
3. **Every change is human-approved** (per-step y/n/edit in the CLI) and
   **audit-logged** (JSONL: rows affected, redacted before→after examples, timing).
4. **Quality is proven, not claimed** — a corruption benchmark with ground
   truth, including the metric most tools won't publish: the **false-fix rate**.

## How it works

```
dirty file ──▶ PROFILER (pure pandas) ──▶ profile JSON (metadata only, PII-redacted)
                                              │
                                              ▼
                                   PLANNER (local LLM, Ollama)
                                   strict JSON schema · 3 retries ·
                                   falls back to rule-based plan
                                              │
                                              ▼
                                    HUMAN GATE (approve/edit/skip)
                                              │
                                              ▼
                                   EXECUTOR (pure pandas) + audit log
                                              │
                                              ▼
                                   VERIFIER (re-profile → diff → verdicts,
                                   max 1 follow-up round)
                                              │
                                              ▼
                       cleaned file + audit_log.jsonl + report.md
```

The verifier loop earns its keep in practice: in one demo run the 4b model
missed whitespace damage in a name column; the verifier's profile diff caught
it and the follow-up round fixed it. See a real generated
[example report](docs/example_report.md).

## Benchmark (ground truth, honest numbers)

Six clean datasets (Titanic-style passengers, retail orders, PH-flavored
customers via Faker `en_PH`, employees, clinic patients, inventory — all
generated offline, seeded) are programmatically corrupted with **labeled**
dirt: duplicates, mixed date formats, PH phone chaos, currency strings,
category casing, dtype corruption, nulls, outliers, whitespace. A scorer
compares YODA's output against the corruption manifest.

| planner | detection | fix rate | false-fix rate |
|---|---:|---:|---:|
| rule-based baseline (no AI) | **100.0%** | **97.3%** | 0.00% |
| qwen3.5:4b (agent) | 91.3% | 88.9% | 0.00% |
| qwen3.5:2b (agent) | 65.7% | 69.7% | 0.00% |

Per-dataset and per-error-type tables: [benchmark/results/](benchmark/results/).
Reproduce with `python -m benchmark.run_benchmark --planner llm --model qwen3.5:4b`
(plans auto-approved with the equivalent of `--yes`; no human in the loop for
benchmark runs).

### Failure analysis: where the small models lose

Recruiter-honest findings, not marketing:

- **The rule-based baseline wins on mechanical dirt.** Every error type in this
  benchmark has a statistical signature the profiler detects perfectly, so
  deterministic "signal → tool" mapping is unbeatable here. The agent's value
  proposition is ambiguous dirt (semantic category merging, domain rules) —
  which this benchmark version does not yet test. Publishing that instead of
  hiding it is the point.
- **qwen3.5:4b's one systematic blind spot: currency (0% of 40).** The profile
  says `currency_like_values: 25`; the model consistently chooses
  `fix_dtypes(numeric)` instead of `normalize_currency`. The coercion then
  fails on `₱1,200.00` strings. A schema `enum` can't fix tool *choice* —
  this is a prompt/fine-tuning problem, documented as such.
- **qwen3.5:2b degrades where reasoning is needed**: it skips ~71% of null
  flags and ~57% of outlier flags, and misses dtype corruption it can plainly
  see in the profile (24% detection). Structured output kept its JSON 100%
  valid — every 2b plan parsed on the first try. Valid JSON ≠ good plan.
- **Zero fallbacks were needed**: all 12 LLM benchmark plans were genuine
  first-attempt model output. The retry/fallback machinery exists and is
  tested (mocked) but wasn't exercised by these models.
- **Why fix rate ≠ 100% even for the baseline**: stacked corruptions interact —
  e.g. a cell that is both nulled and in an outlier column shifts the IQR, so
  ~15% of injected outliers stop being statistical outliers at all.

## Install & use

Requires Python 3.11+ and [Ollama](https://ollama.com) with a small model
(default `qwen3.5:4b`, ~3.4 GB; any JSON-capable instruct model works):

```bash
pip install -e .
ollama pull qwen3.5:4b

yoda clean data.csv                      # full loop with human approval
yoda clean data.csv --dry-run            # show the plan, touch nothing
yoda clean db.sqlite --table customers   # works on databases too
yoda clean data.csv --planner rule_based # no-AI baseline mode
yoda profile data.csv                    # print exactly what the LLM would see
yoda web                                 # local web UI at http://127.0.0.1:8000

# recipes: teach it once, replay forever
yoda clean data.csv --save-recipe weekly.json   # save the approved plan
yoda clean next_week.csv --recipe weekly.json   # replay it (pre-approved)
yoda watch ./inbox --recipe weekly.json         # auto-clean a drop folder;
                                                # failures are quarantined
```

### Local web UI

`pip install -e ".[web]"` then `yoda web` — a dark-mode, spreadsheet-style UI
(FastAPI + vanilla JS, zero CDNs, works with Wi-Fi off). Click a column and
tell the AI what to do with it in plain language; approve its suggested fixes;
changed cells turn green (hover shows the old value), new columns cyan.
Excel-like editing (drag-select, edit/delete cells, rows and columns), full
history timeline with revert-to-original, named versions, per-column stats,
recipes (save/apply), and one-file Excel export (data + audit + verification).
The server binds to `127.0.0.1` only; it is a local tool, never a service.

Outputs land next to your file: `<name>_cleaned.<ext>`, `<name>_audit.jsonl`,
`<name>_report.md`. Originals are never modified.

## The toolbox

`drop_duplicates` · `normalize_dates` (mixed → ISO 8601) · `normalize_phone`
(PH formats → E.164) · `normalize_currency` (₱/PHP/$ strings → float + currency
column) · `standardize_categories` · `fix_dtypes` · `impute_missing`
(**flag-only by default — never silently fills values**) · `flag_outliers`
(flags, never deletes) · `trim_whitespace` (incl. Unicode NFC) ·
`validate_rule` · `rename_columns`

Each tool is a pure function with unit tests; tools never mutate their input.

## Privacy guarantees, tested

- `tests/test_redactor.py` seeds a fixture with real-looking names, emails and
  PH phone numbers, then asserts none of them survive into the serialized
  profile — the only artifact the LLM ever receives.
- The report generator reuses the same redaction for before/after examples.
- The planner talks only to `localhost:11434`. Pull the model once, then the
  whole pipeline runs with Wi-Fi off.

---

Built by [John Andrei Martinez](https://johnandrei.vercel.app) · GitHub [@Zeref538](https://github.com/Zeref538)
