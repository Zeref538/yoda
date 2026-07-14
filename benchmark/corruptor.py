"""Corruptor: injects labeled dirt into clean datasets.

Every injected error is recorded in a manifest (ground truth): error type,
column, and the key of the affected row. The scorer later compares YODA's
output against this manifest to compute detection / fix / false-fix rates.

The key column of each dataset is never corrupted — it is the alignment
handle the scorer uses to match output rows back to clean rows.
"""

from __future__ import annotations

import random

import pandas as pd

# Which columns of each dataset receive which corruption types.
SPECS: dict[str, dict] = {
    "titanic_style": {
        "key": "passenger_id",
        "duplicates": 12,
        "casing": ["sex", "embarked"],
        "nulls": ["age", "fare"],
        "dtype": ["fare"],
        "outliers": ["age"],
        "whitespace": ["name"],
    },
    "retail_orders": {
        "key": "order_id",
        "duplicates": 15,
        "dates": ["order_date"],
        "casing": ["category"],
        "nulls": ["quantity"],
        "dtype": ["unit_price"],
        "outliers": ["quantity"],
        "whitespace": ["product"],
    },
    "ph_customers": {
        "key": "customer_id",
        "duplicates": 10,
        "dates": ["signup_date"],
        "phones": ["phone"],
        "currency": ["monthly_spend"],
        "casing": ["segment", "city"],
        "nulls": ["email"],
        "whitespace": ["full_name"],
    },
    "employees": {
        "key": "employee_id",
        "duplicates": 8,
        "dates": ["hire_date"],
        "casing": ["department", "performance"],
        "nulls": ["salary"],
        "dtype": ["salary"],
        "outliers": ["salary"],
    },
    "clinic_patients": {
        "key": "patient_id",
        "duplicates": 10,
        "dates": ["birth_date", "last_visit"],
        "casing": ["blood_type"],
        "nulls": ["weight_kg"],
        "outliers": ["weight_kg"],
        "whitespace": ["name"],
    },
    "inventory": {
        "key": "sku",
        "duplicates": 14,
        "dates": ["restock_date"],
        "casing": ["warehouse"],
        "nulls": ["unit_cost"],
        "dtype": ["stock"],
        "outliers": ["unit_cost"],
        "whitespace": ["product_name"],
    },
}

_DATE_MUTATORS = [
    lambda d: d.strftime("%m/%d/%Y"),
    lambda d: d.strftime("%B %d, %Y"),
    lambda d: d.strftime("%Y%m%d"),
    lambda d: d.strftime("%Y/%m/%d"),
]
_CASE_MUTATORS = [str.upper, str.lower, str.title, str.swapcase]
_WS_MUTATORS = [
    lambda s: "  " + s,
    lambda s: s + "   ",
    lambda s: s.replace(" ", "  ", 1),
    lambda s: "\t" + s + " ",
]


def _phone_mutate(rng: random.Random, e164: str) -> str:
    digits = e164.lstrip("+")  # 639XXXXXXXXX
    local = "0" + digits[2:]   # 09XXXXXXXXX
    return rng.choice([
        local,
        f"63-{digits[2:5]}-{digits[5:8]}-{digits[8:]}",
        f"{local[:4]} {local[4:7]} {local[7:]}",
    ])


def _currency_mutate(rng: random.Random, x: float) -> str:
    return rng.choice([f"₱{x:,.2f}", f"PHP {x:.2f}", f"php {x:,.2f}"])


def corrupt(df: pd.DataFrame, name: str, seed: int = 42,
            rate: float = 0.10) -> tuple[pd.DataFrame, dict]:
    """Return (dirty_df, manifest). ~`rate` of rows per targeted column."""
    spec = SPECS[name]
    key = spec["key"]
    rng = random.Random(seed)
    out = df.copy()
    errors: list[dict] = []

    def pick(col: str) -> list[int]:
        candidates = [i for i in out.index if pd.notna(out.at[i, col])]
        return rng.sample(candidates, max(3, int(len(candidates) * rate)))

    def record(etype: str, col: str, idx: int):
        errors.append({"type": etype, "col": col, "key": str(df.at[idx, key])})

    for col in spec.get("dates", []):
        for i in pick(col):
            d = pd.Timestamp(out.at[i, col])
            out.at[i, col] = rng.choice(_DATE_MUTATORS)(d)
            record("mixed_date_format", col, i)

    for col in spec.get("phones", []):
        for i in pick(col):
            out.at[i, col] = _phone_mutate(rng, out.at[i, col])
            record("phone_format", col, i)

    for col in spec.get("currency", []):
        out[col] = out[col].astype(object)
        for i in pick(col):
            out.at[i, col] = _currency_mutate(rng, float(out.at[i, col]))
            record("currency_format", col, i)

    for col in spec.get("casing", []):
        for i in pick(col):
            orig = str(out.at[i, col])
            variants = [m(orig) for m in _CASE_MUTATORS if m(orig) != orig]
            if variants:
                out.at[i, col] = rng.choice(variants)
                record("category_casing", col, i)

    for col in spec.get("dtype", []):
        out[col] = out[col].astype(object)
        for i in pick(col):
            v = out.at[i, col]
            out.at[i, col] = f"{v:,}" if isinstance(v, int) else f" {v} "
            record("dtype_corruption", col, i)

    for col in spec.get("outliers", []):
        for i in pick(col):
            out.at[i, col] = out.at[i, col] * 100
            record("outlier", col, i)

    for col in spec.get("whitespace", []):
        for i in pick(col):
            out.at[i, col] = rng.choice(_WS_MUTATORS)(str(out.at[i, col]))
            record("whitespace", col, i)

    for col in spec.get("nulls", []):
        out[col] = out[col].astype(object)
        for i in pick(col):
            out.at[i, col] = None
            record("null", col, i)

    n_dup = spec.get("duplicates", 0)
    if n_dup:
        dup_idx = rng.sample(list(out.index), n_dup)
        for i in dup_idx:
            record("duplicate", key, i)
        out = pd.concat([out, out.loc[dup_idx]], ignore_index=True)
        # shuffle so duplicates aren't all at the bottom
        out = out.sample(frac=1, random_state=seed).reset_index(drop=True)

    manifest = {"dataset": name, "key": key, "seed": seed,
                "n_errors": len(errors), "errors": errors}
    return out, manifest
