# Code 1 (BẢN BACKUP KHÔNG ON-CHAIN): Thu thập, chuẩn hóa UTC và ghép panel

Dự án *Stablecoin Depeg Early-Warning System* (Nhóm 4). Bản này thay thế pipeline chính trong trường hợp **không tải được bất kỳ dữ liệu on-chain/DEX nào** (Curve, Dune, Uniswap). Đầu ra giữ nguyên tên và vị trí để Code 2, 3, 4 dùng ngay: `data/processed/panel.parquet`, panel **stablecoin × ngày (UTC 00:00)**.

Ghi chú kỹ thuật đầy đủ (code làm được gì, giới hạn, lưu ý cho Code 2/3/4 và Viết 1/2): **`CODES_Note.md`**.

## Chạy nhanh

Windows: nhấp đúp `run_all.bat` (mặc định **offline**, dựng lại panel từ dữ liệu đã lưu trong `data/raw/`, không cần mạng, không cần key).
macOS/Linux: `./run_all.sh`.

Chạy từng bước:

```bash
pip install -r requirements.txt
python -m src.data.build_panel --version v1 --offline   # chỉ dùng cache data/raw (khuyến nghị: tái lập đúng bản bàn giao)
python -m src.data.build_panel --version v1             # dùng cache, nguồn nào chưa có cache thì tải
python -m src.data.build_panel --version v1 --refresh   # tải lại toàn bộ từ nguồn (cần mạng)
pytest -q                                               # 20 test, không cần mạng
```

CryptoCompare là tùy chọn: muốn dùng thì sao chép `.env.example` thành `.env` và điền `CRYPTOCOMPARE_API_KEY`. Không có key thì pipeline bỏ qua êm và đối chiếu giá bằng Binance quy USD.

## Đầu ra

| Tệp | Dùng cho |
|---|---|
| `data/processed/panel.parquet`, `panel_v1.parquet` | Bàn giao cho Code 2 (11.244 hàng × 46 cột, 6 coin, 01/01/2020 đến 16/10/2026) |
| `outputs/tables/data_dictionary.csv`, `outputs/appendix/PhuLuc_A_data_dictionary.md` | Phụ lục A (kèm bảng đối chiếu với mục 3.4 của đề) |
| `outputs/tables/source_log_raw.csv`, `outputs/appendix/PhuLuc_B_source_log.md` | Phụ lục B |
| `outputs/tables/qc_report.csv`, `coverage_by_coin.csv`, `outputs/appendix/PhuLuc_E_qc_tai_lap.md` | Phụ lục E (bản nháp: QC và hướng dẫn tái lập) |
| `outputs/tables/blueprint_mapping.csv` | Trường nào của đề có/không có, biến thay thế |
| `outputs/tables/event_count_preview.csv` | Tham khảo cho Code 2: số ngày vượt ngưỡng 0,5/1/2% |
| `outputs/tables/review_*.csv` | Bảng rà tay: lệch nguồn, giá xa neo, râu nến nghi lỗi |

## Cấu trúc

```text
├── README.md, CODES_Note.md, requirements.txt, run_all.bat, run_all.sh, .env.example, .gitignore
├── config/config.yaml          toàn bộ tham số (mẫu, độ trễ, ngưỡng QC, danh sách coin)
├── src/data/
│   ├── fetch.py                tải từng nguồn, cache, source log, chuẩn hóa UTC, chế độ offline
│   ├── build_panel.py          ghép panel, quy đổi Binance về USD, độ lệch đa nguồn, cờ chất lượng
│   ├── dictionary.py           từ điển dữ liệu + bảng đối chiếu với đề
│   ├── qc.py                   kiểm tra chất lượng, độ phủ, bảng rà tay
│   └── appendix.py             sinh bản nháp Phụ lục A, B, E (Markdown)
├── tests/test_panel.py         20 test (dữ liệu giả, không mạng)
├── data/raw/                   cache dữ liệu thô (tải ngày 19/10/2026)
├── data/processed/             panel.parquet, panel_v1.parquet
└── outputs/tables/, outputs/appendix/
```
