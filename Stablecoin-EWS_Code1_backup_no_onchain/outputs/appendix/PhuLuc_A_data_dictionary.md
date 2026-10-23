# Phụ lục A. Từ điển dữ liệu (bản backup không on-chain)

Sinh tự động lúc 2026-10-19 15:37 UTC từ `src/data/dictionary.py`. Panel `panel_v1.parquet` có 11244 hàng và 46 cột, đơn vị quan sát là stablecoin theo ngày UTC.

| column | dtype | unit | definition | source | timing |
|---|---|---|---|---|---|
| timestamp | datetime64[ns, UTC] | UTC 00:00 | Ngày (UTC) của quan sát; khóa cùng với stablecoin. | Pipeline | Hàng t phản ánh thông tin biết được đến hết ngày t (24:00 UTC). |
| stablecoin | string | - | Mã stablecoin (USDT, USDC, DAI, BUSD, FDUSD, UST). | config.yaml | - |
| role | string | - | Vai trò trong mẫu: core / extension / case_study (mục 3.1 của đề). | config.yaml | - |
| coin_type | string | - | Loại: fiat_backed / crypto_backed / algorithmic (dùng cho RQ3). | config.yaml | - |
| price | float64 | USD | Giá đóng cửa ngày. Thứ tự ưu tiên: Yahoo, CryptoCompare (nếu có key), Binance quy USD (coin bật binance_fallback). Xem price_src. | Yahoo Finance / CryptoCompare / Binance | Close của nến ngày t (đến 24:00 UTC). |
| open | float64 | USD | Giá mở cửa ngày (00:00 UTC), cùng nguồn với price. | như price | Biết tại 00:00 ngày t. |
| high | float64 | USD | Giá cao nhất trong ngày; đã chỉnh để >= max(open, close) (xem hl_fixed). | như price | Biết đến hết ngày t. |
| low | float64 | USD | Giá thấp nhất trong ngày; đã chỉnh để <= min(open, close). | như price | Biết đến hết ngày t. |
| peg_dev_signed | float64 | USD | price - 1 (có dấu: âm = dưới neo). | Tính | Dùng price ngày t. |
| peg_deviation | float64 | tỷ lệ | Dev = /price - 1/ theo giá đóng cửa (công thức mục 2.3 của đề). | Tính | Dùng price ngày t. |
| peg_deviation_cc | float64 | tỷ lệ | /cc_close - 1/ theo CryptoCompare. NaN nếu không có key/dữ liệu CryptoCompare. | CryptoCompare | Close ngày t. |
| peg_deviation_bn | float64 | tỷ lệ | /bn_close_usd - 1/ theo Binance đã quy USD. NaN nếu coin không có cặp Binance ngày đó (USDT không có; DAI chỉ 21 ngày năm 2020). | Binance + Yahoo USDT-USD | Close ngày t. |
| peg_deviation_min | float64 | tỷ lệ | Độ lệch 'đồng thuận' = min của các nguồn đang có (Yahoo, CryptoCompare, Binance quy USD): chỉ lớn khi MỌI nguồn có dữ liệu cùng thấy lệch. Nếu chỉ có một nguồn thì bằng độ lệch của nguồn đó (xem n_price_sources). | Tính | Close ngày t. |
| n_price_sources | int | - | Số nguồn giá đóng cửa độc lập có dữ liệu trong ngày (1 = chỉ một nguồn, peg_deviation_min KHÔNG được đối chiếu). | Pipeline | - |
| peg_deviation_hl | float64 | tỷ lệ | Độ lệch trong ngày xấu nhất max(/high-1/, /low-1/), theo nguồn của price. Bắt depeg chỉ xảy ra trong ngày; nhạy với râu nến lỗi của Yahoo. | Tính | Cả ngày t. |
| peg_deviation_hl_cc | float64 | tỷ lệ | Như peg_deviation_hl nhưng theo High/Low CryptoCompare. NaN nếu không có. | CryptoCompare | Cả ngày t. |
| peg_deviation_hl_bn | float64 | tỷ lệ | Như peg_deviation_hl nhưng theo High/Low Binance quy USD (xấp xỉ: nhân với USDT-USD đóng cửa). NaN nếu không có. | Binance + Yahoo USDT-USD | Cả ngày t. |
| peg_deviation_hl_min | float64 | tỷ lệ | min các độ lệch trong ngày đang có (Yahoo, CryptoCompare, Binance): chỉ lớn khi mọi nguồn có dữ liệu cùng thấy lệch trong ngày. | Tính | Cả ngày t. |
| hl_suspect | bool | - | True nếu râu nến nghi lỗi: High/Low lệch neo > quality.hl_spike_threshold (5%) trong khi open và close đều lệch < quality.hl_body_threshold (1%), VÀ (a) nguồn độc lập có dữ liệu nhưng không xác nhận (lệch < một nửa) hoặc (b) râu > quality.hl_extreme_threshold (25%). Không có nguồn độc lập và râu vừa phải thì KHÔNG gắn cờ (vd. USDT 12/05/2022 low 0,9485 được giữ). Ví dụ bị gắn cờ: USDC/DAI 16/11/2021 (high 2,35 và 3,67). | Pipeline | Chỉ dùng dữ liệu ngày t. |
| peg_deviation_hl_clean | float64 | tỷ lệ | Bản đã làm sạch của độ lệch trong ngày: bằng peg_deviation_hl_min, riêng hàng hl_suspect được thay bằng max(/open-1/, /close-1/). Khuyến nghị dùng thay peg_deviation_hl khi tạo nhãn theo High/Low. | Tính | Cả ngày t. |
| volume | float64 | USD | Khối lượng ngày chuẩn hóa USD theo nguồn: Yahoo Volume × close; CryptoCompare volumeto (quote USD); Binance quote volume × USDT-USD. Nếu thiếu tỷ giá Binance, volume = NaN. | như price | Cả ngày t. |
| range_hl | float64 | tỷ lệ | (high - low) / close. Proxy biến động/căng thẳng thanh khoản trong ngày (nên dùng bản tính từ cột đã làm sạch nếu hl_suspect). | Tính | Cả ngày t. |
| turnover | float64 | tỷ lệ | volume (USD chuẩn hóa) / supply (USD). Proxy thanh khoản (không có bid-ask spread lịch sử miễn phí). | Tính | supply đã trễ theo llama_lag_days. |
| xmkt_gap | float64 | tỷ lệ | /price - bn_close_usd/ / price: chênh lệch giá giữa thị trường tổng hợp (Yahoo) và Binance quy USD. Đại diện 'cross-market price deviation' của đề và thay phần nào cho tín hiệu DEX khi không có on-chain. NaN nếu price lấy từ Binance hoặc không có Binance. | Tính | Close ngày t. |
| supply | float64 | USD | Circulating supply tổng các chain, trễ llama_lag_days ngày, ffill tối đa llama_ffill_limit ngày. | DefiLlama | Giá trị gắn nhãn <= t - lag. |
| supply_ffilled | bool | - | True nếu supply hàng này là giá trị ffill. | Pipeline | - |
| supply_change | float64 | tỷ lệ | supply_t / supply_{t-1} - 1. Proxy phát hành/mua lại (mint/burn) ròng toàn chain. | Tính | Chỉ dùng t và t-1 (đã trễ). |
| supply_eth | float64 | USD | Circulating supply của coin trên Ethereum (DefiLlama tách theo chain), trễ llama_lag_days ngày. Gồm cả phần qua cầu nối. NaN nếu không có. | DefiLlama | Giá trị gắn nhãn <= t - lag. |
| supply_eth_change | float64 | tỷ lệ | supply_eth_t / supply_eth_{t-1} - 1: proxy phát hành/hủy ròng trên Ethereum (thay mint/burn on-chain). | Tính | Chỉ dùng t và t-1 (đã trễ). |
| supply_eth_share | float64 | tỷ lệ | supply_eth / supply: tỷ trọng nguồn cung trên Ethereum. Đổi đột ngột = dịch chuyển chain hoặc phát hành/hủy lớn trên Ethereum. | Tính | Cùng độ trễ với supply. |
| tvl | float64 | USD | TVL toàn thị trường DeFi (tổng chain). Biến cấp thị trường, giống nhau giữa các coin. | DefiLlama | Trễ llama_lag_days ngày. |
| tvl_change | float64 | tỷ lệ | tvl_t / tvl_{t-1} - 1 (chia 0 => NaN). | Tính | Chỉ dùng t và t-1 (đã trễ). |
| btc_ret | float64 | log | Log-return ngày của BTC-USD. | Yahoo Finance | Close ngày t. |
| btc_vol | float64 | log-return std | Độ lệch chuẩn log-return BTC trượt vol_window ngày (mặc định 7), chỉ dùng t-6..t. | Tính | Cửa sổ lùi. |
| eth_ret | float64 | log | Log-return ngày của ETH-USD (đại diện cú sốc tài sản thế chấp của DAI). | Yahoo Finance | Close ngày t. |
| eth_vol | float64 | log-return std | Độ lệch chuẩn log-return ETH trượt vol_window ngày. | Tính | Cửa sổ lùi. |
| usdt_usd | float64 | USD | Giá đóng cửa USDT-USD (Yahoo). Dùng để quy giá Binance (quote USDT) về USD; cũng là biến căng thẳng chung của thị trường stablecoin. | Yahoo Finance | Close ngày t. |
| price_src | string | - | Nguồn của price/open/high/low/volume hàng này: yahoo, cryptocompare, binance_usd (đã quy USD) hoặc binance_usdt (giá chưa quy được vì thiếu USDT-USD; volume để NaN). | Pipeline | - |
| hl_fixed | bool | - | True nếu high/low đã bị chỉnh vì mâu thuẫn với open/close. | Pipeline | - |
| is_missing_price | bool | - | True nếu không nguồn nào có giá ngày đó (hàng được giữ để lưới ngày liên tục, các cột giá = NaN). | Pipeline | - |
| src_disagree | bool | - | True nếu giá đóng cửa của price lệch > quality.src_disagree_threshold (0,5%) so với ít nhất một nguồn độc lập (CryptoCompare hoặc Binance quy USD). Nên kiểm tra tay. | Pipeline | - |
| cc_close | float64 | USD | Giá đóng cửa CryptoCompare (đối chiếu). NaN nếu không có key. | CryptoCompare | Close ngày t. |
| bn_close | float64 | USDT | Giá đóng cửa Binance theo USDT (giá gốc, chưa quy đổi). | Binance | Close ngày t. |
| bn_close_usd | float64 | USD | bn_close x usdt_usd. | Tính | Close ngày t. |
| bn_high_usd | float64 | USD | High Binance x usdt_usd (xấp xỉ vì USDT-USD lấy giá đóng cửa). | Tính | Cả ngày t. |
| bn_low_usd | float64 | USD | Low Binance x usdt_usd (xấp xỉ). | Tính | Cả ngày t. |

