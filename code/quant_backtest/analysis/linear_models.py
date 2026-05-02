"""
Linear model factor weighting: Ridge and Lasso regression (from day13).

Key concepts:
- Ridge (L2): shrinks all weights uniformly, retains all factors
- Lasso (L1): produces sparse weights, performs automatic factor selection
- Factor sign adjustment: flip factors with negative IC before regression
  so long-only weight normalization doesn't zero out valid negative-IC factors
- Closed-form Ridge: w = (X'X + αI)^{-1} X'y (no sklearn dependency fallback)
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from analysis.utils import (
    ensure_dir,
    infer_factor_columns,
    load_real_panel,
    normalize_weights,
    zscore_by_date,
)

try:
    from sklearn.linear_model import Lasso, Ridge
except ImportError:
    Ridge = Lasso = None  # type: ignore


def ridge_closed_form(x: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    """w = (X'X + αI)^{-1} X'y — stable via pseudo-inverse."""
    xtx = x.T @ x
    return np.linalg.pinv(xtx + alpha * np.eye(x.shape[1])) @ x.T @ y


def fit_ridge(x: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    if Ridge is None:
        return ridge_closed_form(x, y, alpha)
    model = Ridge(alpha=alpha, fit_intercept=True)
    model.fit(x, y)
    return model.coef_


def fit_lasso(x: np.ndarray, y: np.ndarray, alpha: float) -> Optional[np.ndarray]:
    if Lasso is None:
        print("Warning: sklearn not installed — skipping Lasso.")
        return None
    model = Lasso(alpha=alpha, fit_intercept=True, max_iter=5000)
    model.fit(x, y)
    return model.coef_


def run(
    output_dir: str = "./outputs/linear_models",
    data_dir: str = "./data",
    ret_horizon: str = "1vwap_pct",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_dates: Optional[int] = 240,
    alpha: float = 1e-4,
) -> None:
    """
    Fit Ridge and Lasso regressions to determine factor weights.

    Steps:
      1. Load + z-score panel
      2. Auto-flip factors whose IC < 0 (so long-only normalization works)
      3. Fit Ridge → normalize coefficients
      4. Fit Lasso → normalize coefficients (sparse solution)
      5. Save weights_linear.csv
    """
    panel = load_real_panel(data_dir=data_dir, ret_col=ret_horizon,
                            start_date=start_date, end_date=end_date,
                            max_dates=max_dates)
    factor_cols = infer_factor_columns(panel)
    if not factor_cols:
        raise ValueError("No factor columns found in panel data.")

    panel = zscore_by_date(panel, factor_cols)
    panel = panel.dropna(subset=factor_cols + ["ret"])

    print("\n[Factor direction auto-correction]")
    for col in factor_cols:
        ic = panel[col].corr(panel["ret"])
        if ic < 0:
            panel[col] = -panel[col]
            print(f"  {col}: IC={ic:.4f} → flipped")
        else:
            print(f"  {col}: IC={ic:.4f} → kept")

    x = panel[factor_cols].values
    y = panel["ret"].values

    records = []

    ridge_coef = fit_ridge(x, y, alpha)
    print(f"\n[Ridge raw coefficients (alpha={alpha})]")
    print(pd.Series(ridge_coef, index=factor_cols).round(6).to_string())
    ridge_w = normalize_weights(pd.Series(ridge_coef, index=factor_cols))
    records.append(pd.DataFrame({"method": "ridge", "factor": factor_cols,
                                  "weight": ridge_w.values}))

    lasso_coef = fit_lasso(x, y, alpha)
    if lasso_coef is not None:
        print(f"\n[Lasso raw coefficients (alpha={alpha})]")
        print(pd.Series(lasso_coef, index=factor_cols).round(6).to_string())
        lasso_w = normalize_weights(pd.Series(lasso_coef, index=factor_cols))
        records.append(pd.DataFrame({"method": "lasso", "factor": factor_cols,
                                      "weight": lasso_w.values}))

    weights_df = pd.concat(records, ignore_index=True)
    out = ensure_dir(output_dir)
    weights_df.to_csv(out / "weights_linear.csv", index=False)
    print(f"\n✅ Linear model weights saved to {out}/weights_linear.csv")
    print(weights_df.to_string(index=False))
