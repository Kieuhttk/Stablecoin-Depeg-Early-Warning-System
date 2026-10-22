import pandas as pd
from sklearn.metrics import average_precision_score as ap

def load(d):
    p = pd.read_parquet(f"{d}/dev/predictions_oof.parquet")
    return p[(p.eligible == 1) & (p.h == 1)]

full, nox = load("outputs"), load("outputs_nox")
print(full[full.model == "rf"].groupby("stablecoin")["label"].agg(["sum", "count"]))

rate = full[full.model == "rf"].groupby("stablecoin")["label"].mean()
prior = full[full.model == "rf"].assign(s=lambda d: d.stablecoin.map(rate))
print("Chỉ dùng tỷ lệ sự kiện theo coin (cận trên):", round(ap(prior.label, prior.s), 3))

for name, d in [("đủ biến", full), ("bỏ xmkt", nox)]:
    for m in ["rf", "xgboost", "baseline"]:
        x = d[d.model == m]
        per = {c: round(ap(g.label, g.score_raw), 3)
               for c, g in x.groupby("stablecoin") if g.label.sum() > 0}
        print(name, m, "gộp", round(ap(x.label, x.score_raw), 3), "từng coin", per)