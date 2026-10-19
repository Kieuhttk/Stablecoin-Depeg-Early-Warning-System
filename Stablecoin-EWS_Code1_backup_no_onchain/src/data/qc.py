"""Kiểm tra chất lượng panel (bản backup không on-chain). Trả về bảng (check, status, detail) cho Phụ lục B/E."""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

ONCHAIN_COLS = ("dex_imbalance", "dex_pool_size", "mint_eth", "burn_eth", "net_issuance_eth", "onchain_available")


def coverage(panel: pd.DataFrame) -> pd.DataFrame:
    g = panel.groupby("stablecoin")
    return g.agg(role=("role", "first"), coin_type=("coin_type", "first"),
                 first_date=("timestamp", "min"), last_date=("timestamp", "max"), n_rows=("timestamp", "size"),
                 n_missing_price=("is_missing_price", "sum"), n_src_disagree=("src_disagree", "sum"),
                 n_hl_fixed=("hl_fixed", "sum"), n_hl_suspect=("hl_suspect", "sum"),
                 n_days_2plus_sources=("n_price_sources", lambda s: int((s >= 2).sum())),
                 n_supply_nan=("supply", lambda s: int(s.isna().sum())),
                 max_peg_dev=("peg_deviation", "max"), max_peg_dev_min=("peg_deviation_min", "max"),
                 max_peg_dev_hl=("peg_deviation_hl", "max"), max_peg_dev_hl_clean=("peg_deviation_hl_clean", "max"),
                 ).reset_index()


def event_count_preview(panel: pd.DataFrame, thresholds=(0.005, 0.01, 0.02)) -> pd.DataFrame:
    """CHỈ ĐỂ THAM KHẢO cho Code 2 (đếm ngày vượt ngưỡng, chưa phải nhãn chính thức, chưa áp m ngày liên tiếp)."""
    rows = []
    for coin, g in panel.groupby("stablecoin"):
        for tau in thresholds:
            for col in ("peg_deviation", "peg_deviation_min", "peg_deviation_hl_clean"):
                x = g[col] > tau
                onsets = int((x & ~x.shift(1, fill_value=False)).sum())
                rows.append({"stablecoin": coin, "role": g["role"].iloc[0], "threshold": tau, "measure": col,
                             "n_days_above": int(x.sum()), "n_onsets": onsets})
    return pd.DataFrame(rows)


def review_tables(panel: pd.DataFrame) -> dict:
    """Ba bảng để rà tay: ngày lệch nguồn, ngày giá cách xa 1 USD, ngày râu nến nghi lỗi."""
    d = panel[panel["src_disagree"]].copy()
    d["gap_vs_cc"] = (d["price"] - d["cc_close"]).abs() / d["price"]
    d["gap_vs_bn_usd"] = (d["price"] - d["bn_close_usd"]).abs() / d["price"]
    d["gap_max"] = d[["gap_vs_cc", "gap_vs_bn_usd"]].max(axis=1)
    d = d.sort_values("gap_max", ascending=False)[
        ["stablecoin", "timestamp", "price", "cc_close", "bn_close_usd", "gap_vs_cc", "gap_vs_bn_usd", "volume", "price_src"]]
    pn = panel[~panel["is_missing_price"]]
    far = pn[(pn["price"] < 0.5) | (pn["price"] > 1.5)][
        ["stablecoin", "timestamp", "price", "high", "low", "peg_deviation", "price_src", "bn_close", "usdt_usd"]]
    sus = panel[panel["hl_suspect"]][
        ["stablecoin", "timestamp", "open", "high", "low", "price", "peg_deviation_hl", "peg_deviation_hl_bn",
         "peg_deviation_hl_clean", "price_src"]]
    return {"review_src_disagree_days": d, "review_price_outliers": far, "review_hl_suspect_days": sus}


def alignment_report(raw: dict, lags=(-1, 0, 1), min_overlap: int = 60) -> pd.DataFrame:
    """So Yahoo với nguồn độc lập (CryptoCompare, Binance) ở các độ lệch ngày để phát hiện lệch quy ước nến
    (vd. một nguồn gắn nhãn ngày theo giờ địa phương). Lag tối ưu phải là 0. Binance so trên giá USDT
    nên chỉ dùng coin không phải USDT; sai số tuyệt đối vẫn so được vì USDT ~ 1."""
    rows = []
    for coin, p in raw["price"].items():
        ya = p.get("yahoo")
        if ya is None or not len(ya):
            continue
        for name in ("cc", "binance"):
            other = p.get(name)
            if other is None or not len(other):
                continue
            errs = {}
            for lag in lags:
                j = pd.concat([ya["close"], other["close"].shift(lag, freq="D")], axis=1, join="inner").dropna()
                if len(j) >= min_overlap:
                    errs[lag] = float((j.iloc[:, 0] - j.iloc[:, 1]).abs().mean())
            if errs:
                best = min(errs, key=errs.get)
                rows.append({"stablecoin": coin, "vs": name, "best_lag_days": best,
                             **{f"mae_lag{k}": v for k, v in errs.items()}})
    return pd.DataFrame(rows)


