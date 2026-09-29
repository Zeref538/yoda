# Next attempt: instruction routing

Status: **draft, not run.** Waiting for John's approval. Also blocked on
Ollama not being installed on this laptop (checked 2026-09-30: no `ollama`
command, nothing on port 11434).

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

**Not measured yet** (can't be: no Ollama). Plan once it's installed:
time one full `python -m benchmark.run_instructions --model qwen3.5:4b`
run, then multiply. Total runs: 3 baseline + 3 per idea = 9 runs for two
ideas, with idea 1 costing ~3x and idea 2 ~2x a baseline run. I'll write the
measured time here before starting the rest.

## Results

(empty until run)
