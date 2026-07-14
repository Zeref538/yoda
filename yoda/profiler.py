"""Profiler: pure-pandas metadata extraction. No AI, no raw-row output.

Emits a PROFILE dict (JSON-serializable) with schema, per-column stats,
detected format patterns, duplicate stats, outlier flags, and REDACTED
samples only. This is the sole artifact the planner LLM is allowed to see.
"""

from __future__ import annotations

import math
import re
import unicodedata

import pandas as pd

from yoda.redactor import redact_sample

_DATE_PATTERNS = {
    "ISO (YYYY-MM-DD)": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "US (MM/DD/YYYY)": re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$"),
    "EU (DD-MM-YYYY)": re.compile(r"^\d{1,2}-\d{1,2}-\d{4}$"),
    "long (Month DD, YYYY)": re.compile(r"^[A-Z][a-z]+ \d{1,2},? \d{4}$"),
    "compact (YYYYMMDD)": re.compile(r"^\d{8}$"),
    "slash-ISO (YYYY/MM/DD)": re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$"),
}
_PHONE_PATTERNS = {
    "local (09XXXXXXXXX)": re.compile(r"^09\d{9}$"),
    "intl (+639XXXXXXXXX)": re.compile(r"^\+639\d{9}$"),
    "dashed (63-9XX-XXX-XXXX)": re.compile(r"^63-9\d{2}-\d{3}-\d{4}$"),
    "spaced (0917 123 4567)": re.compile(r"^09\d{2} \d{3} \d{4}$"),
}
_CURRENCY_RE = re.compile(r"^\s*(?:₱|PHP|Php|php|\$|USD)\s*[\d,]+(?:\.\d+)?\s*$")
_NUMERIC_STR_RE = re.compile(r"^\s*-?[\d,]+(?:\.\d+)?\s*$")
_BOOL_STRINGS = {"true", "false", "yes", "no", "y", "n", "t", "f"}


def _safe(x: object) -> object:
    """Make numpy scalars / NaN JSON-safe."""
    if x is None:
        return None
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    if hasattr(x, "item"):
        return x.item()
    return x


def _detect_patterns(values: pd.Series, patterns: dict[str, re.Pattern]) -> dict[str, int]:
    found: dict[str, int] = {}
    for name, rx in patterns.items():
        n = int(values.astype(str).str.match(rx).sum())
        if n:
            found[name] = n
    return found


def _column_profile(name: str, s: pd.Series, n_rows: int) -> dict:
    non_null = s.dropna()
    info: dict = {
        "dtype": str(s.dtype),
        "null_pct": round(100.0 * (1 - len(non_null) / n_rows), 2) if n_rows else 0.0,
        "n_unique": int(non_null.nunique()),
    }

    if pd.api.types.is_bool_dtype(s):
        pass  # no stats beyond null/unique; quantiles are undefined for bools
    elif pd.api.types.is_numeric_dtype(s) and len(non_null):
        info.update(
            min=_safe(non_null.min()),
            max=_safe(non_null.max()),
            mean=_safe(round(float(non_null.mean()), 4)),
            std=_safe(round(float(non_null.std()), 4)) if len(non_null) > 1 else None,
        )
        # IQR outlier flag
        q1, q3 = non_null.quantile(0.25), non_null.quantile(0.75)
        iqr = q3 - q1
        if iqr > 0:
            n_out = int(((non_null < q1 - 1.5 * iqr) | (non_null > q3 + 1.5 * iqr)).sum())
            if n_out:
                info["iqr_outliers"] = n_out
    elif len(non_null):
        as_str = non_null.astype(str)

        dates = _detect_patterns(as_str, _DATE_PATTERNS)
        if dates:
            info["date_formats_seen"] = dates
        phones = _detect_patterns(as_str, _PHONE_PATTERNS)
        if phones:
            info["phone_formats_seen"] = phones

        n_currency = int(as_str.str.match(_CURRENCY_RE).sum())
        if n_currency:
            info["currency_like_values"] = n_currency
        n_numeric_str = int(as_str.str.match(_NUMERIC_STR_RE).sum())
        if n_numeric_str and not dates:
            info["numeric_as_string"] = n_numeric_str
        n_bool_str = int(as_str.str.lower().str.strip().isin(_BOOL_STRINGS).sum())
        if n_bool_str == len(non_null):
            info["bool_as_string"] = n_bool_str

        # Numeric-like object columns (e.g. numbers polluted with strings/
        # nulls) still deserve outlier stats — coerce and check.
        coerced = pd.to_numeric(
            as_str.str.replace(",", "", regex=False).str.strip(), errors="coerce"
        )
        if not dates and not phones and coerced.notna().mean() > 0.9 and len(coerced) > 10:
            q1, q3 = coerced.quantile(0.25), coerced.quantile(0.75)
            iqr = q3 - q1
            if iqr > 0:
                n_out = int(((coerced < q1 - 1.5 * iqr) | (coerced > q3 + 1.5 * iqr)).sum())
                if n_out:
                    info["iqr_outliers"] = n_out

        # Whitespace / unicode issues
        n_ws = int((as_str != as_str.str.strip()).sum())
        n_ws += int(as_str.str.contains(r"\s{2,}", regex=True).sum())
        if n_ws:
            info["whitespace_issues"] = n_ws
        n_nfc = sum(1 for v in as_str.head(500) if unicodedata.normalize("NFC", v) != v)
        if n_nfc:
            info["non_nfc_values"] = n_nfc

        # Category casing variants: low-cardinality columns whose values
        # collide when case-folded and trimmed.
        if info["n_unique"] <= max(20, n_rows // 20):
            canon = as_str.str.strip().str.lower().nunique()
            if canon < info["n_unique"]:
                info["casing_variants"] = {
                    "raw_unique": info["n_unique"],
                    "folded_unique": int(canon),
                    "values": sorted(as_str.unique().tolist())[:25],
                }

        # Redacted samples (most frequent values, shape only for PII cols)
        top = as_str.value_counts().head(5).index.tolist()
        info["redacted_samples"] = [redact_sample(v, name) for v in top]

    if not re.fullmatch(r"[a-z0-9_]+", name):
        info["non_snake_case_name"] = True
    return info


def profile(df: pd.DataFrame) -> dict:
    """Build the metadata profile for a dataframe. Contains no raw PII."""
    n_rows = len(df)
    cols = {c: _column_profile(str(c), df[c], n_rows) for c in df.columns}

    dup_full = int(df.duplicated().sum())
    key_candidates = [
        str(c)
        for c in df.columns
        if df[c].nunique() >= 0.9 * n_rows and re.search(r"id|key|code", str(c), re.I)
    ]
    dup_by_key = {}
    for k in key_candidates:
        n = int(df.duplicated(subset=[k]).sum())
        if n:
            dup_by_key[k] = n

    return {
        "n_rows": n_rows,
        "n_cols": len(df.columns),
        "columns": cols,
        "duplicates": {"full_row": dup_full, "by_key_candidate": dup_by_key},
    }
