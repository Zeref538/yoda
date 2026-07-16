# YODA 🧹 — Your Offline Data Agent

> A privacy-first, fully local data-cleaning agent. The LLM never sees a
> single raw row and **nothing leaves your machine**. The demo runs with
> Wi-Fi off.

**Headline result:** on a ground-truth benchmark of **1,589 labeled errors**
across 6 datasets, YODA's agent (qwen3.5:4b, ~3.4 GB, runs on a laptop) reaches
**94.3% detection / 94.8% fix rate with a 0.00% false-fix rate** — it never
"fixed" anything that wasn't broken. A deterministic rule-based baseline scores
100% / 97.3%, and that comparison — plus how the benchmark found and fixed the
agent's blind spot — is the honest core of this project
([full analysis below](#failure-analysis-what-the-benchmark-caught-and-what-fixing-it-cost)).
A second benchmark scores plain-language understanding: the 4b agent routes
**25/25 real cleaning instructions** (paraphrases and typos included) to the
right tool and column
([details](#instruction-benchmark-does-it-understand-what-you-ask)).

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
| qwen3.5:4b (agent, v2 prompt) | 94.3% | 94.8% | 0.00% |
| qwen3.5:4b (agent, v1 prompt) | 91.3% | 88.9% | 0.00% |
| qwen3.5:2b (agent, v2 prompt) | 54.8% | 56.8% | 0.00% |
| qwen3.5:2b (agent, v1 prompt) | 65.7% | 69.7% | 0.00% |

Per-dataset and per-error-type tables: [benchmark/results/](benchmark/results/).
Reproduce with `python -m benchmark.run_benchmark --planner llm --model qwen3.5:4b`
(plans auto-approved with the equivalent of `--yes`; no human in the loop for
benchmark runs).

### Instruction benchmark: does it understand what you ask?

The web UI accepts plain-language instructions ("remove blank rows", "change
the department to 1,2,3,4 depending on their unique value"). A second labeled
benchmark scores whether the planner routes **28 instructions** — verbatim
asks, paraphrases, typo'd requests, column-scoped asks, and should-refuse cases
— to the correct tool, column, and params:

| model | routed correctly | cleaning asks (25) | refusals (3) |
|---|---:|---:|---:|
| qwen3.5:4b | **26/28 (92.9%)** | **25/25** | 1/3 |
| qwen3.5:2b | 20/28 (71.4%) | 19/25 | 1/3 |

Findings ([full tables](benchmark/results/instructions/)):

- **The 4b model understood every real cleaning request** — including typos
  ("remvoe the blnak rows plz") and indirect phrasing ("Active, active and
  ACTIVE should be one category") — first attempt, correct params.
- **Its only misses were refusals**, and they fail safe: "delete everything"
  was *defused* into dropping blank rows/columns rather than obeyed, and
  "make the data look better for my boss" produced a full (harmless) cleaning
  plan instead of the expected empty one. The human gate still fronts every
  plan, so an over-eager plan costs one click to reject.
- **The 2b model confirms the size story**: it fumbles paraphrases the 4b
  handles (flag-vs-fill imputation, typo'd encode asks, range rules).

Reproduce with `python -m benchmark.run_instructions --model qwen3.5:4b`.

### Failure analysis: what the benchmark caught, and what fixing it cost

Recruiter-honest findings, not marketing:

- **The benchmark caught a systematic blind spot — and fixed it.** With the v1
  prompt, qwen3.5:4b scored **0/40 on currency errors**: the profile said
  `currency_like_values: 25`, but the model consistently chose
  `fix_dtypes(numeric)` (which can't parse `₱1,200.00`) over
  `normalize_currency`. A JSON schema can't fix tool *choice*, so the v2
  prompt added four few-shot signal→tool examples, including an explicit
  "currency beats fix_dtypes" rule. Result: currency **0% → 100%**, overall
  fix rate **88.9% → 94.8%**. That's the eval-driven loop working as designed.
- **The fix wasn't free — documented, not hidden.** The stern "never
  fix_dtypes on currency columns" rule made the 4b model more conservative
  everywhere: dtype-corruption detection dropped 100% → 69.7% and null
  flagging 100% → 85.7%. Net +5.9 points, but prompt engineering moves
  probability mass around; it doesn't add capability.
- **The same prompt made the smaller model worse.** qwen3.5:2b went **65.7% →
  54.8%** detection with the v2 prompt — the added instructions exceeded what
  a 2b model can follow and it started skipping obvious steps. One prompt is
  not optimal across model sizes; per-model prompts would be the next step.
- **The rule-based baseline still wins on mechanical dirt.** Every error type
  here has a statistical signature the profiler detects perfectly, so
  deterministic "signal → tool" mapping is unbeatable on this benchmark. The
  agent's value proposition is ambiguous dirt (semantic category merging,
  domain rules, natural-language column instructions) — which the web UI
  exercises but this benchmark version does not yet score.
- **Zero fallbacks were needed**: every LLM benchmark plan across both prompt
  versions was genuine first-attempt model output, schema-valid on try one.
  The retry/fallback machinery exists and is tested (mocked) but real models
  never triggered it. Valid JSON ≠ good plan remains the 2b lesson.
- **Why fix rate ≠ 100% even for the baseline**: stacked corruptions interact —
  e.g. a cell that is both nulled and in an outlier column shifts the IQR, so
  ~15% of injected outliers stop being statistical outliers at all.

## Install & use

Requires Python 3.11+ and [Ollama](https://ollama.com) with a small model
(default `qwen3.5:4b`, ~3.4 GB; any JSON-capable instruct model works).
Inputs: CSV, Excel, SQLite, Parquet.

```bash
pip install -e .
ollama pull qwen3.5:4b

yoda clean data.csv                      # full loop with human approval
yoda clean data.csv --dry-run            # show the plan, touch nothing
yoda clean db.sqlite --table customers   # works on databases too
yoda clean db.sqlite --all-tables        # ...or every table in one go
yoda clean data.csv --planner rule_based # no-AI baseline mode
yoda profile data.csv                    # print exactly what the LLM would see
yoda web                                 # local web UI at http://127.0.0.1:8000

# privacy & quality gates
yoda scan data.csv                       # PII inventory (counts only, no values);
                                         # exit 1 when high-risk PII is found
yoda validate data.csv --contract c.yaml # enforce a data contract (ranges,
                                         # allowed values, uniqueness, regex)

# recipes: teach it once, replay forever
yoda clean data.csv --save-recipe weekly.json   # save the approved plan
yoda clean next_week.csv --recipe weekly.json   # replay it (pre-approved)
yoda watch ./inbox --recipe weekly.json --contract c.yaml
                                         # auto-clean a drop folder; recipe
                                         # mismatches, unresolved issues, and
                                         # contract breaches are quarantined
```

A contract file looks like:

```yaml
columns:
  age:      {min: 0, max: 120, not_null: true}
  segment:  {allowed: [Retail, SME, Enterprise]}
  order_id: {unique: true, required: true}
table:
  min_rows: 1
  no_duplicate_rows: true
```

### Local web UI

`pip install -e ".[web]"` then `yoda web` — a dark-mode "Mission Control" UI
(FastAPI + vanilla JS, zero CDNs, works with Wi-Fi off): a pipeline view with
detected-issue cards, a live data preview at the top (first 10/50 rows —
changed cells turn green with the old value on hover, new columns cyan), a
history timeline with revert-to-original and named versions, per-column stats,
recipes (save/apply), PII scan, and one-file Excel export (data + audit +
verification). Ask the agent in plain language — *"remove blank rows"*,
*"change the department to 1,2,3,4 depending on their unique value"*, *"replace
N/A with nothing in name"* — review its proposed steps, and approve before
anything runs. Cells are also directly editable (double-click), and everything
is undoable and audit-logged. The server binds to `127.0.0.1` only; it is a
local tool, never a service.

Outputs land next to your file: `<name>_cleaned.<ext>`, `<name>_audit.jsonl`,
`<name>_report.md`. Originals are never modified.

## The toolbox

`drop_duplicates` · `normalize_dates` (mixed → ISO 8601) · `normalize_phone`
(PH formats → E.164) · `normalize_currency` (₱/PHP/$ strings → float + currency
column) · `standardize_categories` · `encode_categories` (label-encode values →
1,2,3,4…; mapping fully audit-logged) · `fix_dtypes` · `impute_missing`
(**flag-only by default — never silently fills values**; mean/median/mode
allowed *only* on an explicit human instruction) · `flag_outliers` (flags,
never deletes) · `trim_whitespace` (incl. Unicode NFC) · `validate_rule` ·
`rename_columns` · `drop_blank_rows` · `drop_blank_columns` · `replace_values`

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
