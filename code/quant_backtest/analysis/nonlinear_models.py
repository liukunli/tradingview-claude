"""
Nonlinear factor models: XGBoost / LightGBM / Random Forest (from day13).

Key concepts:
- Time-series split: strict 60/20/20 chronological split — no shuffle
- Rolling (walk-forward) validation: train→val→test window slides forward
- Feature importance: tree split-gain based factor ranking
- SHAP values: Shapley additive explanations for model interpretability

Optional dependencies: xgboost, lightgbm, scikit-learn, shap
If unavailable, the module loads but run() will raise an informative error.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from analysis.utils import ensure_dir, infer_factor_columns, load_real_panel, zscore_by_date

try:
    import xgboost as xgb
except ImportError:
    xgb = None  # type: ignore

try:
    import lightgbm as lgb
except ImportError:
    lgb = None  # type: ignore

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_squared_error
except ImportError:
    RandomForestRegressor = None  # type: ignore
    mean_squared_error = None  # type: ignore

try:
    import shap
except ImportError:
    shap = None  # type: ignore


# ─────────────────────────────────────────────────────────────────────────────
# Model fitting
# ─────────────────────────────────────────────────────────────────────────────

def fit_model(x_train: np.ndarray, y_train: np.ndarray, model_type: str = "auto"):
    """
    Fit a nonlinear regression model.

    Priority for auto: LightGBM > XGBoost > RandomForest.
    Returns (model_name, model) or ("none", None) if nothing available.
    """
    def _xgb():
        m = xgb.XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.05,
                              subsample=0.8, colsample_bytree=0.8,
                              objective="reg:squarederror", n_jobs=-1, random_state=42)
        m.fit(x_train, y_train)
        return "xgboost", m

    def _lgb():
        m = lgb.LGBMRegressor(n_estimators=200, max_depth=4, learning_rate=0.05,
                               subsample=0.8, colsample_bytree=0.8,
                               objective="regression", n_jobs=-1,
                               random_state=42, verbose=-1)
        m.fit(x_train, y_train)
        return "lightgbm", m

    def _rf():
        m = RandomForestRegressor(n_estimators=200, max_depth=6,
                                  random_state=42, n_jobs=-1)
        m.fit(x_train, y_train)
        return "random_forest", m

    if model_type == "xgboost" and xgb is not None:
        return _xgb()
    if model_type == "lightgbm" and lgb is not None:
        return _lgb()
    if model_type == "random_forest" and RandomForestRegressor is not None:
        return _rf()
    if model_type == "auto":
        if lgb is not None:
            return _lgb()
        if xgb is not None:
            return _xgb()
        if RandomForestRegressor is not None:
            return _rf()
    return "none", None


def compute_shap_values(model, x_sample: np.ndarray, model_name: str):
    """Compute TreeExplainer SHAP values for tree-based models."""
    if shap is None:
        return None, None
    try:
        explainer = shap.TreeExplainer(model)
        shap_vals = explainer.shap_values(x_sample)
        return shap_vals, explainer
    except Exception as e:
        print(f"Warning: SHAP failed: {e}")
        return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Rolling evaluation
# ─────────────────────────────────────────────────────────────────────────────

def rolling_window_evaluation(
    panel: pd.DataFrame,
    factor_cols: list,
    dates: list,
    train_window: int = 120,
    val_window: int = 40,
    test_window: int = 40,
    step_size: int = 20,
    model_type: str = "auto",
) -> Optional[pd.DataFrame]:
    """Walk-forward validation: train→val→test window slides by step_size."""
    if mean_squared_error is None:
        print("sklearn not available; skipping rolling window.")
        return None

    results = []
    total = len(dates)
    w = train_window + val_window + test_window

    for start in range(0, total - w + 1, step_size):
        te = start + train_window
        ve = te + val_window
        xe = ve + test_window

        train = panel[panel["date"].isin(set(dates[start:te]))]
        val = panel[panel["date"].isin(set(dates[te:ve]))]
        test = panel[panel["date"].isin(set(dates[ve:xe]))]

        if train.empty or val.empty or test.empty:
            continue

        model_name, model = fit_model(
            train[factor_cols].values, train["ret"].values, model_type)
        if model is None:
            continue

        def _ic(subset, preds):
            true = subset["ret"].values
            return float(np.corrcoef(true, preds)[0, 1]) if len(true) > 1 else float("nan")

        results.append({
            "window_id": len(results) + 1,
            "train_start": dates[start], "train_end": dates[te - 1],
            "val_start": dates[te], "val_end": dates[ve - 1],
            "test_start": dates[ve], "test_end": dates[xe - 1],
            "model": model_name,
            "train_mse": mean_squared_error(train["ret"].values,
                                             model.predict(train[factor_cols].values)),
            "val_mse": mean_squared_error(val["ret"].values,
                                           model.predict(val[factor_cols].values)),
            "test_mse": mean_squared_error(test["ret"].values,
                                            model.predict(test[factor_cols].values)),
            "train_ic": _ic(train, model.predict(train[factor_cols].values)),
            "val_ic": _ic(val, model.predict(val[factor_cols].values)),
            "test_ic": _ic(test, model.predict(test[factor_cols].values)),
        })

    return pd.DataFrame(results) if results else None


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run(
    output_dir: str = "./outputs/nonlinear_models",
    data_dir: str = "./data",
    ret_horizon: str = "1vwap_pct",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_dates: Optional[int] = 240,
    model_type: str = "auto",
    enable_rolling: bool = True,
    enable_shap: bool = True,
) -> None:
    """
    Train a nonlinear model on a 60/20/20 time-series split.

    Outputs:
      - time_split_info.csv
      - feature_importance_nonlinear.csv
      - shap_summary.csv  (if shap installed)
      - rolling_window_results.csv  (if enable_rolling)
    """
    if lgb is None and xgb is None and RandomForestRegressor is None:
        raise ImportError(
            "No ML library found. Install at least one of: "
            "lightgbm, xgboost, scikit-learn")

    print("=" * 70)
    print("Nonlinear Models Demo (Time Series Split)")
    print("=" * 70)

    panel = load_real_panel(data_dir=data_dir, ret_col=ret_horizon,
                            start_date=start_date, end_date=end_date,
                            max_dates=max_dates)
    factor_cols = infer_factor_columns(panel)
    if not factor_cols:
        raise ValueError("No factor columns found in panel data.")

    print(f"\n  Factors: {len(factor_cols)}   Shape: {panel.shape}")

    panel = zscore_by_date(panel, factor_cols)
    panel = panel.dropna(subset=factor_cols + ["ret"])
    print(f"  After cleaning: {panel.shape}")

    dates = sorted(panel["date"].unique())
    n = len(dates)
    t1 = int(n * 0.6)
    t2 = int(n * 0.8)

    train_dates = set(dates[:t1])
    val_dates = set(dates[t1:t2])
    test_dates = set(dates[t2:])

    print(f"\n  Train: {len(train_dates)} days  ({dates[0]} ~ {dates[t1-1]})")
    print(f"  Val:   {len(val_dates)} days  ({dates[t1]} ~ {dates[t2-1]})")
    print(f"  Test:  {len(test_dates)} days  ({dates[t2]} ~ {dates[-1]})")

    split_info = pd.DataFrame({
        "split": ["train", "val", "test"],
        "start_date": [dates[0], dates[t1], dates[t2]],
        "end_date": [dates[t1 - 1], dates[t2 - 1], dates[-1]],
        "num_dates": [len(train_dates), len(val_dates), len(test_dates)],
    })

    train = panel[panel["date"].isin(train_dates)]
    val = panel[panel["date"].isin(val_dates)]
    test = panel[panel["date"].isin(test_dates)]

    x_train, y_train = train[factor_cols].values, train["ret"].values
    x_val, y_val = val[factor_cols].values, val["ret"].values
    x_test, y_test = test[factor_cols].values, test["ret"].values

    print(f"\n[Training model: {model_type}]")
    model_name, model = fit_model(x_train, y_train, model_type)
    if model is None:
        raise RuntimeError("Could not train any model. Check ML library installations.")
    print(f"  Using: {model_name}")

    feature_importance_df = pd.DataFrame()
    try:
        fi = model.feature_importances_
        feature_importance_df = (
            pd.DataFrame({"factor": factor_cols, "importance": fi, "model": model_name})
            .sort_values("importance", ascending=False))
        print(f"\n  Top-5 feature importance:")
        for _, r in feature_importance_df.head(5).iterrows():
            print(f"    {r['factor']}: {r['importance']:.4f}")
    except AttributeError:
        print("  Model does not expose feature_importances_")

    shap_summary_df = None
    if enable_shap and shap is not None:
        print("\n  Computing SHAP values …")
        n_shap = min(1000, len(x_val))
        idx = np.random.choice(len(x_val), n_shap, replace=False)
        shap_vals, _ = compute_shap_values(model, x_val[idx], model_name)
        if shap_vals is not None:
            mean_shap = np.abs(shap_vals).mean(axis=0)
            shap_summary_df = (
                pd.DataFrame({"factor": factor_cols,
                              "mean_abs_shap": mean_shap, "model": model_name})
                .sort_values("mean_abs_shap", ascending=False))
            print(f"  Top-5 SHAP features:")
            for _, r in shap_summary_df.head(5).iterrows():
                print(f"    {r['factor']}: {r['mean_abs_shap']:.4f}")

    rolling_results = None
    if enable_rolling:
        print("\n  Walk-forward rolling evaluation …")
        rolling_results = rolling_window_evaluation(
            panel, factor_cols, dates,
            train_window=120, val_window=40, test_window=40,
            step_size=20, model_type=model_type)
        if rolling_results is not None:
            print(f"  Completed {len(rolling_results)} rolling windows")

    out = ensure_dir(output_dir)
    split_info.to_csv(out / "time_split_info.csv", index=False)
    if not feature_importance_df.empty:
        feature_importance_df.to_csv(out / "feature_importance_nonlinear.csv", index=False)
    if shap_summary_df is not None:
        shap_summary_df.to_csv(out / "shap_summary.csv", index=False)
    if rolling_results is not None:
        rolling_results.to_csv(out / "rolling_window_results.csv", index=False)

    print(f"\n✅ Nonlinear model analysis complete. Results: {out}")
    print("=" * 70)
