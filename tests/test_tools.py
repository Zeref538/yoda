import pandas as pd
import pytest

from yoda import tools
from yoda.tools import TOOLS


def test_registry_has_all_planned_tools():
    expected = {"drop_duplicates", "normalize_dates", "normalize_phone",
                "normalize_currency", "standardize_categories", "fix_dtypes",
                "impute_missing", "flag_outliers", "trim_whitespace",
                "validate_rule", "rename_columns"}
    assert expected <= set(TOOLS)


def test_tools_never_mutate_input():
    df = pd.DataFrame({"a": [" x ", "y", "y"]})
    snapshot = df.copy()
    tools.trim_whitespace(df, "a")
    tools.drop_duplicates(df)
    pd.testing.assert_frame_equal(df, snapshot)


def test_drop_duplicates():
    df = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    out, stats = tools.drop_duplicates(df)
    assert len(out) == 2 and stats["rows_affected"] == 1


def test_normalize_dates_mixed_formats():
    df = pd.DataFrame({"d": ["2021-03-04", "03/04/2021", "March 4, 2021", "20210304"]})
    out, stats = tools.normalize_dates(df, "d")
    assert out["d"].tolist() == ["2021-03-04"] * 4
    assert stats["rows_affected"] == 3 and stats["parse_failures"] == 0


def test_normalize_phone_ph_formats():
    df = pd.DataFrame({"p": ["09171234567", "+639171234567", "63-917-123-4567",
                             "0917 123 4567", "12345"]})
    out, stats = tools.normalize_phone(df, "p")
    assert out["p"].tolist()[:4] == ["+639171234567"] * 4
    assert out["p"].iloc[4] == "12345" and stats["parse_failures"] == 1


def test_normalize_currency():
    df = pd.DataFrame({"amt": ["₱1,200.00", "PHP 1200", "1200", None]})
    out, stats = tools.normalize_currency(df, "amt")
    assert out["amt"].dropna().tolist() == [1200.0, 1200.0, 1200.0]
    assert out["amt_currency"].tolist()[:2] == ["PHP", "PHP"]


def test_standardize_categories_auto_fold():
    df = pd.DataFrame({"sex": ["Male", "male", "MALE", "Male", "Female"]})
    out, _ = tools.standardize_categories(df, "sex")
    assert set(out["sex"]) == {"Male", "Female"}


def test_standardize_categories_explicit_mapping():
    df = pd.DataFrame({"sex": ["M", "F", "Male"]})
    out, _ = tools.standardize_categories(df, "sex", {"mapping": {"M": "Male", "F": "Female"}})
    assert out["sex"].tolist() == ["Male", "Female", "Male"]


def test_fix_dtypes_numeric_with_fail_count():
    df = pd.DataFrame({"n": ["1,234", " 5.5 ", "oops", None]})
    out, stats = tools.fix_dtypes(df, "n", {"target": "numeric"})
    assert out["n"].tolist()[:2] == [1234.0, 5.5]
    assert stats["coercion_failures"] == 1


def test_fix_dtypes_bool():
    df = pd.DataFrame({"b": ["True", "no", "Y"]})
    out, _ = tools.fix_dtypes(df, "b", {"target": "bool"})
    assert out["b"].tolist() == [True, False, True]


def test_impute_flag_only_never_touches_data():
    df = pd.DataFrame({"x": [1.0, None, 3.0]})
    out, stats = tools.impute_missing(df, "x", {"strategy": "flag_only"})
    assert out["x"].isna().sum() == 1 and out["x_missing"].tolist() == [False, True, False]


def test_impute_median():
    df = pd.DataFrame({"x": [1.0, None, 3.0]})
    out, _ = tools.impute_missing(df, "x", {"strategy": "median"})
    assert out["x"].tolist() == [1.0, 2.0, 3.0] and out["x_missing"].iloc[1]


def test_flag_outliers_flags_not_deletes():
    df = pd.DataFrame({"x": [10, 11, 12, 10, 11, 9000]})
    out, stats = tools.flag_outliers(df, "x", {"method": "iqr"})
    assert len(out) == 6 and out["x_outlier"].sum() == 1 and out["x_outlier"].iloc[5]


def test_trim_whitespace_and_nfc():
    df = pd.DataFrame({"s": ["  a  b ", "ok", "José"]})
    out, stats = tools.trim_whitespace(df, "s")
    assert out["s"].tolist() == ["a b", "ok", "José"] and stats["rows_affected"] == 2


def test_validate_rule_range():
    df = pd.DataFrame({"age": [30, 150, -2, None]})
    out, stats = tools.validate_rule(df, "age", {"min": 0, "max": 120})
    assert out["age_invalid"].tolist() == [False, True, True, False]


def test_rename_columns_snake_case():
    df = pd.DataFrame({"First Name": [1], "orderID": [2], "ok_col": [3]})
    out, _ = tools.rename_columns(df)
    assert list(out.columns) == ["first_name", "order_id", "ok_col"]


@pytest.mark.parametrize("bad", ["nope", ""])
def test_unknown_impute_strategy_raises(bad):
    with pytest.raises(ValueError):
        tools.impute_missing(pd.DataFrame({"x": [1]}), "x", {"strategy": bad})
