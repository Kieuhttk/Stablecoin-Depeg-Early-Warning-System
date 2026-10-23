# Phụ lục B. Nhật ký nguồn dữ liệu (source log)

Sinh tự động lúc 2026-10-19 15:37 UTC. Trạng thái `ok_cache` nghĩa là dữ liệu được đọc từ bản lưu `data/raw/` (đã tải trước đó); `skipped_no_key` nghĩa là CryptoCompare không được gọi vì không có khóa API; `off_midnight` là số mốc thời gian gốc không rơi đúng 00:00 UTC (phải bằng 0).

| source | key | endpoint | status | rows | first_date | last_date | off_midnight | fetched_at_utc | error | note |
|---|---|---|---|---|---|---|---|---|---|---|
| Yahoo Finance | USDT:USDT-USD | yfinance.download(interval=1d) | ok_cache | 2481 | 2020-01-01 | 2026-10-16 | 0 | 2026-10-19 15:37:44 |  |  |
| CryptoCompare | USDT:USDT | min-api.cryptocompare.com/data/v2/histoday | missing_cache | 0 |  |  |  | 2026-10-19 15:37:44 |  |  |
| DefiLlama | USDT:USDT | stablecoins.llama.fi/stablecoin/{id} | ok_cache | 3247 | 2017-11-29 | 2026-10-19 | 0 | 2026-10-19 15:37:44 |  |  |
| Yahoo Finance | USDC:USDC-USD | yfinance.download(interval=1d) | ok_cache | 2481 | 2020-01-01 | 2026-10-16 | 0 | 2026-10-19 15:37:44 |  |  |
| CryptoCompare | USDC:USDC | min-api.cryptocompare.com/data/v2/histoday | missing_cache | 0 |  |  |  | 2026-10-19 15:37:44 |  |  |
| Binance | USDC:USDCUSDT | api.binance.com/api/v3/klines (1d) | ok_cache | 2316 | 2020-01-01 | 2026-10-16 | 0 | 2026-10-19 15:37:44 |  |  |
| DefiLlama | USDC:USDC | stablecoins.llama.fi/stablecoin/{id} | ok_cache | 2961 | 2018-09-11 | 2026-10-19 | 0 | 2026-10-19 15:37:44 |  |  |
| Yahoo Finance | DAI:DAI-USD | yfinance.download(interval=1d) | ok_cache | 2481 | 2020-01-01 | 2026-10-16 | 0 | 2026-10-19 15:37:44 |  |  |
| CryptoCompare | DAI:DAI | min-api.cryptocompare.com/data/v2/histoday | missing_cache | 0 |  |  |  | 2026-10-19 15:37:44 |  |  |
| Binance | DAI:DAIUSDT | api.binance.com/api/v3/klines (1d) | ok_cache | 21 | 2020-07-23 | 2020-08-12 | 0 | 2026-10-19 15:37:44 |  |  |
| DefiLlama | DAI:DAI | stablecoins.llama.fi/stablecoin/{id} | ok_cache | 2527 | 2019-11-19 | 2026-10-19 | 0 | 2026-10-19 15:37:44 |  |  |
| Yahoo Finance | BUSD:BUSD-USD | yfinance.download(interval=1d) | ok_cache | 2481 | 2020-01-01 | 2026-10-16 | 0 | 2026-10-19 15:37:44 |  |  |
| CryptoCompare | BUSD:BUSD | min-api.cryptocompare.com/data/v2/histoday | missing_cache | 0 |  |  |  | 2026-10-19 15:37:44 |  |  |
| Binance | BUSD:BUSDUSDT | api.binance.com/api/v3/klines (1d) | ok_cache | 1445 | 2020-01-01 | 2023-12-15 | 0 | 2026-10-19 15:37:44 |  |  |
| DefiLlama | BUSD:BUSD | stablecoins.llama.fi/stablecoin/{id} | ok_cache | 2371 | 2020-04-17 | 2026-10-19 | 0 | 2026-10-19 15:37:44 |  |  |
| Yahoo Finance | FDUSD:FDUSD-USD | yfinance.download(interval=1d) | ok_cache | 1176 | 2023-07-26 | 2026-10-16 | 0 | 2026-10-19 15:37:44 |  |  |
| CryptoCompare | FDUSD:FDUSD | min-api.cryptocompare.com/data/v2/histoday | missing_cache | 0 |  |  |  | 2026-10-19 15:37:44 |  |  |
| Binance | FDUSD:FDUSDUSDT | api.binance.com/api/v3/klines (1d) | ok_cache | 1179 | 2023-07-26 | 2026-10-16 | 0 | 2026-10-19 15:37:44 |  |  |
| DefiLlama | FDUSD:FDUSD | stablecoins.llama.fi/stablecoin/{id} | ok_cache | 1242 | 2023-05-27 | 2026-10-19 | 0 | 2026-10-19 15:37:44 |  |  |
| Yahoo Finance | UST:UST-USD | yfinance.download(interval=1d) | empty | 0 |  |  | 0 | 2026-10-19 15:37:44 |  |  |
| CryptoCompare | UST:UST | min-api.cryptocompare.com/data/v2/histoday | missing_cache | 0 |  |  |  | 2026-10-19 15:37:44 |  |  |
| Binance | UST:USTUSDT | api.binance.com/api/v3/klines (1d) | ok_cache | 141 | 2021-12-24 | 2022-05-13 | 0 | 2026-10-19 15:37:44 |  |  |
| DefiLlama | UST:UST | stablecoins.llama.fi/stablecoin/{id} | ok_cache | 539 | 2020-12-31 | 2022-06-22 | 0 | 2026-10-19 15:37:44 |  |  |
| Yahoo Finance | BTC:BTC-USD | yfinance.download(interval=1d) | ok_cache | 2511 | 2019-12-02 | 2026-10-16 | 0 | 2026-10-19 15:37:45 |  |  |
| Yahoo Finance | ETH:ETH-USD | yfinance.download(interval=1d) | ok_cache | 2511 | 2019-12-02 | 2026-10-16 | 0 | 2026-10-19 15:37:45 |  |  |
| DefiLlama | TVL:all_chains | api.llama.fi/v2/historicalChainTvl | ok_cache | 3310 | 2017-09-27 | 2026-10-19 | 0 | 2026-10-19 15:37:45 |  |  |

