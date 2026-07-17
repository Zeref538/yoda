# YODA-mini — Fine-Tuned Planner Model

> Replace YODA's stock planner (qwen3.5:4b) with a small model fine-tuned
> specifically for data-cleaning planning — then publish the head-to-head
> benchmark. Target headline: **fine-tuned 1.5B ≈ teacher quality · faster ·
> runs on any laptop.**
>
> **Timeline: August – mid-September 2026** (part-time, alongside internship).

## Why

- YODA's quality ceiling is the planner. The executor is deterministic and the
  verifier already measures plan quality end-to-end (fix rate / false-fix rate),
  so planner improvements translate directly into the published metrics.
- The ground-truth benchmark (1,589 labeled errors + 39-instruction suite)
  already exists — the hard part of any fine-tuning project (a trustworthy eval)
  is done.
- Deliverables double as public artifacts: a model card on Hugging Face, a
  reproducible training recipe, and an honest three-way eval.

## Ground rules

- Same trust architecture as YODA: the fine-tuned model still only sees
  PII-redacted profiles and still emits strict JSON plans. Nothing about the
  privacy guarantee changes.
- Report results honestly, including where the fine-tune loses to the teacher.
- Everything reproducible: seeds, configs, and data-gen scripts committed.

## Phase 0 — Baseline & harness (week 1: Aug 3–9)

- [ ] Freeze the eval: benchmark datasets, metrics, and scoring script tagged
      (`eval-v1`). No changes after this point.
- [ ] Measure the incumbents on the full benchmark:
      qwen3.5:4b (current), qwen3.5:1.7b (small base), teacher model
      (GPT-5-mini via Azure, or qwen 14B local).
- [ ] Record per-model: detection %, fix %, false-fix %, JSON-validity %,
      tokens/sec (CPU), peak RAM.
- **Exit gate:** a table of baseline numbers committed to `docs/`. If the small
  base model is already ≥ 95% of the 4b's fix rate, re-scope (distillation gain
  would be marginal — pivot target to beating the *teacher*).

## Phase 1 — Training data generation (weeks 2–3: Aug 10–23)

- [ ] Corpus: 300–500 messy datasets — synthetic error injection over clean
      seeds (reuse benchmark's error taxonomy: missing values, dtype drift,
      duplicates, outliers, encoding issues, unit inconsistencies) + public
      messy CSVs. **Zero overlap with eval datasets.**
- [ ] Run the teacher over the corpus; capture (profile → plan) pairs.
- [ ] **Execution-validated filtering:** keep only plans that YODA's executor
      applies cleanly AND the verifier confirms improved the dataset. Reject
      the rest. (This is the differentiator — validated data, not blind
      distillation.)
- [ ] Include instruction-following pairs mirroring the 39-instruction suite
      style (plain-language constraints → constrained plans).
- [ ] Target: 3–8k validated pairs. Store as JSONL with provenance.
- **Exit gate:** dataset stats documented (size, error-type coverage, rejection
  rate). Rejection rate itself is a reportable number.

## Phase 2 — Fine-tuning (weeks 4–5: Aug 24 – Sep 6)

- [ ] LoRA SFT with Unsloth on Kaggle/Colab free GPU.
      Base: qwen3.5:1.7b (primary), 4b (stretch).
- [ ] Config discipline: one experiment = one committed YAML + seed.
      Track train/val loss on a held-out 10% split.
- [ ] Ablations if time allows: with/without instruction pairs; 1 vs 2 epochs.
- [ ] Merge LoRA → GGUF (llama.cpp) → Ollama Modelfile → `yoda-mini` tag.
- **Exit gate:** `ollama run yoda-mini` produces valid plans on 10 smoke-test
  profiles.

## Phase 3 — Evaluation (week 6: Sep 7–13)

- [ ] Full benchmark, three-way: small base vs **yoda-mini** vs teacher
      (and the 4b incumbent for context).
- [ ] Report: detection / fix / false-fix / JSON-validity / speed / RAM, plus
      per-error-type breakdown (where does the fine-tune win and lose?).
- [ ] Failure analysis: 10 worst cases, categorized.
- **Exit gate:** results table + analysis in `docs/EVAL.md`. Honest verdict
  written even if the result is mixed.

## Phase 4 — Ship (Sep 14–20)

- [ ] `--model yoda-mini` flag in the CLI + Mission Control model picker.
- [ ] Hugging Face: model card (training data recipe, eval table, limitations,
      license) + GGUF upload.
- [ ] README section + portfolio card update with the headline metric.
- [ ] Blog-style writeup in `docs/` (data-gen → filtering → training → eval).

## Success criteria

| outcome | bar |
|---|---|
| Minimum ship | yoda-mini ≥ base-1.7b on fix rate with ≥ 99% JSON validity |
| Good | yoda-mini ≈ 4b incumbent quality at ~2x speed |
| Headline | yoda-mini within 3 pts of teacher fix rate, no false-fix regression |

Any of the three ships — the writeup frames whichever tier is reached.

## Risks

- **Free GPU limits** → keep runs < 4h (LoRA on 1.7b fits comfortably).
- **Teacher plans too uniform** (low diversity) → raise temperature, diversify
  error injection, dedupe near-identical pairs.
- **Eval leakage** → dataset provenance log; eval seeds never enter Phase 1.
- **September crunch** (classes + internship) → Phases 3–4 are deliberately
  light; Phase 1 is the only heavy one and sits in August.
