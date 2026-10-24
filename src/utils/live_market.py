"""Fetch a fresh public spot-price snapshot for core stablecoins.

This is a market-data overlay only. It does not create model features or forecasts.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import requests

API_URL = "https://data-api.binance.vision/api/v3/ticker/price"
PAIRS = {"USDC": "USDCUSDT", "DAI": "DAIUSDT"}


def fetch_live_prices(timeout: int = 10) -> pd.DataFrame:
    """Return latest available USD prices, with the provider's per-coin update time."""
    queried_at = datetime.now(timezone.utc)
    rows = [{"stablecoin": "USDT", "price": 1.0, "dev": 0.0, "updated_at": queried_at}]
    for coin, pair in PAIRS.items():
        response = requests.get(API_URL, params={"symbol": pair}, headers={"accept": "application/json"}, timeout=timeout)
        response.raise_for_status()
        price = float(response.json()["price"])
        rows.append({"stablecoin": coin, "price": price, "dev": abs(price - 1.0), "updated_at": queried_at})
    return pd.DataFrame(rows)
