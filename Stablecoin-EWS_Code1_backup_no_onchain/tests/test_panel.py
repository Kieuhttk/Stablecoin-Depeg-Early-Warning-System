"""Test panel bản backup không on-chain, bằng dữ liệu giả (không cần mạng). Chạy: pytest -q"""
import copy
import os

import numpy as np
import pandas as pd
import pytest

from src.data.build_panel import binance_to_usd, build_panel
from src.data.fetch import SourceLog, count_off_midnight, empty_ohlcv, tidy, to_utc_midnight
from src.data.qc import ONCHAIN_COLS, review_tables, run_qc

CFG = {
    "llama_lag_days": 1, "llama_ffill_limit": 3, "binance_usd_conversion": True,
    "market": {"vol_window": 7},
    "coins": {
        "USDT": {"role": "core", "type": "fiat_backed"},
        "USDC": {"role": "core", "type": "fiat_backed", "binance_fallback": True},
        "DAI": {"role": "core", "type": "crypto_backed", "binance_fallback": True},
        "UST": {"role": "case_study", "type": "algorithmic", "last_valid_date": "2020-06-30", "binance_fallback": True},
    },
}


def _ohlc(idx, base=1.0, seed=0, vol=0.001):
    rng = np.random.default_rng(seed)
    c = base + rng.normal(0, vol, len(idx))
    df = pd.DataFrame({"open": c + rng.normal(0, vol / 2, len(idx)), "close": c}, index=idx)
    df["high"] = df[["open", "close"]].max(axis=1) + 0.0005
    df["low"] = df[["open", "close"]].min(axis=1) - 0.0005
    df["volume"] = rng.uniform(1e6, 5e6, len(idx))
    df.index.name = "date_utc"
    return df[["open", "high", "low", "close", "volume"]]


@pytest.fixture()
def raw():
    """Mô phỏng tình huống thật: KHÔNG có CryptoCompare (không key), Binance quote USDT, Yahoo thiếu 2 ngày."""
    idx = pd.date_range("2020-01-01", "2020-09-30", freq="D", tz="UTC")
    r = {"price": {}, "supply": {}}
    for i, coin in enumerate(CFG["coins"]):
        full = _ohlc(idx, seed=i)
        ya = full if coin == "USDT" else full.drop(full.index[[40, 41]])   # Yahoo thiếu 2 ngày => Binance lấp
        bn = empty_ohlcv() if coin == "USDT" else full.copy()               # Binance (USDT) gần giống Yahoo
        r["price"][coin] = {"yahoo": ya, "cc": empty_ohlcv(), "binance": bn}
        r["supply"][coin] = pd.DataFrame({"supply": np.linspace(1e9, 2e9, len(idx)), "supply_eth": np.nan}, index=idx)
    r["btc"] = _ohlc(idx, base=9000, seed=7, vol=100)
    r["eth"] = _ohlc(idx, base=200, seed=8, vol=5)
    r["tvl"] = pd.DataFrame({"tvl": np.linspace(1e9, 5e10, len(idx))}, index=idx)
    return r


# ---------------------------------------------------------------- cấu trúc, UTC, lưới ngày
def test_structure_and_utc(raw):
    p = build_panel(raw, CFG)
    assert not p.duplicated(["stablecoin", "timestamp"]).any()
    assert str(p["timestamp"].dt.tz) == "UTC"
    assert (p["timestamp"] == p["timestamp"].dt.normalize()).all()
    assert (p["peg_deviation"].dropna() == (p["price"] - 1).abs().dropna()).all()
    assert (p["high"] >= p["low"]).all()
    assert p.loc[p.stablecoin == "UST", "timestamp"].max() == pd.Timestamp("2020-06-30", tz="UTC")
    assert not p["is_missing_price"].any()                       # 2 ngày Yahoo thiếu đã được Binance lấp
    assert (p["price_src"] == "binance_usd").sum() == 2 * 3      # USDC, DAI, UST


