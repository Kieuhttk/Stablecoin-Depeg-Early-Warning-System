"""F03 - Event-study quanh các depeg lớn (Mục 5.6).

Dashboard dùng biểu đồ Plotly tương tác qua :func:`build_event_figure`.
Chạy module này nếu cần xuất thêm bản tĩnh cho báo cáo.
Ra:    outputs/figures/F03_event_study.png  (+ outputs/tables/F03_event_list.csv)
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.evaluation import monitor_core as mc


def first_alarm_lead(w: pd.DataFrame) -> int | None:
    """Lead time trong cửa sổ: số ngày từ lần cảnh báo (alarm=1) đầu tiên trước onset đến onset."""
    pre = w[(w["tau_day"] < 0) & (w["alarm"] == 1)]
    return int(-pre["tau_day"].min()) if len(pre) else None


def build_event_figure(panel: pd.DataFrame, run: pd.DataFrame, event: pd.Series, cfg: dict) -> go.Figure:
    """Build an interactive, single-event view with shared event-time zoom."""
    coin = str(event["stablecoin"])
    onset = pd.Timestamp(event["onset"])
    window = mc.event_window(panel, run, coin, onset, cfg)
    x = window["tau_day"]
    color = cfg["theme"]["coin"].get(coin, cfg["theme"]["ink"])
    rows = ["Độ lệch neo |P−1| (%)"]
    if "supply_change" in window and window["supply_change"].notna().any():
        rows.append("Thay đổi cung (%)")
    has_market_vol = {"btc_vol", "eth_vol"}.issubset(window.columns) and (
        window["btc_vol"].notna().any() or window["eth_vol"].notna().any()
    )
    if has_market_vol:
        rows.append("Biến động BTC / ETH")
    rows.append(f"Xác suất depeg {cfg['model']['horizon_days']} ngày")

    fig = make_subplots(rows=len(rows), cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        subplot_titles=rows)
    row = 1
    fig.add_trace(go.Scatter(x=x, y=window["dev"] * 100, mode="lines+markers", name="Độ lệch neo",
                             line=dict(color=color, width=2), marker=dict(size=6),
                             customdata=window.index.strftime("%Y-%m-%d"),
                             hovertemplate="Ngày %{customdata}<br>τ = %{x} ngày<br>Độ lệch %{y:.3f}%<extra></extra>"), row=row, col=1)
    fig.add_hline(y=cfg["depeg"]["tau_main"] * 100, line_dash="dash",
                  line_color=cfg["theme"]["level_line"]["Red"], annotation_text="Ngưỡng depeg", row=row, col=1)
    row += 1
    if "Thay đổi cung (%)" in rows:
        fig.add_trace(go.Bar(x=x, y=window["supply_change"] * 100, name="Thay đổi cung",
                             marker_color=color, opacity=0.75,
                             customdata=window.index.strftime("%Y-%m-%d"),
                             hovertemplate="Ngày %{customdata}<br>τ = %{x} ngày<br>Thay đổi cung %{y:.3f}%<extra></extra>"), row=row, col=1)
        row += 1
    if has_market_vol:
        fig.add_trace(go.Scatter(x=x, y=window["btc_vol"], mode="lines+markers", name="BTC vol",
                                 line=dict(color="#27364B", width=1.8), marker=dict(size=5)), row=row, col=1)
        fig.add_trace(go.Scatter(x=x, y=window["eth_vol"], mode="lines+markers", name="ETH vol",
                                 line=dict(color="#8B5CF6", width=1.8, dash="dash"), marker=dict(size=5)), row=row, col=1)
        row += 1
    fig.add_trace(go.Scatter(x=x, y=window["proba"] * 100, mode="lines+markers", name="Xác suất",
                             line=dict(color=color, width=2), marker=dict(size=5),
                             customdata=window.index.strftime("%Y-%m-%d"),
                             hovertemplate="Ngày %{customdata}<br>τ = %{x} ngày<br>Xác suất %{y:.3f}%<extra></extra>"), row=row, col=1)
    alarms = window[window["alarm"] == 1]
    if not alarms.empty:
        fig.add_trace(go.Scatter(x=alarms["tau_day"], y=alarms["proba"] * 100, mode="markers",
                                 name="Cảnh báo Red", marker=dict(color=cfg["theme"]["level_line"]["Red"], size=10,
                                 line=dict(color="white", width=1.5))), row=row, col=1)

    for r in range(1, len(rows) + 1):
        fig.add_vline(x=0, line_color="#263445", line_width=1.4, row=r, col=1)
    lead = first_alarm_lead(window)
    lead_label = f"Lead time: {lead} ngày" if lead is not None else "Không có cảnh báo trước onset"
    fig.update_layout(
        title=f"{coin} · onset {onset:%d/%m/%Y} · độ lệch đỉnh {float(event['peak_dev']) * 100:.2f}% · {lead_label}",
        template="plotly_white", height=230 * len(rows) + 110,
        margin=dict(l=20, r=20, t=85, b=25), hovermode="x unified",
        legend=dict(orientation="h", y=1.02, x=0),
    )
    fig.update_xaxes(title_text="Ngày so với onset (τ = 0 tại onset)", row=len(rows), col=1,
                     tickmode="linear", dtick=2, gridcolor="#EDF0F8")
    for r in range(1, len(rows) + 1):
        fig.update_yaxes(gridcolor="#EDF0F8", row=r, col=1)
    return fig


def main() -> None:
    cfg = mc.load_config()
    paths = mc.resolve_inputs(cfg)
    panel = mc.load_panel(paths["panel"])
    pred, _ = mc.load_predictions(paths["predictions"])
    run = mc.select_run(pred, cfg["model"]["final_model"], cfg["model"]["horizon_days"])
    ev = mc.select_events(panel, cfg)
    if ev.empty:
        raise SystemExit("Không tìm thấy sự kiện nào; kiểm tra ngưỡng/giai đoạn trong config/dashboard.yaml")
    if len(ev) < 3:
        print(f"CẢNH BÁO: chỉ có {len(ev)} sự kiện (đề yêu cầu 3-4). Cân nhắc đổi tau hoặc include_dev_events.")

    pal = cfg["figures"]["palette"]
    has_dex = "dex_imbalance" in panel.columns
    has_liquidity = "liquidity" in panel.columns
    has_supply = "supply_change" in panel.columns
    has_market_vol = {"btc_vol", "eth_vol"}.issubset(panel.columns)
    rows = ["Độ lệch neo |P−1| (%)"]
    if has_liquidity:
        rows.append("Thanh khoản (chỉ số, nền = 1)")
    if has_dex:
        rows.append("Mất cân bằng pool DEX")
    if has_supply:
        rows.append("Thay đổi cung (%)")
    if has_market_vol:
        rows.append("Biến động BTC / ETH")
    rows.append("Xác suất cảnh báo (h = {} ngày)".format(cfg["model"]["horizon_days"]))
    nr, nc = len(rows), len(ev)
    fig, axes = plt.subplots(nr, nc, figsize=(3.9 * nc, 2.2 * nr), sharex=True, squeeze=False)
    lead_log = []
    for j, (_, e) in enumerate(ev.iterrows()):
        w = mc.event_window(panel, run, e["stablecoin"], e["onset"], cfg)
        x = w["tau_day"]
        col = pal[e["stablecoin"]] if e["stablecoin"] in pal else pal["neutral"]
        i = 0
        ax = axes[i][j]
        ax.plot(x, w["dev"] * 100, color=col, lw=1.8, marker="o", ms=3)
        tau = cfg["depeg"]["tau_main"] * 100
        ax.axhline(tau, color=pal["Red"], ls="--", lw=0.9)
        ax.text(x.min(), tau, f" ngưỡng {tau:g}%", color=pal["Red"], fontsize=7, va="bottom")
        i += 1
        if has_liquidity:
            ax = axes[i][j]
            ax.plot(x, w["liquidity_idx"], color=pal["neutral"], lw=1.6)
            ax.axhline(1, color="grey", lw=0.6, ls=":")
            i += 1
        if has_dex:
            axes[i][j].plot(x, w["dex_imbalance"], color=pal["neutral"], lw=1.6)
            i += 1
        if has_supply:
            ax = axes[i][j]
            ax.bar(x, w["supply_change"] * 100, color=col, alpha=0.8, width=0.7)
            ax.axhline(0, color="grey", lw=0.6)
            i += 1
        if has_market_vol:
            ax = axes[i][j]
            ax.plot(x, w["btc_vol"], color="#1F2937", lw=1.4, label="BTC")
            ax.plot(x, w["eth_vol"], color="#7C3AED", lw=1.4, ls="--", label="ETH")
            if j == 0:
                ax.legend(fontsize=7, frameon=False, loc="upper left")
            i += 1
        ax = axes[i][j]
        ax.plot(x, w["proba"], color=col, lw=1.8)
        al = w[w["alarm"] == 1]
        ax.scatter(al["tau_day"], al["proba"], color=pal["Red"], s=22, zorder=3, label="alarm (Red)")
        lead = first_alarm_lead(w)
        msg = f"Lead time: {lead} ngày" if lead else "Không có cảnh báo trước onset"
        ax.text(0.03, 0.9, msg, transform=ax.transAxes, fontsize=8, va="top",
                color=pal["Red"] if not lead else pal["Green"], fontweight="bold")
        types = w["proba_type"].dropna().unique()
        if len(types):
            ax.text(0.97, 0.9, "/".join(types), transform=ax.transAxes, fontsize=7, ha="right", va="top",
                    color=pal["neutral"])
        if j == 0:
            ax.legend(fontsize=7, frameon=False, loc="center left")
        ax.set_xlabel("Ngày so với onset (τ)")
        lead_log.append({"stablecoin": e["stablecoin"], "onset": e["onset"].date(), "peak_dev_pct": e["peak_dev"] * 100,
                         "lead_days_in_window": lead, "nhom": e.get("tag", "")})
        axes[0][j].set_title(f"{e['stablecoin']} – {e['onset']:%d/%m/%Y}\nđộ lệch tối đa {e['peak_dev']*100:.1f}% "
                             f"({e.get('tag','')})", fontsize=9)
        for r in range(nr):
            axes[r][j].axvline(0, color="black", lw=0.9)
            axes[r][j].grid(alpha=0.25)
            axes[r][j].tick_params(labelsize=7)
            if j == 0:
                axes[r][j].set_ylabel(rows[r], fontsize=8)
    fig.suptitle("F03. Event-study quanh các sự kiện depeg lớn (đường đen: onset, τ = 0)", fontsize=11, y=0.995)
    fig.tight_layout()
    out = mc.ROOT / cfg["paths"]["figures"]
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "F03_event_study.png", dpi=cfg["figures"]["dpi"])
    tbl = mc.ROOT / "outputs" / "tables"
    tbl.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(lead_log).to_csv(tbl / "F03_event_list.csv", index=False)
    print("Đã lưu", out / "F03_event_study.png")


if __name__ == "__main__":
    main()
