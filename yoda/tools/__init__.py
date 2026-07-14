"""The agent's toolbox: each cleaning tool is a pure function with unit tests.

Planned tools (see CLAUDE.md): drop_duplicates, normalize_dates,
normalize_phone, normalize_currency, standardize_categories, fix_dtypes,
impute_missing, flag_outliers, trim_whitespace, validate_rule, rename_columns.
"""

TOOL_REGISTRY: dict = {}