## B.1. Độ phủ dữ liệu theo coin

| stablecoin | role | coin_type | first_date | last_date | n_rows | n_missing_price | n_src_disagree | n_hl_fixed | n_hl_suspect | n_days_2plus_sources | n_supply_nan | max_peg_dev | max_peg_dev_min | max_peg_dev_hl | max_peg_dev_hl_clean |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BUSD | extension | fiat_backed | 2020-01-01 | 2026-10-16 | 2481 | 0 | 5 | 0 | 1 | 1445 | 108 | 0.090416 | 0.090416 | 0.146504 | 0.146504 |
| DAI | core | crypto_backed | 2020-01-01 | 2026-10-16 | 2481 | 0 | 8 | 0 | 2 | 21 | 0 | 0.0929511 | 0.0929511 | 2.6684 | 0.140685 |
| FDUSD | extension | fiat_backed | 2023-07-26 | 2026-10-16 | 1179 | 0 | 0 | 0 | 1 | 1176 | 0 | 0.01361 | 0.01361 | 0.11889 | 0.11889 |
| USDC | core | fiat_backed | 2020-01-01 | 2026-10-16 | 2481 | 0 | 39 | 0 | 2 | 2316 | 0 | 0.044029 | 0.040553 | 1.34956 | 0.111217 |
| USDT | core | fiat_backed | 2020-01-01 | 2026-10-16 | 2481 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0535851 | 0.0535851 | 0.10051 | 0.10051 |
| UST | case_study | algorithmic | 2021-12-24 | 2022-05-13 | 141 | 0 | 0 | 0 | 0 | 0 | 0 | 0.754654 | 0.754654 | 0.775929 | 0.775929 |
