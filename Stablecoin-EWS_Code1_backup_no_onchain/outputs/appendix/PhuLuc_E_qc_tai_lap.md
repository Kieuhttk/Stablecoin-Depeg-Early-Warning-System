# Phụ lục E. Kiểm tra chất lượng dữ liệu và hướng dẫn tái lập (bản nháp)

## E.1. Tham số chốt

| Tham số | Giá trị |
|---|---|
| Khoảng mẫu | 2020-01-01 đến 2026-10-16 (UTC, ngày cuối đóng băng) |
| Tần suất | Ngày (nến 00:00 đến 24:00 UTC) |
| Độ trễ dữ liệu DefiLlama | 1 ngày; ffill tối đa 3 ngày |
| Quy đổi Binance | Giá USDT nhân USDT-USD (Yahoo) cùng ngày |
| Dữ liệu on-chain | Không sử dụng; thay bằng proxy DefiLlama và chênh lệch liên thị trường |
| Phiên bản panel | panel_v1.parquet |

## E.2. Kết quả kiểm tra chất lượng

| check | status | detail |
|---|---|---|
| khóa (stablecoin, timestamp) duy nhất | PASS |  |
| timestamp có múi giờ UTC | PASS | UTC |
| timestamp đúng 00:00 UTC | PASS |  |
| không có ngày chưa đóng nến (>= hôm nay UTC) | PASS | max=2026-10-16 00:00:00+00:00 |
| dữ liệu gốc mọi nguồn đều gắn mốc 00:00 UTC (off_midnight = 0) | PASS |  |
| lưới ngày liên tục trong từng coin (cần cho shift(-h) của nhãn) | PASS |  |
| panel không chứa cột on-chain (bản backup) | PASS |  |
| giá dương và <= 5 USD (ngoài khoảng = lỗi dữ liệu) | PASS | 0 quan sát |
| giá ngoài [0.5, 1.5] (thường là depeg thật, cần xem tay và ghi vào bảng sự kiện) | WARN | 2 quan sát: UST 2022-05-12 0.3626 (binance_usd); UST 2022-05-13 0.2453 (binance_usd) |
| high >= low | PASS |  |
| peg_deviation >= 0 | PASS |  |
| peg_deviation_min <= peg_deviation | PASS |  |
| biến cấp thị trường (BTC/ETH, TVL, USDT-USD) giống hệt nhau giữa các coin trong cùng ngày | PASS | 0 ngày khác giá trị, 0 ngày NaN lẫn không NaN |
| supply không âm | PASS |  |
| giá đóng cửa lệch > 0,5% so với nguồn độc lập (CryptoCompare/Binance quy USD) | INFO | 52/4958 ngày có >= 2 nguồn; theo coin: {'BUSD': 5, 'DAI': 8, 'USDC': 39}; xem review_src_disagree_days.csv |
| tỷ lệ ngày có ít nhất 2 nguồn giá độc lập, theo coin | WARN | {'BUSD': '58%', 'DAI': '1%', 'FDUSD': '100%', 'USDC': '93%', 'USDT': '0%', 'UST': '0%'} |
| số ngày râu nến nghi lỗi (hl_suspect), đã làm sạch trong peg_deviation_hl_clean | INFO | {'BUSD': 1, 'DAI': 2, 'FDUSD': 1, 'USDC': 2} |
| không nghi dữ liệu cũ/đứng giá (giá giống nhau >= 20 ngày hoặc volume=0 > 20%) | PASS |  |
| cơ cấu nguồn giá (price_src) | INFO | {'yahoo': 11100, 'binance_usd': 144} |
| dữ liệu on-chain | INFO | KHÔNG dùng (bản backup): thay bằng proxy DefiLlama (supply_change, supply_eth_change, supply_eth_share, tvl_change) và chênh lệch liên thị trường xmkt_gap |
| quy ước nến Yahoo khớp nguồn độc lập (lag tối ưu = 0 ngày) | PASS | tất cả lag 0 (3 cặp so sánh) |

## E.3. Số ngày vượt ngưỡng (tham khảo, chưa phải nhãn chính thức)

| stablecoin | measure | > 0.5% | > 1.0% | > 2.0% |
|---|---|---|---|---|
| BUSD | peg_deviation | 87 | 38 | 14 |
| BUSD | peg_deviation_hl_clean | 169 | 66 | 33 |
| BUSD | peg_deviation_min | 85 | 38 | 14 |
| DAI | peg_deviation | 241 | 135 | 46 |
| DAI | peg_deviation_hl_clean | 424 | 304 | 129 |
| DAI | peg_deviation_min | 240 | 134 | 44 |
| FDUSD | peg_deviation | 6 | 1 | 0 |
| FDUSD | peg_deviation_hl_clean | 27 | 4 | 1 |
| FDUSD | peg_deviation_min | 4 | 1 | 0 |
| USDC | peg_deviation | 56 | 31 | 18 |
| USDC | peg_deviation_hl_clean | 80 | 16 | 7 |
| USDC | peg_deviation_min | 24 | 6 | 4 |
| USDT | peg_deviation | 32 | 9 | 4 |
| USDT | peg_deviation_hl_clean | 263 | 135 | 35 |
| USDT | peg_deviation_min | 32 | 9 | 4 |
| UST | peg_deviation | 10 | 5 | 5 |
| UST | peg_deviation_hl_clean | 42 | 14 | 7 |
| UST | peg_deviation_min | 10 | 5 | 5 |

## E.4. Tái lập

Cài thư viện bằng `pip install -r requirements.txt`, sau đó chạy `python -m src.data.build_panel --version v1 --offline` để dựng lại panel chỉ từ bản lưu trong `data/raw/` (kết quả trùng khớp với bản bàn giao), hoặc bỏ `--offline` và thêm `--refresh` để tải lại toàn bộ từ nguồn. Bộ kiểm thử chạy bằng `pytest -q` và không cần mạng.
