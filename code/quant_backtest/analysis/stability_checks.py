"""
Stability and overfitting checks via walk-forward validation (from day13).

Key concepts:
- Walk-forward (rolling window) validation: train on [t-80, t), test on [t, t+20)
- IC gap diagnostic: if Train IC >> Test IC, model likely overfit
- Weight turnover check: high turnover kills real-world returns
- EWMA smoothing: exponential smoothing to reduce weight churn
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

from analysis.utils import (
    calc_ic_by_date,
    calc_ic_summary,
    ensure_dir,
    ewma_smooth,
    infer_factor_columns,
    load_real_panel,
    normalize_weights,
    time_split_dates,
    weight_turnover,
    zscore_by_date,
)


def estimate_ic_weights(panel: pd.DataFrame, factor_cols: List[str]) -> pd.Series:
    """Compute IC-weighted factor weights from training data."""
    metrics = {}
    for col in factor_cols:
        metrics[col] = calc_ic_summary(panel, col, "ret")["ic_mean"]
    return normalize_weights(pd.Series(metrics))


def composite_ic(panel: pd.DataFrame, factor_cols: List[str], weights: pd.Series) -> float:
    """Average Rank IC of the composite factor over all dates in panel."""
    aligned = weights.reindex(factor_cols).fillna(0.0)
    tmp = panel.copy()
    tmp["composite"] = tmp[factor_cols].values @ aligned.values
    ic = calc_ic_by_date(tmp, "composite", "ret")
    return float(ic.mean()) if not ic.empty else float("nan")


def calculate_backtest_return(
    panel: pd.DataFrame, factor_cols: List[str], weights: pd.Series
) -> dict:
    """Simplified (no-cost) top-quintile long-only backtest for quick diagnostics."""
    aligned = weights.reindex(factor_cols).fillna(0.0)
    tmp = panel.copy()
    tmp["composite"] = tmp[factor_cols].values @ aligned.values

    daily_returns = []
    for date in tmp["date"].unique():
        day = tmp[tmp["date"] == date].copy()
        if len(day) < 10:
            continue
        day = day.sort_values("composite", ascending=False)
        top_n = max(1, len(day) // 5)
        daily_returns.append(day.head(top_n)["ret"].mean())

    if not daily_returns:
        return {k: float("nan") for k in
                ["cumulative_return", "annualized_return", "sharpe_ratio", "max_drawdown"]}

    cumulative = np.prod([1 + r for r in daily_returns]) - 1
    n = len(daily_returns)
    annualized = (1 + cumulative) ** (252 / n) - 1 if n > 0 else float("nan")
    std = np.std(daily_returns)
    sharpe = np.mean(daily_returns) / std * np.sqrt(252) if std > 0 else float("nan")
    cum_arr = np.cumprod([1 + r for r in daily_returns])
    max_dd = float(np.min((cum_arr - np.maximum.accumulate(cum_arr)) / np.maximum.accumulate(cum_arr)))

    return {"cumulative_return": cumulative, "annualized_return": annualized,
            "sharpe_ratio": sharpe, "max_drawdown": max_dd}


def detect_overfitting_signals(overfit_records: pd.DataFrame, turnover: pd.Series) -> dict:
    """
    Diagnose overfitting from walk-forward results.

    Red flags:
    - IC gap (train_ic - test_ic) > 0.03
    - test_ic < 0.01
    - avg weight turnover > 20%
    """
    result = {"has_overfitting": False, "warnings": [], "details": {}}

    train_ic_mean = overfit_records["train_ic"].mean()
    test_ic_mean = overfit_records["test_ic"].mean()
    ic_gap = train_ic_mean - test_ic_mean

    result["details"].update({"train_ic_mean": train_ic_mean,
                               "test_ic_mean": test_ic_mean,
                               "ic_gap": ic_gap})

    if ic_gap > 0.03 and train_ic_mean > 0.05:
        result["has_overfitting"] = True
        result["warnings"].append(
            f"Train IC ({train_ic_mean:.4f}) >> Test IC ({test_ic_mean:.4f}), "
            f"gap={ic_gap:.4f}. High generalization error.")

    if test_ic_mean < 0.01:
        result["has_overfitting"] = True
        result["warnings"].append(
            f"Test IC too low ({test_ic_mean:.4f}). No out-of-sample predictive power.")

    if not turnover.empty:
        avg_to = float(turnover.mean())
        max_to = float(turnover.max())
        result["details"]["avg_turnover"] = avg_to
        result["details"]["max_turnover"] = max_to
        if avg_to > 0.20:
            result["has_overfitting"] = True
            result["warnings"].append(
                f"Avg weight turnover {avg_to:.2%} > 20%. Transaction costs will "
                f"erode returns.")

    return result


def run(
    output_dir: str = "./outputs/stability",
    data_dir: str = "./data",
    ret_horizon: str = "1vwap_pct",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_dates: Optional[int] = 320,
    train_size: int = 80,
    test_size: int = 20,
    step: int = 20,
) -> None:
    """
    Walk-forward stability check.

    1. Load + z-score panel
    2. Slice into (train, test) windows using time_split_dates
    3. Fit IC weights on train, evaluate composite IC on test
    4. Diagnose overfitting gaps and weight turnover
    5. Save results + diagnostic report
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
    if len(dates) < train_size + test_size:
        raise ValueError(f"Need at least {train_size + test_size} dates, "
                         f"got {len(dates)}")

    splits = time_split_dates(dates, train_size=train_size,
                              test_size=test_size, step=step)

    weight_records = []
    overfit_records = []

    for idx, (train_dates, test_dates) in enumerate(splits, start=1):
        train = panel[panel["date"].isin(train_dates)]
        test = panel[panel["date"].isin(test_dates)]
        if train.empty or test.empty:
            continue

        weights = estimate_ic_weights(train, factor_cols)
        weight_records.append(pd.Series(weights, name=f"split_{idx}"))

        train_ic = composite_ic(train, factor_cols, weights)
        test_ic = composite_ic(test, factor_cols, weights)
        train_bt = calculate_backtest_return(train, factor_cols, weights)
        test_bt = calculate_backtest_return(test, factor_cols, weights)

        overfit_records.append({
            "split": idx,
            "train_ic": train_ic,
            "test_ic": test_ic,
            "train_return": train_bt["cumulative_return"],
            "test_return": test_bt["cumulative_return"],
            "test_sharpe": test_bt["sharpe_ratio"],
            "test_max_dd": test_bt["max_drawdown"],
        })

    if not weight_records:
        raise ValueError("No valid walk-forward windows generated.")

    weights_df = pd.DataFrame(weight_records)
    overfit_df = pd.DataFrame(overfit_records)

    turnover = weight_turnover(weights_df)
    ewma_smooth(weights_df, alpha=0.3)  # compute but don't save (for reference)

    diag = detect_overfitting_signals(overfit_df, turnover)

    print("\n" + "=" * 70)
    print("Stability & Overfitting Diagnostic Report")
    print("=" * 70)
    print(f"\n  Train IC (mean): {diag['details']['train_ic_mean']:.4f}")
    print(f"  Test  IC (mean): {diag['details']['test_ic_mean']:.4f}")
    print(f"  IC gap:          {diag['details']['ic_gap']:.4f}")
    if "avg_turnover" in diag["details"]:
        print(f"  Avg turnover:    {diag['details']['avg_turnover']:.2%}")

    if diag["has_overfitting"]:
        print("\n  Status: HIGH RISK — overfitting detected")
        for w in diag["warnings"]:
            print(f"    {w}")
    else:
        print("\n  Status: STABLE — no significant overfitting detected")

    out = ensure_dir(output_dir)
    weights_df.to_csv(out / "weights_raw.csv", index_label="split")
    overfit_df.to_csv(out / "overfit_checks.csv", index=False)
    with open(out / "diagnostic_report.txt", "w", encoding="utf-8") as f:
        f.write("Stability & Overfitting Diagnostic Report\n" + "=" * 40 + "\n")
        f.write(f"Has overfitting: {diag['has_overfitting']}\n")
        for w in diag["warnings"]:
            f.write(f"- {w}\n")

    print(f"\n✅ Results saved to {out}")
