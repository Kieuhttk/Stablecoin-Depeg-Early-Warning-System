from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
import json
import math
import time
import warnings

import numpy as np
import pandas as pd
import yaml
from sklearn.impute import SimpleImputer
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "labels.yaml"
FEATURES_PATH = ROOT / "data" / "processed" / "features.parquet"
OUTPUT_PATH = ROOT / "outputs" / "tables" / "T03_logit_coefficients.csv"
BOOTSTRAP_METADATA_PATH = (
    ROOT / "outputs" / "tables" / "T03_logit_bootstrap_metadata.json"
)

BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_SEED = 20261021
PRIMARY_BLOCK_LENGTH = 14
SENSITIVITY_BLOCK_LENGTHS = (7, 30)
MINIMUM_BOOTSTRAP_SUCCESS = 900


def fit_logit(df: pd.DataFrame, config: dict):
    """Huấn luyện Logistic trên mẫu train đủ điều kiện, không ghi file."""
    required = {
        "timestamp", "stablecoin", "split",
        "onset_label_d1", "eligible_d1",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Thiếu cột bắt buộc: {sorted(missing)}")

    feature_columns = config["feature_columns"]
    missing_features = set(feature_columns) - set(df.columns)
    if missing_features:
        raise ValueError(
            f"Thiếu biến đầu vào theo config: {sorted(missing_features)}"
        )

    train = df.loc[
        (df["split"] == "train") & (df["eligible_d1"] == 1)
    ].copy()

    if train.empty:
        raise ValueError("Không có dòng train đủ điều kiện.")

    y = pd.to_numeric(train["onset_label_d1"], errors="coerce")
    valid_y = y.notna() & y.isin([0, 1])
    train = train.loc[valid_y].copy()
    y = y.loc[valid_y].astype(int)

    if y.nunique() < 2:
        raise ValueError(
            f"Nhãn train chỉ có một lớp: {y.value_counts().to_dict()}"
        )

    forbidden_tokens = (
        "label", "eligible", "onset", "depeg_state",
        "hl_supported", "split", "timestamp", "stablecoin",
        "coin", "quality",
    )
    safe_features = [
        c for c in feature_columns
        if not any(token in c.lower() for token in forbidden_tokens)
    ]

    if not safe_features:
        raise ValueError("Không còn biến đầu vào hợp lệ sau kiểm tra chống rò rỉ.")

    X = train[safe_features].apply(pd.to_numeric, errors="coerce")
    X = X.replace([np.inf, -np.inf], np.nan)

    safe_features = [
        c for c in X.columns
        if X[c].notna().any() and X[c].nunique(dropna=True) > 1
    ]
    X = X[safe_features]

    if X.empty:
        raise ValueError("Không còn biến có thông tin để ước lượng.")

    model = _make_logit_pipeline()

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        model.fit(X, y)

    fitted = model.named_steps["logit"]
    rows = []

    for feature, coef in zip(safe_features, fitted.coef_[0]):
        rows.append({
            "target": "onset_label_d1",
            "horizon_days": 1,
            "model": "L2_LogisticRegression",
            "feature": feature,
            "coefficient_standardized": float(coef),
            "odds_ratio_per_1sd": float(np.exp(np.clip(coef, -700, 700))),
            "C": 1.0,
            "train_rows": int(len(X)),
            "train_positive_rows": int(y.sum()),
            "train_positive_rate": float(y.mean()),
            "features_count": int(len(safe_features)),
            "standard_errors": "not_estimated",
            "fit_sample": "train_only_eligible_d1",
        })

    rows.append({
        "target": "onset_label_d1",
        "horizon_days": 1,
        "model": "L2_LogisticRegression",
        "feature": "(intercept)",
        "coefficient_standardized": float(fitted.intercept_[0]),
        "odds_ratio_per_1sd": np.nan,
        "C": 1.0,
        "train_rows": int(len(X)),
        "train_positive_rows": int(y.sum()),
        "train_positive_rate": float(y.mean()),
        "features_count": int(len(safe_features)),
        "standard_errors": "not_estimated",
        "fit_sample": "train_only_eligible_d1",
    })

    return model, result_frame(rows), safe_features, y


def _make_logit_pipeline():
    """Use the exact preprocessing and L2 Logistic settings of the baseline."""
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("logit", LogisticRegression(
            l1_ratio=0.0,
            C=1.0,
            solver="liblinear",
            max_iter=3000,
            random_state=42,
        )),
    ])


