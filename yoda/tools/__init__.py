"""YODA's cleaning toolbox: pure pandas functions, no AI.

Each tool takes (df, col, params) and returns (new_df, stats) where stats
is a JSON-safe dict with at least ``rows_affected``. Tools never mutate the
input dataframe. Destructive ops are recoverable because the executor keeps
the original df and logs exact diff counts.
"""

from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd
from dateutil import parser as dateparser

TOOLS: dict = {}


def _tool(fn):
    TOOLS[fn.__name__] = fn
    return fn


@_tool
def drop_duplicates(df: pd.DataFrame, col: str | None = None, params: dict | None = None):
    params = params or {}
    subset = params.get("subset") or ([col] if col else None)
    # Index is preserved (not reset) so callers can diff surviving rows.
    out = df.drop_duplicates(subset=subset, keep="first")
    return out, {"rows_affected": len(df) - len(out)}


@_tool
def drop_blank_rows(df: pd.DataFrame, col: str | None = None, params: dict | None = None):
    """Remove rows that are entirely empty (or empty in `col` if given).

    params.min_non_null (int): keep rows with at least this many non-null
    cells (default 1 = drop only fully blank rows). Whitespace-only strings
    count as blank. Index is preserved so callers can diff surviving rows.
    """
    params = params or {}
    # Treat whitespace-only strings as null for blankness purposes.
    with pd.option_context("future.no_silent_downcasting", True):
        probe = df.replace(r"^\s*$", pd.NA, regex=True) if len(df) else df
    if col:
        keep = probe[col].notna()
    else:
        min_non_null = int(params.get("min_non_null", 1))
        keep = probe.notna().sum(axis=1) >= min_non_null
    out = df[keep]
    return out, {"rows_affected": int(len(df) - len(out))}


@_tool
def drop_blank_columns(df: pd.DataFrame, col: str | None = None, params: dict | None = None):
    """Remove columns that are entirely empty (all null / whitespace-only).

    If `col` (or params.columns, a list) is given, drop those specific
    columns instead — an explicit user ask.
    """
    params = params or {}
    named = list(params.get("columns") or ([col] if col else []))
    if named:
        missing = [c for c in named if c not in df.columns]
        if missing:
            raise ValueError(f"column(s) do not exist: {missing}")
        out = df.drop(columns=named)
        return out, {"rows_affected": 0, "columns_dropped": named}
    with pd.option_context("future.no_silent_downcasting", True):
        probe = df.replace(r"^\s*$", pd.NA, regex=True) if len(df) else df
    blank = [c for c in df.columns if probe[c].isna().all()]
    out = df.drop(columns=blank)
    return out, {"rows_affected": 0, "columns_dropped": [str(c) for c in blank]}


@_tool
def replace_values(df: pd.DataFrame, col: str, params: dict | None = None):
    """Find/replace within one column. params: find (required), replace
    (default ""), regex (bool), contains (bool — replace the substring inside
    cells instead of whole-cell match), match_case (bool, default True)."""
    params = params or {}
    if "find" not in params:
        raise ValueError("replace_values needs params.find")
    find = str(params["find"])
    repl = str(params.get("replace", ""))
    use_regex = bool(params.get("regex", False))
    substring = bool(params.get("contains", False))
    match_case = bool(params.get("match_case", True))
    out = df.copy()
    s = out[col].astype("string")
    if use_regex or substring:
        pattern = find if use_regex else re.escape(find)
        flags = 0 if match_case else re.IGNORECASE
        try:
            rx = re.compile(pattern, flags)
        except re.error as exc:
            raise ValueError(f"invalid regex '{find}': {exc}") from exc
        new = s.str.replace(rx, repl, regex=True)
    else:
        if match_case:
            new = s.mask(s == find, repl)
        else:
            new = s.mask(s.str.lower() == find.lower(), repl)
    n = int((new != s).fillna(False).sum())
    out[col] = new.where(s.notna(), other=out[col])
    return out, {"rows_affected": n}


