# Kịch bản trình bày Stablecoin Depeg Early Warning System (khoảng 4–5 phút)

Chuẩn bị: chạy `streamlit run dashboard/app.py`; dashboard đọc panel Code 1 và predictions Code 3 đã lưu trong repo. Ngày theo dõi mặc định là ngày cuối của mẫu.
Ảnh chụp cho Mục 7 nên chụp ở các bước 1, 3, 4 và 5.

**Bước 1. Giới thiệu bài toán (30 giây).** Nêu mục tiêu: cảnh báo trước khi depeg xảy ra, không chỉ phát hiện depeg đang diễn ra.
Chỉ vào ba thẻ USDT, USDC, DAI: mỗi thẻ có giá tại ngày theo dõi, độ lệch neo, điểm rủi ro 0–100, xác suất depeg 24h và mức Green/Amber/Red. Trường không có dữ liệu được ẩn.

**Bước 2. Cách đọc mức cảnh báo (45 giây).** Red lấy từ `alarm` (ngưỡng tối đa hóa F₂ trên validation, ưu tiên bắt sự kiện);
Amber là điểm số thô thuộc top 10% cao nhất của giai đoạn dev; Green là còn lại. Xác suất đã hiệu chuẩn Platt theo từng giai đoạn nên không phải xác suất tuyệt đối.

**Bước 3. Ca bình thường (30 giây).** Với một ngày Green, nêu các driver nếu có; nếu mô hình không có driver rủi ro thì giao diện không hiển thị dòng giữ chỗ lặp lại.

**Bước 4. Ca depeg USDC tháng 3/2023 (90 giây).** Chọn ngày trước onset 1–2 ngày: thẻ USDC chuyển Amber/Red nếu có cảnh báo. Mở tab "Điểm rủi ro & cảnh báo" để xem điểm quanh onset. Trong tab "Event-study (F03)", chọn sự kiện, rê chuột xem dữ liệu và zoom/pan trên biểu đồ Plotly tương tác.

**Bước 5. Đổi mô hình và horizon (30 giây).** Ở thanh bên đổi horizon từ 1 sang 3 ngày để thấy xác suất và mức cảnh báo thay đổi.

**Bước 6. Giới hạn (30 giây).** Mở tab "Diễn giải & giới hạn": dữ liệu daily, sự kiện hiếm, chỉ 3 coin lõi, kết quả đánh giá chính thức nằm ở T04–T05.

Câu hỏi dự kiến và hướng trả lời:
- *Vì sao điểm rủi ro không dùng trực tiếp xác suất?* Vì xác suất oof và final hiệu chuẩn riêng; điểm là phân vị theo phân phối dev nên so sánh được.
- *Amber khác Red thế nào?* Red là quyết định cảnh báo của mô hình; Amber là mức đáng chú ý theo thứ hạng điểm so với lịch sử dev.
- *Mô hình có dùng thông tin tương lai không?* Không: ngưỡng và thang điểm chỉ học từ dev; feature chỉ dùng dữ liệu đến t (xem kiểm tra chống leakage của Code 2).
