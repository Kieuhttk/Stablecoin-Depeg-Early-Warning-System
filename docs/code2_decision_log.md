# Code 2 — Nhật ký quyết định

| Mã | Quyết định | Lý do / hệ quả |
|---|---|---|
| D01 | Mẫu chính gồm USDT, USDC và DAI | Giữ phạm vi nghiên cứu nhất quán giữa các đầu ra Code 2. |
| D02 | Nhãn chính dựa trên `peg_deviation_hl_clean`, ngưỡng 1%, m=1 | Sử dụng độ lệch trong ngày đã làm sạch làm định nghĩa chính. |
| D03 | Xây dựng thêm nhãn độ nhạy từ `peg_deviation_min` và `peg_deviation` | Kiểm tra độ nhạy với nguồn đo lường độ lệch khác. |
| D04 | Chia train 2020–2021, validation 2022, test từ 2023 đến 2026-10-16 | Đánh giá theo thời gian, hạn chế rò rỉ từ tương lai. |
| D05 | Chỉ dùng các đặc trưng được khai báo trong `config/labels.yaml` | Tập trung quản lý danh sách biến ở một nơi. |
| D06 | Không đưa nhãn, điều kiện đủ mẫu, trạng thái mất neo, split hoặc `hl_supported_*` vào đặc trưng chính | Tránh đưa trực tiếp mục tiêu hoặc thông tin đồng thời vào mô hình. |
| D07 | Xử lý thiếu bằng trung vị trong pipeline Logistic | Giữ quy trình điền thiếu và chuẩn hóa trong bước ước lượng. |
| D08 | Dùng Logistic L2 làm mô hình cơ sở, chỉ huấn luyện trên train đủ điều kiện | Có mô hình tham chiếu trước khi đánh giá các mô hình phức tạp hơn. |
| D09 | Báo cáo hệ số chuẩn hóa, odds ratio, sai số chuẩn và khoảng bootstrap percentile; không báo p-value | Bootstrap mô tả độ biến thiên của estimator L2; khoảng không được diễn giải là có độ phủ danh nghĩa được bảo đảm. |
| D10 | F05 đo tỷ lệ các cặp coin khác nhau cùng vượt 1% trong cùng ngày bằng `peg_deviation_hl_clean`; đường chéo là N/A | Mẫu số là số ngày cả hai coin có dữ liệu hợp lệ; đo đồng vượt ngưỡng theo sự kiện, không diễn giải như hệ số tương quan. |
| D11 | Giữ dữ liệu Code 1 ở chế độ chỉ đọc | Bảo toàn nguồn dữ liệu và quy trình đã có. |
| D12 | Xuất target onset và eligibility cho 18 tổ hợp nguồn × ngưỡng × m, cùng benchmark state đúng tại t+h cho h=1,3 | Dùng tên `onset_label_{source}_tau{tau}_m{m}_d{h}` / `onset_label_{source}_tau{tau}_m{m}_eligible_d{h}`; benchmark dùng `depeg_at_t_plus_d{h}_{source}_tau{tau}_m{m}` và cờ eligibility cùng tiền tố. Raw state chỉ nằm ở nhãn trung gian để xác định m=2, không thuộc 27 predictor hoặc artifact bàn giao. |
| D13 | Moving-block bootstrap theo ngày UTC cho hệ số Logit L2 | Độ dài chính 14 ngày, độ nhạy 7/30 ngày; seed 20261021; 1.000 lần mỗi độ dài. Lấy đồng thời các coin hiện diện trong ngày, refit imputer/scaler/Logit trong từng mẫu; không tính p-value. Số thành công/thất bại và thời gian thực tế nằm trong `T03_logit_bootstrap_metadata.json`. |

## Trạng thái

- [x] T01 — danh sách sự kiện.
- [x] T02 — thống kê mô tả.
- [x] T03 — hệ số Logistic cơ sở.
- [x] F01 — lịch sử độ lệch neo.
- [x] F05 — heatmap mất neo đồng thời.
- [x] Kiểm thử leakage: đặc trưng tại T không đổi khi loại dữ liệu sau T.
- [x] Kiểm thử hợp đồng artifact: schema, khóa, split và nhãn giữa interim/processed.
- [x] Toàn bộ pytest sau cập nhật C2-05/C2-06: 39 passed (`python -m pytest -q -p no:cacheprovider`).
- [ ] Rà soát nội dung biểu đồ và tính nhất quán của toàn bộ đầu ra.
- [ ] Rà soát Git, commit một lần và push nhánh `feature/code2`.
- [ ] Tạo pull request vào `main`.
