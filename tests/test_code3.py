"""Kiểm thử Code 3 (chạy: python -m pytest -q tests/test_code3.py).

Các test dùng dữ liệu tổng hợp nhỏ, không cần features.parquet thật.
"""
import numpy as np
import pandas as pd

from src.models import code3_models as c3

CFG = c3.load_config()
SPEC = CFG["spec"]
FEATS = CFG["feature_columns"]


def _synthetic(seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", "2023-01-31", freq="D")
    frames = []
    for coin in ["DAI", "USDC"]:
        d = pd.DataFrame(rng.normal(size=(len(dates), len(FEATS))), columns=FEATS)
        d["stablecoin"], d["date"] = coin, dates
        d["split"] = np.where(d["date"] < "2022-01-01", "train",
                              np.where(d["date"] < "2023-01-01", "validation", "test"))
        for h in CFG["horizons"]:
            y, e, _ = c3.label_cols(SPEC, h)
            d[y] = (rng.random(len(d)) < 0.03).astype(float)
            d[e] = 1
        d[c3.label_cols(SPEC, 1)[2]] = (rng.random(len(d)) < 0.02).astype(int)
        frames.append(d)
    return pd.concat(frames, ignore_index=True).sort_values(c3.KEYS).reset_index(drop=True)


def test_predictors_exclude_labels_and_match_groups():
    assert len(FEATS) == 27
    assert not [c for c in FEATS if c.startswith(c3.FORBIDDEN_PREFIXES)]
    grouped = [c for cols in CFG["feature_groups"].values() for c in cols]
    assert sorted(grouped) == sorted(FEATS)


def test_walk_forward_purge_and_no_lookahead():
    """Điểm OOF của một khối không đổi khi dữ liệu từ ngày bắt đầu khối trở đi bị xáo trộn."""
    df = _synthetic()
    h = 1
    params = CFG["grid"]["rf"][0] | {"n_estimators": 50}
    a = c3.walk_forward(df, CFG, SPEC, h, "rf", params, FEATS)
    first_block = pd.Timestamp(CFG["cv_block_starts"][1])      # fold 0 kiểm tra [2021-01-01, 2021-07-01)
    df2 = df.copy()
    future = df2["date"] >= first_block                          # thay đổi mọi thứ sau khối đầu
    rng = np.random.default_rng(1)
    df2.loc[future, FEATS] = rng.normal(size=(int(future.sum()), len(FEATS)))
    df2.loc[future, c3.label_cols(SPEC, h)[0]] = 1.0 - df2.loc[future, c3.label_cols(SPEC, h)[0]]
    b = c3.walk_forward(df2, CFG, SPEC, h, "rf", params, FEATS)
    rows = a.index[a["fold"] == 0]
    pd.testing.assert_series_equal(a.loc[rows, "score"], b.loc[rows, "score"])


def test_dev_loader_drops_test_split(tmp_path):
    df = _synthetic()
    df["timestamp"] = df["date"].dt.tz_localize("UTC")
    p = tmp_path / "features.pkl"
    df.drop(columns="date").to_pickle(p)
    out = c3.load_data(CFG, str(p), ("test",))
    assert not (out["split"] == "test").any()


def test_pick_threshold_maximises_f2():
    y = np.array([0, 0, 0, 0, 1, 0, 1, 1, 0, 0])
    s = np.array([.1, .2, .15, .3, .8, .4, .6, .9, .05, .35])
    thr = c3.pick_threshold(y, s, beta=2)
    m = c3.obs_metrics(y, s, thr, beta=2)
    for t in np.unique(s):
        assert m["f2"] >= c3.obs_metrics(y, s, t, beta=2)["f2"] - 1e-9


def test_event_level_lead_time():
    dates = pd.date_range("2022-05-01", periods=8)
    f = pd.DataFrame({"stablecoin": "DAI", "date": dates, "onset": 0, "elig": 1, "alarm": 0.0})
    f.loc[f["date"] == "2022-05-06", "onset"] = 1          # sự kiện bắt đầu 06/05
    f.loc[f["date"] == "2022-05-04", "alarm"] = 1.0        # cảnh báo sớm nhất 04/05, cách 2 ngày
    r = c3.event_level(f, h=3, onset_col="onset", elig_col="elig")
    assert r["n_events"] == 1 and r["n_caught"] == 1 and r["mean_lead_days"] == 2
    f["alarm"] = 0.0
    assert c3.event_level(f, 3, "onset", "elig")["n_caught"] == 0


def test_platt_is_monotone_and_bounded():
    rng = np.random.default_rng(2)
    s = rng.random(500)
    y = (rng.random(500) < s * 0.2).astype(float)
    pl = c3.fit_platt(s, y)
    p = c3.apply_platt(np.sort(s), pl)
    assert np.all(np.diff(p) >= -1e-12) and p.min() >= 0 and p.max() <= 1


# ---------------------------------------------------------------- bổ sung 22/10
def test_event_level_lookback_gives_longer_lead_time():
    dates = pd.date_range("2022-05-01", periods=10)
    f = pd.DataFrame({"stablecoin": "DAI", "date": dates, "onset": 0, "elig": 1, "alarm": 0.0})
    f.loc[f["date"] == "2022-05-09", "onset"] = 1
    f.loc[f["date"] == "2022-05-04", "alarm"] = 1.0        # cảnh báo sớm 5 ngày
    short = c3.event_level(f, h=1, onset_col="onset", elig_col="elig")                # cửa sổ = h
    long_ = c3.event_level(f, h=1, onset_col="onset", elig_col="elig", lookback=7)
    assert short["n_caught"] == 0
    assert long_["n_caught"] == 1 and long_["mean_lead_days"] == 5


def test_top_drivers_only_positive_contributions():
    attr = pd.DataFrame([[0.5, 0.2, -0.1, 0.0], [-0.3, -0.2, -0.1, -0.5]],
                        columns=["a", "b", "c", "d"])
    out = c3.top_drivers(attr)
    assert out.loc[0, "top1_driver"] == "a" and out.loc[0, "top2_driver"] == "b"
    assert out.loc[0, "top3_driver"] is None            # còn lại <= 0 thì để trống
    assert out.loc[1].isna().all()                      # không có driver tăng rủi ro


def _small_rf():
    rng = np.random.default_rng(3)
    X = pd.DataFrame(rng.normal(size=(300, 4)), columns=list("abcd"))
    y = (X["a"] + rng.normal(scale=0.5, size=300) > 1).astype(int).to_numpy()
    m = c3.Model("rf", {"n_estimators": 30, "max_depth": 3, "min_samples_leaf": 5}, 0).fit(X, y)
    return m, X


def test_rf_explain_occlusion_fallback_and_shape():
    m, X = _small_rf()
    old = c3.HAS_SHAP
    c3.HAS_SHAP = False
    try:
        vals, method = m.explain(X)
    finally:
        c3.HAS_SHAP = old
    assert method == "occlusion" and vals.shape == X.shape


def test_rf_explain_handles_both_shap_output_shapes():
    """Kiểm tra nhánh xử lý đầu ra của shap (list theo lớp hoặc mảng 3 chiều) bằng shap giả."""
    m, X = _small_rf()
    n, k = X.shape
    marker = np.arange(n * k, dtype=float).reshape(n, k)

    class FakeList:
        def __init__(self, est): pass
        def shap_values(self, Xs): return [-marker, marker]

    class Fake3D:
        def __init__(self, est): pass
        def shap_values(self, Xs): return np.stack([-marker, marker], axis=2)

    old_has, old_shap = c3.HAS_SHAP, getattr(c3, "shap", None)
    try:
        c3.HAS_SHAP = True
        for fake in (FakeList, Fake3D):
            c3.shap = type("S", (), {"TreeExplainer": fake})
            vals, method = m.explain(X)
            assert method == "shap_tree"
            np.testing.assert_array_equal(vals, marker)   # luôn lấy lớp dương
    finally:
        c3.HAS_SHAP = old_has
        if old_shap is None:
            del c3.shap
        else:
            c3.shap = old_shap


def test_t05_contains_precision_recall_and_lookback():
    df = _synthetic()
    h = 1
    ycol, ecol, ocol = c3.label_cols(SPEC, h)
    df[ocol] = df[ycol].shift(-1).fillna(0).astype(int)          # onset giả lập
    scores = pd.Series(np.random.default_rng(4).random(len(df)), index=df.index)
    t04, t05 = c3.evaluate(df, scores, 0.9, CFG, SPEC, h, df["split"] == "validation",
                           "rf", {}, "dev", "validation_2022")
    for col in ("precision", "recall", "f2", "false_alarm_rate", "lead_lookback_days"):
        assert col in t05
    assert t05["lead_lookback_days"] == CFG["lead_lookback"]
    assert t05["precision"] == t04["precision"] or (np.isnan(t05["precision"]) and np.isnan(t04["precision"]))


def test_to_utc_is_timezone_aware():
    s = c3.to_utc(pd.Series(pd.to_datetime(["2022-05-01", "2022-05-02"])))
    assert str(s.dt.tz) == "UTC"


def test_config_drop_features_are_valid_predictors():
    for cols in CFG.get("robustness_drop_features", {}).values():
        assert set(cols) <= set(FEATS)


def test_chance_event_recall_matches_formula():
    df = _synthetic()
    h = 1
    ycol, ecol, ocol = c3.label_cols(SPEC, h)
    df[ocol] = df[ycol].shift(-1).fillna(0).astype(int)
    scores = pd.Series(np.random.default_rng(5).random(len(df)), index=df.index)
    t04, t05 = c3.evaluate(df, scores, 0.9, CFG, SPEC, h, df["split"] == "validation",
                           "rf", {}, "dev", "validation_2022")
    rate = t04["n_alarms"] / t04["n_obs"]
    assert abs(t05["chance_event_recall"] - (1 - (1 - rate) ** CFG["lead_lookback"])) < 1e-12
    assert 0.0 <= t05["chance_event_recall"] <= 1.0


def test_exclude_features_filters_features_and_groups(tmp_path):
    import yaml
    cfg = yaml.safe_load(c3.CONFIG_PATH.read_text(encoding="utf-8"))
    cfg["exclude_features"] = ["xmkt_gap", "xmkt_gap_missing"]
    p = tmp_path / "code3_nox.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    out = c3.load_config(p)
    assert len(out["feature_columns"]) == 25
    assert "xmkt_gap" not in out["feature_columns"] and "xmkt_gap_missing" not in out["feature_columns"]
    assert sorted(c for cols in out["feature_groups"].values() for c in cols) == sorted(out["feature_columns"])
    cfg["exclude_features"] = ["khong_ton_tai"]
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    try:
        c3.load_config(p)
        raise AssertionError("phải báo lỗi với biến không tồn tại")
    except ValueError:
        pass

def test_budget_metrics_alarm_rate_matches_budget():
    df = _synthetic()
    h = 1
    ycol, ecol, ocol = c3.label_cols(SPEC, h)
    df[ocol] = df[ycol].shift(-1).fillna(0).astype(int)
    scores = pd.Series(np.random.default_rng(6).random(len(df)), index=df.index)
    rows = c3.budget_metrics(df, scores, CFG, SPEC, h, df["split"] == "validation",
                             "rf", "dev", "validation_2022")
    assert len(rows) == len(CFG.get("alarm_budgets", [0.03, 0.05, 0.10]))
    for r in rows:
        assert abs(r["alarm_rate_actual"] - r["alarm_budget"]) < 0.01
        assert 0.0 <= r["chance_event_recall"] <= 1.0
    # ngân sách lớn hơn thì recall mức sự kiện không giảm
    rec = [r["event_recall"] for r in rows]
    assert all(x <= y + 1e-12 for x, y in zip(rec, rec[1:]))