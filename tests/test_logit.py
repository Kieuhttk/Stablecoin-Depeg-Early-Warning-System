import numpy as np
import pandas as pd
import pytest
import warnings
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from src.models.code2_logit import (
    _draw_moving_block_sample,
    _fit_bootstrap_sample,
    _summarize_bootstrap,
    fit_logit,
    moving_block_bootstrap,
)


@pytest.fixture
def sample_data():
    n = 40
    x = np.arange(n, dtype=float)

    return pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=n),
        "stablecoin": ["USDT"] * n,
        "split": ["train"] * 30 + ["test"] * 10,
        "eligible_d1": [1] * n,
        "onset_label_d1": [0, 1] * 20,
        "feature_a": x,
        "feature_b": np.sin(x),
        "leaky_label": [0, 1] * 20,
    })


def test_fit_logit_uses_only_eligible_training_rows(sample_data):
    config = {
        "feature_columns": [
            "feature_a",
            "feature_b",
            "leaky_label",
        ]
    }

    _, result, features, y = fit_logit(sample_data, config)

    assert len(y) == 30
    assert result["train_rows"].iloc[0] == 30
    assert result["train_positive_rows"].iloc[0] == int(y.sum())
    assert "leaky_label" not in features
    assert set(features) == {"feature_a", "feature_b"}
    assert "(intercept)" in result["feature"].values


def test_fit_logit_rejects_missing_feature(sample_data):
    config = {
        "feature_columns": ["feature_a", "missing_feature"]
    }

    with pytest.raises(ValueError, match="Thiếu biến đầu vào"):
        fit_logit(sample_data, config)


def test_fit_logit_rejects_empty_eligible_training_sample(sample_data):
    sample_data["eligible_d1"] = 0
    config = {"feature_columns": ["feature_a", "feature_b"]}

    with pytest.raises(ValueError, match="Không có dòng train đủ điều kiện"):
        fit_logit(sample_data, config)


def _panel_for_block_tests(n_days=12):
    dates = pd.date_range("2020-01-01", periods=n_days, tz="UTC")
    rows = []
    for day_idx, day in enumerate(dates):
        for coin in ["USDT", "USDC", "DAI"]:
            rows.append({
                "timestamp": day,
                "stablecoin": coin,
                "split": "train" if day_idx < n_days - 2 else "test",
                "eligible_d1": 1,
                "onset_label_d1": day_idx % 2,
                "feature_a": float(day_idx + (coin == "USDC")),
                "feature_b": float((day_idx % 3) + (coin == "DAI")),
            })
    return pd.DataFrame(rows)


def test_moving_blocks_keep_joint_coin_rows_and_duplicate_days():
    df = _panel_for_block_tests(n_days=6)
    sample, sampled_days = _draw_moving_block_sample(
        df, block_length=2, rng=np.random.default_rng(0)
    )

    assert len(sampled_days) == 4
    assert (sampled_days[1:2] - sampled_days[:1]).days.tolist() == [1]
    assert (sampled_days[3:4] - sampled_days[2:3]).days.tolist() == [1]
    assert set(sample["split"]) == {"train"}
    per_occurrence = sample.groupby("timestamp")["stablecoin"].count()
    assert all(count % 3 == 0 for count in per_occurrence)
    assert per_occurrence.max() > 3  # At least one sampled date is duplicated.
    assert set(sample["stablecoin"]) == {"USDT", "USDC", "DAI"}


def test_bootstrap_refits_imputer_scaler_and_preserves_coefficient_order(monkeypatch):
    df = _panel_for_block_tests(n_days=32)
    calls = {"imputer": 0, "scaler": 0}
    original_imputer_fit = SimpleImputer.fit
    original_scaler_fit = StandardScaler.fit

    def tracked_imputer_fit(self, X, y=None):
        calls["imputer"] += 1
        return original_imputer_fit(self, X, y)

    def tracked_scaler_fit(self, X, y=None, **kwargs):
        calls["scaler"] += 1
        return original_scaler_fit(self, X, y, **kwargs)

    monkeypatch.setattr(SimpleImputer, "fit", tracked_imputer_fit)
    monkeypatch.setattr(StandardScaler, "fit", tracked_scaler_fit)
    results, metadata = moving_block_bootstrap(
        df,
        ["feature_a", "feature_b"],
        replicates=4,
        block_lengths=(2,),
        seed=91,
        minimum_success=0,
    )

    info = metadata["length_results"]["2"]
    assert info["successful"] + info["failed"] == 4
    assert calls["imputer"] == info["successful"]
    assert calls["scaler"] == info["successful"]
    assert results[2] is not None
    assert results[2]["feature"].tolist() == [
        "feature_a", "feature_b", "(intercept)"
    ]
    assert metadata["calendar_train_days"] == 30
    assert metadata["train_panel_rows"] == 90
    assert "p_value" not in results[2].columns


