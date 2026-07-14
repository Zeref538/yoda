"""Edge cases and regressions from the audit pass."""

import pandas as pd

from yoda import tools
from yoda.io import dedupe_columns
from yoda.planner import RuleBasedPlanner
from yoda.profiler import profile


def test_profile_empty_dataframe():
    p = profile(pd.DataFrame())
    assert p["n_rows"] == 0 and RuleBasedPlanner().plan(p) == []


def test_profile_all_null_column():
    p = profile(pd.DataFrame({"a": [None, None]}))
    assert p["columns"]["a"]["null_pct"] == 100.0


def test_duplicate_column_names_are_deduped():
    df = pd.DataFrame([[1, 2, 3]], columns=["x", "x", "y"])
    out = dedupe_columns(df)
    assert list(out.columns) == ["x", "x_2", "y"]
    profile(out)  # must not raise


def test_dedupe_columns_noop_when_unique():
    df = pd.DataFrame({"a": [1], "b": [2]})
    assert dedupe_columns(df) is df


def test_profiler_sampling_scales_counts():
    """Columns above the detection-sample size get scaled (approximate)
    pattern counts, but they must stay the right order of magnitude."""
    n = 60_000
    df = pd.DataFrame({"d": ["03/04/2021"] * n})
    got = profile(df)["columns"]["d"]["date_formats_seen"]["US (MM/DD/YYYY)"]
    assert abs(got - n) / n < 0.02


def test_normalize_dates_memoized_matches_per_cell_semantics():
    df = pd.DataFrame({"d": ["03/04/2021", "2021-01-01", "garbage",
                             None, "03/04/2021"]})
    out, stats = tools.normalize_dates(df, "d")
    assert out["d"].tolist()[:2] == ["2021-03-04", "2021-01-01"]
    assert out["d"].iloc[2] == "garbage" and pd.isna(out["d"].iloc[3])
    assert stats["rows_affected"] == 2  # two corrected cells (dupes count each)
    assert stats["parse_failures"] == 1
