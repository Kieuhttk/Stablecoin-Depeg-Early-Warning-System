from pathlib import Path
import yaml
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Chỉ đọc panel từ Code 1; không sửa dữ liệu gốc.
PANEL_PATH = (
    PROJECT_ROOT
    / "Stablecoin-EWS_Code1_backup_no_onchain"
    / "data"
    / "processed"
    / "panel.parquet"
)
CONFIG_PATH = PROJECT_ROOT / "config" / "labels.yaml"

with CONFIG_PATH.open("r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

CORE_COINS = set(CONFIG["core_coins"])
FEATURE_COLUMNS = CONFIG["feature_columns"]
LABELS_PATH = PROJECT_ROOT / "data" / "interim" / "labels.parquet"

# Đường dẫn đầu ra chính thức theo hợp đồng Code 2.
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "features.parquet"


KEYS = ["date", "coin"]

# Các biến dữ liệu được phép xem xét làm đặc trưng.
BASE_FEATURES = [
    col for col in FEATURE_COLUMNS
    if col in {
        "peg_deviation",
        "volume",
        "turnover",
        "range_hl",
        "xmkt_gap",
        "supply_change",
        "supply_eth_change",
        "supply_eth_share",
        "tvl_change",
        "btc_ret",
        "btc_vol",
        "eth_ret",
        "eth_vol",
        "usdt_usd",
    }
]
# Các cột nhãn và thông tin chia tập cần giữ lại.
# Những cột này không được dùng làm biến đầu vào mô hình.
LABEL_COLUMNS = [
    "split",
    "depeg_state_t",
    "onset_label_d1",
    "eligible_d1",
    "onset_label_d3",
    "eligible_d3",
    "hl_supported_onset",
    "hl_supported_d1",
    "hl_supported_eligible_d1",
    "hl_supported_d3",
    "hl_supported_eligible_d3",
]

# Variant labels and exact-horizon state benchmarks are management/target
# columns. They are merged into the handoff artifact, never into predictors.
for _source_name in CONFIG["sources"]:
    for _tau in CONFIG["thresholds"]:
        for _m in CONFIG["confirmation_days"]:
            _variant = f"{_source_name}_tau{_tau:.3f}_m{_m}"
            LABEL_COLUMNS.extend([
                f"state_{_variant}",
                f"onset_{_variant}",
            ])
            for _h in CONFIG["horizons"]:
                LABEL_COLUMNS.extend([
                    f"onset_label_{_variant}_d{_h}",
                    f"onset_label_{_variant}_eligible_d{_h}",
                    f"depeg_at_t_plus_d{_h}_{_variant}",
                    f"depeg_at_t_plus_d{_h}_eligible_{_variant}",
                ])

FORBIDDEN_FEATURES = {
    "depeg_state_t",
    "depeg_onset_t",
    "onset_label_d1",
    "eligible_d1",
    "onset_label_d3",
    "eligible_d3",
    "hl_supported_onset",
    "hl_supported_d1",
    "hl_supported_eligible_d1",
    "hl_supported_d3",
    "hl_supported_eligible_d3",
    "hl_suspect",
    "n_price_sources",
    "price_src",
    "hl_fixed",
    "is_missing_price",
    "src_disagree",
    "peg_deviation_cc",
    "peg_deviation_bn",
    "peg_deviation_min",
    "peg_deviation_hl",
    "peg_deviation_hl_cc",
    "peg_deviation_hl_bn",
    "peg_deviation_hl_min",
    "peg_deviation_hl_clean",
    "cc_close",
    "bn_close",
    "bn_close_usd",
    "bn_high_usd",
    "bn_low_usd",
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def safe_pct_change(series: pd.Series) -> pd.Series:
    """Tính phần trăm thay đổi và chuyển giá trị vô hạn thành thiếu."""
    result = series.pct_change(fill_method=None)
    return result.replace([float("inf"), float("-inf")], float("nan"))


def safe_diff(series: pd.Series) -> pd.Series:
    """Tính chênh lệch bậc một."""
    return series.diff()


def normalize_date(series: pd.Series) -> pd.Series:
    """Chuẩn hóa thời gian về ngày UTC không có thông tin múi giờ."""
    return (
        pd.to_datetime(series, errors="raise", utc=True)
        .dt.tz_localize(None)
        .dt.normalize()
    )


def normalize_coin(series: pd.Series) -> pd.Series:
    """Chuẩn hóa mã stablecoin."""
    return series.astype("string").str.upper().str.strip()


def check_unique_keys(
    df: pd.DataFrame,
    table_name: str,
) -> None:
    """Báo lỗi nếu bảng có khóa date-coin bị trùng."""
    duplicated = df.duplicated(KEYS, keep=False)

    if duplicated.any():
        examples = df.loc[duplicated, KEYS].head(10)

        raise ValueError(
            f"{table_name} có khóa date-coin bị trùng. Ví dụ:\n"
            f"{examples.to_string(index=False)}"
        )


# ============================================================
# LOAD PANEL
# ============================================================

def load_panel() -> pd.DataFrame:
    """Đọc panel gốc và chuẩn hóa khóa thời gian, mã stablecoin."""
    if not PANEL_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy panel: {PANEL_PATH}"
        )

    panel = pd.read_parquet(PANEL_PATH)

    required = {
        "timestamp",
        "stablecoin",
        "price",
        "peg_deviation",
    }
    missing = required.difference(panel.columns)

    if missing:
        raise ValueError(
            f"Panel thiếu cột bắt buộc: {sorted(missing)}"
        )

    df = panel.copy()

    df["date"] = normalize_date(df["timestamp"])
    df["coin"] = normalize_coin(df["stablecoin"])

    df = df[df["coin"].isin(CORE_COINS)].copy()
    df = df.sort_values(KEYS).reset_index(drop=True)

    check_unique_keys(df, "Panel")

    return df


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def build_features(panel: pd.DataFrame) -> pd.DataFrame:
    """Tạo đặc trưng theo từng stablecoin, không dùng dữ liệu tương lai."""
    required = {
        "timestamp",
        "stablecoin",
        "price",
        "peg_deviation",
    }
    missing = required.difference(panel.columns)

    if missing:
        raise ValueError(
            f"Panel thiếu cột bắt buộc: {sorted(missing)}"
        )

    df = panel.copy()

    df["date"] = normalize_date(df["timestamp"])
    df["coin"] = normalize_coin(df["stablecoin"])

    df = df[df["coin"].isin(CORE_COINS)].copy()
    df = df.sort_values(KEYS).reset_index(drop=True)

    check_unique_keys(df, "Panel sau khi lọc stablecoin")

    missing_base = sorted(set(BASE_FEATURES) - set(df.columns))

    if missing_base:
        raise ValueError(
            "Panel thiếu các cột đặc trưng đầu vào bắt buộc: "
            f"{missing_base}"
        )

    # Chỉ giữ khóa và các đặc trưng đầu vào đã được phê duyệt.
    out = df[KEYS + BASE_FEATURES].copy()

    grouped = df.groupby("coin", sort=False)

    # Biến động giá theo ngày.
    out["price_return_1d"] = grouped["price"].transform(
        safe_pct_change
    )

    out["price_change_1d"] = grouped["price"].transform(
        safe_diff
    )

    # Biến động độ lệch neo.
    out["peg_deviation_change_1d"] = (
        grouped["peg_deviation"].transform(safe_diff)
    )

    # Biến động phần trăm của khối lượng và doanh số.
    for col in ["volume", "turnover"]:
        if col in df.columns:
            out[f"{col}_pct_change_1d"] = (
                grouped[col].transform(safe_pct_change)
            )

    # Chênh lệch bậc một của các biến cung và TVL.
    for col in [
        "supply_change",
        "supply_eth_change",
        "tvl_change",
    ]:
        if col in df.columns:
            out[f"{col}_change_1d"] = (
                grouped[col].transform(safe_diff)
            )

    # Thống kê lợi suất quá khứ, tính riêng từng stablecoin.
    # Rolling chỉ sử dụng dữ liệu đến ngày hiện tại.
    for window in [7, 30]:
        out[f"price_return_mean_{window}d"] = (
            out.groupby("coin", sort=False)["price_return_1d"]
            .transform(
                lambda s: s.rolling(
                    window=window,
                    min_periods=window,
                ).mean()
            )
        )

        out[f"price_return_vol_{window}d"] = (
            out.groupby("coin", sort=False)["price_return_1d"]
            .transform(
                lambda s: s.rolling(
                    window=window,
                    min_periods=window,
                ).std()
            )
        )

    # Chỉ báo thiếu dữ liệu xmkt_gap.
    # Không tự động thay giá trị thiếu bằng 0.
    if "xmkt_gap" in df.columns:
        out["xmkt_gap_missing"] = (
            df["xmkt_gap"].isna().astype("int8")
        )

    # Không cho phép biến nhãn hoặc biến kiểm tra chất lượng
    # dữ liệu xuất hiện trong tập đặc trưng.
    feature_columns = [
        col for col in out.columns
        if col not in KEYS
    ]

    forbidden_found = (
        set(feature_columns) & FORBIDDEN_FEATURES
    )

    if forbidden_found:
        raise ValueError(
            "Phát hiện biến không được phép trong tập đặc trưng: "
            f"{sorted(forbidden_found)}"
        )

    # Chuyển giá trị vô hạn thành NaN.
    numeric_columns = out.select_dtypes(
        include="number"
    ).columns

    out[numeric_columns] = out[numeric_columns].replace(
        [float("inf"), float("-inf")],
        float("nan"),
    )

    check_unique_keys(out, "Bảng đặc trưng")

    return out


# ============================================================
# MERGE LABELS
# ============================================================

def merge_labels(features: pd.DataFrame) -> pd.DataFrame:
    """Ghép đặc trưng với nhãn và thông tin chia tập dữ liệu."""
    if not LABELS_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file nhãn: {LABELS_PATH}"
        )

    labels = pd.read_parquet(LABELS_PATH)

    required_labels = {
        "date",
        "coin",
        "split",
        "depeg_state_t",
        "onset_label_d1",
        "eligible_d1",
        "onset_label_d3",
        "eligible_d3",
    }
    required_labels.update(LABEL_COLUMNS)

    missing = required_labels.difference(labels.columns)

    if missing:
        raise ValueError(
            f"File nhãn thiếu cột bắt buộc: {sorted(missing)}"
        )

    label_columns = [
        col for col in LABEL_COLUMNS
        if col in labels.columns
    ]

    label_data = labels[["date", "coin"] + label_columns].copy()

    label_data["date"] = normalize_date(label_data["date"])
    label_data["coin"] = normalize_coin(label_data["coin"])

    label_data = label_data[
        label_data["coin"].isin(CORE_COINS)
    ].copy()

    check_unique_keys(label_data, "File nhãn")

    # Chuẩn hóa khóa features trước khi ghép.
    feature_data = features.copy()
    feature_data["date"] = normalize_date(feature_data["date"])
    feature_data["coin"] = normalize_coin(feature_data["coin"])

    check_unique_keys(feature_data, "Bảng đặc trưng trước khi ghép")

    merged = feature_data.merge(
        label_data,
        on=KEYS,
        how="left",
        validate="one_to_one",
        indicator=True,
    )

    unmatched = int((merged["_merge"] != "both").sum())

    if unmatched:
        examples = merged.loc[
            merged["_merge"] != "both",
            KEYS,
        ].head(10)

        raise ValueError(
            f"Có {unmatched} dòng đặc trưng không ghép được với nhãn. "
            "Ví dụ:\n"
            f"{examples.to_string(index=False)}"
        )

    merged = merged.drop(columns="_merge")

    # Không điền nhãn NA thành 0: các NA có thể là những ngày
    # không đủ dữ liệu tương lai để xác định kết quả.
    check_unique_keys(merged, "Bảng sau khi ghép nhãn")

    return merged


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    """Chạy quy trình tạo và lưu bảng đặc trưng."""
    print("Đang đọc panel...")
    panel = load_panel()

    print(f"Số dòng panel sau lọc: {len(panel):,}")
    print(f"Số stablecoin: {panel['coin'].nunique()}")

    print("Đang tạo đặc trưng...")
    features = build_features(panel)

    print("Đang ghép nhãn...")
    result = merge_labels(features)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Chuẩn hóa schema bàn giao; giữ nguyên khóa nội bộ
    # date/coin để không ảnh hưởng quá trình tạo feature và ghép nhãn.
    public_result = result.rename(
        columns={
            "date": "timestamp",
            "coin": "stablecoin",
        }
    ).copy()

    # Mốc ngày được biểu diễn tại 00:00 UTC.
    public_result["timestamp"] = pd.to_datetime(
        public_result["timestamp"],
        utc=True,
    )

    if public_result[["timestamp", "stablecoin"]].isna().any().any():
        raise ValueError("Schema đầu ra có khóa timestamp/stablecoin bị thiếu.")

    if public_result.duplicated(["timestamp", "stablecoin"]).any():
        raise ValueError("Schema đầu ra có khóa timestamp/stablecoin bị trùng.")

    public_result.to_parquet(
        OUTPUT_PATH,
        index=False,
    )

    print("\nHOÀN TẤT")
    print(f"File đầu ra: {OUTPUT_PATH}")
    print(f"Số dòng: {len(result):,}")
    print(f"Số cột: {len(result.columns):,}")
    print(
        "Số dòng trùng khóa:",
        int(result.duplicated(KEYS).sum()),
    )

    print("\nSố nhãn dương:")
    for col in ["onset_label_d1", "onset_label_d3"]:
        if col in result.columns:
            print(f"{col}: {result[col].sum()}")

    print("\nSố nhãn thiếu:")
    for col in ["onset_label_d1", "onset_label_d3"]:
        if col in result.columns:
            print(f"{col}: {result[col].isna().sum()}")

    print("\nPhân bố theo tập dữ liệu:")
    if "split" in result.columns:
        print(result["split"].value_counts(dropna=False))

    print("\nCác cột đầu ra:")
    print(result.columns.tolist())


if __name__ == "__main__":
    main()