def test_bootstrap_failure_reasons_are_counted(monkeypatch):
    df = _panel_for_block_tests(n_days=12)
    outcomes = iter([
        (None, "single_class"),
        (None, "fit_error:ValueError"),
        (None, "non_convergence"),
        (np.array([1.0, 2.0, 3.0]), None),
    ])

    monkeypatch.setattr(
        "src.models.code2_logit._fit_bootstrap_sample",
        lambda *args, **kwargs: next(outcomes),
    )
    _, metadata = moving_block_bootstrap(
        df,
        ["feature_a", "feature_b"],
        replicates=4,
        block_lengths=(2,),
        seed=5,
        minimum_success=0,
    )
    info = metadata["length_results"]["2"]

    assert info["successful"] == 1
    assert info["failed"] == 3
    assert info["failure_counts_by_reason"] == {
        "fit_error:ValueError": 1,
        "non_convergence": 1,
        "single_class": 1,
    }


def test_single_class_fit_failure_and_nonconvergence_are_detected(monkeypatch):
    df = _panel_for_block_tests(n_days=12)
    train = df[df["split"].eq("train")].copy()
    names = ["feature_a", "feature_b", "(intercept)"]
    one_class = train.copy()
    one_class["onset_label_d1"] = 0
    coefficients, reason = _fit_bootstrap_sample(
        one_class, names[:-1], names
    )
    assert coefficients is None
    assert reason == "single_class"

    class FailingPipeline:
        def fit(self, X, y):
            raise ValueError("injected fit failure")

    monkeypatch.setattr(
        "src.models.code2_logit._make_logit_pipeline",
        lambda: FailingPipeline(),
    )
    coefficients, reason = _fit_bootstrap_sample(train, names[:-1], names)
    assert coefficients is None
    assert reason == "fit_error:ValueError"

    class WarningPipeline:
        def fit(self, X, y):
            warnings.warn("injected non-convergence", ConvergenceWarning)

    monkeypatch.setattr(
        "src.models.code2_logit._make_logit_pipeline",
        lambda: WarningPipeline(),
    )
    coefficients, reason = _fit_bootstrap_sample(train, names[:-1], names)
    assert coefficients is None
    assert reason == "non_convergence"


def test_nonfinite_bootstrap_coefficients_are_counted_as_failure(monkeypatch):
    df = _panel_for_block_tests(n_days=12)
    train = df[df["split"].eq("train")].copy()

    class NonFinitePipeline:
        named_steps = {
            "logit": type("FakeLogit", (), {
                "coef_": np.array([[np.nan, 0.0]]),
                "intercept_": np.array([0.0]),
            })()
        }

        def fit(self, X, y):
            return self

    monkeypatch.setattr(
        "src.models.code2_logit._make_logit_pipeline",
        lambda: NonFinitePipeline(),
    )
    coefficients, reason = _fit_bootstrap_sample(
        train,
        ["feature_a", "feature_b"],
        ["feature_a", "feature_b", "(intercept)"],
    )

    assert coefficients is None
    assert reason == "non_finite_coefficients"


def test_bootstrap_standard_error_and_percentile_limits_are_exact():
    draws = np.array([
        [0.0, 1.0],
        [2.0, 3.0],
        [4.0, 5.0],
        [6.0, 7.0],
    ])
    result = _summarize_bootstrap(draws, ["feature_a", "(intercept)"])

    np.testing.assert_allclose(result["standard_error"], draws.std(axis=0, ddof=1))
    np.testing.assert_allclose(
        result["ci_95_lower"], np.quantile(draws, 0.025, axis=0)
    )
    np.testing.assert_allclose(
        result["ci_95_upper"], np.quantile(draws, 0.975, axis=0)
    )
    assert not any("p_value" in column for column in result.columns)