@_tool
def drop_rows_where(df: pd.DataFrame, col: str, params: dict | None = None):
    """Delete (or keep only) rows matching a condition on one column.
    Destructive — the planner may only propose it on an explicit user ask,
    and the executor keeps the original df so it is always recoverable.

    params — exactly one condition:
      equals: value            (whole-cell match; match_case bool, default True)
      contains: substring      (literal, case-insensitive if match_case=False)
      regex: pattern
      is_null: true            (rows where the cell is missing)
      min / max: number        (rows with value < min or > max are dropped)
    plus keep: true  — invert: keep ONLY the matching rows instead.
    """
    params = params or {}
    s = df[col]
    match_case = bool(params.get("match_case", True))

    if "equals" in params:
        target = str(params["equals"])
        vals = s.astype(str)
        mask = (vals == target) if match_case else (vals.str.lower() == target.lower())
    elif "contains" in params:
        mask = s.astype(str).str.contains(re.escape(str(params["contains"])),
                                          case=match_case, na=False)
    elif "regex" in params:
        try:
            mask = s.astype(str).str.contains(params["regex"], regex=True, na=False)
        except re.error as exc:
            raise ValueError(f"invalid regex '{params['regex']}': {exc}") from exc
    elif params.get("is_null"):
        mask = s.isna()
    elif "min" in params or "max" in params:
        num = pd.to_numeric(s, errors="coerce")
        mask = pd.Series(False, index=df.index)
        if "min" in params:
            mask |= num < params["min"]
        if "max" in params:
            mask |= num > params["max"]
    else:
        raise ValueError("drop_rows_where needs one of: equals, contains, "
                         "regex, is_null, min/max")
    mask = mask.fillna(False)
    if params.get("keep"):
        mask = ~mask
    out = df[~mask]  # index preserved for diffing
    return out, {"rows_affected": int(mask.sum())}


@_tool
def scale_numeric(df: pd.DataFrame, col: str, params: dict | None = None):
    """Scale a numeric column: minmax (0..1) or zscore. The scaling constants
    go into stats so the transform is documented and invertible."""
    params = params or {}
    method = params.get("method", "minmax")
    out = df.copy()
    s = pd.to_numeric(out[col], errors="coerce").astype(float)
    s = s.mask(~np.isfinite(s.fillna(0.0)) & s.notna())
    if s.notna().sum() < 2:
        raise ValueError(f"'{col}' needs at least 2 numeric values to scale")
    if method == "minmax":
        lo, hi = s.min(), s.max()
        if hi == lo:
            raise ValueError(f"'{col}' is constant; nothing to scale")
        out[col] = (s - lo) / (hi - lo)
        stats = {"min": float(lo), "max": float(hi)}
    elif method == "zscore":
        mu, sd = s.mean(), s.std()
        if sd == 0:
            raise ValueError(f"'{col}' is constant; nothing to scale")
        out[col] = (s - mu) / sd
        stats = {"mean": round(float(mu), 6), "std": round(float(sd), 6)}
    else:
        raise ValueError(f"unknown scale method: {method}")
    return out, {"rows_affected": int(s.notna().sum()), "method": method, **stats}


@_tool
def format_text(df: pd.DataFrame, col: str, params: dict | None = None):
    """Unify text casing in a column: upper / lower / title / sentence."""
    params = params or {}
    case = params.get("case", "title")
    out = df.copy()
    s = out[col].astype("string")
    fns = {"upper": lambda v: v.upper(), "lower": lambda v: v.lower(),
           "title": lambda v: v.title(),
           "sentence": lambda v: v[:1].upper() + v[1:].lower() if v else v}
    if case not in fns:
        raise ValueError(f"unknown case: {case} (use upper/lower/title/sentence)")
    new = s.map(lambda v: v if pd.isna(v) else fns[case](str(v)))
    n = int((new != s).fillna(False).sum())
    out[col] = new
    return out, {"rows_affected": n, "case": case}


