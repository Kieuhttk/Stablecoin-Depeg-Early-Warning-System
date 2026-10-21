from unittest import result

import pandas as pd

from src.features.labels import (
    assign_split,
    build_group_labels,
    add_variant_labels,
    add_benchmark_targets,
    add_targets,
    CONFIRMATION_DAYS,
    HORIZONS,
    SOURCES,
    THRESHOLDS,
)


def test_onset_marks_first_day_of_depeg_run():
    df = pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=4),
        "coin": ["USDT"] * 4,
        "split": ["train"] * 4,
        "deviation": [0.002, 0.015, 0.020, 0.003],
    })

    result = build_group_labels(
        df,
        deviation_col="deviation",
        tau=0.01,
        m=1,
    )

    assert result["state"].tolist() == [0, 1, 1, 0]
    assert result["onset"].tolist() == [0, 1, 0, 0]


def test_missing_deviation_keeps_state_missing():
    df = pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=3),
        "coin": ["USDT"] * 3,
        "split": ["train"] * 3,
        "deviation": [0.002, None, 0.015],
    })

    result = build_group_labels(
        df,
        deviation_col="deviation",
        tau=0.01,
        m=1,
    )

    assert pd.isna(result["state"].iloc[1])


def test_target_does_not_cross_split_boundary():
    df = pd.DataFrame({
        "date": pd.date_range("2021-12-30", periods=4),
        "coin": ["USDT"] * 4,
        "split": ["train", "train", "validation", "validation"],
        "state": pd.Series([0, 0, 1, 0], dtype="Int64"),
        "onset": [0, 0, 1, 0],
    })

    result = add_targets(
        df.copy(),
        state_col="state",
        onset_col="onset",
        prefix="onset_label",
        horizons=[1],
    )

    # NgÃ y 31/12 khÃ´ng Ä‘Æ°á»£c dÃ¹ng nhÃ£n cá»§a ngÃ y 01/01 á»Ÿ validation.
    assert result.loc[1, "onset_label_eligible_d1"] == 0
    assert pd.isna(result.loc[1, "onset_label_d1"])


def test_depeg_day_is_not_eligible_for_prediction():
    df = pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=3),
        "coin": ["USDT"] * 3,
        "split": ["train"] * 3,
        "state": pd.Series([1, 0, 0], dtype="Int64"),
        "onset": [1, 0, 0],
    })

    result = add_targets(
        df.copy(),
        state_col="state",
        onset_col="onset",
        prefix="onset_label",
        horizons=[1],
    )

    assert result.loc[0, "onset_label_eligible_d1"] == 0
    assert pd.isna(result.loc[0, "onset_label_d1"])


def test_insufficient_future_data_keeps_target_missing():
    df = pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=2),
        "coin": ["USDT"] * 2,
        "split": ["train"] * 2,
        "state": pd.Series([0, 0], dtype="Int64"),
        "onset": [0, 0],
    })

    result = add_targets(
        df.copy(),
        state_col="state",
        onset_col="onset",
        prefix="onset_label",
        horizons=[1, 3],
    )

    assert result.loc[1, "onset_label_eligible_d1"] == 0
    assert pd.isna(result.loc[1, "onset_label_d1"])

    assert result.loc[0, "onset_label_eligible_d3"] == 0
    assert pd.isna(result.loc[0, "onset_label_d3"])

def test_threshold_equal_to_tau_is_not_depeg():
    """Độ lệch bằng đúng ngưỡng không được xem là vượt ngưỡng."""
    df = pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=3),
        "coin": ["USDT"] * 3,
        "split": ["train"] * 3,
        "deviation": [0.009, 0.010, 0.011],
    })

    result = build_group_labels(
        df,
        deviation_col="deviation",
        tau=0.01,
        m=1,
    )

    assert result["state"].tolist() == [0, 0, 1]
    assert result["onset"].tolist() == [0, 0, 1]


