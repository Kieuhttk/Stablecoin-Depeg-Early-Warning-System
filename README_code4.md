# Stablecoin Depeg Early Warning System · Code 4

Phần này gồm: Hình F03 (event-study), Hình F04 (xác suất cảnh báo theo thời gian) và dashboard Streamlit.
Công cụ phục vụ nghiên cứu mô phỏng, không phải khuyến nghị đầu tư.

## 1. Cài đặt

```bash
pip install -r requirements.txt -r requirements_code4.txt
```

## 2. Dữ liệu đầu vào

| Tệp | Nguồn | Ghi chú |
| --- | --- | --- |
| `Stablecoin-EWS_Code1_backup_no_onchain/data/processed/panel.parquet` | Code 1 (backup không on-chain) | panel giá/volume/supply và biến thị trường; snapshot đến 16/10/2026 |
| `outputs/predictions.parquet` | Code 3 | cần `timestamp, stablecoin, model, h, proba, proba_type, score_raw, alarm, top1_driver, top2_driver, top3_driver` |

Nếu thiếu panel nhưng có `features.parquet` và predictions, dashboard dùng features thật làm panel dự phòng
và ghi chú rằng giá/thanh khoản có thể không có. Dashboard chỉ dùng dữ liệu thật; nếu thiếu đầu vào, ứng dụng báo lỗi.

Phần **Giá thị trường mới nhất** gọi Binance public spot API (cache 60 giây), độc lập với chuỗi dự báo lịch sử. USDT được lấy mốc $1; USDC và DAI được hiển thị theo cặp USDT trên Binance. Commit `ad909ef` đã khôi phục panel Code 1 (11.244 hàng × 46 cột, 6 coin), nhưng panel và dự báo lịch sử kết thúc ngày 16/10/2026. Giá spot không phải dự báo mới của mô hình.

## 3. Chạy

```bash
python -m src.evaluation.make_f03_event_study            # -> outputs/figures/F03_event_study.png
python -m src.evaluation.make_f04_warning_probability    # -> outputs/figures/F04_warning_probability.png
streamlit run dashboard/app.py                           # dashboard
pytest tests/test_monitor_core.py                        # kiểm thử phần Code 4
```

Tham số (ngưỡng τ, m, h, mô hình chốt, phân vị Amber, cửa sổ event-study, bảng màu) nằm ở `config/dashboard.yaml`.

## 4. Quy ước hiển thị

- **proba_type**: dòng `oof` (dev 2021–2022) và dòng `final` (test) có hiệu chuẩn Platt riêng, không dùng như xác suất tuyệt đối và không nối liền trong F04.
- **Mức cảnh báo**: Red = `alarm` (ngưỡng tối đa hóa F₂ trên validation); Amber = `score_raw` thuộc top 10% giai đoạn dev
  (gộp 3 coin, chỉ học từ dòng `oof`); Green = còn lại. Red ưu tiên hơn Amber.
- **Điểm rủi ro 0–100**: phân vị của `score_raw` trong phân phối dev, nên so sánh được giữa `oof` và `final`.
- **Driver trống**: không chiếm chỗ trên thẻ coin.
- **F03**: biểu đồ Plotly tương tác; chọn sự kiện, rê chuột xem dữ liệu và zoom/pan theo trục thời gian.
- **Onset trong event-study**: tính từ panel với τ và m ở `config/dashboard.yaml` (mặc định τ = 1%, m = 1); nếu chưa đủ
  3–4 sự kiện ở τ chính thì bổ sung sự kiện ở τ = 0.5%.
- **Lead time trong F03**: số ngày từ lần `alarm = 1` đầu tiên trong 10 ngày trước onset đến onset.

## 5. Cấu trúc

```
config/dashboard.yaml
dashboard/app.py
src/evaluation/monitor_core.py            # logic dùng chung
src/evaluation/make_f03_event_study.py
src/evaluation/make_f04_warning_probability.py
tests/test_monitor_core.py
docs/kich_ban_demo.md
```
