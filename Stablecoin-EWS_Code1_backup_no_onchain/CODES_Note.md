# CODES_Note: Ghi chú kỹ thuật bản BACKUP không on-chain (Code 1, Nhóm 4)

> **Quy tắc duy trì:** mỗi lần code được viết hoặc sửa, cập nhật file này (mục 13 *Nhật ký thay đổi* và các mục bị ảnh hưởng).
> **Trạng thái:** bản backup v1, ngày 19/10/2026. Bộ test **20/20 pass** (kể cả khi ép mã hóa mặc định kiểu Windows `PYTHONUTF8=0 LC_ALL=C`).
> Panel đã dựng sẵn: **11.244 hàng × 46 cột, 6 coin, 01/01/2020 đến 16/10/2026 (UTC)**, QC không có mục FAIL.

---

## 1. Bản này là gì và khi nào dùng

Theo phân công, Code 1 phải thử on-chain/DEX và nếu chưa có trước 12h ngày 19/10 thì **cắt** và dùng proxy DefiLlama (supply, TVL). Bản này chính là phương án đã cắt: không phụ thuộc bất kỳ nguồn on-chain nào (Curve API, Dune, Uniswap, Etherscan, BigQuery), không cần key nào, và **chạy được hoàn toàn offline** từ dữ liệu đã tải lưu trong `data/raw/` (tải ngày 19/10/2026, 14:00 UTC).

Đầu ra giữ nguyên tên tệp và vị trí của bản chính (`data/processed/panel.parquet`) để Code 2, 3, 4 thay thế trực tiếp. Khác biệt duy nhất về cột: các cột on-chain đã bị xóa (xem mục 2) và có thêm một số cột đối chiếu/làm sạch.

## 2. So với bản chính trên GitHub: đã bỏ gì, thêm gì

| Hạng mục | Bản chính (repo) | Bản backup này |
|---|---|---|
| `fetch_curve.py`, `fetch_onchain.py`, `check_onchain.py`, `dune_queries.sql`, `data/raw/onchain/` | Có | **Đã xóa** (không dùng được khi không có on-chain) |
| Cột `dex_imbalance`, `dex_pool_size`, `mint_eth`, `burn_eth`, `net_issuance_eth`, `onchain_available` | Có (toàn NaN/False trên dữ liệu thật) | **Đã xóa**; QC kiểm tra panel không còn các cột này |
| `DUNE_API_KEY`, mục `onchain:` trong config, test Curve/Dune | Có | **Đã xóa** |
| CryptoCompare | Bắt buộc key; thiếu key thì lỗi 401 hàng loạt trong source log | **Tùy chọn**: thiếu key thì ghi `skipped_no_key`, không gọi mạng |
| Đối chiếu nguồn giá | Chỉ với CryptoCompare (thực tế 0% vì 401) | **Binance quy USD** (giá USDT × USDT-USD của Yahoo cùng ngày) + CryptoCompare nếu có key |
| Lấp ngày thiếu giá | Chỉ UST dùng Binance (để nguyên đơn vị USDT) | Mọi coin có cặp Binance (`binance_fallback`), **đã quy USD** (`price_src = binance_usd`). FDUSD hết 3 ngày thiếu giá |
| Râu nến lỗi của Yahoo (vd. USDC high 2,35 ngày 16/11/2021) | Không xử lý (max `peg_deviation_hl` của DAI = 2,67) | Cờ `hl_suspect` + cột sạch `peg_deviation_hl_clean` |
| Biến thị trường mới | | `xmkt_gap` (chênh lệch liên thị trường, thay một phần tín hiệu DEX), `usdt_usd`, `n_price_sources`, `peg_deviation_bn`, `peg_deviation_hl_bn` |
| Kiểm tra UTC | Chỉ trên panel | Thêm đếm mốc **lệch 00:00 UTC ở dữ liệu gốc** từng nguồn (`off_midnight` trong source log) và kiểm tra lag nến Yahoo với Binance |
| Chế độ chạy | Luôn cố tải lại nguồn lỗi | Thêm `--offline` (chỉ cache, tái lập đúng bản bàn giao) |
| Phụ lục | CSV | CSV + bản nháp Markdown **Phụ lục A, B, E** trong `outputs/appendix/` + `blueprint_mapping.csv` |