@_tool
def round_numbers(df: pd.DataFrame, col: str, params: dict | None = None):
    """Round a numeric column to N decimals (default 2)."""
    params = params or {}
    decimals = int(params.get("decimals", 2))
    out = df.copy()
    s = pd.to_numeric(out[col], errors="coerce")
    if s.notna().sum() == 0:
        raise ValueError(f"'{col}' has no numeric values to round")
    rounded = s.round(decimals)
    n = int(((rounded != s) & s.notna()).sum())
    # only overwrite cells that parsed as numbers; text/nulls stay untouched
    out[col] = rounded.where(rounded.notna(), other=out[col])
    return out, {"rows_affected": n, "decimals": decimals}


@_tool
def encode_categories(df: pd.DataFrame, col: str, params: dict | None = None):
    """Label-encode a column: map each distinct value to an integer code
    (e.g. 1,2,3,4). Nulls stay null. The full value->code mapping is returned
    in stats so the change is auditable and reversible.

    params: start (int, default 1); order ("sorted" | "frequency" |
    "appearance", default "sorted"); new_column (bool, default False —
    replace in place; True adds a <col>_code column instead).
    """
    params = params or {}
    start = int(params.get("start", 1))
    order = params.get("order", "sorted")
    new_column = bool(params.get("new_column", False))
    out = df.copy()
    s = out[col]
    non_null = s.dropna()
    if order == "frequency":
        cats = list(non_null.value_counts().index)
    elif order == "appearance":
        cats = list(dict.fromkeys(non_null.tolist()))
    else:  # sorted (deterministic, predictable to a human)
        cats = sorted(non_null.unique(), key=lambda v: str(v))
    mapping = {v: i for i, v in enumerate(cats, start=start)}
    target = f"{col}_code" if new_column else col
    out[target] = s.map(lambda v: v if pd.isna(v) else mapping[v])
    return out, {"rows_affected": int(s.notna().sum()),
                 "n_categories": len(mapping), "target": target,
                 "mapping": {str(k): v for k, v in mapping.items()}}


@_tool
def normalize_dates(df: pd.DataFrame, col: str, params: dict | None = None):
    params = params or {}
    dayfirst = bool(params.get("dayfirst", False))
    out = df.copy()

    # Parse each distinct value once (date columns repeat heavily), then map.
    mapping: dict = {}
    failed: set = set()
    for v in out[col].dropna().unique():
        s = str(v).strip()
        try:
            if re.fullmatch(r"\d{8}", s):
                d = pd.Timestamp(s[:4] + "-" + s[4:6] + "-" + s[6:])
            else:
                d = dateparser.parse(s, dayfirst=dayfirst)
            mapping[v] = d.strftime("%Y-%m-%d")
        except (ValueError, OverflowError):
            mapping[v] = v
            failed.add(v)

    old = out[col]
    out[col] = old.map(lambda v: v if pd.isna(v) else mapping[v])
    n_changed = int(((out[col].astype(str) != old.astype(str)) & old.notna()).sum())
    n_failed = int(old.isin(failed).sum())
    return out, {"rows_affected": n_changed, "parse_failures": n_failed}


@_tool
def normalize_phone(df: pd.DataFrame, col: str, params: dict | None = None):
    """PH-aware: 0917... / +63917... / 63-917-... -> E.164 (+639XXXXXXXXX)."""
    out = df.copy()
    n_changed = n_failed = 0

    def conv(v):
        nonlocal n_changed, n_failed
        if pd.isna(v):
            return v
        s = str(v)
        digits = re.sub(r"\D", "", s)
        if digits.startswith("09") and len(digits) == 11:
            e164 = "+63" + digits[1:]
        elif digits.startswith("639") and len(digits) == 12:
            e164 = "+" + digits
        elif digits.startswith("9") and len(digits) == 10:
            e164 = "+63" + digits
        else:
            n_failed += 1
            return v
        if e164 != s:
            n_changed += 1
        return e164

    out[col] = out[col].map(conv)
    return out, {"rows_affected": n_changed, "parse_failures": n_failed}


