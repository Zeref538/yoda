"""Load / save tabular files: CSV, Excel, SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def dedupe_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Make column names unique (a, a_2, a_3...). Duplicate names crash the
    profiler and make plans ambiguous; Excel/SQLite sources can produce them."""
    if not df.columns.duplicated().any():
        return df
    seen: dict[str, int] = {}
    new_cols = []
    for c in map(str, df.columns):
        seen[c] = seen.get(c, 0) + 1
        new_cols.append(c if seen[c] == 1 else f"{c}_{seen[c]}")
    out = df.copy()
    out.columns = new_cols
    return out


def load(path: str | Path, table: str | None = None) -> pd.DataFrame:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return dedupe_columns(pd.read_csv(p))
    if suffix in (".xlsx", ".xls"):
        return dedupe_columns(pd.read_excel(p))
    if suffix in (".sqlite", ".db", ".sqlite3"):
        with sqlite3.connect(p) as conn:
            if table is None:
                tables = [r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")]
                if len(tables) != 1:
                    raise ValueError(
                        f"database has tables {tables}; pick one with --table")
                table = tables[0]
            return dedupe_columns(pd.read_sql_query(f'SELECT * FROM "{table}"', conn))
    raise ValueError(f"unsupported file type: {suffix}")


def save(df: pd.DataFrame, src: str | Path, table: str | None = None) -> Path:
    """Write cleaned output next to the source as <name>_cleaned.<ext>."""
    p = Path(src)
    suffix = p.suffix.lower()
    out = p.with_name(p.stem + "_cleaned" + p.suffix)
    if suffix == ".csv":
        df.to_csv(out, index=False)
    elif suffix in (".xlsx", ".xls"):
        out = out.with_suffix(".xlsx")
        df.to_excel(out, index=False)
    elif suffix in (".sqlite", ".db", ".sqlite3"):
        with sqlite3.connect(out) as conn:
            df.to_sql(table or "cleaned", conn, index=False, if_exists="replace")
    else:
        raise ValueError(f"unsupported file type: {suffix}")
    return out
