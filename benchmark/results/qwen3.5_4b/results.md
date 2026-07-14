# Benchmark results — planner: `qwen3.5_4b`

| dataset | errors | detection | fix | false-fix |
|---|---:|---:|---:|---:|
| titanic_style | 292 | 100.0% | 96.2% | 0.00% |
| retail_orders | 315 | 84.1% | 82.5% | 0.00% |
| ph_customers | 290 | 86.2% | 86.2% | 0.00% |
| employees | 188 | 100.0% | 90.4% | 0.00% |
| clinic_patients | 220 | 84.1% | 84.1% | 0.00% |
| inventory | 284 | 95.1% | 93.7% | 0.00% |
| **overall** | **1589** | **91.3%** | **88.9%** | **0.00%** |

## Per error type (all datasets pooled)

| error type | n | detection | fix |
|---|---:|---:|---:|
| category_casing | 350 | 85.7% | 85.7% |
| currency_format | 40 | 0.0% | 0.0% |
| dtype_corruption | 165 | 100.0% | 91.5% |
| duplicate | 69 | 79.7% | 79.7% |
| mixed_date_format | 235 | 100.0% | 100.0% |
| null | 280 | 100.0% | 100.0% |
| outlier | 200 | 82.5% | 70.5% |
| phone_format | 40 | 100.0% | 100.0% |
| whitespace | 210 | 100.0% | 100.0% |
