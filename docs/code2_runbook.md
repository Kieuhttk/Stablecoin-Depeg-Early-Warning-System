# Code 2: tái lập và bàn giao

## Phạm vi

Code 2 tạo nhãn onset và benchmark, 27 predictor, các bảng mô tả/sự kiện, Logit L2 và hai hình đầu ra. Dữ liệu panel của Code 1 được đọc làm đầu vào; Code 2 không sửa panel đó. Mẫu mô hình gồm USDT, USDC và DAI, dữ liệu hiện kết thúc ngày 2026-10-16.

## Môi trường

Repository hiện không có `pyproject.toml`, `requirements*.txt` hoặc `environment.yml`, nên không quy định phiên bản Python hay phiên bản package. Mã nguồn trực tiếp import `pandas`, `PyYAML`, `numpy`, `scikit-learn`, `matplotlib` và `seaborn`; đọc/ghi Parquet cần một engine tương thích như `pyarrow`; test dùng `pytest`. Hãy ghi lại phiên bản môi trường thực tế khi tái lập. Từ thư mục gốc repo, có thể cài các dependency trực tiếp bằng pip mà không khóa phiên bản:

```powershell
python --version
python -m pip install pandas PyYAML numpy scikit-learn matplotlib seaborn pyarrow pytest
```

Không có lockfile để bảo đảm môi trường cài đặt giống hệt lần tạo artifact.

## Đầu vào và thứ tự chạy

Chạy các lệnh từ thư mục gốc repository. `config/labels.yaml` trỏ tới panel Code 1 tại `Stablecoin-EWS_Code1_backup_no_onchain/data/processed/panel.parquet`; panel này phải tồn tại và có các cột được yêu cầu trong cấu hình/mã nguồn.

1. Tạo `data/interim/labels.parquet`, bảng sự kiện T01, bảng mô tả T02 và các bảng đếm nhãn hỗ trợ:

   ```powershell
   python -m src.features.labels
   ```

2. Tạo artifact features bàn giao và ghép nhãn từ bước trước:

   ```powershell
   python -m src.features.features
   ```

3. Tạo T03 và `T03_logit_bootstrap_metadata.json`. Lệnh này fit Logit trên train và chạy moving-block bootstrap; đây là bước tính toán tốn thời gian:

   ```powershell
   python -m src.models.code2_logit
   ```

4. Tạo F01 và F05. Module hiện gọi cả hai hàm tạo hình trong cùng một lần chạy:

   ```powershell
   python -m src.visualization.code2_figures
   ```

5. Chạy test sau khi đã tạo cả `data/interim/labels.parquet` và `data/processed/features.parquet`:

   ```powershell
   python -m pytest -q -p no:cacheprovider
   ```

`tests/test_artifact_contract.py` đọc trực tiếp hai Parquet trên và cố ý fail nếu thiếu; test không tự tạo hoặc bỏ qua artifact. Vì vậy, khi chỉ chạy test trên checkout sạch, cần chạy hai bước labels rồi features trước.

## Sản phẩm và artifact

| Đường dẫn | Vai trò / nguồn |
|---|---|
| `outputs/tables/T01_depeg_events.csv` | Sự kiện theo coin, nguồn nhãn, ngưỡng, m, split, ngày bắt đầu, thời lượng và độ lệch cực đại; tạo từ panel trong bước labels. |
| `outputs/tables/T02_descriptive_stats.csv` | Thống kê mô tả theo coin; tạo từ panel trong bước labels/features. |
| `outputs/tables/T03_logit_coefficients.csv` | Hệ số Logit L2 trên train và thống kê moving-block bootstrap. |
| `outputs/figures/F01_peg_deviation_history.png` | Lịch sử `peg_deviation_hl_clean` của ba coin lõi, từ panel Code 1. |
| `outputs/figures/F05_codepeg_heatmap.png` | Tỷ lệ ngày các cặp coin cùng vượt ngưỡng 1%, từ `peg_deviation_hl_clean` trong panel. |
| `outputs/tables/T03_logit_bootstrap_metadata.json` | Metadata hỗ trợ để diễn giải/tái lập bootstrap T03; không phải bảng chính thức thứ sáu. |
| `data/processed/features.parquet` | Hợp đồng Code 2 cho Code 3/4: khóa `(timestamp, stablecoin)`, 27 predictor, nhãn, benchmark và cột quản lý. |

`data/interim/labels.parquet` là dữ liệu trung gian cần cho bước features và kiểm thử hợp đồng; `.gitignore` loại thư mục `data/interim/` khỏi Git. Không cần đưa file này vào commit nếu quy trình tạo lại từ panel Code 1 khả dụng.

Các bảng đếm nhãn và notebook trong repo là đầu ra hỗ trợ/kiểm tra, không thay thế T01 chính thức.

## Giới hạn hợp đồng với Code 4

Panel Code 1 là nguồn hiện có chứa `peg_deviation_hl_clean`; Code 2 dùng cột này để tạo nhãn chính và F01/F05, nhưng không đưa nó vào 27 predictor của `features.parquet`. Ghi chú Code 1 mô tả panel processed là dữ liệu dùng chung cho các vai trò. Repository hiện không có source Code 4 hoặc hướng dẫn chạy event-study của Code 4, nên chưa xác minh được Code 4 thực sự đọc panel này hay một artifact khác. Người bàn giao cần xác nhận đường dẫn panel dùng cho event-study và bảo đảm file panel có mặt trong môi trường nhận bàn giao.

\n