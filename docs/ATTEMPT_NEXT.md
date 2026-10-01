# Next attempt: instruction routing

Status: **run 2026-09-30 to 2026-10-01, approved by John. Neither idea won;
the shipped planner is unchanged.** Results at the bottom.

## The one target number

**qwen3.5:4b instruction routing: 33/39 (84.6%)**, from
`benchmark/results/instructions/qwen3.5_4b.md`.

Why this one: the autonomous benchmark (99.1% / 96.4%) is already within a
point of the rule-based baseline. The instruction benchmark is the agent's
whole reason to exist, and it is the lowest agent number in the README. The
6 misses: `rule_scoped`, `drop_where_equals`, `keep_only`, `drop_outliers`,
`refuse_vague`, `refuse_destructive`.

**Known weakness of the current number:** it is one run. The planner sends
`temperature: 0.1` with no seed, so a re-run can land a case or two
differently. Step 0 below measures that before comparing anything.

## What was tried already (not repeated)

- v1 -> v2 -> v3 prompts: few-shot signal->tool examples, "currency beats
  fix_dtypes", worked examples for the analyst playbook, an "obey explicit
  instructions" section (commits 95744f0, 1cf2d54, e47df0a).
- JSON-schema structured output is already on (`format: PLAN_SCHEMA`).
- Thinking is already off for instruction requests.

So another round of prompt wording is out. That is the thing already done
three times, and writing examples that look like the 6 failing cases would
be tuning on the test set.

## Ideas (pick at most 2 to run)

1. **Vote over 3 samples (self-consistency).** Ask the model 3 times at a
   higher temperature (0.7), keep the plan whose (tool, column) set comes up
   most often. Why it should help: the misses look like coin-flip cases
   ("keep only" sometimes loses the inversion, per the README), and voting
   is the standard fix for that. Source: Wang et al., *Self-Consistency
   Improves Chain of Thought Reasoning in Language Models*, 2022,
   arXiv:2203.11171. Cost: 3x the model calls on the instruction path only.
2. **Intent first, then plan.** One small extra call: "which one tool does
   this instruction ask for, or `none`?" (enum-constrained output), then the
   normal plan call with that answer stated. Why: splitting a task into an
   easier first question helps small models, and the `none` answer is a
   direct shot at the 2 refusal misses. Source: Zhou et al., *Least-to-Most
   Prompting Enables Complex Reasoning in Large Language Models*, 2022,
   arXiv:2205.10625. Cost: ~2x calls.

Neither adds examples taken from the 39 cases.

## Rules fixed in advance

- **The 39 cases, their expected steps and `score_case` do not change.**
  Same fixture, same model (`qwen3.5:4b`), same machine.
- **Step 0:** run the current shipped planner 3 times. That gives the real
  baseline as mean and range, instead of the single 33/39.
- Each idea: **3 repeat runs**. Report mean and range (min-max) out of 39.
- **It wins only if** its mean beats the baseline mean by at least 2 cases
  (about 5 points) **and** its worst run is no lower than the baseline's
  best run minus 1. Two cases, because one case is within run-to-run noise.
- **Nothing else gets worse by more than 2 points:** the 4b autonomous
  benchmark (detection 99.1%, fix 96.4%, false-fix 0.00%) is re-run once if
  the change touches the autonomous path. Idea 1 and 2 both stay on the
  instruction path only, so it shouldn't, but I'll check that in the diff.
  False-fix must stay 0.00%.
- **One run per idea, no tuning after seeing the numbers.** If neither wins,
  the shipped planner stays and the README gets a short "tried, didn't help"
  paragraph with the numbers.

## Budget

**Measured, 2026-09-30:** one full `python -m benchmark.run_instructions --model
qwen3.5:4b` run took **15 minutes** (08:39:11 to 08:54:14, 39 cases, laptop CPU,
with the new `num_ctx: 8192`). It scored **34/39**; the previous run scored 33/39,
and exactly one case differs (`drop_where_equals` now passes). That run had no
fallbacks, so the difference is the model's own run-to-run variation, which is
why step 0 exists. This timing run counts as baseline run 1.

| step | runs | minutes per run | total |
|---|---:|---:|---:|
| Step 0: shipped planner | 2 more (3 in all) | 15 | 30 min |
| Idea 1: vote over 3 samples | 3 | ~45 (3x the calls, estimated from the 15) | ~2 h 15 min |
| Idea 2: intent first | 3 | ~30 (2x the calls, estimated) | ~1 h 30 min |
| **all** | | | **~4 h 15 min** |

The per-idea times are the measured 15 minutes times the extra calls, not
measured yet. If idea 1's first run takes over 60 minutes, stop and re-plan
rather than let it run 3 hours.

## Results

All 9 runs: `benchmark/results/instructions/attempt/`, times in `timings.json`.
Same 39 cases, same fixture, same scorer, qwen3.5:4b, one laptop.

| version | run 1 | run 2 | run 3 | mean | range | extra steps | minutes per run |
|---|---:|---:|---:|---:|---|---|---:|
| shipped (single) | 34 | 34 | 34 | 34.0 | 34-34 | 21, 21, 21 | 14-15 |
| idea 1: vote over 3 | 34 | 34 | 34 | 34.0 | 34-34 | 18, 20, 17 | 24-25 |
| idea 2: intent first | 34 | 34 | 34 | 34.0 | 34-34 | 20, 21, 22 | 17-19 |

**Verdict by the rule written in advance:** a win needed a mean of at least 36.
Both ideas averaged 34.0, the same as the shipped planner. Neither ships.

**What it found:**

- **The misses are not luck.** All 9 runs failed the same 5 asks:
  `drop_outliers` (flags instead of removing), `keep_only` (loses the
  inversion), `rule_scoped` ("flag ages outside 0 to 120"), and the refusals
  `refuse_vague` and `refuse_destructive`. Idea 1 assumed coin-flip misses;
  the model gives the same wrong answer every time, so a majority vote picks
  it again.
- **Naming the tool first did not move them either.** The intent call did not
  change which 5 asks fail, including the two refusals it was aimed at.
- **Voting trimmed unrequested extra steps slightly** (17-20 vs 21). Not part of
  the win rule, and too small to ship a 1.7x slower planner for.
- **The 33/39 published before was a single run** from before the context-window
  fix. Three runs of the shipped planner give 34/39 with zero spread.
- **Budget:** the plan guessed 45 and 30 minutes per run for the ideas; measured
  24-25 and 17-19. The runner was killed twice (session restart, then the
  laptop sleeping overnight) and resumed both times from the files on disk.

**Next, if anyone tries again:** these 5 need a different kind of fix, since
sampling and steering did nothing. Candidates: a validator-level rule for
"remove" vs "flag" outliers, and explicit refusal examples, written on new
cases so the 39 stay a fair test.

