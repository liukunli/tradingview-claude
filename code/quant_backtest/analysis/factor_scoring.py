"""
Multi-dimensional factor scoring  (from 12课时/factor_scoring.py).

Combines IC/IR, monotonicity, and turnover into a single composite score
for ranking candidate factors.

Scoring formula (adjustable weights):
    score = 0.40 * IC_IR  +  0.20 * IC_mean  +  0.20 * monotonicity  +  0.20 * (1 − turnover)

Knowledge points
----------------
- IC/IR (0.40): highest weight – captures stable predictive power.
- IC mean (0.20): raw predictive strength.
- Monotonicity (0.20): are groups ranked 1→N actually earning more?
- (1 − turnover) (0.20): stable rankings → lower trading costs.
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

from analysis.utils import (
    calc_ic,
    calc_ic_stats,
    ensure_dir,
    group_returns_series,
    infer_factor_cols,
    load_dates,
    load_factor_frame,
    load_factor_series,
    load_return_series,
)


def _rank_ic(a: pd.Series, b: pd.Series) -> float:
    aligned = pd.concat([a, b], axis=1).dropna()
    return aligned.iloc[:, 0].corr(aligned.iloc[:, 1], method="spearman") if not aligned.empty else np.nan


def score_factors(
    date_path: str,
    factor_dir: str,
    data_dir: str,
    factor_cols: Optional[List[str]] = None,
    ret_col: str = "1vwap_pct",
    n_groups: int = 10,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_dates: Optional[int] = 120,
    score_weights: Optional[dict] = None,
    output_dir: Optional[str] = None,
) -> pd.DataFrame:
    """
    Score factors along IC/IR, monotonicity, and turnover dimensions.

    Parameters
    ----------
    score_weights : dict, optional
        Custom weights for scoring. Keys: 'ic_ir', 'ic_mean', 'monotonicity', 'stability'.
        Defaults to {ic_ir: 0.4, ic_mean: 0.2, monotonicity: 0.2, stability: 0.2}.

    Returns
    -------
    DataFrame sorted by score (descending), one row per factor.
    """
    sw = score_weights or {"ic_ir": 0.4, "ic_mean": 0.2, "monotonicity": 0.2, "stability": 0.2}

    dates = load_dates(date_path, start_date, end_date)
    if max_dates:
        dates = dates[-max_dates:]

    # infer factor columns from first available file
    if not factor_cols:
        for d in dates:
            df = load_factor_frame(factor_dir, d)
            if not df.empty:
                factor_cols = list(df.columns)
                break
    if not factor_cols:
        return pd.DataFrame()

    records = []
    for col in factor_cols:
        ic_vals, mono_vals, ric_vals = [], [], []
        prev = None

        for date in dates:
            factor = load_factor_series(factor_dir, date, factor_col=col)
            ret    = load_return_series(data_dir, date, ret_col=ret_col)
            if factor.empty or ret.empty:
                prev = None
                continue

            ic_vals.append(calc_ic(factor, ret, method="spearman"))
            _, mono = group_returns_series(factor, ret, n_groups)
            mono_vals.append(mono)

            if prev is not None:
                ric = _rank_ic(prev, factor)
                ric_vals.append(1 - ric if not np.isnan(ric) else np.nan)
            prev = factor

        stats        = calc_ic_stats(pd.Series(ic_vals))
        mono_mean    = float(pd.Series(mono_vals).dropna().mean()) if mono_vals else 0.0
        turnover_mean = float(pd.Series(ric_vals).dropna().mean()) if ric_vals else 1.0

        ic_ir  = stats.get("ic_ir") or 0.0
        ic_mean_val = stats.get("ic_mean") or 0.0
        score = (sw["ic_ir"]       * ic_ir
                 + sw["ic_mean"]      * ic_mean_val
                 + sw["monotonicity"] * mono_mean
                 + sw["stability"]    * (1 - turnover_mean))

        records.append({
            "factor":           col,
            "ic_mean":          ic_mean_val,
            "ic_std":           stats.get("ic_std"),
            "ic_ir":            ic_ir,
            "ic_win_rate":      stats.get("ic_win_rate"),
            "ic_t":             stats.get("ic_t"),
            "monotonicity_mean": mono_mean,
            "turnover_mean":    turnover_mean,
            "score":            score,
            "n":                stats.get("n"),
        })

    result = pd.DataFrame(records).sort_values("score", ascending=False)
    if output_dir:
        ensure_dir(output_dir)
        result.to_csv(str(ensure_dir(output_dir) / "factor_scores.csv"), index=False)
    return result
