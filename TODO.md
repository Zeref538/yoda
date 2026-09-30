# TODO

## Left to do

- [ ] Add a leak test on the final prompt, not just the profile: feed the PII fixture
      through the planner with a fake `_chat` (as in `tests/test_llm_planner.py`),
      capture `messages`, assert no seeded secret appears. The original plan asked
      for this; today only `test_profile_contains_no_raw_pii` exists (found 2026-09-30).
