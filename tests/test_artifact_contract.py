from pathlib import Path

import pandas as pd
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
FEATURES_PATH = ROOT / "data" / "processed" / "features.parquet"
LABELS_PATH = ROOT / "data" / "interim" / "labels.parquet"
CONFIG_PATH = ROOT / "config" / "labels.yaml"
QUALITY_FLAGS = {"hl_suspect", "src_disagree", "n_price_sources", "price_src"}


@pytest.fixture(scope="module")
def handoff_artifacts():
    # These are required Code 2 handoff artifacts. Missing files should fail
    # acceptance checks rather than silently skip them.
    assert FEATURES_PATH.is_file(), f"Missing handoff artifact: {FEATURES_PATH}"
    assert LABELS_PATH.is_file(), f"Missing intermediate labels: {LABELS_PATH}"

    with CONFIG_PATH.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)

    features = pd.read_parquet(FEATURES_PATH)
    labels = pd.read_parquet(LABELS_PATH)
    return config, features, labels


def _variant_names(config):
    for source in config["sources"]:
        for tau in config["thresholds"]:
            for confirmation_days in config["confirmation_days"]:
                yield f"{source}_tau{tau:.3f}_m{confirmation_days}"


def _management_columns(config):
    columns = [
        "split",
        "depeg_state_t",
        "onset_label_d1",
        "eligible_d1",
        "onset_label_d3",
        "eligible_d3",
        "hl_supported_onset",
        "hl_supported_d1",
        "hl_supported_eligible_d1",
        "hl_supported_d3",
        "hl_supported_eligible_d3",
    ]
    for variant in _variant_names(config):
        columns.extend([f"state_{variant}", f"onset_{variant}"])
        for horizon in config["horizons"]:
            columns.extend([
                f"onset_label_{variant}_d{horizon}",
                f"onset_label_{variant}_eligible_d{horizon}",
                f"depeg_at_t_plus_d{horizon}_{variant}",
                f"depeg_at_t_plus_d{horizon}_eligible_{variant}",
            ])
    return columns


def _interim_to_processed_column_map(config):
    primary = config["primary"]
    primary_variant = (
        f"{primary['src']}_tau{float(primary['tau']):.3f}_m{int(primary['m'])}"
    )
    return {"depeg_onset_t": f"onset_{primary_variant}"}


def test_handoff_artifact_schema_keys_coins_and_splits(handoff_artifacts):
    config, features, labels = handoff_artifacts

    assert {"timestamp", "stablecoin", "split"}.issubset(features.columns)
    assert str(features["timestamp"].dtype) == "datetime64[ns, UTC]"
    assert features["timestamp"].eq(features["timestamp"].dt.normalize()).all()
    assert not features[["timestamp", "stablecoin"]].isna().any().any()
    assert not features.duplicated(["timestamp", "stablecoin"]).any()
    assert set(features["stablecoin"].unique()) == set(config["core_coins"])

    split_names = set(config["splits"])
    assert features["split"].notna().all()
    assert set(features["split"].unique()).issubset(split_names)
    for split, bounds in config["splits"].items():
        dates = features.loc[features["split"].eq(split), "timestamp"]
        start = pd.Timestamp(bounds["start"], tz="UTC")
        end = pd.Timestamp(bounds["end"], tz="UTC")
        assert dates.between(start, end).all(), f"Dates outside configured {split} split"

    assert {"date", "coin", "split"}.issubset(labels.columns)
    assert not labels.duplicated(["date", "coin"]).any()
    assert set(labels["coin"].unique()) == set(config["core_coins"])


def test_artifact_has_exact_configured_predictors_and_no_forbidden_inputs(
    handoff_artifacts,
):
    config, features, _ = handoff_artifacts
    predictors = config["feature_columns"]

    assert len(predictors) == 27
    assert len(set(predictors)) == 27
    assert set(predictors).issubset(features.columns)
    assert not (set(predictors) & QUALITY_FLAGS)
    assert not any(
        column.startswith(("raw_state_", "state_", "onset_", "depeg_at_t_plus_"))
        or "eligible" in column
        or column.startswith("hl_supported_")
        for column in predictors
    )
    assert not any(column.startswith("raw_state_") for column in features.columns)


def test_artifact_contains_all_variant_targets_and_valid_eligibility(
    handoff_artifacts,
):
    config, features, labels = handoff_artifacts
    variants = list(_variant_names(config))
    assert len(variants) == 18

    for variant in variants:
        for state_col in (f"state_{variant}", f"onset_{variant}"):
            assert state_col in features.columns
            assert pd.api.types.is_integer_dtype(features[state_col].dtype)
        if "_m2" in variant:
            assert f"raw_state_{variant}" in labels.columns
            assert f"raw_state_{variant}" not in features.columns
            assert pd.api.types.is_integer_dtype(
                labels[f"raw_state_{variant}"].dtype
            )

        for horizon in config["horizons"]:
            target = f"onset_label_{variant}_d{horizon}"
            eligible = f"onset_label_{variant}_eligible_d{horizon}"
            benchmark = f"depeg_at_t_plus_d{horizon}_{variant}"
            benchmark_eligible = f"depeg_at_t_plus_d{horizon}_eligible_{variant}"

            for column in (target, eligible, benchmark, benchmark_eligible):
                assert column in features.columns
            for column in (target, benchmark):
                assert pd.api.types.is_integer_dtype(features[column].dtype)
            for column in (eligible, benchmark_eligible):
                assert pd.api.types.is_integer_dtype(features[column].dtype)
                assert features[column].isin([0, 1]).all()

            for value_col, eligible_col in (
                (target, eligible),
                (benchmark, benchmark_eligible),
            ):
                values = features[value_col]
                flags = features[eligible_col]
                assert values.loc[flags.eq(0)].isna().all()
                assert values.loc[flags.eq(1)].notna().all()
                assert values.loc[flags.eq(1)].isin([0, 1]).all()


def test_interim_labels_match_processed_artifact(handoff_artifacts):
    config, features, labels = handoff_artifacts
    interim = labels.copy()
    interim["timestamp"] = pd.to_datetime(interim["date"], utc=True)
    interim["stablecoin"] = interim["coin"].astype("string")

    management = _management_columns(config)
    column_map = _interim_to_processed_column_map(config)
    missing = set([*management, "depeg_onset_t"]) - set(interim.columns)
    assert not missing, f"Interim labels missing columns: {sorted(missing)}"
    missing = set(management) - set(features.columns)
    assert not missing, f"Processed features missing columns: {sorted(missing)}"

    merged = features[["timestamp", "stablecoin", *management]].merge(
        interim[["timestamp", "stablecoin", *management]],
        on=["timestamp", "stablecoin"],
        how="outer",
        validate="one_to_one",
        indicator=True,
        suffixes=("_processed", "_interim"),
    )
    assert merged["_merge"].eq("both").all()
    for column in management:
        pd.testing.assert_series_equal(
            merged[f"{column}_processed"],
            merged[f"{column}_interim"],
            check_dtype=False,
            check_names=False,
        )

    processed_onset = column_map["depeg_onset_t"]
    onset_merge = features[["timestamp", "stablecoin", processed_onset]].merge(
        interim[["timestamp", "stablecoin", "depeg_onset_t"]],
        on=["timestamp", "stablecoin"],
        how="outer",
        validate="one_to_one",
        indicator=True,
        suffixes=("_processed", "_interim"),
    )
    assert onset_merge["_merge"].eq("both").all()
    pd.testing.assert_series_equal(
        onset_merge[processed_onset],
        onset_merge["depeg_onset_t"],
        check_dtype=False,
        check_names=False,
    )