So sánh số liệu với `panel_v1.parquet` của bản chính trên cùng 11.244 hàng: `supply`, `supply_change`, `tvl_change`, `btc_vol`, `supply_eth_share` trùng khớp tuyệt đối; `price` chỉ khác ở UST (nay quy USD, chênh tối đa 0,0031) và 3 ngày FDUSD trước đây thiếu giá.

## 3. Đối chiếu với nhiệm vụ Code 1 trong bảng phân công

| Yêu cầu trong PCCV | Trạng thái trong bản này |
|---|---|
| Kiểm tra giới hạn lịch sử nguồn, chốt nguồn; nguồn thay thế Yahoo, Binance, DefiLlama, CryptoCompare | Đã chốt: Yahoo (giá chính, từ 01/01/2020), Binance (đối chiếu), DefiLlama (supply, TVL), CryptoCompare (tùy chọn). CoinGecko không dùng vì gói miễn phí chỉ ~365 ngày |
| Script tải dữ liệu, **chuẩn hóa UTC**, **merge thành panel** | `fetch.py` + `build_panel.py` (chi tiết mục 5, 6) |
| Lấy giá cao/thấp trong ngày nếu nguồn có | `high`, `low` (Yahoo), `bn_high_usd`, `bn_low_usd` (Binance); thêm bản làm sạch |
| Thử on-chain/DEX, không có thì cắt, dùng proxy DefiLlama | Đã cắt; proxy: `supply_change`, `supply_eth_change`, `supply_eth_share`, `tvl_change` (+ `xmkt_gap` thay `dex_imbalance`) |
| `panel.parquet` v0, v1 | `panel.parquet` và `panel_v1.parquet` (v0 nằm ở repo chính; muốn tạo lại: `--version v0`) |
| Data dictionary (Phụ lục A) | `outputs/tables/data_dictionary.csv`, `outputs/appendix/PhuLuc_A_data_dictionary.md` |
| Source log (Phụ lục B) | `outputs/tables/source_log_raw.csv`, `outputs/appendix/PhuLuc_B_source_log.md` |
| Phụ lục E | Đề chưa nêu rõ; bản nháp QC + hướng dẫn tái lập: `outputs/appendix/PhuLuc_E_qc_tai_lap.md`. **Cần nhóm xác nhận nội dung** |
| Checklist đề: script tái lập, không look-ahead, README | `--offline` tái lập; test nhiễu loạn tương lai; README + file này |

## 4. Luồng xử lý

1. `fetch_all` đọc `config/config.yaml`, với mỗi (coin, nguồn): đọc cache `data/raw/*.csv` nếu có, nếu không thì tải (trừ khi `--offline`). Mỗi lần ghi một dòng source log: trạng thái, số dòng, ngày đầu/cuối, `off_midnight`, lỗi. Nguồn lỗi **không làm sập pipeline**.
2. `build_panel` dựng khối giá từng coin (chọn nguồn theo ngày, sửa High/Low, lưới ngày liên tục) rồi gắn biến DefiLlama (đã trễ), biến thị trường, cột đối chiếu và cờ chất lượng; sắp cột theo `DICTIONARY`.
3. Ghi `panel.parquet` + `panel_<version>.parquet`, các bảng `outputs/tables/`, chạy QC, sinh Phụ lục A/B/E.

## 5. Xử lý UTC (đã cài đặt và kiểm thử)

Mọi mốc thời gian được đưa về **UTC** rồi về **00:00 của ngày UTC**. Mốc không có múi giờ (yfinance cho crypto, CSV cache) được hiểu là UTC; mốc có múi giờ khác được **quy đổi** chứ không cắt bỏ múi giờ (test: 07:00 giờ Việt Nam ngày 02/01 = 00:00 UTC ngày 02/01). Binance (`open_time` ms), CryptoCompare (`time` giây), DefiLlama (`date` giây) đều là epoch UTC.

Ba lớp kiểm tra: (a) `off_midnight` đếm số mốc gốc không đúng 00:00 UTC cho từng nguồn, phải bằng 0 (hiện tất cả = 0); (b) QC xác nhận panel có `tz = UTC`, mọi mốc đúng 00:00, không có ngày chưa đóng nến; (c) so khớp chuỗi giá Yahoo với Binance ở độ lệch −1, 0, +1 ngày: lag tối ưu = 0 cho cả 3 cặp so sánh được (USDC, BUSD, FDUSD), tức hai nguồn cùng quy ước nến 00:00 đến 24:00 UTC.

