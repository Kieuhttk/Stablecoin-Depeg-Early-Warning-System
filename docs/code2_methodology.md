# Code 2 — Phương pháp xây dựng nhãn, đặc trưng và mô hình cơ sở

## 1. Mục tiêu và phạm vi

Code 2 xây dựng nhãn cảnh báo sớm, tập đặc trưng đầu vào, thống kê mô tả, mô hình Logistic cơ sở và phân tích hiện tượng mất neo đồng thời giữa các stablecoin. Code 2 không thay thế dữ liệu gốc của Code 1.

Mẫu nghiên cứu chính gồm USDT, USDC và DAI, với dữ liệu ngày. Dữ liệu hiện có kết thúc ngày 2026-10-16.

## 2. Định nghĩa nhãn

Nhãn chính sử dụng độ lệch neo trong ngày đã làm sạch (`peg_deviation_hl_clean`), ngưỡng 1% và xác nhận một ngày (m=1). Các nhãn theo chân trời dự báo một và ba ngày được lưu trong `onset_label_d1` và `onset_label_d3`; các cột `eligible_d1` và `eligible_d3` xác định quan sát đủ điều kiện.

Các nhãn độ nhạy được xây dựng với nguồn độ lệch khác, ngưỡng 0,5%, 1% và 2%, cùng thời gian xác nhận một hoặc hai ngày. Các nhãn biến thể phục vụ kiểm tra độ nhạy, không thay thế nhãn chính.

Artifact bàn giao lưu state và cờ onset sự kiện cho từng tổ hợp nguồn (`hl`, `cl`, `y`), ngưỡng và m. Target dự báo có tên `onset_label_{source}_tau{tau}_m{m}_d{h}`; eligibility tương ứng có tên `onset_label_{source}_tau{tau}_m{m}_eligible_d{h}`. Benchmark trạng thái chính xác tại t+h có tên `depeg_at_t_plus_d{h}_{source}_tau{tau}_m{m}`, kèm cờ `depeg_at_t_plus_d{h}_eligible_{source}_tau{tau}_m{m}`. Các trường này là nhãn/quản lý, không nằm trong 27 predictor.

Target onset chỉ được gán khi state tại t bằng 0, toàn bộ horizon và phần xác nhận cần thiết quan sát được liên tục trong cùng split, và raw state không thiếu. Với m=2, yêu cầu đủ h+1 ngày tương lai để xác định onset ở cuối horizon; raw state phân biệt vượt ngưỡng chưa xác nhận với dữ liệu thiếu. Nếu không đủ điều kiện, target là NA và eligibility bằng 0. Benchmark lấy state đã xác nhận đúng tại t+h; nó không đòi hỏi state tại t bằng 0, nhưng chỉ đủ điều kiện khi state tương lai đó quan sát được trong cùng split và ngày liên tục.

Raw state theo biến thể chỉ được giữ trong dữ liệu nhãn trung gian để tính target m=2; raw state không được xuất vào bảng features bàn giao và không được dùng làm predictor.

`hl_supported_*` là biến kiểm tra độ nhạy dựa trên thông tin của stablecoin khác trong cùng ngày. Do có thể chứa thông tin đồng thời, các biến này không được dùng làm đặc trưng dự báo chính.

## 3. Chia tập dữ liệu

- Train: 2020-01-01 đến 2021-12-31.
- Validation: năm 2022.
- Test: 2023-01-01 đến 2026-10-16.

Việc chia theo thời gian nhằm tránh sử dụng dữ liệu tương lai để huấn luyện mô hình. Khi đánh giá nhãn có chân trời dự báo hoặc xác nhận nhiều ngày, cần giữ khoảng cách giữa các tập phù hợp với chân trời và quy tắc xác nhận.

## 4. Đặc trưng và kiểm soát rò rỉ

Các đặc trưng được quản lý trong `config/labels.yaml`. Nhóm biến gồm độ lệch neo, thanh khoản và giao dịch, biến động giá, thay đổi nguồn cung, TVL và biến động thị trường tiền mã hóa.

Các cột nhãn, điều kiện đủ mẫu, trạng thái mất neo, thông tin chia tập và biến hỗ trợ đồng thời không được dùng làm đặc trưng. Biến thiếu được xử lý trong pipeline mô hình; không sử dụng nhãn hoặc dữ liệu tương lai để điền đặc trưng.

Kiểm thử cần bao gồm kiểm tra cấu trúc dữ liệu, phân biệt biến đầu vào với biến mục tiêu và kiểm tra tính bất biến của đặc trưng tại thời điểm T khi dữ liệu sau T bị loại bỏ.

## 5. Thống kê và biểu đồ

