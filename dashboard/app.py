"""Stablecoin Depeg Early Warning System dashboard (Code 4), giao diện sáng navy - teal.

Chạy từ thư mục gốc repo:  streamlit run dashboard/app.py
"""
import html
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.evaluation import monitor_core as mc
from src.utils.live_market import fetch_live_prices

st.set_page_config(page_title="Stablecoin Depeg Early Warning System", page_icon="🛡️", layout="wide")
cfg = mc.load_config()
TH = cfg["theme"]
ALERT_VN = {"Green": "Bình thường", "Amber": "Cảnh báo sớm", "Red": "Cảnh báo nguy hiểm"}
ALERT_DOT = {"Green": "●", "Amber": "●", "Red": "●"}

st.markdown(f"""
<style>
#MainMenu, footer {{visibility: hidden;}}
.block-container {{padding-top: 1.35rem; padding-bottom: 2.5rem; max-width: 1320px;}}
html, body, [class*="css"] {{color: {TH['ink']};}}
.hero {{background: {TH['hero_bg']}; border-radius: 18px; padding: 22px 26px; margin-bottom: 14px;
        box-shadow: 0 10px 28px rgba(11,42,91,.22); border-bottom: 5px solid {TH['brand']};}}
.hero h1 {{margin: 0; font-size: 1.9rem; font-weight: 750; letter-spacing: -0.35px; color:#fff;}}
.hero h1 a {{color:inherit; text-decoration:none;}}
.hero h1 a:hover {{text-decoration:underline; text-underline-offset:4px;}}
.hero p {{margin: 5px 0 12px 0; color: {TH['hero_sub']}; font-size: 0.9rem;}}
.pill {{display:inline-block; background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.30); border-radius:999px;
        padding:3px 12px; margin-right:8px; font-size:0.8rem; color:#fff;}}
.card {{background:#fff; border:1px solid {TH['card_border']}; border-radius:18px; padding:18px 20px;
        box-shadow: 0 8px 24px rgba(11,42,91,.10); height:100%; overflow:hidden;}}
.card-top {{display:flex; justify-content:space-between; align-items:center; margin:-18px -20px 14px; padding:12px 20px;}}
.lv-Green .card-top {{background:{TH['level_band']['Green']}; color:{TH['level_on']['Green']};}}
.lv-Amber .card-top {{background:{TH['level_band']['Amber']}; color:{TH['level_on']['Amber']};}}
.lv-Red .card-top {{background:{TH['level_band']['Red']}; color:{TH['level_on']['Red']};}}
.card-top .badge {{background:rgba(255,255,255,.30) !important; color:inherit !important;}}
.coin {{font-size:1.3rem; font-weight:750; display:flex; align-items:center; gap:8px;}}
.coin-dot {{width:14px; height:14px; border-radius:50%; display:inline-block; border:2px solid rgba(255,255,255,.9);}}
.badge {{border-radius:999px; padding:4px 12px; font-size:0.78rem; font-weight:700; white-space:nowrap;}}
.score-row {{display:flex; align-items:baseline; gap:8px;}}
.score {{font-size:3.2rem; font-weight:800; line-height:1;}}
.score-unit {{color:{TH['muted']}; font-size:0.85rem;}}
.gauge {{position:relative; height:10px; border-radius:999px; margin:10px 0 16px 0;
         background: linear-gradient(90deg, #7ADBAE 0%, #FFD27A 60%, #FF9494 100%);}}
.gauge-dot {{position:absolute; top:-4px; width:18px; height:18px; border-radius:50%; background:#fff;
             border:3px solid {TH['ink']}; transform:translateX(-50%); box-shadow:0 2px 6px rgba(0,0,0,.15);}}
.grid {{display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:14px;}}
.stat {{background:#F2F5FC; border:1px solid #E0E7F7; border-radius:12px; padding:9px 12px;}}
.stat .lbl {{color:{TH['muted']}; font-size:0.72rem; text-transform:uppercase; letter-spacing:.4px;}}
.stat .val {{font-size:1.05rem; font-weight:700; margin-top:2px;}}
.drv-title {{color:{TH['muted']}; font-size:0.72rem; text-transform:uppercase; letter-spacing:.4px; margin-bottom:6px;}}
.chip {{display:inline-block; background:{TH['chip_bg']}; color:{TH['chip_fg']}; border-radius:8px;
        padding:3px 10px; margin:0 6px 6px 0; font-size:0.82rem; font-weight:600;}}
.note {{border-radius:9px; padding:7px 10px; margin:4px 0 8px; font-size:0.8rem; line-height:1.45;}}
.note-demo {{background:#FFE3E3; color:#8E2C2C; border:1px solid #F6C4C4;}}
.note-info {{background:#E6EEFF; color:#1E3A8A; border:1px solid #C9D8FF;}}
.note-warn {{background:#FFF5DB; color:#79520A; border:1px solid #F1DFAE;}}
.section {{font-size:1.2rem; font-weight:750; margin: 24px 0 10px 0; color:{TH['hero_bg']}; border-left:5px solid {TH['brand']}; padding-left:10px;}}
.stTabs [data-baseweb="tab"] {{border-radius:10px 10px 0 0; padding:8px 16px;}}
.stTabs [aria-selected="true"] {{color:{TH['brand_dark']}; border-bottom-color:{TH['brand']};}}
button[kind="primary"] {{background:{TH['brand']}; border-color:{TH['brand']};}}
button[kind="primary"]:hover {{background:{TH['brand_dark']}; border-color:{TH['brand_dark']};}}
div[data-testid="stMetric"] {{background:#fff; border:1px solid {TH['card_border']}; border-left:5px solid {TH['brand']}; border-radius:14px; padding:12px 14px;}}
@media (max-width: 800px) {{.hero {{padding:16px;}} .hero h1 {{font-size:1.5rem;}} .pill {{margin:3px 4px 3px 0;}}}}
</style>
""", unsafe_allow_html=True)