def test_m2_requires_two_consecutive_days_above_threshold():
    """m=2 chỉ xác nhận onset khi đủ hai ngày liên tiếp vượt ngưỡng."""
    df = pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=4),
        "coin": ["USDT"] * 4,
        "split": ["train"] * 4,
        "deviation": [0.015, 0.020, 0.003, 0.018],
    })

    result = build_group_labels(
        df,
        deviation_col="deviation",
        tau=0.01,
        m=2,
    )

    assert result["onset"].tolist() == [1, 0, 0, 0]
    assert pd.isna(result["state"].iloc[0])
    assert result["state"].iloc[1] == 1
    assert result["state"].iloc[2] == 0
    assert pd.isna(result["state"].iloc[3])


def test_missing_day_breaks_onset_sequence():
    """Không nối chuỗi depeg qua ngày có dữ liệu thiếu."""
    df = pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=4),
        "coin": ["USDT"] * 4,
        "split": ["train"] * 4,
        "deviation": [0.002, None, 0.015, 0.020],
    })

    result = build_group_labels(
        df,
        deviation_col="deviation",
        tau=0.01,
        m=1,
    )

    assert result["onset"].tolist() == [0, 0, 1, 0]

def test_m2_target_requires_confirmation_day_beyond_horizon():
    """Target m=2 dùng raw_state để xác nhận onset ngoài horizon."""
    df = pd.DataFrame({
        "date": pd.date_range("2021-01-01", periods=5),
        "coin": ["USDT"] * 5,
        "split": ["train"] * 5,
        "deviation": [0.0, 0.02, 0.02, 0.0, 0.0],
    })

    labeled = build_group_labels(
        df,
        deviation_col="deviation",
        tau=0.01,
        m=2,
    )
    result = add_targets(
        labeled,
        state_col="state",
        onset_col="onset",
        prefix="onset_label",
        horizons=[1, 3],
        confirmation_days=2,
        raw_state_col="raw_state",
    )

    assert result["raw_state"].tolist() == [0, 1, 1, 0, 0]
    assert pd.isna(result.loc[1, "state"])
    assert result.loc[2, "state"] == 1
    assert result["onset"].tolist() == [0, 1, 0, 0, 0]

    # t=2021-01-01 predicts the onset on 2021-01-02; confirmation is
    # observed on 2021-01-03, outside h=1 but inside the eligibility window.
    assert result.loc[0, "onset_label_eligible_d1"] == 1
    assert result.loc[0, "onset_label_d1"] == 1
    # h=3 also has four complete future days. This onset is at t+1, inside
    # the horizon; the separate test below covers an onset at t+3.
    assert result.loc[0, "onset_label_eligible_d3"] == 1
    assert result.loc[0, "onset_label_d3"] == 1


def test_m2_h3_positive_onset_on_last_horizon_day():
    df = pd.DataFrame({
        "date": pd.date_range("2021-02-01", periods=6),
        "coin": ["USDT"] * 6,
        "split": ["train"] * 6,
        "deviation": [0.0, 0.0, 0.0, 0.02, 0.02, 0.0],
    })

    labeled = build_group_labels(df, "deviation", tau=0.01, m=2)
    result = add_targets(
        labeled,
        state_col="state",
        onset_col="onset",
        prefix="onset_label",
        horizons=[3],
        confirmation_days=2,
        raw_state_col="raw_state",
    )

    assert result["raw_state"].tolist() == [0, 0, 0, 1, 1, 0]
    assert result["state"].tolist()[0:3] == [0, 0, 0]
    assert pd.isna(result.loc[3, "state"])
    assert result.loc[4, "state"] == 1
    assert result["onset"].tolist() == [0, 0, 0, 1, 0, 0]
    assert result.loc[0, "onset_label_eligible_d3"] == 1
    assert result.loc[0, "onset_label_d3"] == 1


def test_m2_negative_window_is_eligible_when_raw_data_is_complete():
    df = pd.DataFrame({
        "date": pd.date_range("2021-03-01", periods=5),
        "coin": ["USDT"] * 5,
        "split": ["train"] * 5,
        "deviation": [0.0, 0.02, 0.0, 0.0, 0.0],
    })

    labeled = build_group_labels(df, "deviation", tau=0.01, m=2)
    result = add_targets(
        labeled,
        state_col="state",
        onset_col="onset",
        prefix="onset_label",
        horizons=[1],
        confirmation_days=2,
        raw_state_col="raw_state",
    )

    assert result["raw_state"].tolist() == [0, 1, 0, 0, 0]
    assert pd.isna(result.loc[1, "state"])
    assert result["onset"].tolist() == [0, 0, 0, 0, 0]
    assert result.loc[0, "onset_label_eligible_d1"] == 1
    assert result.loc[0, "onset_label_d1"] == 0


