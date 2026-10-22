# Code 3 — Nhật ký quyết định (chốt TRƯỚC khi chạy test set)

Mọi mục dưới đây dựa trên kết quả dev (walk-forward trên train + validation, 2021–2022). Không mục nào
dựa trên điểm số của tập test. Sau khi chạy test không đổi lại các mục này; muốn đổi phải ghi thêm mục mới
và nêu rõ là đổi sau khi thấy test.

| Mã | Quyết định | Lý do / hệ quả |
|---|---|---|
| C3-01 | Cấu hình nhãn chính: nguồn `hl`, ngưỡng 1%, m = 1. Horizon h = 1 ngày là chính, h = 3 ngày bổ sung | Khớp Nhật ký quyết định chung và `labels.yaml` của Code 2 |
| C3-02 | Walk-forward mở rộng trên train + validation, 4 khối nửa năm (2021H1 đến 2022H2). Mỗi fold huấn luyện trên dữ liệu trước khối, cách khối h + m ngày (purge) | Nhãn tại t dùng thông tin tới t + h; purge để nhãn không chồng sang khối kiểm tra. Có test chống look-ahead trong `tests/` |
| C3-03 | Mô hình: baseline ngây thơ (độ lệch neo hiện tại `peg_deviation`), Logit L2, Random Forest, XGBoost. Lưới tham số nhỏ trong `config/code3.yaml`; tham số chọn theo PR-AUC gộp trên OOF | Ít sự kiện nên tránh lưới lớn. Chênh lệch giữa các tham số nằm trong nhiễu (24 sự kiện ở h = 1) |
| C3-04 | Ngưỡng cảnh báo: tối đa hóa F2 trên OOF gộp 2021–2022. Xác suất hiệu chuẩn Platt trên cùng OOF | Cảnh báo sớm ưu tiên recall. Lưu ý: Platt học tỉ lệ sự kiện của 2021–2022, `proba` trên test có thể lệch nếu tỉ lệ nền khác; đọc `score_raw` và xếp hạng khi so sánh |
| C3-05 | `dashboard_model = rf` (Random Forest) cho top 3 driver, SHAP và dashboard. Tiêu chí viết trước: mô hình ML có PR-AUC walk-forward cao nhất ở h = 1 với đủ 27 predictor (RF 0.102 > XGBoost 0.088) | Khi bỏ `xmkt_gap` thì XGBoost 0.078 và RF 0.077 gần như bằng nhau: việc chọn giữa RF và XGBoost là hòa về thống kê. Giữ RF vì thắng ở cả hai horizon trong cấu hình chính và SHAP cho cây của RF dùng được. Cả hai mô hình vẫn được báo cáo |
| C3-06 | Lead time và recall mức sự kiện dùng cửa sổ nhìn lại 7 ngày (`lead_lookback: 7`): sự kiện được bắt nếu có cảnh báo ở ít nhất một ngày trong 7 ngày trước ngày bắt đầu; lead time là số ngày từ cảnh báo sớm nhất trong cửa sổ đến ngày bắt đầu | Với daily và h ≤ 3, lead time theo cửa sổ h tối đa chỉ 1–3 ngày. Cửa sổ 7 ngày cho cảm nhận về lead time nhưng dễ bị cảnh báo kéo dài (độ lệch cao liên tục) làm đẹp số |
| C3-07 | Mốc so sánh may rủi `chance_event_recall = 1 − (1 − tỉ lệ ngày báo động)^7` và so sánh ở cùng ngân sách báo động 3%, 5%, 10% số ngày (bảng T05b) | Ngưỡng F2 làm mỗi mô hình báo động nhiều ít khác nhau nên recall không so trực tiếp được. Công thức giả định báo động độc lập; báo động thực tế dồn cụm nên đây là cận trên của mốc may rủi |
| C3-08 | Giữ `xmkt_gap` và `xmkt_gap_missing` trong mô hình chính (đúng 27 predictor của Code 2); phân tích bỏ hai biến này nằm ở P2 (`drop_xmkt_gap`) | Theo `features.parquet`, `xmkt_gap` có giá trị gần như chỉ ở USDC (khoảng 100% các năm 2020–2021 và 2024–2026, 74–81% năm 2022–2023), USDT 0%, DAI chỉ 6% năm 2020. Vì vậy nó hoạt động như biến nhận diện coin. Khi bỏ nó, PR-AUC của RF giảm từ 0.102 xuống 0.077, nên một phần hiệu năng là nhờ tỉ lệ sự kiện khác nhau giữa các coin. Ghi vào Limitations và khi diễn giải SHAP |
| C3-09 | `top1/2/3_driver` chỉ chứa feature có đóng góp dương (làm tăng rủi ro); để trống nếu không có | Tránh dashboard hiển thị driver làm giảm rủi ro. Code 4 phải xử lý ô trống |
| C3-10 | Test set chạy một lần bằng `--stage test` (khóa `outputs/test_run.lock.json`). Robustness (P2) và P1 chỉ chạy sau đó và chỉ để đo độ nhạy, không chọn lại mô hình | Theo Nhật ký quyết định chung |

## Phát hiện từ dev cần đưa vào báo cáo (đã kiểm chứng trên OOF 2021–2022)

- Baseline ngây thơ khó bị đánh bại: ở cùng ngân sách báo động 3% / 5% / 8,6% số ngày, baseline bắt 14 / 18 / 20 trong 24 sự kiện (cửa sổ 7 ngày); RF bắt 8 / 14 / 16 và XGBoost 8 / 10 / 15.
- Hiệu năng gộp bị DAI chi phối: 16 trong 24 nhãn dương h = 1 là của DAI, USDT 6, USDC 2. Theo từng coin, baseline ≥ ML với USDT (0.482 so với RF 0.279) và USDC; ba mô hình xấp xỉ nhau ở DAI.
- Chỉ dùng tỉ lệ sự kiện theo coin đạt PR-AUC 0.02, thấp xa mức 0.10 của mô hình, nên nhận diện coin không giải thích hết kết quả.
- SHAP (RF, h = 1): nhóm biến động chiếm khoảng 54%, nhóm độ lệch/giá khoảng 20%, thanh khoản khoảng 17%, thị trường crypto khoảng 5%, cung/TVL khoảng 4%. SHAP chỉ mô tả mô hình, không phải quan hệ nhân quả.