Hàng `(stablecoin, t)` = thông tin biết được **đến hết ngày t (24:00 UTC)**. Cột `timestamp` có kiểu `datetime64[ns, UTC]`.

## 6. Ghép panel (merge)

**Khóa:** `(stablecoin, timestamp)`, duy nhất (QC kiểm tra). Panel **không cân bằng**: mỗi coin có mặt từ ngày đầu đến ngày cuối có giá trong mẫu, trên **lưới ngày liên tục** (ngày thiếu giữ lại với `is_missing_price = True`) để `shift(-h)` theo coin tạo nhãn đúng.

**Chọn nguồn giá mỗi ngày:** Yahoo → CryptoCompare (nếu có key) → Binance quy USD (coin bật `binance_fallback`) → Binance giữ USDT (chỉ khi thiếu USDT-USD ngày đó). Nguồn từng hàng ở `price_src`. Hiện tại: 11.100 hàng `yahoo`, 144 hàng `binance_usd` (141 UST + 3 FDUSD).

**Quy đổi Binance về USD:** `bn_*_usd = bn_* × usdt_usd` với `usdt_usd` = giá đóng cửa USDT-USD của Yahoo cùng ngày. High/Low quy đổi chỉ là xấp xỉ (nhân với giá đóng cửa của USDT).

**Biến cấp thị trường** (`btc_*`, `eth_*`, `tvl*`, `usdt_usd`) tính trên **toàn chuỗi nguồn** rồi mới đưa vào lưới từng coin (BTC/ETH tải sớm 30 ngày để có `btc_vol` từ ngày đầu). Cùng một ngày mọi coin có cùng giá trị (QC kiểm tra).

**DefiLlama:** `supply`, `supply_eth`, `tvl` trễ `llama_lag_days = 1` ngày, ffill tối đa 3 ngày (`supply_ffilled`); `*_change` tính trên chuỗi đầy đủ rồi mới đưa vào lưới coin; chia 0 → NaN.

## 7. Quy tắc point-in-time (chống look-ahead)

Mọi cột tại hàng t chỉ dùng dữ liệu đến hết ngày t (giá, volume, High/Low, Binance, USDT-USD) hoặc đến hết ngày t − 1 (DefiLlama). Cửa sổ trượt (`btc_vol`, `eth_vol`) chỉ nhìn lùi. Cờ `hl_suspect` chỉ dùng dữ liệu của chính ngày t. Test `test_no_lookahead_perturbation` nhân toàn bộ dữ liệu **sau** ngày T của mọi nguồn với hệ số lớn và xác nhận không giá trị nào tại hoặc trước T thay đổi.

**Nhãn depeg không có trong panel** (việc của Code 2).

## 8. Cột của `panel.parquet` (46 cột)

Bảng sinh tự động từ `src/data/dictionary.py` (cũng là `outputs/tables/data_dictionary.csv`).