def note(kind: str, text: str):
    st.markdown(f"<div class='note note-{kind}'>{text}</div>", unsafe_allow_html=True)


@st.cache_data(show_spinner="Đang tải dữ liệu...")
def load_all():
    resolved = mc.resolve_inputs(cfg)
    # Tương thích với tiến trình Streamlit còn giữ module Code 4 cũ trong bộ nhớ,
    # nơi resolve_inputs trả về cặp (paths, is_demo).
    paths = resolved[0] if isinstance(resolved, tuple) else resolved
    panel = mc.load_panel(paths["panel"])
    pred, flags = mc.load_predictions(paths["predictions"])
    flags["panel_source"] = paths["panel"].relative_to(ROOT).as_posix()
    flags["features_panel_fallback"] = paths["panel"].name == "features.parquet"
    return panel, pred, flags


@st.cache_data(ttl=60, show_spinner="Đang lấy giá thị trường mới nhất...")
def load_live_market():
    return fetch_live_prices()


def style_fig(fig: go.Figure, ytitle: str, height: int = 360) -> go.Figure:
    fig.update_layout(
        template="plotly_white", height=height, margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis_title=ytitle,
        font=dict(color=TH["ink"]), hovermode="x unified",
        legend=dict(orientation="h", y=1.1, x=0),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#E3E9F7")
    return fig


def coin_card(cn: str, r, h: int) -> str:
    lv = r["alert"]
    fmt = lambda v, f: (f.format(v) if v is not None and pd.notna(v) else "—")
    drv = [d for d in mc.drivers_of(r) if d != mc.EMPTY_DRIVER_MSG]
    drv_html = "".join(f"<span class='chip'>{html.escape(str(d))}</span>" for d in drv)
    score = float(r["risk_score"]) if pd.notna(r.get("risk_score")) else 0.0
    proba = float(r["proba"]) * 100 if pd.notna(r.get("proba")) else None
    liquidity_value = r.get("liquidity")
    has_liquidity = liquidity_value is not None and pd.notna(liquidity_value)
    stats = [
        ("Giá tại ngày theo dõi", fmt(r.get("price"), "{:.4f}")),
        ("Độ lệch neo", fmt(r.get("dev") * 100 if pd.notna(r.get("dev")) else None, "{:.2f}%")),
        (f"Xác suất depeg {h * 24}h", fmt(proba, "{:.2f}%")),
    ]
    if has_liquidity:
        stats.append(("Thanh khoản", html.escape(str(r.get("liquidity_state", "—")))))
    stats_html = "".join(
        f"<div class='stat'><div class='lbl'>{label}</div><div class='val'>{value}</div></div>"
        for label, value in stats
    )
    drivers_html = f"<div class='drv-title'>Tín hiệu rủi ro chính</div>{drv_html}" if drv else ""
    return f"""
<div class='card lv-{lv}'>
  <div class='card-top'>
    <div class='coin'><span class='coin-dot' style='background:{TH['coin'][cn]}'></span>{cn}</div>
    <span class='badge' style='background:{TH['level_bg'][lv]};color:{TH['level_fg'][lv]}'>
      {ALERT_DOT[lv]} {lv.upper()} · {ALERT_VN[lv]}</span>
  </div>
  <div class='score-row'><span class='score' style='color:{TH['level_fg'][lv]}'>{score:.0f}</span>
    <span class='score-unit'>/ 100 điểm rủi ro</span></div>
  <div class='gauge'><div class='gauge-dot' style='left:{min(max(score, 1), 99):.1f}%'></div></div>
  <div class='grid'>{stats_html}</div>
  {drivers_html}
</div>"""


# ------------------------------------------------------------------ sidebar
st.sidebar.markdown("### ⚙️ Thiết lập")
if st.sidebar.button("Cập nhật giá ngay"):
    load_live_market.clear()
    st.rerun()
panel, pred, flags = load_all()

combos = pred.groupby(["model", "h"]).size().reset_index()[["model", "h"]]
models = sorted(combos["model"].unique())
default_model = cfg["model"]["final_model"] if cfg["model"]["final_model"] in models else None
default_model = default_model or mc.select_run(pred, None, cfg["model"]["horizon_days"])["model"].iloc[0]
model = st.sidebar.selectbox("Mô hình", models, index=models.index(default_model))
hs = sorted(combos.loc[combos["model"] == model, "h"].astype(int).unique())
h_def = cfg["model"]["horizon_days"]
h = st.sidebar.selectbox("Horizon h (ngày)", hs, index=hs.index(h_def) if h_def in hs else 0)

run = mc.select_run(pred, model, float(h))
frame, scale = mc.build_monitor_frame(panel, run, cfg)

dmin, dmax = frame["timestamp"].min().date(), frame["timestamp"].max().date()
sel_date = pd.Timestamp(st.sidebar.date_input("Ngày theo dõi", value=dmax, min_value=dmin, max_value=dmax))
coin = st.sidebar.selectbox("Stablecoin xem chi tiết", cfg["coins"])
win = st.sidebar.slider("Cửa sổ biểu đồ (ngày)", 30, 730, 180, step=30)

# ------------------------------------------------------------------ hero
st.markdown(f"""
<div class='hero'>
  <h1>🛡️ <a href="https://github.com/Kieuhttk/Stablecoin-Depeg-Early-Warning-System" target="_blank" rel="noopener noreferrer">Stablecoin Depeg Early Warning System</a></h1>
  <p>Hệ thống cảnh báo sớm rủi ro mất neo (depeg) của USDT, USDC, DAI · công cụ nghiên cứu, không phải khuyến nghị đầu tư.</p>
  <span class='pill'>Mô hình: <b>{html.escape(str(model))}</b></span>
  <span class='pill'>Horizon: <b>{h} ngày</b></span>
  <span class='pill'>Ngày theo dõi: <b>{sel_date:%d/%m/%Y}</b></span>
  <span class='pill'>Nguồn dữ liệu: <b>{'features + predictions' if flags.get('features_panel_fallback') else 'panel + predictions'}</b></span>
</div>""", unsafe_allow_html=True)

st.markdown("<div class='section'>Giá thị trường mới nhất · dữ liệu trực tiếp</div>", unsafe_allow_html=True)
try:
    live = load_live_market()
    updated_at = pd.to_datetime(live["updated_at"], utc=True).max()
    st.caption(f"Nguồn: Binance public spot · truy vấn lúc {updated_at:%d/%m/%Y %H:%M:%S} UTC · USDT được lấy mốc $1; USDC/DAI báo giá theo USDT. Giá này không phải dự báo của mô hình.")
    live_cols = st.columns(len(cfg["coins"]), gap="medium")
    live_by_coin = live.set_index("stablecoin")
    for live_col, live_coin in zip(live_cols, cfg["coins"]):
        with live_col:
            if live_coin in live_by_coin.index:
                live_row = live_by_coin.loc[live_coin]
                st.metric(f"{live_coin} · giá USD", f"${live_row['price']:.6f}", f"{live_row['dev'] * 100:.3f}% lệch khỏi $1")
            else:
                st.metric(f"{live_coin} · giá USD", "Không có dữ liệu")
    st.caption("Giá spot là dữ liệu của một sàn và có thể lệch so với giá USD tổng hợp; chỉ dùng để xem trạng thái thị trường, không đưa vào dự báo rủi ro đã huấn luyện.")
except Exception as exc:
    st.warning(f"Chưa lấy được giá trực tiếp: {exc}. Kiểm tra kết nối hoặc tải lại sau.")

if flags.get("features_panel_fallback"):
    st.caption("Đang ghép features.parquet với predictions.parquet; bộ features hiện chưa có giá và thanh khoản.")
st.info(f"Dự báo mô hình bên dưới là dữ liệu lịch sử, kết thúc ngày {pd.to_datetime(frame['timestamp']).max():%d/%m/%Y}; giá trực tiếp được trình bày riêng ở phía trên.")

runtime_notes = []
if flags.get("proba_type_derived"):
    runtime_notes.append("Thiếu proba_type; loại xác suất được suy ra từ split.")
if flags.get("score_raw_missing"):
    runtime_notes.append("Thiếu score_raw; dùng proba làm điểm thay thế.")
if flags.get("alarm_missing"):
    runtime_notes.append("Thiếu alarm; không thể xác định mức Red.")
if scale["fallback"]:
    runtime_notes.append("Không có OOF; ngưỡng Amber dùng các dòng ngoài test.")
if runtime_notes:
    note("warn", " · ".join(runtime_notes))

day = frame[frame["timestamp"] == sel_date]
if day.empty:
    st.caption("Ngày này không có dự báo; đang hiển thị ngày gần nhất có dữ liệu của từng coin.")
    day = frame[frame["timestamp"] <= sel_date].sort_values("timestamp").groupby("stablecoin").tail(1)
if (day["proba_type"] == "oof").any():
    note("info", "Giai đoạn dev (OOF): xác suất OOF và final được hiệu chuẩn riêng, không so sánh trực tiếp và không phải xác suất tuyệt đối.")

# ------------------------------------------------------------------ thẻ từng coin
cols = st.columns(len(cfg["coins"]), gap="medium")
for c_ui, cn in zip(cols, cfg["coins"]):
    r = day[day["stablecoin"] == cn]
    with c_ui:
        if r.empty:
            st.markdown(f"<div class='card'><div class='coin'>{cn}</div><p>Chưa có dự báo tại ngày đã chọn.</p></div>",
                        unsafe_allow_html=True)
        else:
            st.markdown(coin_card(cn, r.iloc[0], h), unsafe_allow_html=True)

# ------------------------------------------------------------------ chi tiết
st.markdown(f"<div class='section'>Chi tiết {coin}</div>", unsafe_allow_html=True)
f = frame[(frame["stablecoin"] == coin) & (frame["timestamp"] <= sel_date)].tail(win)
p = panel[(panel["stablecoin"] == coin) & (panel["timestamp"] <= sel_date)].tail(win)
price_tab = "📈 Giá & độ lệch neo" if "price" in panel.columns else "📈 Độ lệch neo"
t1, t2, t3, t4 = st.tabs([price_tab, "🚦 Điểm rủi ro & cảnh báo", "🔍 Event-study (F03)", "📘 Diễn giải & giới hạn"])
ccol = TH["coin"].get(coin, "#7BA7F0")

with t1:
    if p.empty:
        st.info("Chưa có dữ liệu độ lệch neo cho coin và khoảng thời gian đã chọn.")
    else:
        fig = go.Figure()
        fig.add_scatter(x=p["timestamp"], y=p["dev"] * 100, mode="lines", name="|P−1| (%)",
                        line=dict(color=ccol, width=2.4), fill="tozeroy", fillcolor="rgba(47,107,255,0.12)")
        tau = cfg["depeg"]["tau_main"] * 100
        fig.add_hline(y=tau, line_dash="dash", line_color=TH["level_line"]["Red"], annotation_text=f"ngưỡng depeg {tau:g}%")
        st.plotly_chart(style_fig(fig, "Độ lệch neo (%)"), width="stretch")

with t2:
    if f.empty:
        st.info("Chưa có dữ liệu rủi ro cho coin và khoảng thời gian đã chọn.")
    else:
        amber_score = float(mc.risk_score(pd.Series([scale["amber_thr"]]), scale).iloc[0])
        fig = go.Figure()
        fig.add_hrect(y0=amber_score, y1=102, fillcolor=TH["level_line"]["Amber"], opacity=0.18, line_width=0,
                      annotation_text="vùng Amber (top 10% dev)", annotation_position="top left")
        fig.add_scatter(x=f["timestamp"], y=f["risk_score"], mode="lines", name="Điểm rủi ro",
                        line=dict(color=ccol, width=2.4))
        red = f[f["alert"] == "Red"]
        fig.add_scatter(x=red["timestamp"], y=red["risk_score"], mode="markers", name="Red (alarm)",
                        marker=dict(color=TH["level_line"]["Red"], size=10, line=dict(color="#fff", width=1.5)))
        fig = style_fig(fig, "Điểm rủi ro (0–100)")
        fig.update_yaxes(range=[0, 102])
        st.plotly_chart(fig, width="stretch")
        tbl = f.tail(10).copy()
        tbl["alert"] = tbl["alert"].map(lambda x: f"{ALERT_DOT[x]} {x}")
        tbl["timestamp"] = pd.to_datetime(tbl["timestamp"]).dt.strftime("%Y-%m-%d")
        tbl["risk_score"] = tbl["risk_score"].round(1)
        tbl["proba"] = (tbl["proba"] * 100).round(2).map(lambda x: f"{x:.2f}%" if pd.notna(x) else "—")
        columns = ["timestamp", "alert", "risk_score", "proba"]
        rename = {"timestamp": "Ngày", "alert": "Mức", "risk_score": "Điểm rủi ro", "proba": "Xác suất"}
        # Tránh lặp một thông tin vô ích ở cả 10 dòng, nhưng vẫn giữ khi có driver thực.
        if any(mc.drivers_of(row) != [mc.EMPTY_DRIVER_MSG] for _, row in tbl.iterrows()):
            tbl["Driver"] = tbl.apply(lambda row: "; ".join(mc.drivers_of(row)), axis=1)
            columns.append("Driver")
            rename["Driver"] = "Driver"
        # Chỉ cần nhãn loại khi bảng có cả OOF và final.
        if tbl["proba_type"].nunique(dropna=True) > 1:
            columns.append("proba_type")
            rename["proba_type"] = "Loại"
        show = tbl[columns].rename(columns=rename)
        st.dataframe(show.sort_values("Ngày", ascending=False), hide_index=True, width="stretch")

with t3:
    events = mc.select_events(panel, cfg)
    if events.empty:
        st.info("Không tìm thấy sự kiện phù hợp trong panel đang chọn.")
    else:
        event_labels = [f"{e.stablecoin} · {e.onset:%d/%m/%Y} · {e.get('tag', '')}" for _, e in events.iterrows()]
        selected_event = st.selectbox("Sự kiện depeg", range(len(event_labels)), format_func=lambda i: event_labels[i])
        event = events.iloc[selected_event]
        interactive_run = mc.select_run(pred, model, float(h))
        from src.evaluation.make_f03_event_study import build_event_figure
        fig = build_event_figure(panel, interactive_run, event, cfg)
        st.plotly_chart(fig, width="stretch", config={"scrollZoom": True, "displaylogo": False})
        st.caption("Di chuột để xem giá trị; kéo để phóng to vùng thời gian; dùng thanh công cụ để pan hoặc tải biểu đồ.")

with t4:
    st.markdown(f"""
**Cách đọc các chỉ báo**
- **Red**: mô hình phát cảnh báo (`alarm`), ngưỡng chọn trên validation bằng cách tối đa hóa F₂.
- **Amber**: `score_raw` thuộc top {int((1 - cfg['alert']['amber_quantile']) * 100)}% cao nhất của giai đoạn dev (xếp hạng gộp 3 coin); Red được ưu tiên hơn Amber.
- **Green**: các trường hợp còn lại.
- **Điểm rủi ro 0–100**: phân vị của `score_raw` so với phân phối giai đoạn dev, nên không phụ thuộc cách hiệu chuẩn xác suất.
- **Xác suất depeg**: xác suất đã hiệu chuẩn Platt; dòng `oof` (dev) và `final` (test) hiệu chuẩn riêng nên không phải xác suất tuyệt đối.
- **Driver**: top 3 biến có đóng góp SHAP dương cao nhất; để trống nếu không biến nào đóng góp dương.

**Giới hạn**
- Dữ liệu daily; giá đóng cửa có thể bỏ sót depeg trong ngày.
- Sự kiện depeg hiếm nên xác suất cảnh báo có độ bất định lớn; mô hình chỉ có 3 coin lõi.
- Mô hình: `{model}`, horizon h = {h} ngày. Đánh giá chính thức nằm ở các Bảng T04–T05 của bài.
""")
