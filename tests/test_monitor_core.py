"""Test cho lõi Code 4: mức cảnh báo, driver trống, onset, và không rò rỉ từ test sang ngưỡng Amber."""
import numpy as np
import pandas as pd

from src.evaluation import monitor_core as mc


def _run(n_dev=1000, n_final=50, seed=0):
    rng = np.random.default_rng(seed)
    dev = pd.DataFrame({"score_raw": rng.normal(0, 1, n_dev), "proba_type": "oof"})
    fin = pd.DataFrame({"score_raw": rng.normal(5, 1, n_final), "proba_type": "final"})  # test lệch hẳn
    df = pd.concat([dev, fin], ignore_index=True)
    df["alarm"] = 0
    return df


def test_amber_threshold_uses_dev_only():
    run = _run()
    scale = mc.fit_risk_scale(run, 0.90)
    dev_only = run[run.proba_type == "oof"]["score_raw"]
    assert np.isclose(scale["amber_thr"], np.quantile(dev_only, 0.90))
    assert scale["n_dev"] == 1000 and not scale["fallback"]


def test_red_has_priority_over_amber_and_green_is_rest():
    run = _run()
    scale = mc.fit_risk_scale(run, 0.90)
    run.loc[0, ["score_raw", "alarm"]] = [scale["amber_thr"] + 1, 1]   # vừa Amber vừa alarm -> Red
    run.loc[1, ["score_raw", "alarm"]] = [scale["amber_thr"] + 1, 0]   # Amber
    run.loc[2, ["score_raw", "alarm"]] = [-5, 0]                       # Green
    lv = mc.assign_alert(run, scale)
    assert lv[0] == "Red" and lv[1] == "Amber" and lv[2] == "Green"


def test_risk_score_in_0_100_and_nan_safe():
    scale = mc.fit_risk_scale(_run(), 0.90)
    s = mc.risk_score(pd.Series([-10, 0, 10, np.nan]), scale)
    assert s.iloc[0] == 0 and s.iloc[2] == 100 and np.isnan(s.iloc[3])
    assert 0 <= s.iloc[1] <= 100


def test_empty_drivers_show_message_not_error():
    df = pd.DataFrame({"top1_driver": [None, ""], "top2_driver": ["nan", None], "top3_driver": [pd.NA, "None"]})
    df = mc.clean_drivers(df)
    assert mc.drivers_of(df.iloc[0]) == [mc.EMPTY_DRIVER_MSG]
    assert mc.drivers_of(df.iloc[1]) == [mc.EMPTY_DRIVER_MSG]
    one = mc.clean_drivers(pd.DataFrame({"top1_driver": ["vol_7d"]}))   # thiếu hẳn cột top2/top3
    assert mc.drivers_of(one.iloc[0]) == ["vol_7d"]


def test_depeg_state_and_onset_with_persistence():
    dev = pd.Series([0, 0.02, 0, 0.02, 0.03, 0.02, 0])
    assert mc.depeg_state(dev, 0.01, 1).tolist() == [False, True, False, True, True, True, False]
    assert mc.depeg_state(dev, 0.01, 2).tolist() == [False, False, False, False, True, True, False]
    panel = pd.DataFrame({"stablecoin": "X", "timestamp": pd.date_range("2024-01-01", periods=7), "dev": dev})
    on = mc.find_onsets(panel, 0.01, 2)
    assert len(on) == 1 and on.iloc[0]["onset"] == pd.Timestamp("2024-01-04")  # ngày đầu của chuỗi 2 ngày


def test_missing_proba_type_is_derived_from_split(tmp_path):
    df = pd.DataFrame({"timestamp": pd.date_range("2022-12-30", periods=4), "stablecoin": "USDC", "model": "m", "h": 1,
                       "split": ["val", "val", "test", "test"], "proba": [0.1, 0.2, 0.3, 0.4]})
    p = tmp_path / "pred.parquet"
    df.to_parquet(p)
    out, flags = mc.load_predictions(p)
    assert flags["proba_type_derived"] and out["proba_type"].tolist() == ["oof", "oof", "final", "final"]