- `T01_depeg_events.csv`: danh sách sự kiện theo coin, nguồn nhãn, ngưỡng, thời gian xác nhận, ngày bắt đầu, tập dữ liệu, độ lệch cực đại và thời lượng.
- `T02_descriptive_stats.csv`: thống kê mô tả và tỷ lệ thiếu dữ liệu theo coin và biến.
- `F01_peg_deviation_history.png`: lịch sử độ lệch neo theo ba stablecoin.
- `F05_codepeg_heatmap.png`: tỷ lệ đồng thời vượt ngưỡng giữa các cặp stablecoin.

F05 sử dụng `peg_deviation_hl_clean`; với mỗi cặp coin khác nhau, tỷ lệ bằng số ngày cả hai có dữ liệu hợp lệ và cùng có độ lệch lớn hơn 1%, chia cho tổng số ngày cả hai có dữ liệu hợp lệ. Chỉ số này là tỷ lệ đồng vượt ngưỡng, không phải hệ số tương quan Pearson. Đường chéo là N/A vì F05 chỉ định nghĩa tỷ lệ cho cặp coin khác nhau.

## 6. Mô hình Logistic cơ sở

`T03_logit_coefficients.csv` được ước lượng bằng hồi quy Logistic có điều chuẩn L2. Mô hình dự báo `onset_label_d1`, chỉ dùng các quan sát thuộc tập train có `eligible_d1 = 1`. Đặc trưng được điền giá trị thiếu bằng trung vị và chuẩn hóa trước khi ước lượng.

Hệ số được báo cáo trên thang đặc trưng đã chuẩn hóa. Tỷ số chênh được tính bằng hàm mũ của hệ số; với biến liên tục, đây là tỷ số chênh ứng với mức tăng một độ lệch chuẩn của biến, giữ các biến khác không đổi theo mô hình.

Độ biến thiên của hệ số L2 được mô tả bằng moving-block bootstrap theo ngày UTC. Mỗi khối giữ đồng thời mọi hàng coin hiện diện trong ngày; mẫu được tạo từ train, lấy khối liên tiếp có hoàn lại và giữ nguyên các ngày được lặp. Mỗi lần lặp lọc lại `eligible_d1` và target hợp lệ, rồi fit lại median imputer, StandardScaler và Logistic L2 với cấu hình gốc. Không tính lại feature qua ranh giới các khối.

Môi trường không có `arch` hoặc `statsmodels` với selector độ dài khối phù hợp đã được xác minh, nên dùng độ dài định trước 14 ngày làm cấu hình chính; 7 và 30 ngày là phân tích độ nhạy. Seed là 20261021; mỗi độ dài chạy 1.000 lần. Lượt chạy cuối ghi nhận 1.000/1.000 thành công cho cả ba độ dài, không có lỗi hoặc cảnh báo không hội tụ. Thời gian đo lần lượt là 72,5 giây (14 ngày), 67,4 giây (7 ngày), 58,0 giây (30 ngày), tổng 197,8 giây. Metadata và thống kê độ nhạy theo từng hệ số được lưu trong `T03_logit_bootstrap_metadata.json`.

`standard_error` là độ lệch chuẩn mẫu của hệ số bootstrap thành công; `ci_95_lower` và `ci_95_upper` là phân vị 2,5% và 97,5% của phân phối bootstrap. T03 giữ nguyên hệ số fit trên train gốc và odds ratio gốc; khoảng dùng độ dài 14 ngày. Không tính p-value. Sai số chuẩn/khoảng này mô tả độ biến thiên của estimator L2 trong thiết kế bootstrap, không đảm bảo độ phủ danh nghĩa chính xác 95%, không phải kiểm định ý nghĩa thống kê và không chứng minh quan hệ nhân quả. Kết quả độ nhạy 7/30 ngày cũng cần được xem xét do độ dài khối có thể ảnh hưởng đáng kể trong chuỗi ngắn và sự kiện hiếm.

## 7. Hạn chế cần nêu khi diễn giải

- Số sự kiện độc lập ở validation và test còn ít, khiến ước lượng hiệu năng và lựa chọn ngưỡng cảnh báo chưa ổn định.
- Tỷ lệ nhãn dương khác nhau đáng kể giữa các tập thời gian; precision-recall giữa các tập không nên được so sánh mà không xét tỷ lệ sự kiện nền.
- Độ lệch giá của một số coin và giai đoạn phụ thuộc vào nguồn dữ liệu công khai; các đợt biến động bất thường có thể ảnh hưởng đến nhãn.
- `xmkt_gap` có tỷ lệ thiếu rất cao, nên hệ số của biến này và cờ thiếu dữ liệu cần được diễn giải thận trọng.
- Mẫu chỉ gồm ba stablecoin; kết quả chưa đại diện cho toàn bộ stablecoin.
- Đặc trưng on-chain chi tiết chưa đầy đủ; turnover và biên độ giá chỉ là đại diện hạn chế cho thanh khoản.
- Mô hình Logit là đường cơ sở. Cần đánh giá ngoài mẫu trước khi kết luận về khả năng cảnh báo thực tế.