def run_qc(panel: pd.DataFrame, raw: dict | None, cfg: dict, source_log: pd.DataFrame | None = None) -> pd.DataFrame:
    res = []

    def add(name, ok, detail=""):
        res.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    def info(name, detail, status="INFO"):
        res.append({"check": name, "status": status, "detail": detail})

    ts = panel["timestamp"]
    add("khóa (stablecoin, timestamp) duy nhất", not panel.duplicated(["stablecoin", "timestamp"]).any())
    add("timestamp có múi giờ UTC", str(ts.dt.tz) == "UTC", str(ts.dt.tz))
    add("timestamp đúng 00:00 UTC", bool((ts == ts.dt.normalize()).all()))
    today = pd.Timestamp(dt.datetime.now(dt.timezone.utc).date(), tz="UTC")
    add("không có ngày chưa đóng nến (>= hôm nay UTC)", bool((ts < today).all()), f"max={ts.max()}")
    if source_log is not None and "off_midnight" in source_log.columns:
        off = pd.to_numeric(source_log["off_midnight"], errors="coerce").fillna(0)
        bad = source_log.loc[off > 0, "key"].tolist()
        add("dữ liệu gốc mọi nguồn đều gắn mốc 00:00 UTC (off_midnight = 0)", not bad, ", ".join(bad))

    contiguous = True
    for _, g in panel.groupby("stablecoin"):
        d = g["timestamp"].sort_values().diff().dropna()
        contiguous &= bool((d == pd.Timedelta(days=1)).all())
    add("lưới ngày liên tục trong từng coin (cần cho shift(-h) của nhãn)", contiguous)
    present = [c for c in ONCHAIN_COLS if c in panel.columns]
    add("panel không chứa cột on-chain (bản backup)", not present, ", ".join(present))

    pn = panel.loc[~panel["is_missing_price"]]
    broken = pn[(pn["price"] <= 0) | (pn["price"] > 5)]
    add("giá dương và <= 5 USD (ngoài khoảng = lỗi dữ liệu)", broken.empty, f"{len(broken)} quan sát")
    far = pn[(pn["price"] < 0.5) | (pn["price"] > 1.5)]
    listing = "; ".join(f"{r.stablecoin} {r.timestamp.date()} {r.price:.4f} ({r.price_src})" for r in far.head(10).itertuples())
    info("giá ngoài [0.5, 1.5] (thường là depeg thật, cần xem tay và ghi vào bảng sự kiện)",
         f"{len(far)} quan sát: {listing}" if len(far) else "", "WARN" if len(far) else "PASS")
    add("high >= low", bool((panel["high"].dropna() >= panel["low"].dropna()).all()))
    add("peg_deviation >= 0", bool((panel["peg_deviation"].dropna() >= 0).all()))
    add("peg_deviation_min <= peg_deviation", bool((panel["peg_deviation_min"] <= panel["peg_deviation"] + 1e-12).dropna().all()))
    mk = ["btc_ret", "btc_vol", "eth_ret", "eth_vol", "tvl", "tvl_change", "usdt_usd"]
    mk = [c for c in mk if c in panel.columns]
    by_day = panel.groupby("timestamp")[mk]
    n_diff = int((by_day.nunique(dropna=True) > 1).any(axis=1).sum())
    n_mixed = int(by_day.agg(lambda s: bool(s.isna().any() and s.notna().any())).any(axis=1).sum())
    add("biến cấp thị trường (BTC/ETH, TVL, USDT-USD) giống hệt nhau giữa các coin trong cùng ngày", n_diff == 0 and n_mixed == 0,
        f"{n_diff} ngày khác giá trị, {n_mixed} ngày NaN lẫn không NaN")
    add("supply không âm", bool((panel["supply"].dropna() >= 0).all()))

    n_cmp = int((panel["n_price_sources"] >= 2).sum())
    n_dis = int(panel["src_disagree"].sum())
    by = panel[panel["src_disagree"]].groupby("stablecoin").size().to_dict()
    info("giá đóng cửa lệch > 0,5% so với nguồn độc lập (CryptoCompare/Binance quy USD)",
         f"{n_dis}/{n_cmp} ngày có >= 2 nguồn; theo coin: {by}; xem review_src_disagree_days.csv",
         "INFO" if n_cmp else "WARN")
    share = panel.groupby("stablecoin")["n_price_sources"].apply(lambda s: f"{(s >= 2).mean():.0%}").to_dict()
    info("tỷ lệ ngày có ít nhất 2 nguồn giá độc lập, theo coin", str(share),
         "WARN" if any(v == "0%" for v in share.values()) else "INFO")
    info("số ngày râu nến nghi lỗi (hl_suspect), đã làm sạch trong peg_deviation_hl_clean",
         str(panel[panel["hl_suspect"]].groupby("stablecoin").size().to_dict()))

    stale = []
    for coin, g in panel.groupby("stablecoin"):
        pr = g["price"]
        run = int(pr.groupby((pr != pr.shift()).cumsum()).size().max()) if pr.notna().any() else 0
        zv = float((g["volume"] == 0).mean())
        if run >= 20 or zv > 0.2:
            stale.append(f"{coin}: giá đứng yên tối đa {run} ngày, {zv:.0%} ngày volume=0")
    info("không nghi dữ liệu cũ/đứng giá (giá giống nhau >= 20 ngày hoặc volume=0 > 20%)", "; ".join(stale),
         "WARN" if stale else "PASS")
    info("cơ cấu nguồn giá (price_src)", str(panel["price_src"].value_counts().to_dict()))
    info("dữ liệu on-chain", "KHÔNG dùng (bản backup): thay bằng proxy DefiLlama (supply_change, supply_eth_change, "
         "supply_eth_share, tvl_change) và chênh lệch liên thị trường xmkt_gap")

    if raw is not None:
        al = alignment_report(raw)
        if len(al):
            bad = al[al["best_lag_days"] != 0]
            add("quy ước nến Yahoo khớp nguồn độc lập (lag tối ưu = 0 ngày)", bad.empty,
                "; ".join(f"{r.stablecoin} vs {r.vs}: lag {r.best_lag_days}" for r in bad.itertuples())
                or f"tất cả lag 0 ({len(al)} cặp so sánh)")
    return pd.DataFrame(res)
