# YODA 🧹 — Your Offline Data Agent

> A privacy-first, fully local data-cleaning agent. The LLM never sees a
> single raw row and **nothing leaves your machine**. The demo runs with
> Wi-Fi off.

**Status: in development** — see `CLAUDE.md` for the full build spec and phase plan.

## How it works

AI plans. Deterministic code executes.

1. **Profiler** (pure pandas) reads your file and produces a metadata profile:
   schema, null %, duplicate stats, detected format chaos, redacted samples.
2. **Planner agent** (local LLM via Ollama) sees *only that profile* and emits
   a structured cleaning plan.
3. **You approve** each step (human-in-the-loop).
4. **Executor** (pure pandas) applies the plan deterministically, writing a
   full audit log of every change.
5. **Verifier** re-profiles and confirms the issues are actually resolved.

The LLM cannot corrupt or leak your data — it never touches it.

```bash
yoda clean data.csv
```

## Honest evaluation (coming with Phase 2)

Clean public datasets are programmatically corrupted with *labeled* dirt, so
every metric has ground truth: detection rate, fix rate, and **false-fix rate**
(things "fixed" that weren't broken), benchmarked against a rule-based baseline.

---

Built by [John Andrei Martinez](https://johnandrei.vercel.app) · GitHub [@Zeref538](https://github.com/Zeref538)
