# YODA cleaning report

- **Source:** `examples/customers.csv`
- **Generated:** 2026-07-14T17:04:02
- **Rows:** 160 → 150 · **Columns:** 8 → 10
- **Rounds:** 2 (max 2)

## Round 1 — executed steps

| # | tool | column | rows affected | status | detail |
|---:|---|---|---:|---|---|
| 1 | drop_duplicates | — | 10 | ok |  |
| 2 | trim_whitespace | email | 0 | ok |  |
| 3 | normalize_phone | phone | 15 | ok | 6********7 → +********7; 0********8 → +********8 |
| 4 | standardize_categories | city | 15 | ok | MAKATI → Makati; manila → Manila |
| 5 | normalize_dates | signup_date | 15 | ok | 20****** → 2024-05-12; 2025/02/22 → 2025-02-22 |
| 6 | impute_missing | email | 15 | ok |  |
| 7 | normalize_currency | monthly_spend | 150 | ok | php 4,318.16 → 4318.16; ₱7,947.36 → 7947.36 |
| 8 | standardize_categories | segment | 15 | ok | enterprise → Enterprise; Sme → SME |

## Round 2 — executed steps

| # | tool | column | rows affected | status | detail |
|---:|---|---|---:|---|---|
| 1 | trim_whitespace | full_name | 15 | ok |  ********g → M********g; S********e → S********e |

## Verification (profile diff)

| issue | column | before | after | verdict |
|---|---|---:|---:|---|
| nulls | email | 9.38 | 10.0 | 🚩 flagged |
| duplicates | — | 10 | 0 | ✅ resolved |
| casing_variants | city | 9 | 0 | ✅ resolved |
| whitespace | full_name | 26 | 0 | ✅ resolved |
| currency_strings | monthly_spend | 15 | 0 | ✅ resolved |
| numeric_as_string | monthly_spend | 145 | 0 | ✅ resolved |
| phone_format_chaos | phone | 4 | 0 | ✅ resolved |
| numeric_as_string | phone | 8 | 0 | ✅ resolved |
| casing_variants | segment | 7 | 0 | ✅ resolved |
| mixed_date_formats | signup_date | 5 | 0 | ✅ resolved |

**Summary:** all detected issues resolved or flagged.

_All sample values in this report are redacted; raw data never left this machine and was never shown to the language model._