def test_m2_missing_calendar_day_makes_target_ineligible():
    df = pd.DataFrame({
        "date": pd.to_datetime([
            "2021-04-01", "2021-04-02", "2021-04-04", "2021-04-05"
        ]),
        "coin": ["USDT"] * 4,
        "split": ["train"] * 4,
        "deviation": [0.0, 0.02, 0.02, 0.0],
    })

    labeled = build_group_labels(df, "deviation", tau=0.01, m=2)
    result = add_targets(
        labeled,
        state_col="state",
        onset_col="onset",
        prefix="onset_label",
        horizons=[1],
        confirmation_days=2,
        raw_state_col="raw_state",
    )

    assert result["raw_state"].tolist() == [0, 1, 1, 0]
    assert pd.isna(result.loc[1, "state"])
    assert result["onset"].tolist() == [0, 0, 0, 0]
    assert result.loc[0, "onset_label_eligible_d1"] == 0
    assert pd.isna(result.loc[0, "onset_label_d1"])


def test_m2_missing_deviation_in_confirmation_window_is_ineligible():
    df = pd.DataFrame({
        "date": pd.date_range("2021-05-01", periods=5),
        "coin": ["USDT"] * 5,
        "split": ["train"] * 5,
        "deviation": [0.0, 0.02, None, 0.0, 0.0],
    })

    labeled = build_group_labels(df, "deviation", tau=0.01, m=2)
    result = add_targets(
        labeled,
        state_col="state",
        onset_col="onset",
        prefix="onset_label",
        horizons=[1],
        confirmation_days=2,
        raw_state_col="raw_state",
    )

    assert result["raw_state"].tolist() == [0, 1, pd.NA, 0, 0]
    assert result["state"].tolist()[0] == 0
    assert pd.isna(result.loc[1, "state"])
    assert pd.isna(result.loc[2, "state"])
    assert result["onset"].tolist() == [0, 0, 0, 0, 0]
    assert result.loc[0, "onset_label_eligible_d1"] == 0
    assert pd.isna(result.loc[0, "onset_label_d1"])


def test_m2_target_window_does_not_cross_split_boundary():
    df = pd.DataFrame({
        "date": pd.date_range("2021-12-30", periods=5),
        "coin": ["USDT"] * 5,
        "split": ["train", "train", "validation", "validation", "validation"],
        "deviation": [0.0, 0.0, 0.02, 0.02, 0.0],
    })

    labeled = build_group_labels(df, "deviation", tau=0.01, m=2)
    result = add_targets(
        labeled,
        state_col="state",
        onset_col="onset",
        prefix="onset_label",
        horizons=[1],
        confirmation_days=2,
        raw_state_col="raw_state",
    )

    assert result["raw_state"].tolist() == [0, 0, 1, 1, 0]
    assert result["state"].tolist()[0:2] == [0, 0]
    assert pd.isna(result.loc[2, "state"])
    assert result.loc[3, "state"] == 1
    assert result["onset"].tolist() == [0, 0, 1, 0, 0]
    assert result.loc[1, "onset_label_eligible_d1"] == 0
    assert pd.isna(result.loc[1, "onset_label_d1"])