def test_no_onchain_columns(raw):
    p = build_panel(raw, CFG)
    assert not [c for c in ONCHAIN_COLS if c in p.columns]


def test_qc_has_no_fail(raw):
    p = build_panel(raw, CFG)
    rep = run_qc(p, raw, CFG)
    assert rep[rep.status == "FAIL"].empty, rep[rep.status == "FAIL"].to_string()


def test_utc_normalization_of_mixed_inputs():
    # mốc có múi giờ khác (UTC+7) phải quy về đúng ngày UTC; mốc không múi giờ được hiểu là UTC
    idx_local = pd.DatetimeIndex(["2020-01-02 07:00"]).tz_localize("Asia/Ho_Chi_Minh")    # = 2020-01-02 00:00 UTC
    assert to_utc_midnight(idx_local)[0] == pd.Timestamp("2020-01-02", tz="UTC")
    assert count_off_midnight(idx_local) == 0
    late = pd.DatetimeIndex(["2020-01-02 06:00"]).tz_localize("Asia/Ho_Chi_Minh")          # = 01/01 23:00 UTC
    assert count_off_midnight(late) == 1                                                    # bị phát hiện
    strings = pd.Index(["2020-01-01 00:00:00+00:00", "2020-01-02 00:00:00+00:00"])          # dạng cache CSV
    assert list(to_utc_midnight(strings)) == list(pd.date_range("2020-01-01", periods=2, tz="UTC"))
    df = pd.DataFrame({"open": [1.0, 1.0], "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0},
                      index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-02 12:00"]))
    t = tidy(df, "2020-01-01", "2020-01-31")
    assert t.attrs["off_midnight"] == 1 and str(t.index.tz) == "UTC"


# ---------------------------------------------------------------- point-in-time
def test_supply_is_lagged(raw):
    p = build_panel(raw, CFG)
    coin = p[p.stablecoin == "USDC"].set_index("timestamp")
    t = pd.Timestamp("2020-05-10", tz="UTC")
    assert coin.loc[t, "supply"] == pytest.approx(raw["supply"]["USDC"]["supply"].loc[t - pd.Timedelta(days=1)])


def test_no_lookahead_perturbation(raw):
    """Đổi toàn bộ dữ liệu SAU ngày T (mọi nguồn) không được làm thay đổi bất kỳ giá trị nào tại hoặc trước T."""
    T = pd.Timestamp("2020-07-15", tz="UTC")
    base = build_panel(raw, CFG)
    pert = copy.deepcopy(raw)
    after = lambda df: df.index > T  # noqa: E731
    for coin in CFG["coins"]:
        for src in ("yahoo", "binance"):
            df = pert["price"][coin][src]
            if len(df):
                df.loc[after(df), ["open", "high", "low", "close"]] *= 1.37
                df.loc[after(df), "volume"] *= 3
        s = pert["supply"][coin]
        s.loc[after(s), "supply"] *= 2.5
    for k in ("btc", "eth"):
        pert[k].loc[after(pert[k]), ["open", "high", "low", "close"]] *= 1.9
    pert["tvl"].loc[after(pert["tvl"]), "tvl"] *= 4
    new = build_panel(pert, CFG)
    a = base[base.timestamp <= T].reset_index(drop=True)
    b = new[new.timestamp <= T].reset_index(drop=True)
    num = a.select_dtypes("number").columns
    pd.testing.assert_frame_equal(a[num], b[num], check_exact=False, rtol=1e-12)
    pd.testing.assert_frame_equal(a.select_dtypes("bool"), b.select_dtypes("bool"))


# ---------------------------------------------------------------- Binance quy USD và đồng thuận nhiều nguồn
def test_binance_usd_conversion(raw):
    usdt = raw["price"]["USDT"]["yahoo"]["close"]
    conv = binance_to_usd(raw["price"]["USDC"]["binance"], usdt)
    t = conv.index[10]
    assert conv.loc[t, "close"] == pytest.approx(raw["price"]["USDC"]["binance"].loc[t, "close"] * usdt.loc[t])
    p = build_panel(raw, CFG).set_index(["stablecoin", "timestamp"])
    assert p.loc[("USDC", t), "bn_close_usd"] == pytest.approx(conv.loc[t, "close"])
    assert p.loc[("USDC", t), "usdt_usd"] == pytest.approx(usdt.loc[t])


def test_binance_raw_usdt_when_no_rate(raw):
    """Không có USDT-USD => không quy đổi được, giá Binance giữ đơn vị USDT và gắn nhãn binance_usdt."""
    raw["price"]["USDT"]["yahoo"] = empty_ohlcv()
    cfg = copy.deepcopy(CFG)
    del cfg["coins"]["USDT"]
    p = build_panel(raw, cfg)
    assert set(p.loc[p.price_src.str.startswith("binance", na=False), "price_src"]) == {"binance_usdt"}
    assert p["bn_close_usd"].isna().all()


def test_consensus_and_source_count(raw):
    p = build_panel(raw, CFG)
    assert (p["peg_deviation_min"] <= p["peg_deviation"] + 1e-15).all()
    both = p.dropna(subset=["peg_deviation_bn"])
    assert (both["peg_deviation_min"] <= both["peg_deviation_bn"] + 1e-15).all()
    u = p[p.stablecoin == "USDT"]
    assert (u["n_price_sources"] == 1).all()
    assert (u["peg_deviation_min"] == u["peg_deviation"]).all()       # một nguồn => bằng chính nó
    c = p[(p.stablecoin == "USDC") & (p.price_src == "yahoo")]
    assert (c["n_price_sources"] == 2).all()


def test_src_disagree_and_xmkt_gap(raw):
    t = raw["price"]["USDC"]["binance"].index[100]
    raw["price"]["USDC"]["binance"].loc[t, "close"] *= 1.02          # Binance lệch 2% một ngày
    p = build_panel(raw, CFG).set_index(["stablecoin", "timestamp"])
    assert p.loc[("USDC", t), "src_disagree"]
    assert p.loc[("USDC", t), "xmkt_gap"] > 0.015
    gaps = p.loc["USDC"]
    assert gaps.loc[gaps.price_src == "binance_usd", "xmkt_gap"].isna().all()   # không tự so với chính nó


# ---------------------------------------------------------------- râu nến lỗi
def test_hl_suspect_refuted_by_binance(raw):
    t = raw["price"]["USDC"]["yahoo"].index[120]
    raw["price"]["USDC"]["yahoo"].loc[t, "high"] = 2.35                 # râu lỗi kiểu Yahoo 16/11/2021
    p = build_panel(raw, CFG).set_index(["stablecoin", "timestamp"])
    r = p.loc[("USDC", t)]
    assert r["hl_suspect"]
    assert r["peg_deviation_hl"] > 1.0 and r["peg_deviation_hl_clean"] < 0.01


def test_hl_moderate_wick_without_second_source_is_kept(raw):
    """USDT 12/05/2022: low 0,9485, không có nguồn thứ hai => KHÔNG được coi là lỗi."""
    t = raw["price"]["USDT"]["yahoo"].index[130]
    raw["price"]["USDT"]["yahoo"].loc[t, "low"] = 0.9485
    p = build_panel(raw, CFG).set_index(["stablecoin", "timestamp"])
    r = p.loc[("USDT", t)]
    assert not r["hl_suspect"]
    assert r["peg_deviation_hl_clean"] == pytest.approx(r["peg_deviation_hl"])
    raw["price"]["USDT"]["yahoo"].loc[t, "low"] = 0.60                   # râu cực đoan, thân nến sát neo
    p2 = build_panel(raw, CFG).set_index(["stablecoin", "timestamp"])
    assert p2.loc[("USDT", t), "hl_suspect"]
    assert len(review_tables(p2.reset_index())["review_hl_suspect_days"]) >= 1


def test_hl_confirmed_by_binance_is_kept(raw):
    t = raw["price"]["USDC"]["yahoo"].index[150]
    raw["price"]["USDC"]["yahoo"].loc[t, "low"] = 0.90
    raw["price"]["USDC"]["binance"].loc[t, "low"] = 0.91               # Binance xác nhận => depeg trong ngày thật
    p = build_panel(raw, CFG).set_index(["stablecoin", "timestamp"])
    assert not p.loc[("USDC", t), "hl_suspect"]
    assert p.loc[("USDC", t), "peg_deviation_hl_clean"] > 0.08


# ---------------------------------------------------------------- biến thị trường, ngày cuối, cảnh báo QC
def test_market_vars_consistent_across_coins_and_late_start(raw):
    long_idx = pd.date_range("2019-11-01", "2020-09-30", freq="D", tz="UTC")
    raw["btc"] = _ohlc(long_idx, base=9000, seed=7, vol=100)
    raw["eth"] = _ohlc(long_idx, base=200, seed=8, vol=5)
    late = pd.Timestamp("2020-06-01", tz="UTC")
    for src in ("yahoo", "binance"):
        df = raw["price"]["DAI"][src]
        raw["price"]["DAI"][src] = df[df.index >= late]
    p = build_panel(raw, CFG)
    first = p[p.stablecoin == "DAI"].sort_values("timestamp").iloc[0]
    assert first["timestamp"] == late
    assert pd.notna(first["btc_vol"]) and pd.notna(first["tvl_change"]) and pd.notna(first["supply_change"])
    by_day = p.groupby("timestamp")[["btc_vol", "eth_vol", "btc_ret", "tvl", "tvl_change", "usdt_usd"]].nunique(dropna=True)
    assert (by_day <= 1).all().all()
    rep = run_qc(p, raw, CFG)
    assert rep[rep.check.str.contains("cấp thị trường")].iloc[0].status == "PASS"


def test_sample_end_freeze_and_tvl_zero_safe(raw):
    cfg = copy.deepcopy(CFG)
    cfg["sample"] = {"start": "2020-02-01", "end": "2020-08-31"}
    raw["tvl"].iloc[:60, 0] = 0.0
    p = build_panel(raw, cfg)
    assert p["timestamp"].min() >= pd.Timestamp("2020-02-01", tz="UTC")
    assert p["timestamp"].max() <= pd.Timestamp("2020-08-31", tz="UTC")
    assert not np.isinf(p["tvl_change"].dropna()).any()


def test_real_depeg_is_warn_not_fail(raw):
    p = build_panel(raw, CFG)
    i = p.index[(p.stablecoin == "USDC")][100]
    p.loc[i, "price"] = 0.30
    rep = run_qc(p, raw, CFG)
    assert rep[rep.status == "FAIL"].empty
    assert (rep[rep.check.str.contains("thường là depeg thật")].status == "WARN").all()


def test_supply_eth_proxy_and_missing(raw):
    p0 = build_panel(raw, CFG)
    assert p0[["supply_eth", "supply_eth_change", "supply_eth_share"]].isna().all().all()
    for coin in CFG["coins"]:
        raw["supply"][coin]["supply_eth"] = raw["supply"][coin]["supply"] * 0.4
    u = build_panel(raw, CFG)
    u = u[u.stablecoin == "USDC"].set_index("timestamp")
    t = pd.Timestamp("2020-05-10", tz="UTC")
    assert u.loc[t, "supply_eth_share"] == pytest.approx(0.4)
    s = raw["supply"]["USDC"]["supply_eth"]
    assert u.loc[t, "supply_eth_change"] == pytest.approx(s.loc[t - pd.Timedelta(days=1)] / s.loc[t - pd.Timedelta(days=2)] - 1)


# ---------------------------------------------------------------- source log, offline, bảo mật key
def test_offline_mode_never_calls_network(tmp_path):
    called = []
    log = SourceLog(offline=True)
    out = log.run("Yahoo Finance", "X", "e", lambda: called.append(1), tmp_path / "missing.csv")
    assert not called and len(out) == 0
    assert log.to_frame().loc[0, "status"] == "missing_cache"
    cache = tmp_path / "c.csv"
    pd.DataFrame({"close": [1.0]}, index=pd.Index(["2020-01-01 00:00:00+00:00"], name="date_utc")).to_csv(cache, encoding="utf-8")
    out = log.run("Yahoo Finance", "Y", "e", lambda: called.append(1), cache)
    assert not called and log.to_frame().loc[1, "status"] == "ok_cache"
    assert log.to_frame().loc[1, "off_midnight"] == 0 and str(out.index.tz) == "UTC"


def test_env_loader_and_secret_hygiene(tmp_path, monkeypatch):
    from src.data import fetch
    envf = tmp_path / ".env"
    envf.write_bytes("﻿# ghi chú\nexport CC_TEST_KEY = \"abc123\"\nEMPTY=\nCC_TEST_PRE=file\n".encode("utf-8"))
    monkeypatch.delenv("CC_TEST_KEY", raising=False)
    monkeypatch.setenv("CC_TEST_PRE", "terminal")
    fetch.load_env(envf)
    assert os.environ["CC_TEST_KEY"] == "abc123" and os.environ["CC_TEST_PRE"] == "terminal"
    monkeypatch.delenv("CC_TEST_KEY", raising=False)

    seen = {}

    class R:
        def raise_for_status(self): pass
        def json(self): return {"Data": {"Data": []}}

    def fake_get(url, params=None, headers=None, timeout=None):
        seen["params"], seen["headers"] = params, headers
        return R()
    monkeypatch.setattr(fetch.requests, "get", fake_get)
    fetch.fetch_cryptocompare("USDC", "2020-01-01", "2020-01-10", "SECRET123")
    assert "SECRET123" not in str(seen["params"]) and seen["headers"]["authorization"] == "Apikey SECRET123"
    log = fetch.SourceLog(redact=["SECRET123"])

    def boom(): raise RuntimeError("401 for url https://x?api_key=SECRET123")
    log.run("CryptoCompare", "t", "e", boom)
    assert "SECRET123" not in log.to_frame().loc[0, "error"]


def test_fetch_all_skips_cryptocompare_without_key(tmp_path, monkeypatch):
    """Không key => CryptoCompare không được gọi, ghi skipped_no_key; chế độ offline không gọi mạng."""
    from src.data import fetch
    monkeypatch.delenv("CRYPTOCOMPARE_API_KEY", raising=False)
    monkeypatch.setattr(fetch, "load_env", lambda *a, **k: None)
    monkeypatch.setattr(fetch.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("gọi mạng!")))
    cfg = {"sample": {"start": "2020-01-01", "end": "2020-01-31"}, "cryptocompare_api_key_env": "CRYPTOCOMPARE_API_KEY",
           "coins": {"USDC": {"yahoo": "USDC-USD", "cc": "USDC", "binance": "USDCUSDT", "llama_symbol": "USDC", "llama_name": "USD Coin"}},
           "market": {"btc_yahoo": "BTC-USD", "eth_yahoo": "ETH-USD", "warmup_days": 30}}
    _, log = fetch.fetch_all(cfg, tmp_path, offline=True)
    st = dict(zip(log["source"] + ":" + log["key"], log["status"]))
    assert st["CryptoCompare:USDC:USDC"] == "skipped_no_key"
    assert set(log.loc[log.source != "CryptoCompare", "status"]) == {"missing_cache"}
