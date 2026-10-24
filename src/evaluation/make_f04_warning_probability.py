"""F04 - Xác suất cảnh báo theo thời gian (Mục 5.7).

Mặc định chỉ vẽ giai đoạn test (proba_type = final). Dùng --include-dev để vẽ thêm giai đoạn dev (oof):
hai đoạn có hiệu chuẩn Platt riêng nên được tách bằng đường dọc và nét nhạt hơn, không nối liền.

Chạy:  python -m src.evaluation.make_f04_warning_probability [--include-dev]
"""
from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.evaluation import monitor_core as mc


def _spans(mask: pd.Series, dates: pd.Series):
    """Các đoạn liên tiếp mask=True -> [(start, end)]."""
    out, start = [], None
    for d, v in zip(dates, mask):
        if v and start is None:
            start = d
        if not v and start is not None:
            out.append((start, prev))
            start = None
        prev = d
    if start is not None:
        out.append((start, prev))
    return out


def main(include_dev: bool = False) -> None:
    cfg = mc.load_config()
    paths = mc.resolve_inputs(cfg)
    panel = mc.load_panel(paths["panel"])
    pred, _ = mc.load_predictions(paths["predictions"])
    run = mc.select_run(pred, cfg["model"]["final_model"], cfg["model"]["horizon_days"])
    pal = cfg["figures"]["palette"]
    coins = cfg["coins"]
    m, tau = cfg["depeg"]["m_main"], cfg["depeg"]["tau_main"]
    fig, axes = plt.subplots(len(coins), 1, figsize=(11, 2.6 * len(coins)), sharex=True, squeeze=False)
    for ax, coin in zip(axes[:, 0], coins):
        r = run[run.stablecoin == coin].sort_values("timestamp")
        if not include_dev:
            r = r[r.proba_type == "final"]
        col = pal.get(coin, pal["neutral"])
        for ptype, g in r.groupby("proba_type"):
            ax.plot(g["timestamp"], g["proba"], color=col, lw=1.3 if ptype == "final" else 0.9,
                    alpha=1 if ptype == "final" else 0.45, label=f"xác suất ({ptype})")
        al = r[r.alarm == 1]
        ax.scatter(al["timestamp"], al["proba"], color=pal["Red"], s=10, zorder=3, label="alarm (Red)")
        # trạng thái depeg thực tế và onset (tính từ panel, ngưỡng chính)
        p = panel[panel.stablecoin == coin].sort_values("timestamp")
        if len(r):
            p = p[p.timestamp.between(r.timestamp.min(), r.timestamp.max())]
        st = mc.depeg_state(p["dev"].reset_index(drop=True), tau, m)
        for a, b in _spans(st, p["timestamp"].reset_index(drop=True)):
            ax.axvspan(a - pd.Timedelta(hours=12), b + pd.Timedelta(hours=12), color="grey", alpha=0.25, lw=0)
        on = mc.find_onsets(p.assign(stablecoin=coin), tau, m)
        for d in on["onset"]:
            ax.axvline(d, color="black", lw=0.8, ls=":")
        if include_dev and (r.proba_type == "final").any() and (r.proba_type == "oof").any():
            ax.axvline(r.loc[r.proba_type == "final", "timestamp"].min(), color=pal["neutral"], lw=1)
        ax.set_ylabel(f"{coin}\nxác suất depeg", fontsize=9)
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7, frameon=False, loc="upper left", ncol=3)
    axes[-1][0].xaxis.set_major_locator(mdates.YearLocator())
    axes[-1][0].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[-1][0].set_xlabel("Thời gian (UTC)")
    fig.suptitle(f"F04. Xác suất cảnh báo depeg {cfg['model']['horizon_days']} ngày theo thời gian"
                 "\n(vùng xám: đang depeg; đường chấm: onset; chấm đỏ: alarm)", fontsize=10)
    fig.tight_layout()
    out = mc.ROOT / cfg["paths"]["figures"]
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "F04_warning_probability.png", dpi=cfg["figures"]["dpi"])
    print("Đã lưu", out / "F04_warning_probability.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-dev", action="store_true")
    a = ap.parse_args()
    main(a.include_dev)