## A.1. Đối chiếu với cấu trúc dữ liệu đề xuất (mục 3.4 của đề)

| truong_trong_de | cot_trong_panel | trang_thai | ghi_chu |
|---|---|---|---|
| timestamp | timestamp | Có |  |
| stablecoin | stablecoin | Có |  |
| price | price (+ open/high/low) | Có | Daily, UTC 00:00 |
| peg_deviation | peg_deviation, peg_deviation_min, peg_deviation_hl_clean | Có | Thêm bản đồng thuận nhiều nguồn và bản trong ngày đã làm sạch |
| volume | volume | Có |  |
| liquidity | turnover, range_hl, xmkt_gap | Proxy | Không có bid-ask spread/order book lịch sử miễn phí |
| supply | supply | Có | DefiLlama, trễ 1 ngày |
| supply_change | supply_change, supply_eth_change | Có/Proxy | Proxy mint/burn ròng |
| dex_imbalance | (không có) -> xmkt_gap, supply_eth_share | KHÔNG | Không tải được dữ liệu on-chain/DEX; dùng chênh lệch giá liên thị trường làm proxy |
| mint/burn, exchange flows | (không có) -> supply_change, supply_eth_change | KHÔNG | Không có on-chain; dùng thay đổi supply DefiLlama |
| btc_vol | btc_vol (+ btc_ret) | Có |  |
| eth_vol | eth_vol (+ eth_ret) | Có |  |
| collateral price shocks | eth_ret, eth_vol | Proxy | ETH đại diện tài sản thế chấp của DAI |
| tvl_change | tvl_change (+ tvl) | Có | DefiLlama, trễ 1 ngày |
| depeg_label_h1/h6/h24 | (Code 2 tạo) | Không thuộc Code 1 | Panel daily: h tính theo ngày (h = 1, 3) bằng shift(-h) trong từng coin |
