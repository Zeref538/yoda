# Benchmark results — planner: `qwen3.5_2b`

| dataset | errors | detection | fix | false-fix |
|---|---:|---:|---:|---:|
| titanic_style | 292 | 100.0% | 96.2% | 0.00% |
| retail_orders | 315 | 52.4% | 68.2% | 0.00% |
| ph_customers | 290 | 41.4% | 41.4% | 0.00% |
| employees | 188 | 52.1% | 47.3% | 0.00% |
| clinic_patients | 220 | 68.2% | 65.9% | 0.00% |
| inventory | 284 | 15.8% | 18.7% | 0.00% |
| **overall** | **1589** | **54.8%** | **56.8%** | **0.00%** |

## Per error type (all datasets pooled)

| error type | n | detection | fix |
|---|---:|---:|---:|
| category_casing | 350 | 67.1% | 67.1% |
| currency_format | 40 | 0.0% | 0.0% |
| dtype_corruption | 165 | 42.4% | 69.1% |
| duplicate | 69 | 65.2% | 65.2% |
| mixed_date_format | 235 | 66.0% | 66.0% |
| null | 280 | 28.6% | 28.6% |
| outlier | 200 | 37.5% | 32.0% |
| phone_format | 40 | 0.0% | 0.0% |
| whitespace | 210 | 100.0% | 100.0% |