def _prepare_moving_block_panel(train_panel):
    """Index the train calendar once so repeated draws avoid regrouping rows."""
    dated = train_panel.loc[train_panel["split"] == "train"].copy()
    if dated.empty:
        raise ValueError("Moving-block sampling requires train rows")
    dated["_bootstrap_day"] = pd.to_datetime(
        dated["timestamp"], utc=True
    ).dt.normalize()
    calendar = pd.date_range(
        dated["_bootstrap_day"].min(),
        dated["_bootstrap_day"].max(),
        freq="D",
    )
    dated = dated.sort_values(
        ["_bootstrap_day", "stablecoin"], kind="stable"
    ).reset_index(drop=True)
    rows_by_day = {
        day: positions
        for day, positions in dated.groupby("_bootstrap_day", sort=False).indices.items()
    }
    return dated, calendar, rows_by_day


def _draw_moving_block_sample(train_panel, block_length, rng, prepared=None):
    """Resample calendar-day blocks, retaining all observed coin rows per day."""
    if block_length < 1:
        raise ValueError("block_length must be positive")
    if prepared is None:
        prepared = _prepare_moving_block_panel(train_panel)
    dated, calendar, rows_by_day = prepared
    n_days = len(calendar)
    if block_length > n_days:
        raise ValueError("block_length exceeds the train calendar length")

    n_blocks = math.ceil(n_days / block_length)
    starts = rng.integers(
        0,
        n_days - block_length + 1,
        size=n_blocks,
    )
    selected_positions = np.concatenate([
        np.arange(start, start + block_length) for start in starts
    ])[:n_days]
    selected_days = calendar.take(selected_positions)

    # Empty calendar dates contribute no rows; incomplete dates retain only
    # their observed coin rows. No synthetic coin observations are created.
    row_positions = [rows_by_day[day] for day in selected_days if day in rows_by_day]
    if not row_positions:
        sample = dated.iloc[0:0].drop(columns="_bootstrap_day")
    else:
        selected_rows = np.concatenate(row_positions)
        sample = dated.iloc[selected_rows].drop(columns="_bootstrap_day").reset_index(drop=True)
    return sample, selected_days


def _fit_bootstrap_sample(sample, feature_columns, coefficient_names):
    """Fit one bootstrap draw and return (coefficients, failure_reason)."""
    train = sample.loc[
        (sample["split"] == "train") & (sample["eligible_d1"] == 1)
    ]
    y = pd.to_numeric(train["onset_label_d1"], errors="coerce")
    valid_y = y.notna() & y.isin([0, 1])
    train = train.loc[valid_y]
    y = y.loc[valid_y].astype(int)

    if y.nunique() < 2:
        return None, "single_class"

    X = train[feature_columns].apply(pd.to_numeric, errors="coerce")
    X = X.replace([np.inf, -np.inf], np.nan)
    if X.isna().all().any():
        return None, "all_missing_predictor"

    model = _make_logit_pipeline()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            model.fit(X, y)
        except Exception as exc:  # Count failures instead of hiding draws.
            return None, f"fit_error:{type(exc).__name__}"

    if any(issubclass(w.category, ConvergenceWarning) for w in caught):
        return None, "non_convergence"

    fitted = model.named_steps["logit"]
    coefficients = np.concatenate([
        fitted.coef_[0],
        fitted.intercept_,
    ])
    if len(coefficients) != len(coefficient_names):
        return None, "coefficient_schema_mismatch"
    if not np.isfinite(coefficients).all():
        return None, "non_finite_coefficients"
    return coefficients.astype(float), None


