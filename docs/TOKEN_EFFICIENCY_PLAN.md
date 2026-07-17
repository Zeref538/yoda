# Tipid — Token-Efficiency Fine-Tune of a Free Model

> Take a free open-weights model and fine-tune it to say the same thing in
> far fewer tokens — same correctness, roughly half the output length.
> Target headline: **−40–55% output tokens · quality within 1 pt · same model,
> same hardware.**
>
> **Timeline: late September – October 2026**, after [YODA-mini](YODA_MINI_PLAN.md)
> ships (reuses its LoRA tooling and eval discipline).

## Why this matters (the pitch)

Output tokens are the dominant cost of LLM serving: latency scales with tokens
generated, and API pricing bills output tokens at 3–5x input rates. Most open
models are verbose by default — restating the question, hedging, over-explaining.
A model fine-tuned to be *terse but complete* is directly worth money: same
quality, ~half the latency and serving cost. "I made a free model 2x cheaper to
run with no quality loss, and here's the benchmark" is a resume line any
inference/platform team understands instantly.

## Ground rules

- **Only verifiable tasks.** Every task family must have a mechanical
  correctness check, so "quality preserved" is measured, never vibes:
  - math word problems (final answer check, GSM8K-style),
  - structured extraction (JSON schema + field-exact match),
  - short code functions (unit tests pass),
  - YODA planning profiles (executor + verifier accept the plan).
- Quality and token counts always reported **together** — a shorter wrong
  answer is a failure, not a saving.
- Same reproducibility discipline as YODA-mini: committed configs, seeds,
  frozen eval (`tipid-eval-v1`).

## Method

**Compression distillation:** generate concise gold outputs, verify they are
still correct, fine-tune on them.

1. Run the base model on training prompts → capture its (verbose) outputs.
2. A teacher rewrites each output to its minimal complete form — answer
   preserved, filler removed (no restating the question, no hedging, no
   "Certainly!", CoT collapsed to the minimum steps that still reach the
   answer).
3. **Keep a pair only if the compressed output still passes the task's
   mechanical check.** Log the rejection rate.
4. LoRA SFT on the (prompt → concise output) pairs.

## Phases

### Phase 0 — Baseline (week 1)
- [ ] Pick base: qwen3.5:1.7b (primary; same as yoda-mini for tooling reuse).
- [ ] Freeze `tipid-eval-v1`: ~150 held-out items per task family.
- [ ] Measure base model: accuracy, mean/median output tokens, tokens/sec,
      per family. Also measure the teacher for reference.
- **Exit gate:** baseline table committed. If the base is already terse on some
  family (<20% headroom), drop that family.

### Phase 1 — Data (weeks 2–3)
- [ ] 2–5k prompts per family from public sets (GSM8K train split, synthetic
      extraction docs, MBPP-style functions, YODA profile corpus — Phase 1
      assets reused).
- [ ] Compression pipeline (steps 1–3 above) with provenance JSONL.
- [ ] Report compression stats: mean tokens before/after, rejection rate.
- **Exit gate:** ≥ 30% average token reduction in the gold data itself —
  if the ceiling is lower than that, the headline is unreachable; re-scope.

### Phase 2 — Train (week 4)
- [ ] LoRA SFT (Unsloth, free Kaggle/Colab GPU), one YAML + seed per run.
- [ ] Ablation: mixed-family training vs per-family adapters.
- [ ] Merge → GGUF → Ollama tag `tipid`.

### Phase 3 — Evaluate (week 5)
- [ ] Three-way on `tipid-eval-v1`: base vs tipid vs teacher.
- [ ] Per family: accuracy Δ, token Δ, latency Δ (CPU), plus a
      cost-per-1k-requests table at current API output-token prices.
- [ ] Overcompression analysis: cases where brevity broke correctness.
- **Exit gate:** honest verdict in `docs/TIPID_EVAL.md`.

### Phase 4 — Ship (week 6)
- [ ] Hugging Face model card + GGUF (recipe, eval table, limitations).
- [ ] Writeup: method, rejection-rate story, where it failed.
- [ ] Portfolio card + optional YODA integration (`--model tipid` for terse
      plans → faster runs; feeds the yoda-mini speed metric).

## Success criteria

| outcome | bar |
|---|---|
| Minimum ship | −30% tokens, accuracy within 2 pts on all families |
| Good | −45% tokens, accuracy within 1 pt |
| Headline | −50%+ tokens, accuracy matched, with cost table |

## Risks

- **Quality collapses under brevity** on math → allow minimal CoT (compressed,
  not deleted); report the tradeoff curve if needed.
- **Base already terse** → measured in Phase 0 before any training time is spent.
- **Benchmark contamination** (GSM8K is widely trained-on) → report absolute
  accuracy only as Δ vs the same base model, which cancels contamination.
- **Timeline slip from yoda-mini** → phases are independent of yoda-mini's
  outcome; only the tooling is shared.
