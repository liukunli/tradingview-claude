"""
Portfolio weight constraints and implementability checks (from day13).

Key concepts:
- Simplex projection: maps raw scores to long-only weights (non-negative, sum=1)
- Weight capping: enforces per-factor max weight (e.g. 30%)
- Turnover smoothing: EWMA blending to reduce churn (new = (1-α)*target + α*prev)
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from analysis.utils import (
    calc_ic_summary,
    cap_weights,
    ensure_dir,
    infer_factor_columns,
    load_real_panel,
    project_simplex,
    zscore_by_date,
)


def ic_scores(panel: pd.DataFrame, factor_cols: list) -> pd.Series:
    """Compute IC mean for each factor as baseline weight scores."""
    metrics = {}
    for col in factor_cols:
        metrics[col] = calc_ic_summary(panel, col, "ret")["ic_mean"]
    series = pd.Series(metrics).fillna(0.0)
    if series.abs().sum() == 0:
        return pd.Series(1.0 / len(series), index=series.index)
    return series


def run(
    output_dir: str = "./outputs/constraints",
    data_dir: str = "./data",
    ret_horizon: str = "1vwap_pct",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_dates: Optional[int] = 240,
    cap: float = 0.3,
    turnover_penalty: float = 0.2,
) -> None:
    """
    Demonstrate factor weight constraint pipeline:
      1. Compute IC-based scores on two time splits (prev / curr)
      2. Simplex projection → long-only, sum-to-1 weights
      3. Cap weights at `cap` (iterative redistribution)
      4. EWMA smoothing with previous weights to reduce turnover

    Outputs weights_constraints.csv comparing raw, simplex, capped, smoothed.
    """
    panel = load_real_panel(data_dir=data_dir, ret_col=ret_horizon,
                            start_date=start_date, end_date=end_date,
                            max_dates=max_dates)
    factor_cols = infer_factor_columns(panel)
    if not factor_cols:
        raise ValueError("No factor columns found in panel data.")

    panel = zscore_by_date(panel, factor_cols)
    panel = panel.dropna(subset=factor_cols + ["ret"])

    dates = sorted(panel["date"].unique())
    if len(dates) < 2:
        raise ValueError("Need at least 2 dates.")

    split_idx = max(int(len(dates) * 0.7), 1)
    prev_dates = dates[:split_idx]
    curr_dates = dates[split_idx:] or prev_dates

    prev_panel = panel[panel["date"].isin(prev_dates)]
    curr_panel = panel[panel["date"].isin(curr_dates)]

    prev_simplex = project_simplex(ic_scores(prev_panel, factor_cols).values)
    raw = ic_scores(curr_panel, factor_cols).values

    simplex = project_simplex(raw)
    capped = cap_weights(simplex, cap)
    smoothed = cap_weights(
        (1 - turnover_penalty) * capped + turnover_penalty * prev_simplex, cap)

    df = pd.DataFrame({
        "factor": factor_cols,
        "raw_score": raw,
        "simplex": simplex,
        "capped": capped,
        "smoothed": smoothed,
    })

    out = ensure_dir(output_dir)
    df.to_csv(out / "weights_constraints.csv", index=False)
    print(f"Weight constraint results saved to {out}/weights_constraints.csv")
    print(df.round(4).to_string(index=False))