def test_m2_onset_at_horizon_end_is_ineligible_if_confirmation_crosses_split():
    # Isolate add_targets: the candidate onset is in train at t+1, while
    # its second exceedance needed for confirmation falls in validation.
    df = pd.DataFrame({
        "date": pd.date_range("2021-12-30", periods=3),
        "coin": ["USDT"] * 3,
        "split": ["train", "train", "validation"],
        "raw_state": pd.Series([0, 1, 1], dtype="Int64"),
        "state": pd.Series([0, pd.NA, pd.NA], dtype="Int64"),
        "onset": [0, 1, 0],
    })

    result = add_targets(
        df,
        state_col="state",
        onset_col="onset",
        prefix="onset_label",
        horizons=[1],
        confirmation_days=2,
        raw_state_col="raw_state",
    )

    assert result["raw_state"].tolist() == [0, 1, 1]
    assert result.loc[0, "state"] == 0
    assert pd.isna(result.loc[1, "state"])
    assert pd.isna(result.loc[2, "state"])
    assert result["onset"].tolist() == [0, 1, 0]
    assert result.loc[0, "onset_label_eligible_d1"] == 0
    assert pd.isna(result.loc[0, "onset_label_d1"])


def test_benchmark_is_exact_future_state_not_onset_within_horizon():
    df = pd.DataFrame({
        "date": pd.date_range("2022-01-01", periods=5),
        "coin": ["USDT"] * 5,
        "split": ["train"] * 5,
        "deviation": [0.0, 0.02, 0.0, 0.0, 0.0],
    })
    labeled = build_group_labels(df, "deviation", tau=0.01, m=1)
    result = add_targets(
        labeled, "state", "onset", "", [1, 3], confirmation_days=1
    )
    result = add_benchmark_targets(
        result, "state", "hl_tau0.010_m1", [1, 3]
    )

    assert result.loc[0, "onset_label_d3"] == 1
    assert result.loc[0, "depeg_at_t_plus_d3_hl_tau0.010_m1"] == 0
    assert result.loc[0, "depeg_at_t_plus_d1_hl_tau0.010_m1"] == 1
    assert result.loc[0, "depeg_at_t_plus_d1_eligible_hl_tau0.010_m1"] == 1


def test_m2_benchmark_requires_confirmed_state_at_exact_horizon_date():
    df = pd.DataFrame({
        "date": pd.date_range("2022-01-01", periods=6),
        "coin": ["USDT"] * 6,
        "split": ["train"] * 6,
        "deviation": [0.0, 0.0, 0.0, 0.02, 0.02, 0.0],
    })
    labeled = build_group_labels(df, "deviation", tau=0.01, m=2)
    result = add_benchmark_targets(
        labeled, "state", "hl_tau0.010_m2", [3]
    )

    assert result.loc[0, "onset" ] == 0
    assert pd.isna(result.loc[0, "depeg_at_t_plus_d3_hl_tau0.010_m2"])
    assert result.loc[0, "depeg_at_t_plus_d3_eligible_hl_tau0.010_m2"] == 0
    assert result.loc[1, "depeg_at_t_plus_d3_hl_tau0.010_m2"] == 1
    assert result.loc[1, "depeg_at_t_plus_d3_eligible_hl_tau0.010_m2"] == 1


def test_all_configured_variants_have_targets_eligibility_and_benchmarks():
    df = pd.DataFrame({
        "date": pd.date_range("2022-02-01", periods=12),
        "coin": ["USDT"] * 12,
        "split": ["train"] * 12,
        **{column: [0.0, 0.02] * 6 for column in SOURCES.values()},
    })
    for source, deviation_col in SOURCES.items():
        for tau in THRESHOLDS:
            for m in CONFIRMATION_DAYS:
                state_col, onset_col, raw_col = add_variant_labels(
                    df, deviation_col, source, tau, m
                )
                variant = f"{source}_tau{tau:.3f}_m{m}"
                df = add_targets(
                    df, state_col, onset_col, f"onset_label_{variant}",
                    HORIZONS, confirmation_days=m,
                    raw_state_col=raw_col if m > 1 else None,
                )
                df = add_benchmark_targets(df, state_col, variant, HORIZONS)
                for h in HORIZONS:
                    assert f"onset_label_{variant}_d{h}" in df
                    assert f"onset_label_{variant}_eligible_d{h}" in df
                    assert f"depeg_at_t_plus_d{h}_{variant}" in df
                    assert f"depeg_at_t_plus_d{h}_eligible_{variant}" in df

    assert len(SOURCES) * len(THRESHOLDS) * len(CONFIRMATION_DAYS) == 18
