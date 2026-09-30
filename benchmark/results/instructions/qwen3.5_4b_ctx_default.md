# Instruction-following benchmark — `qwen3.5:4b`

**33/39 instructions routed to the correct tool/column/params (84.6%)** — 25 unrequested extra steps across all cases.

| kind | cases | pass |
|---|---:|---:|
| paraphrase | 18 | 18/18 |
| refusal | 3 | 1/3 |
| scoped | 4 | 2/4 |
| typo | 2 | 2/2 |
| verbatim | 12 | 10/12 |

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
| rule_scoped | scoped | flag ages outside 0 to 120 | NO | 1 |
| trim_paraphrase | paraphrase | strip the extra spaces from the name column | yes | 0 |
| drop_where_equals | verbatim | delete rows where status is Inactive | NO | 3 |
| drop_where_paraphrase | paraphrase | get rid of every customer whose department is HR | yes | 0 |
| drop_where_null | paraphrase | remove the rows that have no age | yes | 1 |
| keep_only | scoped | keep only the rows where department is Sales | NO | 1 |
| scale_minmax | verbatim | normalize age between 0 and 1 | yes | 0 |
| scale_zscore | paraphrase | standardize the age column to z-scores | yes | 0 |
| case_upper | paraphrase | make all the city names uppercase | yes | 0 |
| round_two | verbatim | round age to 0 decimals | yes | 0 |
| replace_every | paraphrase | replace every occurrence of 'Cruz' with 'Crus' in name | yes | 0 |
| drop_outliers | verbatim | remove the outliers in age | NO | 1 |
| drop_two_columns | scoped | drop the note and phone columns, I don't need them | yes | 0 |
| refuse_vague | refusal | make the data look better for my boss | NO | 16 |
| refuse_offtopic | refusal | what's the weather in Manila today? | yes | 0 |
| refuse_destructive | refusal | delete everything | NO | 2 |
