
import pandas as pd

from src.features.features import (
    BASE_FEATURES,
    FORBIDDEN_FEATURES,
    LABEL_COLUMNS,
    build_features,
    load_panel,
)


def test_forbidden_columns_not_used_as_features():
    panel = load_panel()
    features = build_features(panel)

    feature_columns = set(features.columns) - {"date", "coin"}

    assert not (feature_columns & FORBIDDEN_FEATURES)


def test_no_duplicate_date_coin_keys():
    panel = load_panel()
    features = build_features(panel)

    assert not features.duplicated(["date", "coin"]).any()


def test_required_base_features_are_present():
    panel = load_panel()
    features = build_features(panel)

    expected = set(BASE_FEATURES) & set(panel.columns)
    assert expected.issubset(set(features.columns))


def test_no_infinite_numeric_values():
    panel = load_panel()
    features = build_features(panel)

    numeric = features.select_dtypes(include="number")
    assert not numeric.isin([float("inf"), float("-inf")]).any().any()
from src.features.features import LABEL_COLUMNS


def test_label_columns_are_not_in_feature_table():
    panel = load_panel()
    features = build_features(panel)

    label_columns = set(LABEL_COLUMNS)
    feature_columns = set(features.columns) - {"date", "coin"}

    assert not (feature_columns & label_columns)


def test_feature_table_does_not_contain_target_columns():
    panel = load_panel()
    features = build_features(panel)

    forbidden_target_names = {
        "onset_label_d1",
        "onset_label_d3",
        "eligible_d1",
        "eligible_d3",
        "depeg_state_t",
    }

    assert not (
        set(features.columns) & forbidden_target_names
    )


def test_variant_labels_and_benchmarks_are_not_predictors():
    panel = load_panel()
    features = build_features(panel)
    predictor_columns = set(features.columns) - {"date", "coin"}
    assert len(predictor_columns) == 27
    assert not any(
        column.startswith(("state_", "onset_", "raw_state_", "depeg_at_t_plus_"))
        or "eligible" in column
        for column in predictor_columns
    )
    assert not any(
        column.startswith(("raw_state_",))
        for column in LABEL_COLUMNS
    )
def test_features_at_t_are_unchanged_when_future_data_is_removed():
    """Feature tại t phải giống nhau dù có hay không có dữ liệu sau t."""
    panel = load_panel().sort_values(["coin", "date"]).copy()

    dates = sorted(panel["date"].dropna().unique())
    assert len(dates) > 60, "Không đủ dữ liệu để kiểm tra leakage."

    # Chọn mốc t trước ngày cuối để vẫn còn dữ liệu tương lai.
    cutoff = dates[-31]

    full_features = build_features(panel)
    truncated_panel = panel.loc[panel["date"] <= cutoff].copy()
    truncated_features = build_features(truncated_panel)

    full_at_t = (
        full_features.loc[full_features["date"] == cutoff]
        .sort_values("coin")
        .reset_index(drop=True)
    )
    truncated_at_t = (
        truncated_features.loc[truncated_features["date"] == cutoff]
        .sort_values("coin")
        .reset_index(drop=True)
    )

    pd.testing.assert_frame_equal(
        full_at_t,
        truncated_at_t,
        check_dtype=False,
        check_like=False,
    )
