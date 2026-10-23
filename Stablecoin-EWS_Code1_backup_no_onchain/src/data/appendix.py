"""Sinh bản nháp Phụ lục A, B, E (Markdown) từ kết quả pipeline để Viết 1/Viết 2 dán vào báo cáo.

Chỉ là KHUNG số liệu tự động: phần diễn giải do nhóm viết. Các file nằm ở outputs/appendix/.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from src.data.dictionary import BLUEPRINT_MAPPING, DICTIONARY


def _md(df: pd.DataFrame) -> str:
    """Bảng Markdown không cần thư viện tabulate."""
    def cell(v):
        if isinstance(v, float):
            v = f"{v:.6g}"
        return str(v).replace("|", "/").replace("\n", " ")
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def write_all(out_dir: Path, panel: pd.DataFrame, source_log: pd.DataFrame, qc: pd.DataFrame,
              cov: pd.DataFrame, ev: pd.DataFrame, cfg: dict, version: str) -> None:
    app = out_dir / "appendix"
    app.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    bm = pd.DataFrame(BLUEPRINT_MAPPING, columns=["truong_trong_de", "cot_trong_panel", "trang_thai", "ghi_chu"])
    bm.to_csv(out_dir / "tables" / "blueprint_mapping.csv", index=False, encoding="utf-8-sig")

    # ---------------- Phụ lục A
    dd = pd.DataFrame(DICTIONARY)[["column", "dtype", "unit", "definition", "source", "timing"]]
    a = [f"# Phụ lục A. Từ điển dữ liệu (bản backup không on-chain)",
         "",
         f"Sinh tự động lúc {now} từ `src/data/dictionary.py`. Panel `panel_{version}.parquet` có "
         f"{panel.shape[0]} hàng và {panel.shape[1]} cột, đơn vị quan sát là stablecoin theo ngày UTC.",
         "",
         _md(dd),
         "",
         "## A.1. Đối chiếu với cấu trúc dữ liệu đề xuất (mục 3.4 của đề)",
         "",
         _md(bm)]
    (app / "PhuLuc_A_data_dictionary.md").write_text("\n".join(a) + "\n", encoding="utf-8")

    # ---------------- Phụ lục B
    cols = [c for c in ["source", "key", "endpoint", "status", "rows", "first_date", "last_date", "off_midnight",
                        "fetched_at_utc", "error", "note"] if c in source_log.columns]
    b = ["# Phụ lục B. Nhật ký nguồn dữ liệu (source log)",
         "",
         f"Sinh tự động lúc {now}. Trạng thái `ok_cache` nghĩa là dữ liệu được đọc từ bản lưu `data/raw/` "
         "(đã tải trước đó); `skipped_no_key` nghĩa là CryptoCompare không được gọi vì không có khóa API; "
         "`off_midnight` là số mốc thời gian gốc không rơi đúng 00:00 UTC (phải bằng 0).",
         "",
         _md(source_log[cols].fillna("")),
         "",
         "## B.1. Độ phủ dữ liệu theo coin",
         "",
         _md(cov.assign(first_date=cov["first_date"].astype(str).str[:10], last_date=cov["last_date"].astype(str).str[:10]))]
    (app / "PhuLuc_B_source_log.md").write_text("\n".join(b) + "\n", encoding="utf-8")

    # ---------------- Phụ lục E
    s = cfg.get("sample", {})
    e = ["# Phụ lục E. Kiểm tra chất lượng dữ liệu và hướng dẫn tái lập (bản nháp)",
         "",
         "## E.1. Tham số chốt",
         "",
         _md(pd.DataFrame([
             ("Khoảng mẫu", f"{s.get('start')} đến {s.get('end')} (UTC, ngày cuối đóng băng)"),
             ("Tần suất", "Ngày (nến 00:00 đến 24:00 UTC)"),
             ("Độ trễ dữ liệu DefiLlama", f"{cfg.get('llama_lag_days', 1)} ngày; ffill tối đa {cfg.get('llama_ffill_limit', 3)} ngày"),
             ("Quy đổi Binance", "Giá USDT nhân USDT-USD (Yahoo) cùng ngày"),
             ("Dữ liệu on-chain", "Không sử dụng; thay bằng proxy DefiLlama và chênh lệch liên thị trường"),
             ("Phiên bản panel", f"panel_{version}.parquet"),
         ], columns=["Tham số", "Giá trị"])),
         "",
         "## E.2. Kết quả kiểm tra chất lượng",
         "",
         _md(qc),
         "",
         "## E.3. Số ngày vượt ngưỡng (tham khảo, chưa phải nhãn chính thức)",
         "",
         _md(ev.assign(threshold=ev["threshold"].map(lambda x: f"> {x:.1%}"))
             .pivot_table(index=["stablecoin", "measure"], columns="threshold", values="n_days_above").reset_index()),
         "",
         "## E.4. Tái lập",
         "",
         "Cài thư viện bằng `pip install -r requirements.txt`, sau đó chạy `python -m src.data.build_panel --version v1 --offline` "
         "để dựng lại panel chỉ từ bản lưu trong `data/raw/` (kết quả trùng khớp với bản bàn giao), hoặc bỏ `--offline` "
         "và thêm `--refresh` để tải lại toàn bộ từ nguồn. Bộ kiểm thử chạy bằng `pytest -q` và không cần mạng.",
         ]
    (app / "PhuLuc_E_qc_tai_lap.md").write_text("\n".join(e) + "\n", encoding="utf-8")
