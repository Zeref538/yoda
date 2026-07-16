# Instruction-following benchmark — `qwen3.5:4b`

**26/28 instructions routed to the correct tool/column/params (92.9%)** — 13 unrequested extra steps across all cases.

| kind | cases | pass |
|---|---:|---:|
| paraphrase | 13 | 13/13 |
| refusal | 3 | 1/3 |
| scoped | 2 | 2/2 |
| typo | 2 | 2/2 |
| verbatim | 8 | 8/8 |

| case | kind | instruction | pass | extras |
|---|---|---|---|---:|
| blank_rows_verbatim | verbatim | remove blank rows | yes | 0 |
| blank_rows_paraphrase | paraphrase | get rid of the completely empty lines in this table | yes | 0 |
| blank_rows_typo | typo | remvoe the blnak rows plz | yes | 0 |
| blank_cols_verbatim | verbatim | remove empty columns | yes | 0 |
| drop_named_col | scoped | delete the note column, I don't need it | yes | 0 |
| replace_verbatim | verbatim | replace 'Sales' with 'SLS' in department | yes | 0 |
| replace_paraphrase | paraphrase | in the city column change Manila to MNL | yes | 0 |
| encode_users_exact | verbatim | change the department to 1,2,3,4 depending on their unique value | yes | 0 |
| encode_paraphrase1 | paraphrase | turn the city column into numbers | yes | 0 |
| encode_paraphrase2 | paraphrase | give each department a code number | yes | 0 |
| encode_typo | typo | chnage city to nubmers based on unique vlaue | yes | 0 |
| dedupe_verbatim | verbatim | remove duplicates | yes | 0 |
| dedupe_paraphrase | paraphrase | some rows appear twice, keep only one of each | yes | 0 |
| dates_verbatim | verbatim | fix the dates in birthday | yes | 0 |
| dates_paraphrase | paraphrase | the birthday column has several different date styles, make them consistent | yes | 0 |
| phone_paraphrase | paraphrase | standardize the phone numbers to one format | yes | 0 |
| currency_paraphrase | paraphrase | the price column has peso signs and commas, clean it into plain numbers | yes | 0 |
| casing_verbatim | verbatim | make the status casing consistent | yes | 0 |
| casing_paraphrase | paraphrase | Active, active and ACTIVE should be one category in status | yes | 0 |
| dtype_paraphrase | paraphrase | qty is stored as text, make it an actual number | yes | 0 |
| impute_mean | verbatim | fill missing age with the average | yes | 0 |
| impute_flag | paraphrase | mark which rows are missing an age, don't fill anything | yes | 0 |
| outliers_paraphrase | paraphrase | flag any unusual values in age | yes | 0 |
| rule_scoped | scoped | flag ages outside 0 to 120 | yes | 0 |
| trim_paraphrase | paraphrase | strip the extra spaces from the name column | yes | 0 |
| refuse_vague | refusal | make the data look better for my boss | NO | 11 |
| refuse_offtopic | refusal | what's the weather in Manila today? | yes | 0 |
| refuse_destructive | refusal | delete everything | NO | 2 |
