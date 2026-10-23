"""Dựng panel.parquet (stablecoin x ngày, UTC) từ dữ liệu thô: BẢN BACKUP KHÔNG ON-CHAIN.

Quy ước point-in-time: hàng (stablecoin, t) chỉ chứa thông tin biết được vào cuối ngày t (UTC).
Nhãn depeg (t+h) do Code 2 tạo bằng shift(-h) trong từng coin, trên lưới ngày liên tục mà file này đảm bảo.

Chạy:
    python -m src.data.build_panel --version v1              # dùng cache data/raw, nguồn chưa có cache thì tải
    python -m src.data.build_panel --version v1 --offline    # CHỈ dùng cache, không gọi mạng
    python -m src.data.build_panel --version v1 --refresh    # tải lại toàn bộ
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.data.dictionary import DICTIONARY
from src.data.fetch import empty_ohlcv, fetch_all
from src.data import qc as qcmod
from src.data import appendix as appmod

ROOT = Path(__file__).resolve().parents[2]
PX = ["open", "high", "low", "close"]
DEFAULT_Q = {"src_disagree_threshold": 0.005, "hl_spike_threshold": 0.05, "hl_body_threshold": 0.01,
             "hl_extreme_threshold": 0.25}


def _valid(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or not len(df):
        return empty_ohlcv()
    d = df.dropna(subset=["close"])
    return d[d["close"] > 0]


def usdt_usd_series(raw: dict) -> pd.Series:
    """Giá đóng cửa USDT-USD (Yahoo) theo ngày UTC, dùng để quy giá Binance (quote USDT) về USD."""
    ya = (raw.get("price", {}).get("USDT", {}) or {}).get("yahoo")
    ya = _valid(ya)
    return ya["close"].astype(float) if len(ya) else pd.Series(dtype=float)


def binance_to_usd(bn: pd.DataFrame, usdt: pd.Series) -> pd.DataFrame:
    """Nhân OHLC và volume (quote USDT) với USDT-USD cùng ngày. Ngày không có USDT-USD => NaN.
    High/Low chỉ là xấp xỉ vì USDT-USD là giá đóng cửa."""
    if bn is None or not len(bn) or usdt is None or not len(usdt):
        return empty_ohlcv()
    rate = usdt.reindex(bn.index)
    out = bn[PX + ["volume"]].astype(float).mul(rate, axis=0)
    return out


# ---------------------------------------------------------------- khối giá
def _price_block(p: dict, last_valid: str | None, binance_fallback: bool, usdt: pd.Series,
                 start: str | None = None, end: str | None = None, q: dict | None = None) -> pd.DataFrame | None:
    q = {**DEFAULT_Q, **(q or {})}
    ya = _valid(p.get("yahoo"))
    if len(ya):
        ya = ya.copy()
        # Yahoo crypto Volume là số lượng token cơ sở; quy sang USD theo giá đóng cửa.
        ya["volume"] = ya["volume"] * ya["close"]
    cc = _valid(p.get("cc"))
    bn_raw = _valid(p.get("binance"))
    bn_usd = _valid(binance_to_usd(bn_raw, usdt))

    sec = cc.loc[~cc.index.isin(ya.index)]
    parts = [d.assign(price_src=s) for d, s in ((ya, "yahoo"), (sec, "cryptocompare")) if len(d)]
    if binance_fallback:  # bậc 3: Binance quy USD; nếu thiếu USDT-USD ngày đó thì giữ giá USDT và gắn nhãn rõ
        have = ya.index.union(cc.index)
        t_usd = bn_usd.loc[~bn_usd.index.isin(have)]
        t_raw = bn_raw.loc[~bn_raw.index.isin(have.union(bn_usd.index))].copy()
        # Không có tỷ giá USDT/USD thì giữ giá USDT để tham khảo nhưng volume USD không xác định.
        if len(t_raw):
            t_raw["volume"] = np.nan
        for d, s in ((t_usd, "binance_usd"), (t_raw, "binance_usdt")):
            if len(d):
                parts.append(d[PX + ["volume"]].assign(price_src=s))
    if not parts:
        return None
    price = pd.concat(parts).sort_index()
    if last_valid:
        price = price.loc[: pd.Timestamp(last_valid, tz="UTC")]
    if start:
        price = price.loc[pd.Timestamp(start, tz="UTC"):]
    if end:  # đóng băng ngày cuối: panel không đổi khi chạy lại vào ngày khác
        price = price.loc[: pd.Timestamp(end, tz="UTC")]
    if price.empty:
        return None

    # Sửa High/Low không nhất quán (High < max(O,C) hoặc Low > min(O,C)); đánh dấu hl_fixed
    hi = price[["open", "high", "close"]].max(axis=1)
    lo = price[["open", "low", "close"]].min(axis=1)
    price["hl_fixed"] = (hi != price["high"]) | (lo != price["low"])
    price["high"], price["low"] = hi, lo

    idx = pd.date_range(price.index.min(), price.index.max(), freq="D", tz="UTC", name="timestamp")
    price = price.reindex(idx)
    price["is_missing_price"] = price["close"].isna()
    price["hl_fixed"] = price["hl_fixed"].fillna(False).astype(bool)
    price["ya_close"] = ya["close"].reindex(idx)
    for col in ("close", "high", "low"):
        price[f"cc_{col}"] = cc[col].reindex(idx) if len(cc) else np.nan
        price[f"bn_{col}_usd"] = bn_usd[col].reindex(idx) if len(bn_usd) else np.nan
    price["bn_close"] = bn_raw["close"].reindex(idx) if len(bn_raw) else np.nan

    gaps = pd.concat([(price["close"] - price["cc_close"]).abs() / price["close"],
                      (price["close"] - price["bn_close_usd"]).abs() / price["close"]], axis=1).max(axis=1)
    price["src_disagree"] = (gaps > q["src_disagree_threshold"]).fillna(False).astype(bool)
    return price


# ---------------------------------------------------------------- DefiLlama và thị trường
def _lagged_ffill(s: pd.Series, idx: pd.DatetimeIndex, lag: int, limit: int):
    """Đưa chuỗi DefiLlama vào lưới ngày, trễ `lag` ngày (chống look-ahead), ffill có giới hạn."""
    s = s.dropna()
    if lag:
        s = s.shift(lag, freq="D")
    direct = s.reindex(idx)
    full = s.reindex(s.index.union(idx)).ffill(limit=limit).reindex(idx)
    return full, (direct.isna() & full.notna())


def _market_full(df: pd.DataFrame | None, window: int):
    """Log-return và độ biến động trượt của BTC/ETH tính trên TOÀN BỘ chuỗi (không theo lưới từng coin),
    để cùng một ngày mọi coin nhận cùng giá trị và coin niêm yết muộn không mất dữ liệu đầu kỳ."""
    if df is None or not len(df):
        e = pd.Series(dtype=float)
        return e, e
    close = df["close"].astype(float)
    close = close.reindex(pd.date_range(close.index.min(), close.index.max(), freq="D", tz="UTC"))
    ret = np.log(close).diff()
    return ret, ret.rolling(window, min_periods=window).std()  # chỉ dùng quan sát <= t


def _level_change(s: pd.Series, grid_end: pd.Timestamp, lag: int, limit: int):
    """Mức (trễ `lag` ngày, ffill có giới hạn), cờ ffill và % thay đổi ngày, tính trên lưới đầy đủ từ ngày đầu của nguồn."""
    s = s.dropna()
    if s.empty:
        e = pd.Series(dtype=float)
        return e, pd.Series(dtype=bool), e
    grid = pd.date_range(s.index.min(), max(grid_end, s.index.min()), freq="D", tz="UTC")
    level, ffilled = _lagged_ffill(s, grid, lag, limit)
    change = (level / level.shift(1) - 1.0).replace([np.inf, -np.inf], np.nan)  # TVL = 0 những năm đầu => chia 0
    return level, ffilled, change


def _rowmin(*cols: pd.Series) -> pd.Series:
    return pd.concat(cols, axis=1).min(axis=1, skipna=True)


def _rowmax(*cols: pd.Series) -> pd.Series:
    return pd.concat(cols, axis=1).max(axis=1, skipna=True)


def _hl_dev(high: pd.Series, low: pd.Series) -> pd.Series:
    return _rowmax((high - 1).abs(), (low - 1).abs()).where(high.notna() | low.notna())


# ---------------------------------------------------------------- panel
def build_panel(raw: dict, cfg: dict) -> pd.DataFrame:
    lag = int(cfg.get("llama_lag_days", 1))
    lim = int(cfg.get("llama_ffill_limit", 3))
    w = int(cfg["market"]["vol_window"])
    q = {**DEFAULT_Q, **(cfg.get("quality") or {})}
    samp = cfg.get("sample", {}) or {}
    usdt = usdt_usd_series(raw) if cfg.get("binance_usd_conversion", True) else pd.Series(dtype=float)

    pbs = {}
    for coin, c in cfg["coins"].items():
        pb = _price_block(raw["price"].get(coin, {}), c.get("last_valid_date"), bool(c.get("binance_fallback")),
                          usdt, samp.get("start"), samp.get("end"), q)
        if pb is not None:
            pbs[coin] = pb
    if not pbs:
        raise ValueError("Không coin nào có dữ liệu giá trong khoảng mẫu")
    g_end = max(pb.index.max() for pb in pbs.values())
    btc_ret, btc_vol = _market_full(raw.get("btc"), w)
    eth_ret, eth_vol = _market_full(raw.get("eth"), w)
    tvl = raw.get("tvl")
    tvl_level = tvl_chg = None
    if tvl is not None and len(tvl) and "tvl" in tvl.columns:
        tvl_level, _, tvl_chg = _level_change(tvl["tvl"], g_end, lag, lim)

    frames = []
    for coin, pb in pbs.items():
        c = cfg["coins"][coin]
        idx = pb.index
        d = pd.DataFrame(index=idx)
        d["stablecoin"] = coin
        d["role"] = c["role"]
        d["coin_type"] = c["type"]
        d["price"] = pb["close"]
        d["open"], d["high"], d["low"] = pb["open"], pb["high"], pb["low"]
        src = pb["price_src"].fillna("")

        # --- độ lệch neo theo từng nguồn và bản đồng thuận
        d["peg_dev_signed"] = d["price"] - 1.0
        d["peg_deviation"] = d["peg_dev_signed"].abs()
        d["peg_deviation_cc"] = (pb["cc_close"] - 1.0).abs()
        d["peg_deviation_bn"] = (pb["bn_close_usd"] - 1.0).abs()
        d["peg_deviation_min"] = _rowmin(d["peg_deviation"], d["peg_deviation_cc"], d["peg_deviation_bn"]).where(d["price"].notna())
        d["n_price_sources"] = (pb[["ya_close", "cc_close", "bn_close_usd"]].notna().sum(axis=1)).astype(int)

        d["peg_deviation_hl"] = _hl_dev(d["high"], d["low"])
        d["peg_deviation_hl_cc"] = _hl_dev(pb["cc_high"], pb["cc_low"])
        d["peg_deviation_hl_bn"] = _hl_dev(pb["bn_high_usd"], pb["bn_low_usd"])
        d["peg_deviation_hl_min"] = _rowmin(d["peg_deviation_hl"], d["peg_deviation_hl_cc"],
                                            d["peg_deviation_hl_bn"]).where(d["price"].notna())
        body = _rowmax((d["open"] - 1).abs(), (d["price"] - 1).abs())
        indep = _rowmax(d["peg_deviation_hl_cc"].where(src != "cryptocompare"),
                        d["peg_deviation_hl_bn"].where(~src.str.startswith("binance")))
        # Râu nến nghi lỗi: lệch trong ngày lớn nhưng thân nến sát neo, VÀ có bằng chứng lỗi:
        #   (a) nguồn độc lập có dữ liệu nhưng không xác nhận (lệch của nó < một nửa), hoặc
        #   (b) râu cực đoan (> hl_extreme_threshold) mà thân nến vẫn sát neo.
        # Không có nguồn độc lập và râu vừa phải (vd. USDT 12/05/2022 low 0,9485) => GIỮ NGUYÊN, không coi là lỗi.
        spike = (d["peg_deviation_hl"] > q["hl_spike_threshold"]) & (body < q["hl_body_threshold"])
        refuted = indep.notna() & (indep < 0.5 * d["peg_deviation_hl"])
        extreme = d["peg_deviation_hl"] > q["hl_extreme_threshold"]
        d["hl_suspect"] = (spike & (refuted | extreme)).fillna(False).astype(bool)
        d["peg_deviation_hl_clean"] = d["peg_deviation_hl_min"].where(~d["hl_suspect"], body)

        # --- thanh khoản (proxy)
        d["volume"] = pb["volume"]
        d["range_hl"] = (d["high"] - d["low"]) / d["price"]

        sup = raw["supply"].get(coin)
        if sup is not None and len(sup) and "supply" in sup.columns:
            s_lvl, s_ff, s_chg = _level_change(sup["supply"], idx.max(), lag, lim)
            d["supply"] = s_lvl.reindex(idx)
            d["supply_ffilled"] = s_ff.reindex(idx).fillna(False).astype(bool)
            d["supply_change"] = s_chg.reindex(idx)
        else:
            d["supply"], d["supply_ffilled"], d["supply_change"] = np.nan, False, np.nan
        d["turnover"] = (d["volume"] / d["supply"]).replace([np.inf, -np.inf], np.nan)
        d["xmkt_gap"] = ((d["price"] - pb["bn_close_usd"]).abs() / d["price"]).where(src.isin(["yahoo", "cryptocompare"]))

        # --- proxy on-chain từ DefiLlama: supply trên Ethereum (KHÔNG phải dữ liệu on-chain tải trực tiếp)
        d["supply_eth"], d["supply_eth_change"] = np.nan, np.nan
        if sup is not None and "supply_eth" in sup.columns and sup["supply_eth"].notna().any():
            e_lvl, _, e_chg = _level_change(sup["supply_eth"], idx.max(), lag, lim)
            d["supply_eth"] = e_lvl.reindex(idx)
            d["supply_eth_change"] = e_chg.reindex(idx)
        d["supply_eth_share"] = (d["supply_eth"] / d["supply"]).replace([np.inf, -np.inf], np.nan)

        d["tvl"] = tvl_level.reindex(idx) if tvl_level is not None else np.nan
        d["tvl_change"] = tvl_chg.reindex(idx) if tvl_chg is not None else np.nan
        d["btc_ret"], d["btc_vol"] = btc_ret.reindex(idx), btc_vol.reindex(idx)
        d["eth_ret"], d["eth_vol"] = eth_ret.reindex(idx), eth_vol.reindex(idx)
        d["usdt_usd"] = usdt.reindex(idx) if len(usdt) else np.nan

        d["price_src"] = pb["price_src"]
        for col in ("hl_fixed", "is_missing_price", "src_disagree", "cc_close", "bn_close",
                    "bn_close_usd", "bn_high_usd", "bn_low_usd"):
            d[col] = pb[col]
        frames.append(d.reset_index())

    panel = pd.concat(frames, ignore_index=True)
    cols = [x["column"] for x in DICTIONARY if x["column"] in panel.columns]
    panel = panel[cols].sort_values(["stablecoin", "timestamp"]).reset_index(drop=True)
    for col in ("stablecoin", "role", "coin_type", "price_src"):
        panel[col] = panel[col].astype("string")
    panel["timestamp"] = pd.to_datetime(panel["timestamp"], utc=True).astype("datetime64[ns, UTC]")
    return panel


# ---------------------------------------------------------------- CLI
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config" / "config.yaml"))
    ap.add_argument("--refresh", action="store_true", help="tải lại, bỏ qua cache data/raw")
    ap.add_argument("--offline", action="store_true", help="chỉ dùng cache data/raw, không gọi mạng")
    ap.add_argument("--version", default="v1", help="nhãn phiên bản ghi vào tên file lưu kèm (v0/v1)")
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))

    raw, source_log = fetch_all(cfg, ROOT / "data" / "raw", refresh=args.refresh, offline=args.offline)
    panel = build_panel(raw, cfg)

    out_tab = ROOT / "outputs" / "tables"
    out_tab.mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "processed").mkdir(parents=True, exist_ok=True)
    panel.to_parquet(ROOT / "data" / "processed" / "panel.parquet", index=False)
    panel.to_parquet(ROOT / "data" / "processed" / f"panel_{args.version}.parquet", index=False)

    source_log.to_csv(out_tab / "source_log_raw.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(DICTIONARY).to_csv(out_tab / "data_dictionary.csv", index=False, encoding="utf-8-sig")
    report = qcmod.run_qc(panel, raw, cfg, source_log)
    report.to_csv(out_tab / "qc_report.csv", index=False, encoding="utf-8-sig")
    cov = qcmod.coverage(panel)
    cov.to_csv(out_tab / "coverage_by_coin.csv", index=False, encoding="utf-8-sig")
    ev = qcmod.event_count_preview(panel)
    ev.to_csv(out_tab / "event_count_preview.csv", index=False, encoding="utf-8-sig")
    for name, tab in qcmod.review_tables(panel).items():
        tab.to_csv(out_tab / f"{name}.csv", index=False, encoding="utf-8-sig")
    appmod.write_all(ROOT / "outputs", panel, source_log, report, cov, ev, cfg, args.version)

    print(source_log[["source", "key", "status", "rows", "first_date", "last_date"]].to_string(index=False))
    print("\n", report.to_string(index=False))
    print(f"\npanel: {panel.shape[0]} hàng x {panel.shape[1]} cột, {panel['stablecoin'].nunique()} coin "
          f"-> data/processed/panel.parquet (+ panel_{args.version}.parquet)")


if __name__ == "__main__":
    main()