def _summarize_bootstrap(coefficient_draws, coefficient_names):
    """Summarize successful draws with sample SD and percentile interval."""
    matrix = np.asarray(coefficient_draws, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != len(coefficient_names):
        raise ValueError("Bootstrap coefficient matrix has an invalid shape")
    if matrix.shape[0] < 2:
        raise ValueError("At least two successful draws are required")
    return pd.DataFrame({
        "feature": coefficient_names,
        "standard_error": matrix.std(axis=0, ddof=1),
        "ci_95_lower": np.quantile(matrix, 0.025, axis=0),
        "ci_95_upper": np.quantile(matrix, 0.975, axis=0),
    })


def moving_block_bootstrap(
    df,
    feature_columns,
    *,
    replicates=BOOTSTRAP_REPLICATES,
    block_lengths=(PRIMARY_BLOCK_LENGTH, *SENSITIVITY_BLOCK_LENGTHS),
    seed=BOOTSTRAP_SEED,
    minimum_success=MINIMUM_BOOTSTRAP_SUCCESS,
):
    """Estimate L2 coefficient variability from joint-coin train-day blocks."""
    train_panel = df.loc[df["split"] == "train"].copy()
    if train_panel.empty:
        raise ValueError("No train rows available for bootstrap")
    train_panel["timestamp"] = pd.to_datetime(
        train_panel["timestamp"], utc=True
    ).dt.normalize()
    prepared_panel = _prepare_moving_block_panel(train_panel)
    dates_per_coin = train_panel.groupby("timestamp")["stablecoin"].nunique()
    calendar = pd.date_range(
        train_panel["timestamp"].min(),
        train_panel["timestamp"].max(),
        freq="D",
    )
    n_calendar_days = len(calendar)
    coefficient_names = [*feature_columns, "(intercept)"]
    rng = np.random.default_rng(seed)
    results = {}
    metadata = {
        "method": "moving_block_bootstrap_by_utc_calendar_day",
        "block_length_selection": "prespecified_14_day_primary; 7_and_30_day_sensitivity",
        "automatic_selector_used": False,
        "automatic_selector_check": {
            "arch_installed": False,
            "statsmodels_installed": False,
            "scipy_version": "1.18.1",
            "reason": "Available environment did not provide a verified automatic moving-block length selector.",
        },
        "primary_block_length_days": PRIMARY_BLOCK_LENGTH,
        "sensitivity_block_lengths_days": list(SENSITIVITY_BLOCK_LENGTHS),
        "replicates_requested_per_length": int(replicates),
        "minimum_success_for_official_estimate": int(minimum_success),
        "seed": int(seed),
        "calendar_train_days": int(n_calendar_days),
        "train_panel_rows": int(len(train_panel)),
        "dates_with_all_three_coins": int((dates_per_coin == 3).sum()),
        "dates_with_partial_coin_panel": int((dates_per_coin < 3).sum()),
        "calendar_dates_with_no_rows": int(n_calendar_days - dates_per_coin.size),
        "coin_rows_are_not_synthesized": True,
        "predictor_order": list(feature_columns),
        "coefficient_order": coefficient_names,
        "preprocessing_refit_each_draw": ["median_imputation", "standard_scaling"],
        "logit": {
            "penalty": "L2",
            "C": 1.0,
            "solver": "liblinear",
            "max_iter": 3000,
            "random_state": 42,
        },
        "interval_method": "empirical_2.5th_and_97.5th_percentiles_of_successful_draws",
        "standard_error_method": "sample_standard_deviation_of_successful_draws_ddof_1",
        "p_values": "not_estimated",
        "interpretation_limit": "Describes variability of the penalized estimator; percentile intervals do not have guaranteed nominal 95% coverage.",
        "length_results": {},
    }

    for block_length in block_lengths:
        start_time = time.perf_counter()
        draws = []
        failures = Counter()
        for _ in range(replicates):
            sample, _ = _draw_moving_block_sample(
                train_panel, block_length, rng, prepared=prepared_panel
            )
            coefficients, failure = _fit_bootstrap_sample(
                sample, feature_columns, coefficient_names
            )
            if failure:
                failures[failure] += 1
            else:
                draws.append(coefficients)

        elapsed = time.perf_counter() - start_time
        successful = len(draws)
        length_metadata = {
            "block_length_days": int(block_length),
            "requested": int(replicates),
            "successful": int(successful),
            "failed": int(replicates - successful),
            "failure_counts_by_reason": dict(sorted(failures.items())),
            "elapsed_seconds": float(elapsed),
        }
        if successful >= 2:
            summary = _summarize_bootstrap(draws, coefficient_names)
            length_metadata["coefficient_summaries"] = summary.to_dict("records")
            results[block_length] = summary
        else:
            length_metadata["coefficient_summaries"] = None
            results[block_length] = None
        metadata["length_results"][str(block_length)] = length_metadata

    insufficient = {
        length: result["successful"]
        for length, result in metadata["length_results"].items()
        if result["successful"] < minimum_success
    }
    metadata["all_lengths_meet_minimum_success"] = not insufficient
    metadata["insufficient_success_counts"] = insufficient
    metadata["elapsed_seconds_total"] = float(sum(
        item["elapsed_seconds"]
        for item in metadata["length_results"].values()
    ))
    metadata["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    return results, metadata


def result_frame(rows):
    """Chuyển danh sách kết quả thành bảng."""
    return pd.DataFrame(rows)


def main():
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    df = pd.read_parquet(FEATURES_PATH)
    model, result, safe_features, y = fit_logit(df, config)

    bootstrap_results, bootstrap_metadata = moving_block_bootstrap(
        df,
        safe_features,
    )
    for length, details in bootstrap_metadata["length_results"].items():
        print(
            f"Bootstrap block={length}d: "
            f"{details['successful']}/{details['requested']} thành công, "
            f"{details['failed']} thất bại, "
            f"{details['elapsed_seconds']:.1f}s"
        )

    if not bootstrap_metadata["all_lengths_meet_minimum_success"]:
        raise RuntimeError(
            "Bootstrap có cấu hình dưới ngưỡng thành công 900/1000; "
            "không ghi đè T03. Chi tiết: "
            f"{bootstrap_metadata['insufficient_success_counts']}"
        )

    primary_summary = bootstrap_results[PRIMARY_BLOCK_LENGTH]
    if primary_summary is None:
        raise RuntimeError("Không có đủ lần bootstrap thành công cho L=14.")
    result = result.drop(columns=["standard_errors"])
    result = result.merge(
        primary_summary,
        on="feature",
        how="left",
        validate="one_to_one",
    )
    if result[["standard_error", "ci_95_lower", "ci_95_upper"]].isna().any().any():
        raise RuntimeError("Thiếu thống kê bootstrap cho một hoặc nhiều hệ số.")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BOOTSTRAP_METADATA_PATH.open("w", encoding="utf-8") as f:
        json.dump(bootstrap_metadata, f, ensure_ascii=False, indent=2)
    result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")

    print("T03 đã được tạo:", OUTPUT_PATH.relative_to(ROOT))
    print("Số dòng train đủ điều kiện:", int(result["train_rows"].iloc[0]))
    print("Số dòng dương:", int(y.sum()))
    print("Tỷ lệ nhãn dương:", round(float(y.mean()), 6))
    print("Số biến được ước lượng:", len(safe_features))
    print("Biến sử dụng:", ", ".join(safe_features))
    print("Thời gian bootstrap tổng (giây):", round(
        bootstrap_metadata["elapsed_seconds_total"], 2
    ))
    print("\nTop hệ số theo trị tuyệt đối:")
    print(
        result.loc[result["feature"] != "(intercept)"]
        .assign(abs_coef=lambda d: d["coefficient_standardized"].abs())
        .sort_values("abs_coef", ascending=False)
        .head(10)[["feature", "coefficient_standardized",
                   "odds_ratio_per_1sd"]]
        .to_string(index=False)
    )

if __name__ == "__main__":
    main()
