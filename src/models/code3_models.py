"""Code 3: mô hình ML, đánh giá sự kiện hiếm, lead time và giải thích mô hình.

Chạy từ thư mục gốc repository (xem code3_runbook.md):

    python -m src.models.code3_models --stage dev          # 22/10 và sáng 23/10
    python -m src.models.code3_models --stage test         # chiều 23/10, CHỈ MỘT LẦN
    python -m src.models.code3_models --stage robustness   # sau khi test xong (P2)

Nguyên tắc:
  * Stage dev không bao giờ nạp hàng thuộc split test vào bộ nhớ.
  * Mọi lựa chọn (tham số, ngưỡng, hiệu chuẩn xác suất) dựa trên walk-forward trên
    train + validation, rồi đóng băng trong model_freeze.json.
  * Stage test đọc file đóng băng, huấn luyện lại trên train + validation và chấm test
    một lần; tạo khóa outputs/test_run.lock.json để chặn chạy lại.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

try:  # tùy chọn: có thì dùng, không có thì dùng phương án thay thế đã ghi nhãn rõ
    import xgboost as xgb

    HAS_XGB = True
except ImportError:  # pragma: no cover
    HAS_XGB = False
try:
    import shap

    HAS_SHAP = True
except ImportError:  # pragma: no cover
    HAS_SHAP = False

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "code3.yaml"
KEYS = ["stablecoin", "date"]
FORBIDDEN_PREFIXES = ("onset_", "state_", "depeg_", "hl_supported", "split", "eligible")


# ============================================================
# Cấu hình, đọc/ghi dữ liệu
# ============================================================

def load_config(path: Path = CONFIG_PATH) -> dict:
    with Path(path).open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with (PROJECT_ROOT / cfg["labels_config"]).open("r", encoding="utf-8") as f:
        cfg["labels"] = yaml.safe_load(f)
    all_features = list(cfg["labels"]["feature_columns"])
    exclude = set(cfg.get("exclude_features") or [])
    unknown = exclude - set(all_features)
    if unknown:
        raise ValueError(f"exclude_features chứa biến không có trong labels.yaml: {sorted(unknown)}")
    cfg["exclude_features"] = sorted(exclude)
    cfg["feature_columns"] = [c for c in all_features if c not in exclude]
    cfg["feature_groups"] = {g: [c for c in cols if c not in exclude]
                             for g, cols in cfg["feature_groups"].items()}
    cfg["feature_groups"] = {g: cols for g, cols in cfg["feature_groups"].items() if cols}
    grouped = [c for cols in cfg["feature_groups"].values() for c in cols]
    if sorted(grouped) != sorted(cfg["feature_columns"]):
        raise ValueError("feature_groups trong code3.yaml không trùng 27 predictor của labels.yaml")
    bad = [c for c in cfg["feature_columns"] if c.startswith(FORBIDDEN_PREFIXES)]
    if bad:
        raise ValueError(f"Predictor chứa cột nhãn/quản lý không được phép: {bad}")
    return cfg


def read_table(path: Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix == ".pkl":  # chỉ dùng khi môi trường không có engine parquet
        return pd.read_pickle(path)
    return pd.read_csv(path)


def write_table(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=False)
        return path
    except ImportError:
        alt = path.with_suffix(".csv")
        warnings.warn(f"Không có engine parquet; ghi {alt.name} thay cho {path.name}")
        df.to_csv(alt, index=False)
        return alt


def to_utc(s: pd.Series) -> pd.Series:
    """Hợp đồng với Code 2/4: timestamp là datetime64[ns, UTC] (00:00 UTC)."""
    return pd.to_datetime(s, utc=True)


def variant_name(spec: dict) -> str:
    return f"{spec['source']}_tau{spec['tau']:.3f}_m{spec['m']}"


def label_cols(spec: dict, h: int) -> tuple[str, str, str]:
    v = variant_name(spec)
    return f"onset_label_{v}_d{h}", f"onset_label_{v}_eligible_d{h}", f"onset_{v}"


def load_data(cfg: dict, features_path: str | None, drop_splits: tuple[str, ...]) -> pd.DataFrame:
    path = Path(features_path) if features_path else PROJECT_ROOT / cfg["features_path"]
    df = read_table(path)
    df["date"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None).dt.normalize()
    df = df[~df["split"].isin(drop_splits)].copy()   # bỏ split bị cấm NGAY khi nạp
    df = df.sort_values(KEYS).reset_index(drop=True)
    if df.duplicated(KEYS).any():
        raise ValueError("features có khóa (stablecoin, date) bị trùng")
    missing = [c for c in cfg["feature_columns"] if c not in df.columns]
    if missing:
        raise ValueError(f"features.parquet thiếu predictor: {missing}")
    return df


# ============================================================
# Mô hình
# ============================================================

def impl_name(kind: str) -> str:
    if kind == "gboost":
        return "xgboost" if HAS_XGB else "hgb_sklearn"
    return kind


class Model:
    """Bao các mô hình về cùng giao diện fit/score; điểm số nằm trong [0, 1]."""

    def __init__(self, kind: str, params: dict, seed: int):
        self.kind, self.params, self.seed = kind, dict(params), seed
        self.est = None
        self.medians: pd.Series | None = None

    @property
    def name(self) -> str:
        return impl_name(self.kind)

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> "Model":
        self.medians = X.median()
        if self.kind == "baseline":
            return self
        Xn, p = X.to_numpy(float), self.params
        if self.kind == "logit":
            self.est = make_pipeline(
                SimpleImputer(strategy="median"), StandardScaler(),
                LogisticRegression(C=p["C"], class_weight="balanced", max_iter=5000),
            )
        elif self.kind == "rf":
            self.est = make_pipeline(
                SimpleImputer(strategy="median"),
                RandomForestClassifier(
                    n_estimators=p["n_estimators"], max_depth=p["max_depth"],
                    min_samples_leaf=p["min_samples_leaf"], max_features="sqrt",
                    class_weight="balanced_subsample", n_jobs=-1, random_state=self.seed),
            )
        elif self.kind == "gboost" and HAS_XGB:
            n_pos = max(float(np.sum(y)), 1.0)
            self.est = xgb.XGBClassifier(
                n_estimators=p["n_estimators"], max_depth=p["max_depth"],
                learning_rate=p["learning_rate"], subsample=0.8, colsample_bytree=0.8,
                reg_lambda=5.0, scale_pos_weight=min((len(y) - n_pos) / n_pos, 200.0),
                tree_method="hist", eval_metric="aucpr", random_state=self.seed, n_jobs=-1)
        elif self.kind == "gboost":
            self.est = HistGradientBoostingClassifier(
                max_depth=p["max_depth"], max_iter=p["n_estimators"],
                learning_rate=p["learning_rate"], min_samples_leaf=p["min_leaf"],
                l2_regularization=5.0, class_weight="balanced", early_stopping=False,
                random_state=self.seed)
        else:
            raise ValueError(f"Mô hình không hỗ trợ: {self.kind}")
        self.est.fit(Xn, y.astype(int))
        return self

    def score(self, X: pd.DataFrame) -> np.ndarray:
        if self.kind == "baseline":
            return X["peg_deviation"].to_numpy(float)       # baseline ngây thơ: độ lệch hiện tại
        return self.est.predict_proba(X.to_numpy(float))[:, 1]

    def explain(self, X: pd.DataFrame) -> tuple[np.ndarray, str]:
        """Đóng góp từng feature vào điểm rủi ro. SHAP cây nếu có (RF, XGBoost); nếu không thì
        occlusion: đặt từng feature về "thiếu" (NaN: mô hình xử lý bằng cách điền trung vị
        train hoặc nhánh NaN gốc) rồi đo mức giảm điểm. Cột `method` ở T06 ghi rõ phương pháp."""
        if HAS_SHAP and ((self.kind == "gboost" and HAS_XGB) or self.kind == "rf"):
            if self.kind == "rf":      # pipeline: imputer -> RF; SHAP tính trên dữ liệu đã điền
                est, Xs = self.est[-1], self.est[:-1].transform(X.to_numpy(float))
            else:
                est, Xs = self.est, X.to_numpy(float)
            vals = shap.TreeExplainer(est).shap_values(Xs)
            if isinstance(vals, list):          # shap cũ: [lớp 0, lớp 1]
                vals = vals[1]
            vals = np.asarray(vals)
            if vals.ndim == 3:                  # shap mới: (n, feature, lớp)
                vals = vals[:, :, 1]
            return vals, "shap_tree"
        base = self.score(X)
        out = np.zeros((len(X), X.shape[1]))
        for j, c in enumerate(X.columns):
            Xo = X.copy()
            Xo[c] = np.nan
            out[:, j] = base - self.score(Xo)
        return out, "occlusion"


def grid_for(cfg: dict, kind: str) -> list[dict]:
    return [{}] if kind == "baseline" else cfg["grid"][kind]


# ============================================================
# Walk-forward (expanding window) có purge
# ============================================================

def walk_forward(df, cfg, spec, h, kind, params, features, explain=False):
    """Điểm out-of-fold cho các khối kiểm tra trong cấu hình.
    Trả về DataFrame (index của df) gồm score, fold và (tùy chọn) đóng góp từng feature."""
    ycol, ecol, _ = label_cols(spec, h)
    starts = pd.to_datetime(cfg["cv_block_starts"] + [cfg["cv_end"]])
    purge = pd.Timedelta(days=h + spec["m"])           # nhãn t dùng tới t + h (+ xác nhận m)
    parts, attrs, method = [], [], None
    for i in range(len(starts) - 1):
        b0, b1 = starts[i], starts[i + 1]
        tr = df[(df["date"] <= b0 - purge) & (df[ecol] == 1)]
        te = df[(df["date"] >= b0) & (df["date"] < b1)]
        assert tr["date"].max() < b0 - pd.Timedelta(days=h), "purge không đủ: nhãn chồng sang khối kiểm tra"
        if te.empty:
            continue
        if tr[ycol].sum() < 2 and kind != "baseline":
            parts.append(pd.DataFrame({"score": np.nan, "fold": i}, index=te.index))
            continue
        m = Model(kind, params, cfg["seed"]).fit(tr[features], tr[ycol].to_numpy())
        parts.append(pd.DataFrame({"score": m.score(te[features]), "fold": i}, index=te.index))
        if explain:
            a, method = m.explain(te[features])
            attrs.append(pd.DataFrame(a, index=te.index, columns=features))
    out = pd.concat(parts)
    return (out, pd.concat(attrs), method) if explain else out


# ============================================================
# Metrics
# ============================================================

def pick_threshold(y: np.ndarray, s: np.ndarray, beta: float) -> float:
    if y.sum() == 0:
        return float("nan")
    prec, rec, thr = precision_recall_curve(y, s)
    p, r = prec[:-1], rec[:-1]
    f = np.where(p + r > 0, (1 + beta**2) * p * r / (beta**2 * p + r + 1e-300), 0.0)
    best = np.flatnonzero(f >= f.max() - 1e-12).max()   # nhiều ngưỡng bằng nhau: lấy ngưỡng cao nhất
    return float(thr[best])


def obs_metrics(y: np.ndarray, s: np.ndarray, thr: float, beta: float) -> dict:
    n, pos = len(y), int(np.sum(y))
    out = {"n_obs": n, "n_pos": pos, "prevalence": pos / n if n else np.nan}
    out["pr_auc"] = average_precision_score(y, s) if pos > 0 else np.nan
    out["pr_auc_lift"] = out["pr_auc"] / out["prevalence"] if pos > 0 else np.nan
    out["roc_auc"] = roc_auc_score(y, s) if 0 < pos < n else np.nan
    pred = s >= thr if not np.isnan(thr) else np.zeros(n, bool)
    tp, fp = int(np.sum(pred & (y == 1))), int(np.sum(pred & (y == 0)))
    fn, tn = int(np.sum(~pred & (y == 1))), int(np.sum(~pred & (y == 0)))
    prec = tp / (tp + fp) if tp + fp else np.nan
    rec = tp / (tp + fn) if tp + fn else np.nan
    f = lambda b: ((1 + b**2) * prec * rec / (b**2 * prec + rec)) if tp > 0 else (0.0 if pos else np.nan)
    out.update(threshold=thr, precision=prec, recall=rec, f1=f(1.0), f2=f(beta),
               false_alarm_rate=fp / (fp + tn) if fp + tn else np.nan, n_alarms=tp + fp)
    return out


def event_level(frame: pd.DataFrame, h: int, onset_col: str, elig_col: str, lookback: int = None) -> dict:
    """Mức sự kiện: một sự kiện được bắt nếu có cảnh báo ở ít nhất một ngày trong cửa sổ lookback.
    Lead time = số ngày từ cảnh báo sớm nhất trong cửa sổ đến ngày bắt đầu sự kiện."""
    lb = lookback or h  # Nếu không truyền lookback thì lấy giá trị của h
    leads, caught, evaluable, total = [], 0, 0, 0
    for _, g in frame.groupby("stablecoin"):
        g = g.set_index("date").sort_index()
        for d in g.index[g[onset_col] == 1]:
            total += 1
            w = g.loc[d - pd.Timedelta(days=lb): d - pd.Timedelta(days=1)]
            w = w[(w[elig_col] == 1) & w["alarm"].notna()]
            if w.empty:
                continue
            evaluable += 1
            hit = w[w["alarm"] == True]  # noqa: E712
            if len(hit):
                caught += 1
                leads.append((d - hit.index.min()).days)
    return {"n_events": total, "n_evaluable": evaluable, "n_caught": caught,
            "event_recall": caught / evaluable if evaluable else np.nan,
            "mean_lead_days": float(np.mean(leads)) if leads else np.nan,
            "median_lead_days": float(np.median(leads)) if leads else np.nan,
            "max_lead_days": float(np.max(leads)) if leads else np.nan}

def scope_masks(df: pd.DataFrame, stage: str) -> dict[str, pd.Series]:
    if stage == "test":
        return {"test": df["split"] == "test"}
    return {"oof_2021_2022": df["date"] >= pd.Timestamp("2021-01-01"),
            "validation_2022": df["split"] == "validation"}


def evaluate(df, scores, thr, cfg, spec, h, scope_mask, kind, params, stage, scope):
    """Gộp metric mức quan sát (T04) và mức sự kiện (T05) cho một mô hình, một horizon."""
    ycol, ecol, ocol = label_cols(spec, h)
    d = df.assign(score=scores)[scope_mask & scores.notna()]
    d = d.assign(alarm=np.where(d["score"].notna(), d["score"] >= thr, np.nan))
    de = d[d[ecol] == 1]
    base = {"stage": stage, "scope": scope, "h": h, "model": impl_name(kind),
            "params": json.dumps(params, sort_keys=True)}
    t04 = {**base, **obs_metrics(de[ycol].to_numpy(float), de["score"].to_numpy(float), thr, cfg["f_beta"])}
    ev = event_level(d[KEYS + [ocol, ecol, "alarm"]], h, ocol, ecol, lookback=cfg.get("lead_lookback", h))
    # T05 (Precision, Recall, lead time theo horizon): ghép precision/recall mức quan sát từ T04
    lb = cfg.get("lead_lookback", h)
    alarm_rate = t04["n_alarms"] / max(t04["n_obs"], 1)
    t05 = {**base,
           "precision": t04["precision"], "recall": t04["recall"], "f2": t04["f2"],
           "false_alarm_rate": t04["false_alarm_rate"],
           **ev, "lead_lookback_days": lb,
           # Mốc so sánh: xác suất có >= 1 báo động trong cửa sổ nếu báo động rải độc lập với cùng
           # tần suất. Mô hình báo động nhiều thì event_recall cao hơn chỉ nhờ may rủi; đọc
           # event_recall cùng cột này (báo động thực tế thường dồn cụm nên mốc này là cận trên).
           "chance_event_recall": 1.0 - (1.0 - alarm_rate) ** lb,
           "n_alarm_days": t04["n_alarms"],
           "alarm_days_per_100_obs": 100 * alarm_rate}
    return t04, t05


def budget_metrics(df, scores, cfg, spec, h, scope_mask, kind, stage, scope):
    """So sánh công bằng giữa các mô hình ở CÙNG ngân sách báo động (tỉ lệ ngày bị báo động).

    Ngưỡng là phân vị của điểm số trong chính phạm vi đánh giá (không dùng nhãn), nên mô hình
    nào cũng báo động đúng cùng số ngày. Đây là cách đọc RQ4 (ML có tăng recall mà không tăng
    báo động giả không) và cách so với baseline, vì ngưỡng F2 làm mỗi mô hình báo động nhiều
    ít khác nhau."""
    ycol, ecol, ocol = label_cols(spec, h)
    lb = cfg.get("lead_lookback", h)
    d = df.assign(score=scores)[scope_mask & scores.notna()]
    elig = d[d[ecol] == 1]
    rows = []
    for b in cfg.get("alarm_budgets", [0.03, 0.05, 0.10]):
        thr = float(np.quantile(elig["score"], 1 - b))
        dd = d.assign(alarm=np.where(d["score"].notna(), d["score"] >= thr, np.nan))
        ee = dd[dd[ecol] == 1]
        y, a = ee[ycol].to_numpy(float), ee["alarm"].to_numpy(float) == 1
        tp = int(np.sum(a & (y == 1)))
        ev = event_level(dd[KEYS + [ocol, ecol, "alarm"]], h, ocol, ecol, lookback=lb)
        rows.append({"stage": stage, "scope": scope, "h": h, "model": impl_name(kind),
                     "alarm_budget": b, "alarm_rate_actual": float(a.mean()), "threshold": thr,
                     "obs_recall": tp / y.sum() if y.sum() else np.nan,
                     "precision": tp / a.sum() if a.sum() else np.nan,
                     "n_events": ev["n_events"], "n_evaluable": ev["n_evaluable"],
                     "n_caught": ev["n_caught"], "event_recall": ev["event_recall"],
                     "mean_lead_days": ev["mean_lead_days"], "lead_lookback_days": lb,
                     "chance_event_recall": 1.0 - (1.0 - float(a.mean())) ** lb})
    return rows


# ============================================================
# Hiệu chuẩn xác suất (Platt) và giải thích
# ============================================================

def _z(s: np.ndarray) -> np.ndarray:
    s = np.clip(s, 1e-6, 1 - 1e-6)
    return np.log(s / (1 - s)).reshape(-1, 1)


def fit_platt(s: np.ndarray, y: np.ndarray) -> dict:
    if y.sum() < 2:
        return {"coef": float("nan"), "intercept": float("nan")}
    lr = LogisticRegression(C=1e6, max_iter=1000).fit(_z(s), y.astype(int))
    return {"coef": float(lr.coef_[0, 0]), "intercept": float(lr.intercept_[0])}


def apply_platt(s: np.ndarray, platt: dict) -> np.ndarray:
    if np.isnan(platt["coef"]):
        return np.full(len(s), np.nan)
    return 1.0 / (1.0 + np.exp(-(platt["coef"] * _z(s)[:, 0] + platt["intercept"])))


def top_drivers(attr: pd.DataFrame) -> pd.DataFrame:
    """Top 3 feature làm TĂNG rủi ro nhiều nhất ở từng dòng. Feature có đóng góp <= 0 không
    được coi là driver rủi ro nên để trống (None), tránh dashboard hiển thị driver sai."""
    a = attr.to_numpy()
    order = np.argsort(-a, axis=1)[:, :3]
    cols = np.array(attr.columns, dtype=object)
    vals = np.take_along_axis(a, order, axis=1)
    names = np.where(vals > 0, cols[order], None)
    return pd.DataFrame({f"top{k + 1}_driver": names[:, k] for k in range(3)}, index=attr.index)


def importance_table(attr: pd.DataFrame, groups: dict, extra: dict) -> pd.DataFrame:
    g_of = {c: g for g, cols in groups.items() for c in cols}
    imp = attr.abs().mean().sort_values(ascending=False)
    out = pd.DataFrame({"rank": range(1, len(imp) + 1), "feature": imp.index,
                        "feature_group": [g_of[c] for c in imp.index],
                        "mean_abs_attr": imp.to_numpy(), "share": imp.to_numpy() / imp.sum()})
    return out.assign(**extra)


# ============================================================
# Biểu đồ
# ============================================================

def plot_pr(curves: dict, prevalence: dict, path: Path, title: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    hs = sorted({h for h, _ in curves})
    fig, axes = plt.subplots(1, len(hs), figsize=(6 * len(hs), 4.6), squeeze=False)
    for ax, h in zip(axes[0], hs):
        for (hh, model), (rec, prec, ap) in curves.items():
            if hh == h:
                ax.plot(rec, prec, lw=1.6, label=f"{model} (AP = {ap:.3f})")
        ax.axhline(prevalence[h], ls="--", c="grey", lw=1, label=f"ngẫu nhiên = {prevalence[h]:.4f}")
        ax.set(xlabel="Recall", ylabel="Precision", title=f"h = {h} ngày", xlim=(0, 1), ylim=(0, 1.02))
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(alpha=0.3)
    fig.suptitle(title, fontsize=11)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300)
    plt.close(fig)


# ============================================================
# Stage dev: chọn tham số, ngưỡng, hiệu chuẩn; đóng băng mô hình
# ============================================================

def stage_dev(cfg, df, out_dir: Path) -> None:
    assert not (df["split"] == "test").any(), "Stage dev không được chứa dữ liệu test"
    spec, feats, beta = cfg["spec"], cfg["feature_columns"], cfg["f_beta"]
    dev_dir = out_dir / "dev"
    grid_rows, t04, t05, t05b, t06, preds, freeze = [], [], [], [], [], [], {}
    curves, prevalence = {}, {}

    for h in cfg["horizons"]:
        ycol, ecol, _ = label_cols(spec, h)
        freeze[str(h)] = {}
        for kind in cfg["models"]:
            t0, best = time.time(), None
            for params in grid_for(cfg, kind):
                oof = walk_forward(df, cfg, spec, h, kind, params, feats)
                m = (df[ecol] == 1) & oof["score"].reindex(df.index).notna()
                y, s = df.loc[m, ycol].to_numpy(float), oof["score"].reindex(df.index)[m].to_numpy(float)
                ap = average_precision_score(y, s) if y.sum() > 0 else np.nan
                grid_rows.append({"h": h, "model": impl_name(kind), "params": json.dumps(params, sort_keys=True),
                                  "cv_pr_auc": ap, "n_obs": len(y), "n_pos": int(y.sum())})
                if best is None or (not np.isnan(ap) and (np.isnan(best[0]) or ap > best[0])):
                    best = (ap, params, oof)
            ap, params, oof = best
            score = oof["score"].reindex(df.index)
            m = (df[ecol] == 1) & score.notna()
            y, s = df.loc[m, ycol].to_numpy(float), score[m].to_numpy(float)
            thr = pick_threshold(y, s, beta)
            platt = fit_platt(s, y)
            freeze[str(h)][kind] = {"implementation": impl_name(kind), "params": params, "threshold": thr,
                                    "platt": platt, "cv_pr_auc": ap}
            for scope, mask in scope_masks(df, "dev").items():
                a, b = evaluate(df, score, thr, cfg, spec, h, mask, kind, params, "dev", scope)
                t04.append(a)
                t05.append(b)
                t05b.extend(budget_metrics(df, score, cfg, spec, h, mask, kind, "dev", scope))
            mm = scope_masks(df, "dev")["oof_2021_2022"] & (df[ecol] == 1) & score.notna()
            yy, ss = df.loc[mm, ycol].to_numpy(float), score[mm].to_numpy(float)
            prec, rec, _ = precision_recall_curve(yy, ss)
            curves[(h, impl_name(kind))] = (rec, prec, average_precision_score(yy, ss))
            prevalence[h] = yy.mean()
            preds.append(pd.DataFrame({
                "timestamp": to_utc(df.loc[score.notna(), "date"]), "stablecoin": df.loc[score.notna(), "stablecoin"],
                "model": impl_name(kind), "h": h, "split": df.loc[score.notna(), "split"],
                "score_raw": score[score.notna()], "threshold_raw": thr,
                "proba": apply_platt(score[score.notna()].to_numpy(float), platt),
                "alarm": score[score.notna()] >= thr, "eligible": df.loc[score.notna(), ecol].astype(int),
                "label": df.loc[score.notna(), ycol], "proba_type": "oof"}))
            print(f"[dev] h={h} {impl_name(kind):12s} cv_PR-AUC={ap:.4f} thr={thr:.4f} ({time.time() - t0:.0f}s)")

        # Giải thích cho mô hình dashboard: refit từng fold với tham số đã chốt
        dk = cfg["dashboard_model"]
        _, attr, method = walk_forward(df, cfg, spec, h, dk, freeze[str(h)][dk]["params"], feats, explain=True)
        mm = (df[ecol] == 1) & df.index.isin(attr.index) & (df["date"] >= pd.Timestamp("2021-01-01"))
        t06.append(importance_table(attr.loc[df.index[mm]], cfg["feature_groups"],
                                    {"stage": "dev", "scope": "oof_2021_2022", "h": h,
                                     "model": impl_name(dk), "method": method}))
        drv = top_drivers(attr)
        for p in preds:
            if p["h"].iloc[0] == h and p["model"].iloc[0] == impl_name(dk):
                p["explain_method"] = method
                for c in drv.columns:
                    p[c] = drv[c].reindex(p.index)

    # Tiêu chí chọn mô hình viết sẵn (ghi vào Nhật ký quyết định): mô hình ML có PR-AUC
    # walk-forward cao nhất ở horizon chính; baseline và logit chỉ là benchmark.
    ph = str(cfg.get("primary_horizon", cfg["horizons"][0]))
    ml_kinds = [k for k in cfg["models"] if k not in ("baseline", "logit")]
    by_rule = max(ml_kinds, key=lambda k: np.nan_to_num(freeze[ph][k]["cv_pr_auc"], nan=-1.0))
    if by_rule != cfg["dashboard_model"]:
        print(f"\nCẢNH BÁO: dashboard_model = {cfg['dashboard_model']} nhưng theo tiêu chí PR-AUC walk-forward "
              f"ở h={ph} thì là {by_rule}. Ghi lý do vào Nhật ký quyết định nếu giữ nguyên.")

    pred_df = pd.concat(preds, ignore_index=True)
    dev_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(grid_rows).to_csv(dev_dir / "dev_cv_grid.csv", index=False)
    pd.DataFrame(t04).to_csv(dev_dir / "T04_dev_model_performance.csv", index=False)
    pd.DataFrame(t05).to_csv(dev_dir / "T05_dev_event_level.csv", index=False)
    pd.DataFrame(t05b).to_csv(dev_dir / "T05b_dev_matched_budget.csv", index=False)
    pd.concat(t06).to_csv(dev_dir / "T06_dev_feature_importance.csv", index=False)
    write_table(pred_df, dev_dir / "predictions_oof.parquet")
    plot_pr(curves, prevalence, dev_dir / "F02_dev_pr_curves.png",
            "Đường precision-recall, out-of-fold 2021-2022 (giai đoạn dev, chưa phải test)")
    freeze_doc = {"created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "spec": spec, "seed": cfg["seed"], "has_xgboost": HAS_XGB, "has_shap": HAS_SHAP,
                  "lead_lookback": cfg.get("lead_lookback"), "dashboard_model": cfg["dashboard_model"],
                  "exclude_features": cfg["exclude_features"],
                  "model_by_selection_rule": by_rule,
                  "feature_columns": feats, "models": freeze}
    (dev_dir / "model_freeze.json").write_text(json.dumps(freeze_doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nXong stage dev. Đã ghi {dev_dir}/ (model_freeze.json là bản đóng băng cho stage test).")


# ============================================================
# Stage test: chạy MỘT LẦN
# ============================================================

def _final_fit_predict(df, cfg, spec, h, kind, params, features, train_splits, holdout):
    ycol, ecol, _ = label_cols(spec, h)
    tr = df[df["split"].isin(train_splits) & (df[ecol] == 1)]
    m = Model(kind, params, cfg["seed"]).fit(tr[features], tr[ycol].to_numpy())
    return m, pd.Series(m.score(df.loc[df["split"] == holdout, features]), index=df.index[df["split"] == holdout])


def stage_test(cfg, df, out_dir: Path, args) -> None:
    dev_dir = out_dir / "dev"
    freeze_path = dev_dir / "model_freeze.json"
    lock_path = out_dir / "test_run.lock.json"
    if not freeze_path.exists():
        raise SystemExit("Thiếu model_freeze.json. Chạy --stage dev và chốt mô hình trước.")
    if lock_path.exists() and not args.dry_run:
        raise SystemExit(f"Test đã chạy ({lock_path}). Test set chỉ được chạy một lần.")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    freeze_hash = hashlib.sha256(freeze_path.read_bytes()).hexdigest()
    spec, feats, beta = cfg["spec"], cfg["feature_columns"], cfg["f_beta"]
    hold, train_splits = (args.holdout, args.train_splits)
    final_dir = out_dir / ("dry_run" if args.dry_run else "")
    oof_all = read_table(next(dev_dir.glob("predictions_oof.*")))
    t04, t05, t05b, t06, preds, curves, prevalence, p1 = [], [], [], [], [], {}, {}, []
    for h in cfg["horizons"]:
        ycol, ecol, ocol = label_cols(spec, h)
        for kind in cfg["models"]:
            cfgm = freeze["models"][str(h)][kind]
            model, sc = _final_fit_predict(df, cfg, spec, h, kind, cfgm["params"], feats, train_splits, hold)
            score = pd.Series(np.nan, index=df.index)
            score.loc[sc.index] = sc
            thr, platt = cfgm["threshold"], cfgm["platt"]
            mask = df["split"] == hold
            a, b = evaluate(df, score, thr, cfg, spec, h, mask, kind, cfgm["params"], "test", hold)
            t04.append(a)
            t05.append(b)
            t05b.extend(budget_metrics(df, score, cfg, spec, h, mask, kind, "test", hold))
            d = df[mask & (df[ecol] == 1) & score.notna()]
            ss, yy = score[d.index].to_numpy(float), d[ycol].to_numpy(float)
            prec, rec, _ = precision_recall_curve(yy, ss)
            curves[(h, impl_name(kind))] = (rec, prec, average_precision_score(yy, ss) if yy.sum() else np.nan)
            prevalence[h] = yy.mean()
            # P1: theo loại stablecoin và từng coin
            for label, coins in [*[(t, [c for c, tt in cfg["coin_types"].items() if tt == t])
                                   for t in sorted(set(cfg["coin_types"].values()))],
                                 *[(c, [c]) for c in cfg["coin_types"]]]:
                sub = mask & df["stablecoin"].isin(coins)
                x, y_ = evaluate(df, score, thr, cfg, spec, h, sub, kind, cfgm["params"], "test", f"{hold}:{label}")
                p1.append({**x, **{k: y_[k] for k in ("n_events", "n_evaluable", "n_caught", "event_recall", "mean_lead_days")},
                           "group": label})
            sel = score.notna()
            frame = pd.DataFrame({
                "timestamp": to_utc(df.loc[sel & mask, "date"]), "stablecoin": df.loc[sel & mask, "stablecoin"],
                "model": impl_name(kind), "h": h, "split": df.loc[sel & mask, "split"],
                "score_raw": score[sel & mask], "threshold_raw": thr,
                "proba": apply_platt(score[sel & mask].to_numpy(float), platt),
                "alarm": score[sel & mask] >= thr, "eligible": df.loc[sel & mask, ecol].astype(int),
                "label": df.loc[sel & mask, ycol], "proba_type": "final"})
            if kind == cfg["dashboard_model"]:
                att, method = model.explain(df.loc[sel & mask, feats])
                att = pd.DataFrame(att, index=df.index[sel & mask], columns=feats)
                frame["explain_method"] = method
                for c, v in top_drivers(att).items():
                    frame[c] = v.reindex(frame.index)
                t06.append(importance_table(att.loc[(df.loc[att.index, ecol] == 1)], cfg["feature_groups"],
                                            {"stage": "test", "scope": hold, "h": h, "model": impl_name(kind),
                                             "method": method}))
            preds.append(frame)
            print(f"[test] h={h} {impl_name(kind):12s} PR-AUC={a['pr_auc']:.4f}  recall={a['recall']:.3f}  "
                  f"events caught {b['n_caught']}/{b['n_evaluable']}")

    out_dir_f = final_dir
    (out_dir_f / "tables").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(t04).to_csv(out_dir_f / "tables" / "T04_model_performance.csv", index=False)
    pd.DataFrame(t05).to_csv(out_dir_f / "tables" / "T05_precision_recall_by_horizon.csv", index=False)
    pd.DataFrame(t05b).to_csv(out_dir_f / "tables" / "T05b_matched_budget.csv", index=False)
    pd.concat(t06).to_csv(out_dir_f / "tables" / "T06_shap_ranking.csv", index=False)
    pd.DataFrame(p1).to_csv(out_dir_f / "tables" / "P1_by_stablecoin_type.csv", index=False)
    pred_all = pd.concat([oof_all.assign(timestamp=to_utc(oof_all["timestamp"])), *preds], ignore_index=True)
    write_table(pred_all, out_dir_f / "predictions.parquet")
    plot_pr(curves, prevalence, out_dir_f / "figures" / "F02_pr_curves.png",
            f"Đường precision-recall trên tập {hold}")
    if not args.dry_run:
        lock_path.write_text(json.dumps({
            "test_run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "freeze_sha256": freeze_hash, "has_xgboost": HAS_XGB, "has_shap": HAS_SHAP}, indent=2), encoding="utf-8")
    print("\nXong stage test." + ("" if args.dry_run else f" Đã tạo khóa {lock_path.name}."))


# ============================================================
# Stage robustness (P2): sau khi test đã chạy; chỉ đo độ nhạy
# ============================================================

def stage_robustness(cfg, df, out_dir: Path, args) -> None:
    if not (out_dir / "test_run.lock.json").exists() and not args.dry_run:
        raise SystemExit("Chạy --stage test trước; robustness chỉ đo độ nhạy sau khi test đã chạy.")
    freeze = json.loads((out_dir / "dev" / "model_freeze.json").read_text(encoding="utf-8"))
    feats = cfg["feature_columns"]
    hold, train_splits = args.holdout, args.train_splits
    rows = []

    def run(variant_type, variant, spec, h, features, kind, ycol=None, ecol=None):
        yc, ec, _ = label_cols(spec, h)
        ycol, ecol = ycol or yc, ecol or ec
        params = freeze["models"][str(h)][kind]["params"]
        tr = df[df["split"].isin(train_splits) & (df[ecol] == 1)]
        te = df[(df["split"] == hold) & (df[ecol] == 1)]
        if tr[ycol].sum() < 2 or te.empty:
            return
        m = Model(kind, params, cfg["seed"]).fit(tr[features], tr[ycol].to_numpy())
        met = obs_metrics(te[ycol].to_numpy(float), m.score(te[features]), float("nan"), cfg["f_beta"])
        rows.append({"variant_type": variant_type, "variant": variant, "h": h, "model": impl_name(kind),
                     **{k: met[k] for k in ("n_obs", "n_pos", "prevalence", "pr_auc", "pr_auc_lift", "roc_auc")}})

    for h in cfg["horizons"]:
        for kind in cfg["robustness_models"]:
            run("baseline_spec", variant_name(cfg["spec"]), cfg["spec"], h, feats, kind)
            for sp in cfg["robustness_specs"]:
                run("label_variant", variant_name(sp), sp, h, feats, kind)
            v = variant_name(cfg["spec"])      # nhãn đúng như đề: Depeg tại t + h
            run("paper_label", f"depeg_at_t_plus_d{h}_{v}", cfg["spec"], h, feats, kind,
                ycol=f"depeg_at_t_plus_d{h}_{v}", ecol=f"depeg_at_t_plus_d{h}_eligible_{v}")
            if kind == "baseline":      # baseline chỉ dùng peg_deviation: không áp dụng bỏ feature
                continue
            for g, cols in cfg["feature_groups"].items():
                run("drop_feature_group", f"drop_{g}", cfg["spec"], h, [c for c in feats if c not in cols], kind)
            # xmkt_gap có thể đóng vai trò biến thay cho mã coin (gần như chỉ có ở USDC): kiểm tra riêng
            for name, cols in cfg.get("robustness_drop_features", {}).items():
                run("drop_features", name, cfg["spec"], h, [c for c in feats if c not in cols], kind)
    res = pd.DataFrame(rows)
    path = out_dir / ("dry_run" if args.dry_run else "") / "tables" / "P2_robustness.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(path, index=False)
    print(res.groupby(["variant_type", "h"]).size().to_string())
    print(f"\nĐã ghi {path}")


# ============================================================
# CLI
# ============================================================

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["dev", "test", "robustness"], required=True)
    ap.add_argument("--config", default=str(CONFIG_PATH))
    ap.add_argument("--features-path", default=None, help="mặc định theo code3.yaml")
    ap.add_argument("--dry-run", action="store_true",
                    help="chạy thử đường mã stage test/robustness trên validation, không đụng split test")
    ap.add_argument("--holdout", default="test")
    ap.add_argument("--train-splits", nargs="+", default=["train", "validation"])
    args = ap.parse_args()
    cfg = load_config(Path(args.config))
    out_dir = PROJECT_ROOT / cfg["output_dir"]
    if args.dry_run:
        args.holdout, args.train_splits = "validation", ["train"]
    drop = ("test",) if args.stage == "dev" or args.dry_run else ()
    df = load_data(cfg, args.features_path, drop)
    print(f"Nạp {len(df):,} dòng | split: {df['split'].value_counts().to_dict()} | "
          f"xgboost={HAS_XGB} shap={HAS_SHAP}")
    if args.stage == "dev":
        stage_dev(cfg, df, out_dir)
    elif args.stage == "test":
        stage_test(cfg, df, out_dir, args)
    else:
        stage_robustness(cfg, df, out_dir, args)


if __name__ == "__main__":
    main()