"""Lõi dùng chung cho dashboard Stablecoin Risk Monitor, F03 và F04 (Code 4).

Nguyên tắc:
- Chỉ đọc panel.parquet (Code 1) và predictions.parquet (Code 3); không sửa tên cột.
- Phân biệt proba_type: 'oof' (giai đoạn dev 2021-2022) và 'final' (test).
  Hai loại xác suất đã hiệu chuẩn Platt riêng nên KHÔNG so sánh/gộp như xác suất tuyệt đối.
- Driver trống -> hiển thị EMPTY_DRIVER_MSG, không gây lỗi giao diện.
- Mức cảnh báo: Red = alarm; Amber = score_raw trong top 10% giai đoạn dev; còn lại Green.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
EMPTY_DRIVER_MSG = "Không có driver rủi ro rõ ràng"
DRIVER_COLS = ["top1_driver", "top2_driver", "top3_driver"]
LEVELS = ["Green", "Amber", "Red"]
_NULL_STR = {"", "nan", "none", "null", "<na>"}


# ----------------------------------------------------------------- cấu hình / đường dẫn
def load_config(path=None) -> dict:
    path = pathlib.Path(path) if path else ROOT / "config" / "dashboard.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_inputs(cfg: dict) -> dict:
    """Trả về đường dẫn panel/predictions thật; không có nhánh dữ liệu demo.

    Nếu panel gốc chưa có nhưng predictions thật và features.parquet đã có, dùng
    features làm panel đọc-only để dashboard vẫn hiển thị kết quả thật.
    """
    real = {k: ROOT / cfg["paths"][k] for k in ("panel", "predictions")}
    if real["predictions"].exists() and real["panel"].exists():
        return real
    features = ROOT / "data" / "processed" / "features.parquet"
    if real["predictions"].exists() and features.exists():
        return {"panel": features, "predictions": real["predictions"]}
    missing = [str(path.relative_to(ROOT)) for path in (real["panel"], real["predictions"]) if not path.exists()]
    raise FileNotFoundError(
        "Thiếu dữ liệu thật cần cho dashboard: " + ", ".join(missing)
    )


# ----------------------------------------------------------------- đọc dữ liệu
def _to_day(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, utc=True).dt.tz_convert(None).dt.normalize()


def load_panel(path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["timestamp"] = _to_day(df["timestamp"])
    df["stablecoin"] = df["stablecoin"].astype(str).str.strip().str.upper()
    # Dev = |P - 1| theo quy ước (giá đóng cửa); nếu thiếu price thì dùng peg_deviation của Code 1
    if "price" in df:
        df["dev"] = (df["price"] - 1).abs()
    else:
        df["dev"] = df["peg_deviation"].abs()
    return df.sort_values(["stablecoin", "timestamp"]).reset_index(drop=True)


def clean_drivers(df: pd.DataFrame) -> pd.DataFrame:
    for c in DRIVER_COLS:
        if c not in df:
            df[c] = pd.NA
        s = df[c].astype("string").str.strip()
        df[c] = s.mask(s.str.lower().isin(_NULL_STR))
    return df


def drivers_of(row) -> list[str]:
    out = [row[c] for c in DRIVER_COLS if c in row and pd.notna(row[c])]
    return out if out else [EMPTY_DRIVER_MSG]


def load_predictions(path) -> tuple[pd.DataFrame, dict]:
    """Chuẩn hóa predictions.parquet. Trả về (df, flags) - flags ghi lại cột nào phải suy ra."""
    df = pd.read_parquet(path)
    flags = {}
    df["timestamp"] = _to_day(df["timestamp"])
    df["stablecoin"] = df["stablecoin"].astype(str).str.strip().str.upper()
    if "model" not in df:
        df["model"] = "model"
    if "h" in df:
        if pd.api.types.is_numeric_dtype(df["h"]):
            df["h"] = pd.to_numeric(df["h"], errors="coerce").astype(float)
        else:
            df["h"] = df["h"].astype("string").str.extract(r"(\d+)")[0].astype(float)
    else:
        df["h"] = 1.0
    if "proba_type" not in df:  # hợp đồng cũ chỉ có split
        flags["proba_type_derived"] = True
        split = df["split"].astype(str).str.lower() if "split" in df else pd.Series("test", index=df.index)
        df["proba_type"] = np.where(split.eq("test"), "final", "oof")
    df["proba_type"] = df["proba_type"].astype(str).str.lower().str.strip()
    if "score_raw" not in df:
        flags["score_raw_missing"] = True
        df["score_raw"] = df["proba"]
    if "alarm" not in df:
        flags["alarm_missing"] = True
        df["alarm"] = 0
    df["alarm"] = pd.to_numeric(df["alarm"], errors="coerce").fillna(0).astype(int)
    df = clean_drivers(df)
    return df.sort_values(["stablecoin", "timestamp"]).reset_index(drop=True), flags


def select_run(pred: pd.DataFrame, model: str | None, h: float) -> pd.DataFrame:
    """Lọc một cặp (model, h). model=None -> model đầu tiên có dòng 'final'."""
    p = pred[pred["h"] == h]
    if model is None:
        fin = p.loc[p["proba_type"] == "final", "model"]
        model = fin.iloc[0] if len(fin) else p["model"].iloc[0]
    return p[p["model"] == model].copy()


# ----------------------------------------------------------------- điểm rủi ro & mức cảnh báo
def fit_risk_scale(run: pd.DataFrame, amber_q: float) -> dict:
    """Phân phối score_raw của giai đoạn dev (proba_type == 'oof') - gộp 3 coin.
    Ngưỡng Amber và thang điểm 0-100 chỉ học từ dev, không nhìn test."""
    dev = run.loc[run["proba_type"] == "oof", "score_raw"].dropna().to_numpy()
    fallback = False
    if len(dev) == 0:  # không có dòng oof: dùng dòng không phải final, rồi mới tới toàn bộ
        dev = run.loc[run["proba_type"] != "final", "score_raw"].dropna().to_numpy()
        fallback = True
    if len(dev) == 0:
        dev = run["score_raw"].dropna().to_numpy()
    dev = np.sort(dev)
    return {"sorted_dev": dev, "amber_thr": float(np.quantile(dev, amber_q)), "n_dev": len(dev), "fallback": fallback}


def risk_score(x: pd.Series, scale: dict) -> pd.Series:
    """Điểm 0-100 = phân vị (ECDF) của score_raw so với phân phối dev. Amber bắt đầu từ ~90."""
    arr = x.to_numpy(dtype=float)
    d = scale["sorted_dev"]
    out = 100.0 * np.searchsorted(d, arr, side="right") / len(d)
    return pd.Series(np.where(np.isnan(arr), np.nan, out), index=x.index)


def assign_alert(run: pd.DataFrame, scale: dict) -> pd.Series:
    """Red (alarm) ưu tiên hơn Amber; còn lại Green."""
    red = run["alarm"].eq(1)
    amber = run["score_raw"].ge(scale["amber_thr"])
    return pd.Series(np.where(red, "Red", np.where(amber, "Amber", "Green")), index=run.index)


def liquidity_state(panel: pd.DataFrame, cfg: dict) -> pd.Series:
    """Phân vị thanh khoản trong 90 ngày gần nhất (chỉ dùng quá khứ) -> nhãn tiếng Việt."""
    a = cfg["alert"]
    if "liquidity" not in panel:
        return pd.Series("Không có dữ liệu", index=panel.index)
    pct = panel.groupby("stablecoin")["liquidity"].transform(lambda s: s.rolling(90, min_periods=30).rank(pct=True))
    if not a.get("liquidity_higher_is_better", True):
        pct = 1 - pct
    lab = np.where(pct <= a["liquidity_low_pct"], "Suy giảm rõ",
                   np.where(pct <= a["liquidity_mid_pct"], "Thấp hơn bình thường", "Bình thường"))
    return pd.Series(np.where(pct.isna(), "Chưa đủ lịch sử", lab), index=panel.index)


def build_monitor_frame(panel: pd.DataFrame, run: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    scale = fit_risk_scale(run, cfg["alert"]["amber_quantile"])
    run = run.copy()
    run["risk_score"] = risk_score(run["score_raw"], scale)
    run["alert"] = assign_alert(run, scale)
    pn = panel.copy()
    pn["liquidity_state"] = liquidity_state(pn, cfg)
    keep = [c for c in ["timestamp", "stablecoin", "price", "dev", "liquidity", "volume", "supply_change",
                        "liquidity_state"] if c in pn]
    out = run.merge(pn[keep], on=["timestamp", "stablecoin"], how="left")
    return out, scale


# ----------------------------------------------------------------- sự kiện depeg
def depeg_state(dev: pd.Series, tau: float, m: int) -> pd.Series:
    """1 nếu dev > tau trong ít nhất m quan sát liên tiếp tính đến t (khớp Mục 3 quy ước chung)."""
    over = (dev > tau).astype(int)
    return over.rolling(m, min_periods=m).sum().eq(m).fillna(False)


def find_onsets(panel: pd.DataFrame, tau: float, m: int) -> pd.DataFrame:
    rows = []
    for coin, g in panel.groupby("stablecoin"):
        g = g.sort_values("timestamp").reset_index(drop=True)
        st = depeg_state(g["dev"], tau, m)
        onset = st & ~st.shift(1, fill_value=False)
        for i in g.index[onset]:
            # onset là ngày đầu tiên của chuỗi m quan sát -> lùi m-1 ngày
            j = max(i - (m - 1), 0)
            seg = g.loc[j: j + 5, "dev"]
            rows.append({"stablecoin": coin, "onset": g.loc[j, "timestamp"], "peak_dev": float(seg.max()), "tau": tau})
    return pd.DataFrame(rows, columns=["stablecoin", "onset", "peak_dev", "tau"])


def select_events(panel: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    es = cfg["event_study"]
    if es.get("manual_events"):
        rows = []
        for e in es["manual_events"]:
            d = pd.Timestamp(str(e["date"]))
            g = panel[(panel.stablecoin == e["coin"].upper()) & panel.timestamp.between(d, d + pd.Timedelta(days=5))]
            rows.append({"stablecoin": e["coin"].upper(), "onset": d, "peak_dev": float(g["dev"].max()),
                         "tau": np.nan, "tag": "thủ công"})
        return pd.DataFrame(rows)
    m = cfg["depeg"]["m_main"]
    lo = pd.Timestamp(str(es["test_start"]))
    pools = []
    for tau in (cfg["depeg"]["tau_main"], cfg["depeg"]["tau_fallback"]):
        on = find_onsets(panel, tau, m)
        if not es.get("include_dev_events", False):
            on = on[on.onset >= lo]
        pools.append(on)
    chosen: list[pd.Series] = []
    sep = pd.Timedelta(days=es["min_separation_days"])
    # ưu tiên sự kiện ở ngưỡng chính, sau đó mới nới sang ngưỡng phụ nếu chưa đủ n_events
    for pool in pools:
        for _, r in pool.sort_values("peak_dev", ascending=False).iterrows():
            if len(chosen) >= es["n_events"]:
                break
            if any(c["stablecoin"] == r["stablecoin"] and abs(c["onset"] - r["onset"]) < sep for c in chosen):
                continue
            chosen.append(r)
    out = pd.DataFrame(chosen).sort_values("onset").reset_index(drop=True) if chosen else pd.DataFrame(
        columns=["stablecoin", "onset", "peak_dev", "tau"])
    if len(out):
        out["tag"] = np.where(out["onset"] >= lo, "test", "dev (oof)")
    return out


def event_window(panel: pd.DataFrame, run: pd.DataFrame, coin: str, onset: pd.Timestamp, cfg: dict) -> pd.DataFrame:
    es = cfg["event_study"]
    idx = pd.date_range(onset - pd.Timedelta(days=es["window_before"]), onset + pd.Timedelta(days=es["window_after"]))
    p = panel[panel.stablecoin == coin].set_index("timestamp")
    w = p.reindex(idx)
    base = p.loc[onset + pd.Timedelta(days=es["baseline_start"]): onset + pd.Timedelta(days=es["baseline_end"])]
    if "liquidity" in p:
        med = base["liquidity"].median()
        w["liquidity_idx"] = w["liquidity"] / med if pd.notna(med) and med != 0 else np.nan
    r = run[run.stablecoin == coin].set_index("timestamp").reindex(idx)
    for c in ("proba", "score_raw", "alarm", "proba_type"):
        w[c] = r[c] if c in r else np.nan
    w["tau_day"] = (w.index - onset).days
    return w
