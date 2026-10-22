# Code 3: chạy lại và bàn giao

## Môi trường

Cần `pandas`, `numpy`, `scikit-learn`, `PyYAML`, `matplotlib`, `pyarrow`, `xgboost`, `shap`, `pytest`.
Hãy ghi phiên bản thực tế khi chạy (`pip freeze`) vào Phụ lục C. Script tự ghi `has_xgboost`, `has_shap`
vào `model_freeze.json`; hai giá trị này phải là `true` cho kết quả cuối.

## Thứ tự chạy (từ thư mục gốc repository)

```powershell
# 0. Kiểm thử
python -m pytest -q tests/test_code3.py

# 1. Dev: chọn tham số, ngưỡng, hiệu chuẩn; đóng băng mô hình. KHÔNG nạp split test.
#    Chạy lại sau khi thay code3_models.py để có thêm T05b; kiểm tra cv_pr_auc trong
#    outputs/dev/model_freeze.json trùng bản cũ (0.1016 cho RF h=1, 0.0884 cho XGBoost h=1).
python -m src.models.code3_models --stage dev

# 2. Chốt: commit code3.yaml, model_freeze.json, code3_decision_log.md, rồi gắn tag
git add config/code3.yaml outputs/dev/model_freeze.json docs/code3_decision_log.md
git commit -m "Code 3: chốt mô hình trước khi chạy test"
git tag code3-freeze

# 3. Thử đường mã test trên validation (không đụng split test, không tạo khóa)
python -m src.models.code3_models --stage test --dry-run

# 4. Test: CHỈ MỘT LẦN. Tạo outputs/test_run.lock.json
python -m src.models.code3_models --stage test

# 5. Robustness (P2): sau test, chỉ đo độ nhạy
python -m src.models.code3_models --stage robustness
```

Lưu ý: `outputs_nox/` (bản bỏ `xmkt_gap`) chỉ để so sánh, không dùng để chốt mô hình. Việc bỏ `xmkt_gap`
sẽ được báo cáo trong P2 (`drop_xmkt_gap`). Khóa `test_run.lock.json` chỉ được ghi khi bước 4 chạy xong.
Nếu bước 4 dừng giữa chừng vì lỗi kỹ thuật (thiếu thư viện, lỗi ghi tệp), chỉ sửa lỗi đó, không đổi tham
số hay lựa chọn mô hình, rồi chạy lại và ghi việc chạy lại vào Nhật ký quyết định. Nếu khóa đã tồn tại,
script từ chối chạy.

## Đầu ra và người nhận

| Tệp | Nội dung | Người nhận |
|---|---|---|
| `outputs/predictions.parquet` | `timestamp` (UTC), `stablecoin`, `model`, `h`, `split`, `score_raw`, `threshold_raw`, `proba`, `alarm`, `eligible`, `label`, `proba_type` (`oof` hoặc `final`), `explain_method`, `top1/2/3_driver` | Code 4, Viết 2 |
| `outputs/tables/T04_model_performance.csv` | Hiệu năng mức quan sát | Viết 2 (Mục 5.2) |
| `outputs/tables/T05_precision_recall_by_horizon.csv` | Precision, recall, lead time, recall mức sự kiện, mốc may rủi | Viết 2 (Mục 5.2–5.3) |
| `outputs/tables/T05b_matched_budget.csv` | So sánh cùng ngân sách báo động 3%, 5%, 10% | Viết 2 (RQ4) |
| `outputs/tables/T06_shap_ranking.csv` | Xếp hạng feature theo SHAP, kèm nhóm feature | Viết 2 (Mục 5.4, RQ1–RQ2) |
| `outputs/figures/F02_pr_curves.png` | Đường precision–recall trên test | Viết 2 |
| `outputs/tables/P1_by_stablecoin_type.csv` | Theo loại stablecoin và từng coin (RQ3) | Viết 2 (Mục 5.5) |
| `outputs/tables/P2_robustness.csv` | Độ nhạy: ngưỡng, m, nguồn nhãn, nhãn theo đề, bỏ nhóm feature, bỏ `xmkt_gap` | Viết 2 (Mục 6) |
| `outputs/dev/*` | Kết quả dev (OOF 2021–2022) | Phụ lục C, D |

Ghi chú cho Code 4: `top1/2/3_driver` có thể để trống; `proba` đã hiệu chuẩn trên 2021–2022 nên dùng
`alarm` và `score_raw` cho mức Red/Amber/Green thay vì diễn giải `proba` như xác suất tuyệt đối.

## Phụ lục C (tham số và seed)

Lấy từ `outputs/dev/model_freeze.json` (tham số, ngưỡng, hệ số Platt, `seed = 20261022`) và `pip freeze`.