
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[2]
PANEL_PATH = (
    ROOT
    / "Stablecoin-EWS_Code1_backup_no_onchain"
    / "data"
    / "processed"
    / "panel.parquet"
)
FIGURES_PATH = ROOT / "outputs" / "figures"

COINS = ["USDT", "USDC", "DAI"]
COLORS = {
    "USDT": "#2878B5",
    "USDC": "#E07B39",
    "DAI": "#27966F",
}
START_DATE = "2020-01-01"
END_DATE = "2026-10-16"


def load_panel():
    if not PANEL_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy panel: {PANEL_PATH}")

    df = pd.read_parquet(PANEL_PATH)

    required = {"timestamp", "stablecoin", "peg_deviation_hl_clean"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Panel thiếu các cột: {sorted(missing)}")

    df["timestamp"] = pd.to_datetime(
        df["timestamp"], utc=True, errors="coerce"
    )
    df["stablecoin"] = df["stablecoin"].astype(str).str.upper()
    df["peg_deviation_hl_clean"] = pd.to_numeric(
        df["peg_deviation_hl_clean"], errors="coerce"
    )

    start = pd.Timestamp(START_DATE, tz="UTC")
    end = pd.Timestamp(END_DATE, tz="UTC")

    df = df[
        df["stablecoin"].isin(COINS)
        & df["timestamp"].between(start, end)
    ].copy()

    return df.sort_values(["stablecoin", "timestamp"])


def plot_peg_deviation(df):
    fig, ax = plt.subplots(figsize=(14, 6))

    for coin in COINS:
        part = df[df["stablecoin"] == coin]
        ax.plot(
            part["timestamp"],
            part["peg_deviation_hl_clean"] * 100,
            label=coin,
            color=COLORS[coin],
            linewidth=0.85,
            alpha=0.85,
        )

    ax.axhline(
        1.0,
        color="#B22222",
        linestyle="--",
        linewidth=1.2,
        label="Ngưỡng depeg 1%",
    )
    ax.axhline(
        0.5,
        color="grey",
        linestyle=":",
        linewidth=0.9,
        label="Ngưỡng độ nhạy 0,5%",
    )

    ax.set_title(
        "Lịch sử độ lệch neo giá của USDT, USDC và DAI",
        loc="left",
        fontsize=14,
        fontweight="bold",
    )
    ax.set_xlabel("Ngày")
    ax.set_ylabel("Độ lệch neo giá (%)")
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(axis="y", alpha=0.25)
    ax.legend(ncol=4, frameon=False)
    fig.tight_layout()

    output = FIGURES_PATH / "F01_peg_deviation_history.png"
    fig.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Đã tạo: {output}")


def plot_codepeg_heatmap(df):
    # Tỷ lệ ngày cùng vượt ngưỡng 1% trong từng cặp stablecoin.
    # Dùng peg_deviation_hl_clean nhất quán với nhãn chính.
    wide = df.pivot(
        index="timestamp",
        columns="stablecoin",
        values="peg_deviation_hl_clean",
    ).reindex(columns=COINS)

    exceed = wide.gt(0.01)
    exceed = exceed.where(wide.notna())

    pair_matrix = pd.DataFrame(index=COINS, columns=COINS, dtype=float)
    for coin_a in COINS:
        for coin_b in COINS:
            if coin_a == coin_b:
                # F05 describes co-depeg between distinct coins; self-pairs
                # are undefined and must not look like a measured 100% rate.
                pair_matrix.loc[coin_a, coin_b] = float("nan")
                continue

            pair = exceed[[coin_a, coin_b]].dropna()
            pair_matrix.loc[coin_a, coin_b] = (
                (pair[coin_a] & pair[coin_b]).mean()
                if not pair.empty
                else float("nan")
            )

    fig, ax = plt.subplots(figsize=(7, 5.5))
    sns.heatmap(
        pair_matrix.astype(float),
        annot=True,
        fmt=".1%",
        cmap="YlOrRd",
        vmin=0,
        vmax=1,
        square=True,
        linewidths=0.5,
        cbar_kws={"label": "Tỷ lệ ngày cả hai cùng vượt ngưỡng 1%"},
        ax=ax,
    )
    ax.grid(False)
    for position in range(len(COINS)):
        ax.text(
            position + 0.5,
            position + 0.5,
            "N/A",
            ha="center",
            va="center",
            color="#555555",
            fontsize=10,
        )
    ax.set_title(
        "Đồng lệch neo giá giữa các stablecoin",
        loc="left",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xlabel("Stablecoin")
    ax.set_ylabel("Stablecoin")
    fig.tight_layout()

    output = FIGURES_PATH / "F05_codepeg_heatmap.png"
    fig.savefig(output, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Đã tạo: {output}")


def main():
    FIGURES_PATH.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="notebook")

    df = load_panel()
    print("Số dòng theo stablecoin:")
    print(df.groupby("stablecoin").size().to_string())

    plot_peg_deviation(df)
    plot_codepeg_heatmap(df)


if __name__ == "__main__":
    main()