@_tool
def normalize_currency(df: pd.DataFrame, col: str, params: dict | None = None):
    """'₱1,200.00' / 'PHP 1200' / '1200' -> float, plus a <col>_currency column."""
    out = df.copy()
    # Categorical .map() operates on categories, not values — flatten first.
    out[col] = out[col].astype(object)
    n_changed = n_failed = 0
    currencies = []

    def conv(v):
        nonlocal n_changed, n_failed
        if pd.isna(v):
            currencies.append(None)
            return v
        s = str(v).strip()
        m = re.match(r"^(₱|PHP|Php|php|\$|USD)?\s*(-?[\d,]+(?:\.\d+)?)$", s)
        if not m:
            n_failed += 1
            currencies.append(None)
            return v
        sym = m.group(1)
        currencies.append({"₱": "PHP", "$": "USD"}.get(sym, sym.upper() if sym else "PHP"))
        n_changed += 1
        return float(m.group(2).replace(",", ""))

    out[col] = out[col].map(conv)
    out[f"{col}_currency"] = currencies
    out[col] = pd.to_numeric(out[col], errors="coerce")
    return out, {"rows_affected": n_changed, "parse_failures": n_failed}


@_tool
def standardize_categories(df: pd.DataFrame, col: str, params: dict | None = None):
    """Apply a value mapping. If none given, fold case/whitespace to the
    most frequent variant of each group (deterministic fallback)."""
    params = params or {}
    mapping: dict = dict(params.get("mapping") or {})
    out = df.copy()
    s = out[col].astype("string")
    if not mapping:
        folded = s.str.strip().str.lower()
        for key in folded.dropna().unique():
            variants = s[folded == key]
            canonical = variants.mode().iloc[0].strip()
            for v in variants.unique():
                if v != canonical:
                    mapping[v] = canonical
    n = int(s.isin(mapping.keys()).sum())
    out[col] = s.map(lambda v: mapping.get(v, v))
    return out, {"rows_affected": n, "mapping_size": len(mapping)}


@_tool
def fix_dtypes(df: pd.DataFrame, col: str, params: dict | None = None):
    params = params or {}
    target = params.get("target", "numeric")
    out = df.copy()
    s = out[col]
    if target == "numeric":
        cleaned = s.astype(str).str.replace(",", "", regex=False).str.strip()
        converted = pd.to_numeric(cleaned, errors="coerce")
        n_failed = int((converted.isna() & s.notna()).sum())
        n_changed = int((converted.notna() & s.notna()).sum())
        out[col] = converted.where(s.notna(), other=pd.NA)
    elif target == "bool":
        truthy = {"true": True, "yes": True, "y": True, "t": True, "1": True,
                  "false": False, "no": False, "n": False, "f": False, "0": False}
        low = s.astype(str).str.strip().str.lower()
        converted = low.map(truthy)
        n_failed = int((converted.isna() & s.notna()).sum())
        n_changed = int(converted.notna().sum())
        out[col] = converted.where(s.notna(), other=pd.NA)
    else:
        raise ValueError(f"unknown dtype target: {target}")
    return out, {"rows_affected": n_changed, "coercion_failures": n_failed}