| Cột | Kiểu | Đơn vị | Định nghĩa | Nguồn | Quy ước thời điểm |
|---|---|---|---|---|---|
| `timestamp` | datetime64[ns, UTC] | UTC 00:00 | Ngày (UTC) của quan sát; khóa cùng với stablecoin. | Pipeline | Hàng t phản ánh thông tin biết được đến hết ngày t (24:00 UTC). |
| `stablecoin` | string | - | Mã stablecoin (USDT, USDC, DAI, BUSD, FDUSD, UST). | config.yaml | - |
| `role` | string | - | Vai trò trong mẫu: core / extension / case_study (mục 3.1 của đề). | config.yaml | - |
| `coin_type` | string | - | Loại: fiat_backed / crypto_backed / algorithmic (dùng cho RQ3). | config.yaml | - |
| `price` | float64 | USD | Giá đóng cửa ngày. Thứ tự ưu tiên: Yahoo, CryptoCompare (nếu có key), Binance quy USD (coin bật binance_fallback). Xem price_src. | Yahoo Finance / CryptoCompare / Binance | Close của nến ngày t (đến 24:00 UTC). |
| `open` | float64 | USD | Giá mở cửa ngày (00:00 UTC), cùng nguồn với price. | như price | Biết tại 00:00 ngày t. |
| `high` | float64 | USD | Giá cao nhất trong ngày; đã chỉnh để >= max(open, close) (xem hl_fixed). | như price | Biết đến hết ngày t. |
| `low` | float64 | USD | Giá thấp nhất trong ngày; đã chỉnh để <= min(open, close). | như price | Biết đến hết ngày t. |
| `peg_dev_signed` | float64 | USD | price - 1 (có dấu: âm = dưới neo). | Tính | Dùng price ngày t. |
| `peg_deviation` | float64 | tỷ lệ | Dev = &#124;price - 1&#124; theo giá đóng cửa (công thức mục 2.3 của đề). | Tính | Dùng price ngày t. |
| `peg_deviation_cc` | float64 | tỷ lệ | &#124;cc_close - 1&#124; theo CryptoCompare. NaN nếu không có key/dữ liệu CryptoCompare. | CryptoCompare | Close ngày t. |
| `peg_deviation_bn` | float64 | tỷ lệ | &#124;bn_close_usd - 1&#124; theo Binance đã quy USD. NaN nếu coin không có cặp Binance ngày đó (USDT không có; DAI chỉ 21 ngày năm 2020). | Binance + Yahoo USDT-USD | Close ngày t. |
| `peg_deviation_min` | float64 | tỷ lệ | Độ lệch 'đồng thuận' = min của các nguồn đang có (Yahoo, CryptoCompare, Binance quy USD): chỉ lớn khi MỌI nguồn có dữ liệu cùng thấy lệch. Nếu chỉ có một nguồn thì bằng độ lệch của nguồn đó (xem n_price_sources). | Tính | Close ngày t. |
| `n_price_sources` | int | - | Số nguồn giá đóng cửa độc lập có dữ liệu trong ngày (1 = chỉ một nguồn, peg_deviation_min KHÔNG được đối chiếu). | Pipeline | - |
| `peg_deviation_hl` | float64 | tỷ lệ | Độ lệch trong ngày xấu nhất max(&#124;high-1&#124;, &#124;low-1&#124;), theo nguồn của price. Bắt depeg chỉ xảy ra trong ngày; nhạy với râu nến lỗi của Yahoo. | Tính | Cả ngày t. |
| `peg_deviation_hl_cc` | float64 | tỷ lệ | Như peg_deviation_hl nhưng theo High/Low CryptoCompare. NaN nếu không có. | CryptoCompare | Cả ngày t. |
| `peg_deviation_hl_bn` | float64 | tỷ lệ | Như peg_deviation_hl nhưng theo High/Low Binance quy USD (xấp xỉ: nhân với USDT-USD đóng cửa). NaN nếu không có. | Binance + Yahoo USDT-USD | Cả ngày t. |
| `peg_deviation_hl_min` | float64 | tỷ lệ | min các độ lệch trong ngày đang có (Yahoo, CryptoCompare, Binance): chỉ lớn khi mọi nguồn có dữ liệu cùng thấy lệch trong ngày. | Tính | Cả ngày t. |
| `hl_suspect` | bool | - | True nếu râu nến nghi lỗi: High/Low lệch neo > quality.hl_spike_threshold (5%) trong khi open và close đều lệch < quality.hl_body_threshold (1%), VÀ (a) nguồn độc lập có dữ liệu nhưng không xác nhận (lệch < một nửa) hoặc (b) râu > quality.hl_extreme_threshold (25%). Không có nguồn độc lập và râu vừa phải thì KHÔNG gắn cờ (vd. USDT 12/05/2022 low 0,9485 được giữ). Ví dụ bị gắn cờ: USDC/DAI 16/11/2021 (high 2,35 và 3,67). | Pipeline | Chỉ dùng dữ liệu ngày t. |
| `peg_deviation_hl_clean` | float64 | tỷ lệ | Bản đã làm sạch của độ lệch trong ngày: bằng peg_deviation_hl_min, riêng hàng hl_suspect được thay bằng max(&#124;open-1&#124;, &#124;close-1&#124;). Khuyến nghị dùng thay peg_deviation_hl khi tạo nhãn theo High/Low. | Tính | Cả ngày t. |
| `volume` | float64 | USD | Khối lượng giao dịch ngày quy USD, cùng nguồn với price (Yahoo là tổng hợp nhiều sàn). | như price | Cả ngày t. |
| `range_hl` | float64 | tỷ lệ | (high - low) / close. Proxy biến động/căng thẳng thanh khoản trong ngày (nên dùng bản tính từ cột đã làm sạch nếu hl_suspect). | Tính | Cả ngày t. |
| `turnover` | float64 | tỷ lệ | volume / supply. Proxy thanh khoản (không có bid-ask spread lịch sử miễn phí). | Tính | supply đã trễ theo llama_lag_days. |
| `xmkt_gap` | float64 | tỷ lệ | &#124;price - bn_close_usd&#124; / price: chênh lệch giá giữa thị trường tổng hợp (Yahoo) và Binance quy USD. Đại diện 'cross-market price deviation' của đề và thay phần nào cho tín hiệu DEX khi không có on-chain. NaN nếu price lấy từ Binance hoặc không có Binance. | Tính | Close ngày t. |
| `supply` | float64 | USD | Circulating supply tổng các chain, trễ llama_lag_days ngày, ffill tối đa llama_ffill_limit ngày. | DefiLlama | Giá trị gắn nhãn <= t - lag. |
| `supply_ffilled` | bool | - | True nếu supply hàng này là giá trị ffill. | Pipeline | - |
| `supply_change` | float64 | tỷ lệ | supply_t / supply_{t-1} - 1. Proxy phát hành/mua lại (mint/burn) ròng toàn chain. | Tính | Chỉ dùng t và t-1 (đã trễ). |
| `supply_eth` | float64 | USD | Circulating supply của coin trên Ethereum (DefiLlama tách theo chain), trễ llama_lag_days ngày. Gồm cả phần qua cầu nối. NaN nếu không có. | DefiLlama | Giá trị gắn nhãn <= t - lag. |
| `supply_eth_change` | float64 | tỷ lệ | supply_eth_t / supply_eth_{t-1} - 1: proxy phát hành/hủy ròng trên Ethereum (thay mint/burn on-chain). | Tính | Chỉ dùng t và t-1 (đã trễ). |
| `supply_eth_share` | float64 | tỷ lệ | supply_eth / supply: tỷ trọng nguồn cung trên Ethereum. Đổi đột ngột = dịch chuyển chain hoặc phát hành/hủy lớn trên Ethereum. | Tính | Cùng độ trễ với supply. |
| `tvl` | float64 | USD | TVL toàn thị trường DeFi (tổng chain). Biến cấp thị trường, giống nhau giữa các coin. | DefiLlama | Trễ llama_lag_days ngày. |
| `tvl_change` | float64 | tỷ lệ | tvl_t / tvl_{t-1} - 1 (chia 0 => NaN). | Tính | Chỉ dùng t và t-1 (đã trễ). |
| `btc_ret` | float64 | log | Log-return ngày của BTC-USD. | Yahoo Finance | Close ngày t. |
| `btc_vol` | float64 | log-return std | Độ lệch chuẩn log-return BTC trượt vol_window ngày (mặc định 7), chỉ dùng t-6..t. | Tính | Cửa sổ lùi. |
| `eth_ret` | float64 | log | Log-return ngày của ETH-USD (đại diện cú sốc tài sản thế chấp của DAI). | Yahoo Finance | Close ngày t. |
| `eth_vol` | float64 | log-return std | Độ lệch chuẩn log-return ETH trượt vol_window ngày. | Tính | Cửa sổ lùi. |
| `usdt_usd` | float64 | USD | Giá đóng cửa USDT-USD (Yahoo). Dùng để quy giá Binance (quote USDT) về USD; cũng là biến căng thẳng chung của thị trường stablecoin. | Yahoo Finance | Close ngày t. |
| `price_src` | string | - | Nguồn của price/open/high/low/volume hàng này: yahoo, cryptocompare, binance_usd (đã quy USD) hoặc binance_usdt (không quy được vì thiếu USDT-USD). | Pipeline | - |
| `hl_fixed` | bool | - | True nếu high/low đã bị chỉnh vì mâu thuẫn với open/close. | Pipeline | - |
| `is_missing_price` | bool | - | True nếu không nguồn nào có giá ngày đó (hàng được giữ để lưới ngày liên tục, các cột giá = NaN). | Pipeline | - |
| `src_disagree` | bool | - | True nếu giá đóng cửa của price lệch > quality.src_disagree_threshold (0,5%) so với ít nhất một nguồn độc lập (CryptoCompare hoặc Binance quy USD). Nên kiểm tra tay. | Pipeline | - |
| `cc_close` | float64 | USD | Giá đóng cửa CryptoCompare (đối chiếu). NaN nếu không có key. | CryptoCompare | Close ngày t. |
| `bn_close` | float64 | USDT | Giá đóng cửa Binance theo USDT (giá gốc, chưa quy đổi). | Binance | Close ngày t. |
| `bn_close_usd` | float64 | USD | bn_close x usdt_usd. | Tính | Close ngày t. |
| `bn_high_usd` | float64 | USD | High Binance x usdt_usd (xấp xỉ vì USDT-USD lấy giá đóng cửa). | Tính | Cả ngày t. |
| `bn_low_usd` | float64 | USD | Low Binance x usdt_usd (xấp xỉ). | Tính | Cả ngày t. |

## 9. Phạm vi dữ liệu theo coin (số liệu thật)

| Coin | Vai trò / loại | Khoảng thời gian | Số ngày | Ngày có ≥ 2 nguồn giá | Ghi chú |
|---|---|---|---|---|---|
| USDT | core / fiat | 01/01/2020 đến 16/10/2026 | 2.481 | 0 | Không có cặp Binance (USDT là đồng định giá): **chỉ một nguồn**, `peg_deviation_min = peg_deviation` |
| USDC | core / fiat | 01/01/2020 đến 16/10/2026 | 2.481 | 2.316 (93%) | Đối chiếu tốt nhất |
| DAI | core / crypto | 01/01/2020 đến 16/10/2026 | 2.481 | 21 | Cặp DAIUSDT Binance chỉ tồn tại 23/07 đến 12/08/2020: gần như một nguồn |
| BUSD | extension / fiat | 01/01/2020 đến 16/10/2026 | 2.481 | 1.445 | Binance ngừng 15/12/2023. Sau đó volume trung vị sụt từ ~5×10⁹ (2022) xuống ~3,6×10⁶ (2025) và ~0,9×10⁶ (2026); giá 09/2025 lên 1,09 là thị trường mất thanh khoản, **không phải depeg có ý nghĩa** |
| FDUSD | extension / fiat | 26/07/2023 đến 16/10/2026 | 1.179 | 1.176 | Sự kiện 02/04/2025: close 0,9864, đáy trong ngày lệch ~11,9% |
| UST | case_study / algorithmic | 24/12/2021 đến 13/05/2022 | 141 | 0 | Chỉ có Binance (đã quy USD); chuỗi dừng 13/05/2022 ở 0,2453 nên không thấy đáy |

## 10. Phát hiện chất lượng dữ liệu và cách đã xử lý

| Vấn đề | Chi tiết | Xử lý |
|---|---|---|
| CryptoCompare 401 | Không có key | Tùy chọn hóa; đối chiếu bằng Binance quy USD |
| Râu nến lỗi của Yahoo | USDC 16–17/11/2021 high 2,35 và 1,17; DAI cùng ngày 3,67 và 1,50; BUSD 10/05/2020; FDUSD 29/07/2023 (Binance không xác nhận) | `hl_suspect` = 6 ngày; `peg_deviation_hl_clean` thay bằng max(&#124;open−1&#124;, &#124;close−1&#124;). Danh sách: `review_hl_suspect_days.csv` |
| Râu lớn **không** có nguồn thứ hai | USDT 12/05/2022 low 0,9485 (sự kiện thật thời điểm UST sụp) | **Giữ nguyên**: chỉ gắn cờ khi có bằng chứng lỗi (nguồn khác bác bỏ, hoặc râu > 25% mà thân nến sát neo) |
| Lệch giá đóng cửa > 0,5% giữa Yahoo và Binance | 52 ngày (USDC 39, DAI 8, BUSD 5), phần lớn năm 2020 | Cờ `src_disagree`; dùng `peg_deviation_min` cho nhãn bảo thủ. Danh sách: `review_src_disagree_days.csv` |
| Giá ngoài [0,5; 1,5] | UST 12/05 (0,3626) và 13/05/2022 (0,2453) | Depeg thật: QC để WARN, không FAIL |
| Coin chỉ có một nguồn | USDT 100%, DAI 99%, UST 100% số ngày | `n_price_sources` cho biết; đọc kết quả của các coin này thận trọng hơn |
| TVL = 0 trước ~2018 | Dữ liệu gốc DefiLlama, nằm ngoài mẫu | `tvl_change` chia 0 → NaN |
| `supply` thiếu 108 ngày đầu của BUSD | DefiLlama có BUSD từ 17/04/2020 | NaN (không lấp) |

## 11. Giới hạn đã biết

1. **Không có dữ liệu on-chain trực tiếp:** không có tỷ trọng pool DEX, mint/burn theo giao dịch, exchange flows. Proxy `supply_*` là số liệu DefiLlama theo ngày (gồm cả cầu nối chuỗi), không phải mint/burn thuần. RQ2 của đề (*market liquidity hay on-chain flows quan trọng hơn*) phải được **diễn đạt lại** thành "thanh khoản thị trường và tín hiệu chênh lệch liên thị trường so với biến động nguồn cung (proxy on-chain)".
2. **Tần suất ngày** (theo PCCV), không có panel hourly; nhãn h1/h6/h24 của đề được thay bằng h = 1 và 3 ngày.
3. **Không có bid-ask spread lịch sử:** `turnover`, `range_hl`, `xmkt_gap` chỉ là proxy thanh khoản.
4. **Binance quote USDT:** quy USD bằng giá đóng cửa USDT-USD của Yahoo, nên `peg_deviation_bn` của một coin có chứa sai số đo của chính USDT; High/Low quy đổi là xấp xỉ.
5. **Yahoo nhiễu giai đoạn 2020 đến đầu 2021** (xác nhận trên USDC bằng Binance). USDT và DAI không có nguồn thứ hai để kiểm chứng.
6. **Ngày cuối đóng băng 16/10/2026** do cache Yahoo dừng ở ngày này. Nếu chạy `--refresh` được, có thể dời `sample.end` tới ngày UTC gần nhất mà Yahoo và DefiLlama đều có dữ liệu.
7. Mốc chụp số liệu của DefiLlama chưa kiểm chứng; trễ 1 ngày là lựa chọn bảo thủ.

## 12. Lưu ý bàn giao cho các vai trò khác

**Code 2 (nhãn, feature, Logit, co-depeg)**
- Nếu code đã viết có tham chiếu `dex_imbalance`, `dex_pool_size`, `mint_eth`, `burn_eth`, `net_issuance_eth`, `onchain_available`: **xóa các tham chiếu này** (cột không còn trong panel).
- Nhãn chính khuyến nghị: `peg_deviation_min` (giá đóng cửa, đồng thuận nhiều nguồn); nhãn trong ngày: `peg_deviation_hl_clean` (**không** dùng `peg_deviation_hl` thô vì râu nến lỗi 2,67). Nhãn theo `peg_deviation` (chỉ Yahoo) làm kiểm tra độ nhạy.
- Tạo nhãn bằng `groupby("stablecoin")` rồi `shift(-h)` với h = 1, 3 ngày; lưới ngày liên tục đã được bảo đảm. Áp m = 1, 2 ngày liên tiếp cho định nghĩa sự kiện.
- `event_count_preview.csv` cho số ngày vượt ngưỡng và số lần khởi phát (chưa áp m) để chốt cách chia train/validation/test. Ví dụ với `peg_deviation_min` > 1%: DAI 134 ngày, BUSD 38, USDT 9, USDC 6, FDUSD 1, UST 5. **Sự kiện ở USDC/USDT/FDUSD rất hiếm** nên cân nhắc gộp panel nhiều coin hoặc ngưỡng 0,5%.
- Lọc mẫu mô hình theo `role`: loại UST khỏi mô hình chung (case study); cân nhắc loại BUSD sau 15/12/2023 (mất thanh khoản, chỉ một nguồn).
- Biến dùng được làm feature (đều point-in-time): `peg_deviation`, `peg_dev_signed`, độ biến động trượt của giá (tự tính từ `price`), `volume`/`turnover` và thay đổi của chúng, `range_hl`, `xmkt_gap`, `supply_change`, `supply_eth_change`, `supply_eth_share`, `tvl_change`, `btc_vol`, `eth_vol`, `eth_ret`, `usdt_usd`. **Không** dùng `hl_suspect`, `src_disagree`, `n_price_sources`, `price_src` làm feature (đó là cờ chất lượng).
- `xmkt_gap` và `peg_deviation_bn` thiếu khoảng 55 đến 56% số hàng (USDT không có Binance; DAI gần như không có; BUSD sau 12/2023): với Logit cần thêm biến chỉ báo thiếu hoặc chỉ dùng trên mẫu có dữ liệu; cây quyết định (LightGBM/XGBoost) xử lý NaN trực tiếp.
- `supply*` thiếu 1% (BUSD đầu 2020).
- Co-depeg heatmap (F05): dùng `peg_deviation_min` dạng bảng rộng theo ngày; UST chỉ có 141 ngày.

**Code 3 (ML, SHAP)**
- Không dùng SMOTE; chia walk-forward theo `timestamp`. RQ3 so theo `coin_type` (lưu ý: chỉ một coin crypto-backed là DAI và một coin algorithmic là UST).
- Trong SHAP, nhóm biến "on-chain" của đề nay là nhóm **proxy nguồn cung DefiLlama** (`supply_*`, `tvl_change`); nhóm "DEX" được thay bằng `xmkt_gap`.

**Code 4 (event study, dashboard)**
- Sự kiện gợi ý (kiểm chứng bằng `review_price_outliers.csv` và top độ lệch): 12–18/03/2020 (USDT, USDC, DAI), 09–13/05/2022 (UST; USDT đáy trong ngày 0,9485 ngày 12/05), 11/03/2023 (USDC, đóng cửa 0,9715, đáy ~0,88 trên Binance), 02/04/2025 (FDUSD).
- Biến cho F03: `peg_deviation`, `peg_deviation_hl_clean`, `turnover`, `xmkt_gap` (thay DEX imbalance), `supply_change` (thay supply/redemption proxy), `btc_vol`, `eth_vol`, `usdt_usd`.
- Dashboard: "liquidity condition" lấy từ `turnover` và `range_hl`; ghi rõ là proxy.

**Viết 1 (Mục 3, Phụ lục A)** dùng `outputs/appendix/PhuLuc_A_data_dictionary.md` (kèm bảng đối chiếu với mục 3.4 của đề) và mục 5, 6, 9, 11 của file này. Cần nêu rõ lý do không có on-chain và các proxy thay thế.

**Viết 2 (Phụ lục B, G; Mục 4.1 đến 4.3)** dùng `PhuLuc_B_source_log.md`; bảng sự kiện lịch sử đối chiếu với mục 9, 10 và `review_*.csv`; chuỗi UST dừng ngày 13/05/2022 nên mức đáy cần lấy từ nguồn khác (ghi nguồn).

**Mọi người viết code:** mọi đọc/ghi text phải chỉ định `encoding=` (Windows mặc định không phải UTF-8); thử test bằng `PYTHONUTF8=0 LC_ALL=C pytest`.

## 13. Nhật ký thay đổi

| Lần | Nội dung |
|---|---|
| 1 (19/10/2026) | Tạo bản backup từ repo chính: xóa toàn bộ thành phần on-chain (Curve, Dune, 6 cột on-chain, key Dune, test liên quan); CryptoCompare thành tùy chọn; thêm quy đổi Binance về USD và đối chiếu đa nguồn (`peg_deviation_bn`, `peg_deviation_min` đa nguồn, `n_price_sources`, `src_disagree` mở rộng, `xmkt_gap`, `usdt_usd`); thêm `hl_suspect` và `peg_deviation_hl_clean`; đếm `off_midnight` và kiểm tra lag nến Yahoo với Binance; chế độ `--offline`; sinh Phụ lục A, B, E dạng Markdown, `blueprint_mapping.csv`, `event_count_preview.csv`, `review_hl_suspect_days.csv`; `run_all.sh`; viết lại bộ test (20/20) |
