# Benchmark results — planner: `qwen3.5_4b`

| dataset | errors | detection | fix | false-fix |
|---|---:|---:|---:|---:|
| titanic_style | 292 | 100.0% | 96.2% | 0.00% |
| retail_orders | 315 | 100.0% | 98.4% | 0.00% |
| ph_customers | 290 | 100.0% | 100.0% | 0.00% |
| employees | 188 | 100.0% | 90.4% | 0.00% |
| clinic_patients | 220 | 100.0% | 97.7% | 0.00% |
| inventory | 284 | 95.1% | 93.7% | 0.00% |
| **overall** | **1589** | **99.1%** | **96.4%** | **0.00%** |

## Per error type (all datasets pooled)

| error type | n | detection | fix |
|---|---:|---:|---:|
| category_casing | 350 | 100.0% | 100.0% |
| currency_format | 40 | 100.0% | 100.0% |
| dtype_corruption | 165 | 100.0% | 91.5% |
| duplicate | 69 | 79.7% | 79.7% |
| mixed_date_format | 235 | 100.0% | 100.0% |
| null | 280 | 100.0% | 100.0% |
| outlier | 200 | 100.0% | 85.5% |
| phone_format | 40 | 100.0% | 100.0% |
| whitespace | 210 | 100.0% | 100.0% |
