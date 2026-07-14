# Benchmark results — planner: `qwen3.5_2b`

| dataset | errors | detection | fix | false-fix |
|---|---:|---:|---:|---:|
| titanic_style | 292 | 100.0% | 96.2% | 0.00% |
| retail_orders | 315 | 52.4% | 68.2% | 0.00% |
| ph_customers | 290 | 72.4% | 72.4% | 0.00% |
| employees | 188 | 36.2% | 47.3% | 0.00% |
| clinic_patients | 220 | 52.3% | 52.3% | 0.00% |
| inventory | 284 | 68.3% | 69.7% | 0.00% |
| **overall** | **1589** | **65.7%** | **69.7%** | **0.00%** |

## Per error type (all datasets pooled)

| error type | n | detection | fix |
|---|---:|---:|---:|
| category_casing | 350 | 91.4% | 91.4% |
| currency_format | 40 | 0.0% | 0.0% |
| dtype_corruption | 165 | 24.2% | 69.1% |
| duplicate | 69 | 100.0% | 100.0% |
| mixed_date_format | 235 | 85.1% | 85.1% |
| null | 280 | 28.6% | 28.6% |
| outlier | 200 | 42.5% | 37.5% |
| phone_format | 40 | 100.0% | 100.0% |
| whitespace | 210 | 100.0% | 100.0% |
