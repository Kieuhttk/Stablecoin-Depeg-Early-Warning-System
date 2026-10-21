

from pathlib import Path

import pandas as pd
import yaml


# ============================================================
# 1. Cáº¤U HÃŒNH
# ============================================================

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "labels.yaml"

with CONFIG_PATH.open("r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

PANEL_PATH = ROOT / CONFIG["panel_path"]
OUTPUT_PATH = ROOT / CONFIG["labels_output"]
TABLES_PATH = ROOT / CONFIG["tables_output"]

CORE_COINS = [str(coin).upper() for coin in CONFIG["core_coins"]]
SPLITS = {
    name: (values["start"], values["end"])
    for name, values in CONFIG["splits"].items()
}

PRIMARY_SOURCE = CONFIG["primary"]["src"]
PRIMARY_TAU = float(CONFIG["primary"]["tau"])
PRIMARY_M = int(CONFIG["primary"]["m"])

SOURCES = CONFIG["sources"]
THRESHOLDS = [float(value) for value in CONFIG["thresholds"]]
CONFIRMATION_DAYS = [
    int(value) for value in CONFIG["confirmation_days"]
]
HORIZONS = [int(value) for value in CONFIG["horizons"]]

SUPPORT_CLOSE_THRESHOLD = 0.005



# ============================================================
# 2. HÃ€M XÃC Äá»ŠNH Cá»˜T VÃ€ CHIA Táº¬P Dá»® LIá»†U
# ============================================================

def find_column(df, candidates, description):
    """TÃ¬m tÃªn cá»™t trong danh sÃ¡ch tÃªn cÃ³ thá»ƒ sá»­ dá»¥ng."""
    for col in candidates:
        if col in df.columns:
            return col

    raise KeyError(
        f"KhÃ´ng tÃ¬m tháº¥y cá»™t {description}. "
        f"CÃ¡c cá»™t Ä‘Ã£ thá»­: {candidates}. "
        f"CÃ¡c cá»™t hiá»‡n cÃ³: {df.columns.tolist()}"
    )


def assign_split(dates):
    """GÃ¡n train, validation hoáº·c test theo thá»i gian."""
    result = pd.Series(index=dates.index, dtype="object")

    for split_name, (start, end) in SPLITS.items():
        mask = dates.between(
            pd.Timestamp(start),
            pd.Timestamp(end),
        )
        result.loc[mask] = split_name

    return result


# ============================================================
# 3. Táº O TRáº NG THÃI DEPEG VÃ€ NHÃƒN ONSET
# ============================================================


def build_group_labels(group, deviation_col, tau, m):
    """
    Táº¡o tráº¡ng thÃ¡i vÆ°á»£t ngÆ°á»¡ng vÃ  onset depeg.

    raw_state:
        1 náº¿u deviation > tau
        0 náº¿u deviation <= tau
        NA náº¿u thiáº¿u dá»¯ liá»‡u.

    state:
        Vá»›i m=1, báº±ng raw_state.
        Vá»›i m>1, chá»‰ báº±ng 1 khi Ä‘Ã£ cÃ³ Ä‘á»§ m ngÃ y liÃªn tiáº¿p
        vÆ°á»£t ngÆ°á»¡ng; ngÃ y chÆ°a Ä‘á»§ xÃ¡c nháº­n giá»¯ NA náº¿u Ä‘ang
        vÆ°á»£t ngÆ°á»¡ng, cÃ²n ngÃ y dÆ°á»›i ngÆ°á»¡ng báº±ng 0.

    onset:
        ÄÃ¡nh dáº¥u ngÃ y Ä‘áº§u tiÃªn cá»§a chuá»—i Ä‘Æ°á»£c xÃ¡c nháº­n,
        khÃ´ng Ä‘Ã¡nh dáº¥u cÃ¡c ngÃ y tiáº¿p theo trong cÃ¹ng chuá»—i.
    """
    if m < 1:
        raise ValueError("m pháº£i lá»›n hÆ¡n hoáº·c báº±ng 1.")

    group = group.sort_values("date").copy()

    deviation = pd.to_numeric(
        group[deviation_col],
        errors="coerce",
    )

    raw_state = pd.Series(
        pd.NA,
        index=group.index,
        dtype="Int64",
    )
    valid = deviation.notna()
    raw_state.loc[valid] = (
        deviation.loc[valid] > tau
    ).astype("int64")

    state = pd.Series(
        pd.NA,
        index=group.index,
        dtype="Int64",
    )
    state.loc[valid & (raw_state == 0)] = 0

    onset = pd.Series(
        0,
        index=group.index,
        dtype="int64",
    )

    dates = group["date"]
    splits = group["split"]

    for pos in range(len(group)):
        if pd.isna(raw_state.iloc[pos]) or raw_state.iloc[pos] != 1:
            continue

        # Chá»‰ xÃ¡c nháº­n náº¿u Ä‘á»§ m ngÃ y liÃªn tá»¥c, cÃ¹ng split,
        # vÃ  má»i ngÃ y Ä‘á»u cÃ³ dá»¯ liá»‡u vÆ°á»£t ngÆ°á»¡ng.
        end_pos = pos + m
        if end_pos > len(group):
            continue

        window_raw = raw_state.iloc[pos:end_pos]
        window_dates = dates.iloc[pos:end_pos]
        window_splits = splits.iloc[pos:end_pos]

        if window_raw.isna().any() or not (window_raw == 1).all():
            continue

        if window_splits.isna().any() or window_splits.nunique() != 1:
            continue

        if not (window_dates.diff().dropna().dt.days == 1).all():
            continue

        # Tráº¡ng thÃ¡i depeg Ä‘Æ°á»£c xÃ¡c nháº­n tá»« ngÃ y Ä‘áº§u chuá»—i.
        state.iloc[pos + m - 1] = 1

        # Onset chá»‰ lÃ  ngÃ y Ä‘áº§u tiÃªn cá»§a chuá»—i.
        if pos > 0:
            prev_date = dates.iloc[pos - 1]
            current_date = dates.iloc[pos]
            prev_state = raw_state.iloc[pos - 1]

            consecutive_prev = (
                (current_date - prev_date).days == 1
            )
            same_prev_split = (
                splits.iloc[pos] == splits.iloc[pos - 1]
            )

            # KhÃ´ng ná»‘i chuá»—i qua ngÃ y thiáº¿u hoáº·c split khÃ¡c.
            if (
                consecutive_prev
                and same_prev_split
                and pd.notna(prev_state)
                and prev_state == 1
            ):
                continue

        onset.iloc[pos] = 1

    group["raw_state"] = raw_state
    group["state"] = state
    group["onset"] = onset

    return group



def add_variant_labels(df, deviation_col, source_name, tau, m):
    """Táº¡o state vÃ  onset cho má»™t tá»• há»£p nguá»“n, ngÆ°á»¡ng vÃ  m."""
    state_col = f"state_{source_name}_tau{tau:.3f}_m{m}"
    onset_col = f"onset_{source_name}_tau{tau:.3f}_m{m}"
    raw_state_col = f"raw_state_{source_name}_tau{tau:.3f}_m{m}"

    pieces = []

    for _, group in df.groupby("coin", sort=False):
        labeled = build_group_labels(
            group,
            deviation_col=deviation_col,
            tau=tau,
            m=m,
        )

        pieces.append(
            labeled[["raw_state", "state", "onset"]]
        )

    result = pd.concat(pieces).sort_index()

    df[state_col] = result["state"]
    df[onset_col] = result["onset"]
    df[raw_state_col] = result["raw_state"]

    return state_col, onset_col, raw_state_col


def add_benchmark_targets(df, state_col, suffix, horizons):
    """Create exact-horizon depeg-state targets, independent of onset eligibility."""
    target_values = {h: {} for h in horizons}
    eligible_values = {h: {} for h in horizons}
    for h in horizons:
        target_col = f"depeg_at_t_plus_d{h}_{suffix}"
        eligible_col = f"depeg_at_t_plus_d{h}_eligible_{suffix}"
        eligible_values[h] = {idx: 0 for idx in df.index}

    for _, group in df.groupby("coin", sort=False):
        group = group.sort_values("date")
        indices = group.index.tolist()
        states = group[state_col].tolist()
        dates = group["date"].tolist()
        splits = group["split"].tolist()

        for pos, idx in enumerate(indices):
            for h in horizons:
                target_pos = pos + h
                if target_pos >= len(indices):
                    continue
                future_positions = range(pos + 1, target_pos + 1)
                if any(
                    (dates[p] - dates[p - 1]).days != 1
                    or pd.isna(splits[p])
                    or splits[p] != splits[pos]
                    for p in future_positions
                ):
                    continue
                value = states[target_pos]
                if pd.isna(value):
                    continue
                target_values[h][idx] = int(value)
                eligible_values[h][idx] = 1

    for h in horizons:
        target_col = f"depeg_at_t_plus_d{h}_{suffix}"
        eligible_col = f"depeg_at_t_plus_d{h}_eligible_{suffix}"
        df[target_col] = pd.Series(
            pd.array([target_values[h].get(idx, pd.NA) for idx in df.index], dtype="Int64"),
            index=df.index,
        )
        df[eligible_col] = pd.Series(
            [eligible_values[h][idx] for idx in df.index], index=df.index, dtype="int8"
        )

    return df


# ============================================================
# 4. Táº O NHÃƒN Dá»° BÃO TRONG 1 VÃ€ 3 NGÃ€Y
# ============================================================


def add_targets(
    df,
    state_col,
    onset_col,
    prefix,
    horizons,
    confirmation_days=1,
    raw_state_col=None,
):
    """
    Create an onset target over the next h days.

    Prediction rows require state_t == 0. Future observations must be
    consecutive, remain within the same split, and have observed raw states.
    For m > 1, raw_state_col is required so an unconfirmed exceedance (whose
    confirmed state is intentionally NA) is not confused with missing data.
    The extra m-1 observations after the horizon are used only to determine
    whether an onset at the horizon end is confirmed.
    """
    if confirmation_days > 1 and raw_state_col is None:
        raise ValueError(
            "raw_state_col is required when confirmation_days > 1."
        )
    if raw_state_col is not None and raw_state_col not in df.columns:
        raise ValueError(f"Raw-state column not found: {raw_state_col}")

    target_values = {h: {} for h in horizons}
    eligible_values = {h: {idx: 0 for idx in df.index} for h in horizons}

    for _, group in df.groupby("coin", sort=False):
        group = group.sort_values("date")
        indices = group.index.tolist()

        states = group[state_col].tolist()
        onsets = group[onset_col].tolist()
        observed_states = (
            group[raw_state_col].tolist()
            if raw_state_col is not None
            else states
        )
        dates = group["date"].tolist()
        splits = group["split"].tolist()

        for pos, idx in enumerate(indices):
            current_state = states[pos]

            if pd.isna(current_state) or current_state != 0:
                continue

            for h in horizons:
                required_future = h + max(
                    confirmation_days - 1, 0
                )
                end_pos = pos + required_future

                if end_pos >= len(indices):
                    continue

                future_positions = list(range(pos + 1, end_pos + 1))

                # raw_state distinguishes an observed but unconfirmed
                # exceedance from a missing deviation. Never infer that NA
                # raw data means no depeg.
                if any(pd.isna(observed_states[p]) for p in future_positions):
                    continue

                if any(
                    pd.isna(splits[p]) or splits[p] != splits[pos]
                    or (dates[p] - dates[p - 1]).days != 1
                    for p in future_positions
                ):
                    continue

                # Chá»‰ tÃ­nh onset trong t+1 Ä‘áº¿n t+h.
                target_positions = range(pos + 1, pos + h + 1)
                target_value = int(
                    any(onsets[p] == 1 for p in target_positions)
                )

                target_values[h][idx] = target_value
                eligible_values[h][idx] = 1

    for h in horizons:
        target_col = (
            f"{prefix}_d{h}" if prefix else f"onset_label_d{h}"
        )
        eligible_col = (
            f"{prefix}_eligible_d{h}"
            if prefix
            else f"eligible_d{h}"
        )
        df[target_col] = pd.Series(
            pd.array([target_values[h].get(idx, pd.NA) for idx in df.index], dtype="Int64"),
            index=df.index,
        )
        df[eligible_col] = pd.Series(
            [eligible_values[h][idx] for idx in df.index], index=df.index, dtype="int8"
        )

    return df



# ============================================================
# 5. Táº O NHÃƒN Há»– TRá»¢ hl_supported
# ============================================================

def add_hl_supported(df, primary_onset_col):
    """
    Má»™t onset Ä‘Æ°á»£c há»— trá»£ náº¿u:
    - Äá»™ lá»‡ch giÃ¡ Ä‘Ã³ng cá»­a cá»§a chÃ­nh coin > 0.5%; hoáº·c
    - CÃ³ coin khÃ¡c trong cÃ¹ng ngÃ y cÃ³ Ä‘á»™ lá»‡ch intraday >= 1%.

    ÄÃ¢y lÃ  nhÃ£n kiá»ƒm tra Ä‘á»™ nháº¡y, khÃ´ng thay nhÃ£n chÃ­nh.
    """
    df["hl_supported_onset"] = 0

    close_col = SOURCES["cl"]
    intraday_col = SOURCES["hl"]

    required_cols = [close_col, intraday_col]

    for col in required_cols:
        if col not in df.columns:
            raise KeyError(f"Thiáº¿u cá»™t cáº§n thiáº¿t Ä‘á»ƒ táº¡o hl_supported: {col}")

    daily_other_intraday = {}

    for date, day_group in df.groupby("date"):
        daily_other_intraday[date] = {
            coin: bool(
                (
                    pd.to_numeric(
                        other_group[intraday_col],
                        errors="coerce",
                    ) >= PRIMARY_TAU
                ).any()
            )
            for coin, other_group in day_group.groupby("coin")
        }

    for idx in df.index[df[primary_onset_col] == 1]:
        coin = df.loc[idx, "coin"]
        date = df.loc[idx, "date"]

        own_close = pd.to_numeric(
            pd.Series([df.loc[idx, close_col]]),
            errors="coerce",
        ).iloc[0]

        close_support = (
            pd.notna(own_close)
            and own_close > SUPPORT_CLOSE_THRESHOLD
        )

        other_support = any(
            supported
            for other_coin, supported
            in daily_other_intraday.get(date, {}).items()
            if other_coin != coin
        )

        if close_support or other_support:
            df.loc[idx, "hl_supported_onset"] = 1

    return df


# ============================================================
# 6. Báº¢NG THá»NG KÃŠ
# ============================================================

def save_primary_counts(df):
    rows = []

    for split in SPLITS:
        split_df = df[df["split"] == split]

        for h in HORIZONS:
            eligible_col = f"eligible_d{h}"
            target_col = f"onset_label_d{h}"

            eligible = split_df[eligible_col] == 1
            targets = split_df.loc[eligible, target_col].dropna()

            positive = int((targets == 1).sum())
            negative = int((targets == 0).sum())

            rows.append({
                "split": split,
                "horizon_days": h,
                "eligible_samples": len(targets),
                "positive_samples": positive,
                "negative_samples": negative,
            })

    pd.DataFrame(rows).to_csv(
        TABLES_PATH / "label_primary_counts.csv",
        index=False,
    )


def save_variant_counts(df, variant_columns):
    rows = []

    for variant_name, onset_col in variant_columns.items():
        for split in SPLITS:
            subset = df[df["split"] == split]
            onset_rows = subset[onset_col] == 1

            rows.append({
                "variant": variant_name,
                "split": split,
                "onset_rows": int(onset_rows.sum()),
                "distinct_event_dates": int(
                    subset.loc[onset_rows, "date"].nunique()
                ),
            })

    pd.DataFrame(rows).to_csv(
        TABLES_PATH / "label_variant_onset_counts.csv",
        index=False,
    )



def save_event_dates(df, primary_onset_col):
    """Xuáº¥t sá»± kiá»‡n depeg theo coin, nguá»“n, ngÆ°á»¡ng vÃ  sá»‘ ngÃ y xÃ¡c nháº­n."""
    rows = []

    for source_name, deviation_col in SOURCES.items():
        for tau in THRESHOLDS:
            for m in CONFIRMATION_DAYS:
                state_col = f"state_{source_name}_tau{tau:.3f}_m{m}"
                onset_col = f"onset_{source_name}_tau{tau:.3f}_m{m}"

                if state_col not in df.columns or onset_col not in df.columns:
                    continue

                for coin, coin_df in df.groupby("coin"):
                    coin_df = coin_df.sort_values("date").reset_index(drop=True)
                    onset_positions = coin_df.index[
                        coin_df[onset_col].eq(1)
                    ].tolist()

                    for pos in onset_positions:
                        event = coin_df.iloc[pos]
                        event_date = event["date"]
                        split = event["split"]

                        # Äáº¿m toÃ n bá»™ chuá»—i ngÃ y vÆ°á»£t ngÆ°á»¡ng liÃªn tá»¥c,
                        # khÃ´ng Ä‘i qua ngÃ y thiáº¿u dá»¯ liá»‡u hoáº·c ranh giá»›i split.
                        duration = 0
                        max_deviation = float("-inf")
                        expected_date = event_date

                        for j in range(pos, len(coin_df)):
                            day = coin_df.iloc[j]
                            deviation = pd.to_numeric(
                                pd.Series([day[deviation_col]]),
                                errors="coerce",
                            ).iloc[0]

                            if (
                                day["split"] != split
                                or day["date"] != expected_date
                                or pd.isna(deviation)
                                or deviation <= tau
                            ):
                                break

                            duration += 1
                            max_deviation = max(max_deviation, float(deviation))
                            expected_date += pd.Timedelta(days=1)

                        rows.append({
                            "coin": coin,
                            "source": source_name,
                            "threshold": tau,
                            "confirmation_days": m,
                            "event_date": event_date,
                            "split": split,
                            "max_deviation": (
                                max_deviation if duration else float("nan")
                            ),
                            "duration_days": duration,
                        })

    columns = [
        "coin", "source", "threshold", "confirmation_days",
        "event_date", "split", "max_deviation", "duration_days",
    ]
    pd.DataFrame(rows, columns=columns).to_csv(
        TABLES_PATH / "T01_depeg_events.csv",
        index=False,
    )



# ============================================================
# 7. CHáº Y TOÃ€N Bá»˜ QUY TRÃŒNH
# ============================================================

def main():
    if not PANEL_PATH.exists():
        raise FileNotFoundError(
            f"KhÃ´ng tÃ¬m tháº¥y panel: {PANEL_PATH}"
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TABLES_PATH.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(PANEL_PATH)
    save_descriptive_stats(df)

    # Tá»± nháº­n diá»‡n tÃªn cá»™t ngÃ y vÃ  coin.
    date_col = find_column(
        df,
        ["date", "timestamp", "datetime", "time"],
        "ngÃ y",
    )
    coin_col = find_column(
        df,
        ["coin", "stablecoin", "symbol", "asset"],
        "stablecoin",
    )

    df = df.rename(columns={
        date_col: "date",
        coin_col: "coin",
    })

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
        utc=True,
    ).dt.tz_localize(None).dt.normalize()

    df["coin"] = df["coin"].astype(str).str.upper()

    # Chá»‰ sá»­ dá»¥ng ba stablecoin trong pháº¡m vi nghiÃªn cá»©u.
    df = df[df["coin"].isin(CORE_COINS)].copy()

    # Kiá»ƒm tra cá»™t nguá»“n cáº§n thiáº¿t.
    for col in SOURCES.values():
        if col not in df.columns:
            raise KeyError(
                f"KhÃ´ng tÃ¬m tháº¥y cá»™t nguá»“n '{col}' trong panel."
            )

    if df["date"].isna().any():
        raise ValueError("CÃ³ dÃ²ng khÃ´ng xÃ¡c Ä‘á»‹nh Ä‘Æ°á»£c ngÃ y.")

    if df.duplicated(["coin", "date"]).any():
        duplicated = df.loc[
            df.duplicated(["coin", "date"], keep=False),
            ["coin", "date"],
        ].head(10)

        raise ValueError(
            "Dá»¯ liá»‡u cÃ³ coin-date bá»‹ trÃ¹ng. "
            f"Má»™t sá»‘ dÃ²ng trÃ¹ng:\n{duplicated}"
        )

    df = df.sort_values(["coin", "date"]).reset_index(drop=True)
    df["split"] = assign_split(df["date"])

    # KhÃ´ng sá»­ dá»¥ng cÃ¡c cá»™t kiá»ƒm tra cháº¥t lÆ°á»£ng dá»¯ liá»‡u
    # lÃ m biáº¿n Ä‘áº§u vÃ o cá»§a nhÃ£n.
    df = df[df["split"].notna()].copy()
    df = df.sort_values(["coin", "date"]).reset_index(drop=True)

    # --------------------------------------------------------
    # A. Táº¡o táº¥t cáº£ biáº¿n state/onset Ä‘á»ƒ phÃ¢n tÃ­ch Ä‘á»™ nháº¡y
    # --------------------------------------------------------
    variant_columns = {}

    for source_name, deviation_col in SOURCES.items():
        for tau in THRESHOLDS:
            for m in CONFIRMATION_DAYS:
                state_col, onset_col, raw_state_col = add_variant_labels(
                    df,
                    deviation_col=deviation_col,
                    source_name=source_name,
                    tau=tau,
                    m=m,
                )

                variant_name = (
                    f"{source_name}_tau{tau:.3f}_m{m}"
                )
                variant_columns[variant_name] = onset_col
                df = add_targets(
                    df=df,
                    state_col=state_col,
                    onset_col=onset_col,
                    prefix=f"onset_label_{variant_name}",
                    horizons=HORIZONS,
                    confirmation_days=m,
                    raw_state_col=raw_state_col if m > 1 else None,
                )
                df = add_benchmark_targets(
                    df=df,
                    state_col=state_col,
                    suffix=variant_name,
                    horizons=HORIZONS,
                )

    # --------------------------------------------------------
    # B. XÃ¡c Ä‘á»‹nh nhÃ£n chÃ­nh
    # --------------------------------------------------------
    primary_state_col = (
        f"state_{PRIMARY_SOURCE}_tau{PRIMARY_TAU:.3f}_m{PRIMARY_M}"
    )
    primary_onset_col = (
        f"onset_{PRIMARY_SOURCE}_tau{PRIMARY_TAU:.3f}_m{PRIMARY_M}"
    )

    df["depeg_state_t"] = df[primary_state_col]
    df["depeg_onset_t"] = df[primary_onset_col]

    # Táº¡o target vá»›i tÃªn cá»™t thá»‘ng nháº¥t:
    # onset_label_d1, onset_label_d3,
    # eligible_d1, eligible_d3.
    df = add_targets(
        df=df,
        state_col=primary_state_col,
        onset_col=primary_onset_col,
        prefix="",
        horizons=HORIZONS,
        confirmation_days=PRIMARY_M,
    )

    # --------------------------------------------------------
    # C. NhÃ£n kiá»ƒm tra Ä‘á»™ nháº¡y hl_supported
    # --------------------------------------------------------
    df = add_hl_supported(df, primary_onset_col)

    df = add_targets(
        df=df,
        state_col=primary_state_col,
        onset_col="hl_supported_onset",
        prefix="hl_supported",
        horizons=HORIZONS,
        confirmation_days=PRIMARY_M,
    )

    # --------------------------------------------------------
    # D. Xuáº¥t dá»¯ liá»‡u vÃ  báº£ng thá»‘ng kÃª
    # --------------------------------------------------------
    df.to_parquet(OUTPUT_PATH, index=False)

    save_descriptive_stats(df)
    save_primary_counts(df)
    save_variant_counts(df, variant_columns)
    save_event_dates(df, primary_onset_col)


def save_descriptive_stats(df):
    """Xuáº¥t thá»‘ng kÃª mÃ´ táº£ cÃ¡c biáº¿n theo stablecoin."""
    panel = pd.read_parquet(PANEL_PATH)

    date_col = find_column(
        panel, ["date", "timestamp", "datetime", "time"], "ngÃ y"
    )
    coin_col = find_column(
        panel, ["coin", "stablecoin", "symbol", "asset"], "stablecoin"
    )

    panel = panel.rename(columns={date_col: "date", coin_col: "coin"})
    panel["date"] = pd.to_datetime(panel["date"], utc=True, errors="coerce")
    panel["coin"] = panel["coin"].astype(str).str.upper()

    panel = panel[
        panel["coin"].isin(CORE_COINS)
        & panel["date"].between(
            pd.Timestamp(SPLITS["train"][0], tz="UTC"),
            pd.Timestamp(SPLITS["test"][1], tz="UTC"),
        )
    ].copy()

    candidate_columns = [
        "peg_deviation",
        "peg_deviation_hl_clean",
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
    ]
    numeric_columns = [
        col for col in candidate_columns
        if col in panel.columns
        and pd.api.types.is_numeric_dtype(panel[col])
    ]

    rows = []
    for coin, group in panel.groupby("coin"):
        for col in numeric_columns:
            values = pd.to_numeric(group[col], errors="coerce")
            nonmissing = values.dropna()

            rows.append({
                "coin": coin,
                "variable": col,
                "n_observations": int(nonmissing.size),
                "missing_count": int(values.isna().sum()),
                "missing_rate": float(values.isna().mean()),
                "mean": nonmissing.mean(),
                "std": nonmissing.std(),
                "min": nonmissing.min(),
                "p25": nonmissing.quantile(0.25),
                "median": nonmissing.median(),
                "p75": nonmissing.quantile(0.75),
                "max": nonmissing.max(),
            })

    output = pd.DataFrame(rows)
    output.to_csv(
        TABLES_PATH / "T02_descriptive_stats.csv",
        index=False,
    )

if __name__ == "__main__":
    main()