@_tool
def impute_missing(df: pd.DataFrame, col: str, params: dict | None = None):
    """Strategies: mean / median / mode / constant / flag_only. Never a
    silent default — flag_only just adds <col>_missing without touching data."""
    params = params or {}
    strategy = params.get("strategy", "flag_only")
    out = df.copy()
    n_null = int(out[col].isna().sum())
    if strategy == "flag_only":
        out[f"{col}_missing"] = out[col].isna()
        return out, {"rows_affected": n_null, "strategy": strategy}
    if strategy in ("mean", "median"):
        numeric = pd.to_numeric(out[col], errors="coerce").astype(float)
        numeric = numeric.mask(~np.isfinite(numeric.fillna(0.0)) & numeric.notna())
        if numeric.notna().sum() == 0:
            raise ValueError(f"impute '{strategy}' needs a numeric column; "
                             f"'{col}' has no numeric values")
        fill = numeric.mean() if strategy == "mean" else numeric.median()
    elif strategy == "mode":
        modes = out[col].mode()
        if modes.empty:
            raise ValueError(f"'{col}' has no values to compute a mode from")
        fill = modes.iloc[0]
    elif strategy == "constant":
        fill = params.get("value")
        if fill is None:
            raise ValueError("impute 'constant' needs params.value")
    else:
        raise ValueError(f"unknown impute strategy: {strategy}")
    out[f"{col}_missing"] = out[col].isna()
    if isinstance(out[col].dtype, pd.CategoricalDtype) \
            and fill not in out[col].cat.categories:
        out[col] = out[col].astype(object)  # fill value is a new category
    with pd.option_context("future.no_silent_downcasting", True):
        out[col] = out[col].fillna(fill).infer_objects(copy=False)
    return out, {"rows_affected": n_null, "strategy": strategy, "fill_value": str(fill)}


@_tool
def flag_outliers(df: pd.DataFrame, col: str, params: dict | None = None):
    """IQR or z-score -> adds <col>_outlier bool column. Flags by default —
    params.action="drop" removes the flagged rows instead, and the planner
    may only propose that on an explicit user ask (recoverable regardless:
    the executor keeps the original df)."""
    params = params or {}
    method = params.get("method", "iqr")
    out = df.copy()
    s = pd.to_numeric(out[col], errors="coerce").astype(float)
    s = s.mask(~np.isfinite(s.fillna(0.0)) & s.notna())  # ±inf -> NaN
    if method == "iqr":
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        mask = (s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)
    elif method == "zscore":
        z = (s - s.mean()) / s.std()
        mask = z.abs() > float(params.get("threshold", 3.0))
    else:
        raise ValueError(f"unknown outlier method: {method}")
    mask = mask.fillna(False)
    if params.get("action") == "drop":
        out = out[~mask]  # index preserved for diffing
        return out, {"rows_affected": int(mask.sum()), "method": method,
                     "action": "drop"}
    out[f"{col}_outlier"] = mask
    return out, {"rows_affected": int(mask.sum()), "method": method}


@_tool
def trim_whitespace(df: pd.DataFrame, col: str, params: dict | None = None):
    out = df.copy()
    s = out[col].astype("string")

    def conv(v):
        if pd.isna(v):
            return v
        return unicodedata.normalize("NFC", re.sub(r"\s+", " ", str(v)).strip())

    new = s.map(conv)
    n = int((new != s).fillna(False).sum())
    out[col] = new
    return out, {"rows_affected": n}


@_tool
def validate_rule(df: pd.DataFrame, col: str, params: dict | None = None):
    """Declarative range/set check -> adds <col>_invalid flag column."""
    params = params or {}
    out = df.copy()
    s = out[col]
    invalid = pd.Series(False, index=out.index)
    if "min" in params:
        invalid |= pd.to_numeric(s, errors="coerce") < params["min"]
    if "max" in params:
        invalid |= pd.to_numeric(s, errors="coerce") > params["max"]
    if "allowed" in params:
        invalid |= ~s.isin(params["allowed"]) & s.notna()
    out[f"{col}_invalid"] = invalid.fillna(False)
    return out, {"rows_affected": int(invalid.sum())}


@_tool
def rename_columns(df: pd.DataFrame, col: str | None = None, params: dict | None = None):
    """snake_case all column names (or apply an explicit mapping)."""
    params = params or {}
    mapping = params.get("mapping")
    if not mapping:
        def snake(name: str) -> str:
            s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name))
            s = re.sub(r"[^\w]+", "_", s)
            return re.sub(r"_+", "_", s).strip("_").lower()
        mapping = {c: snake(c) for c in df.columns if snake(c) != c}
    out = df.rename(columns=mapping)
    return out, {"rows_affected": 0, "columns_renamed": len(mapping)}


# Back-compat alias used by the Phase 0 scaffold.
TOOL_REGISTRY = TOOLS
