"""
Multi-factor backtest validation and attribution analysis (from day13).

Key concepts:
- Rolling window weights: dynamic IC_IR-weighted factor combination
- Attribution analysis: Brinson-style contribution decomposition
- Raw vs neutralized comparison: validates whether preprocessing improves Sharpe
- PrecomputedSignalStrategy: adapter pattern to feed pre-built signals into BacktestEngine
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from analysis.utils import (
    calc_ic_summary,
    ensure_dir,
    infer_factor_columns,
    industry_neutralize_by_date,
    load_real_panel,
    zscore_by_date,
)
from core.backtest_engine import BacktestEngine
from core.strategy_base import Strategy


# ─────────────────────────────────────────────────────────────────────────────
# Weight utilities
# ─────────────────────────────────────────────────────────────────────────────

def normalize_signed_weights(raw: pd.Series) -> pd.Series:
    """Normalize to unit absolute sum while preserving sign."""
    values = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    total = values.abs().sum()
    if total == 0:
        return pd.Series(np.full(len(values), 1.0 / len(values)), index=values.index)
    return values / total


def compute_rolling_weights(
    panel: pd.DataFrame,
    factor_cols: Sequence[str],
    lookback: int,
    min_history: int,
    metric: str = "ic_ir",
) -> pd.DataFrame:
    """
    Estimate factor weights at each date using a rolling lookback window.

    For each date t, uses data in [t-lookback, t) to compute IC or IC_IR
    for each factor and normalizes into signed weights.
    """
    dates = sorted(panel["date"].unique())
    records: List[Dict] = []

    for idx, date in enumerate(dates):
        start = max(0, idx - lookback)
        history_dates = dates[start:idx]
        if len(history_dates) < max(1, min_history):
            continue

        subset = panel[panel["date"].isin(history_dates)]
        if subset.empty:
            continue

        metrics = {}
        for col in factor_cols:
            stats = calc_ic_summary(subset, col, "ret")
            metrics[col] = stats["ic_mean"] if metric == "ic" else stats["ic_ir"]

        weights = normalize_signed_weights(pd.Series(metrics, index=factor_cols))
        record: Dict = {"date": date}
        for col in factor_cols:
            record[col] = float(weights.get(col, 0.0))
        records.append(record)

    return pd.DataFrame(records).sort_values("date").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# Signal building and attribution
# ─────────────────────────────────────────────────────────────────────────────

def build_signals_and_stats(
    panel: pd.DataFrame,
    factor_cols: Sequence[str],
    weights_df: pd.DataFrame,
    top_n: int,
) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    """
    Build daily composite signals and compute L/S returns and factor attribution.

    Returns
    -------
    signals : dict[date -> DataFrame[code, date, factor_value]]
    contrib_df : per-date attribution breakdown
    ls_df : per-date long/short returns
    """
    panel_by_date = {date: df.copy() for date, df in panel.groupby("date")}
    signals: Dict[str, pd.DataFrame] = {}
    contrib_records: List[Dict] = []
    ls_records: List[Dict] = []

    for _, row in weights_df.iterrows():
        date = row["date"]
        weights = row[list(factor_cols)].astype(float)

        day_panel = panel_by_date.get(date)
        if day_panel is None or day_panel.empty:
            continue

        day_panel = day_panel.copy()
        day_panel["factor_value"] = day_panel[list(factor_cols)].values @ weights.values
        day_panel = day_panel.dropna(subset=["factor_value", "ret"])
        if day_panel.empty:
            continue

        signals[date] = (
            day_panel[["asset", "factor_value"]]
            .rename(columns={"asset": "code"})
            .assign(date=date)
        )

        ranked = day_panel.sort_values("factor_value", ascending=False)
        long = ranked.head(top_n)
        short = ranked.tail(top_n)
        if long.empty or short.empty:
            continue

        long_ret = long["ret"].mean()
        short_ret = short["ret"].mean()
        ls_records.append({"date": date, "long_ret": float(long_ret),
                           "short_ret": float(short_ret),
                           "ls_ret": float(long_ret - short_ret)})

        contrib: Dict = {"date": date, "ls_ret": float(long_ret - short_ret)}
        for col in factor_cols:
            gap = float(long[col].mean() - short[col].mean())
            contrib[f"{col}_gap"] = gap
            contrib[f"{col}_contribution"] = gap * float(weights[col])
            contrib[f"{col}_weight"] = float(weights[col])
        contrib_records.append(contrib)

    return signals, pd.DataFrame(contrib_records), pd.DataFrame(ls_records)


def summarize_contributions(
    weights_df: pd.DataFrame,
    contrib_df: pd.DataFrame,
    factor_cols: Sequence[str],
    variant: str,
) -> pd.DataFrame:
    """Aggregate factor contribution statistics across all dates."""
    if weights_df.empty:
        return pd.DataFrame()

    gap_means = pd.Series(dtype=float)
    contrib_means = pd.Series(dtype=float)
    if not contrib_df.empty:
        gap_cols = [f"{col}_gap" for col in factor_cols]
        contrib_cols = [f"{col}_contribution" for col in factor_cols]
        gap_means = contrib_df[[c for c in gap_cols if c in contrib_df.columns]].mean()
        contrib_means = contrib_df[[c for c in contrib_cols if c in contrib_df.columns]].mean()

    rows = []
    for col in factor_cols:
        rows.append({
            "variant": variant,
            "factor": col,
            "avg_weight": weights_df[col].mean(),
            "weight_std": weights_df[col].std(ddof=0),
            "avg_score_gap": gap_means.get(f"{col}_gap", np.nan),
            "score_contribution": contrib_means.get(f"{col}_contribution", np.nan),
        })

    summary = pd.DataFrame(rows)
    total = summary["score_contribution"].sum()
    summary["contribution_pct"] = (
        summary["score_contribution"] / total
        if not np.isnan(total) and total != 0 else np.nan
    )
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Adapter strategy for BacktestEngine
# ─────────────────────────────────────────────────────────────────────────────

class PrecomputedSignalStrategy(Strategy):
    """
    Adapter pattern: wraps pre-computed factor scores into the Strategy interface
    so BacktestEngine can run them with its standard cost/rebalance/IC logic.
    """

    def __init__(self, name: str, signals: Dict[str, pd.DataFrame]):
        super().__init__(name)
        self.signals = signals

    def calculate_factor(self, date: str, data_loader, **kwargs) -> pd.DataFrame:
        df = self.signals.get(date)
        if df is None:
            return pd.DataFrame(columns=["code", "date", "factor_value"])
        return df.copy()

    def generate_signal(self, factor_df: pd.DataFrame, top_n: int = 10) -> List[str]:
        if factor_df.empty:
            return []
        ranked = factor_df.sort_values("factor_value", ascending=False)
        return ranked.head(top_n)["code"].tolist()


# ─────────────────────────────────────────────────────────────────────────────
# Backtest runner
# ─────────────────────────────────────────────────────────────────────────────

def _series_max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return np.nan
    cumulative = (1 + returns).cumprod()
    peak = cumulative.cummax()
    return float((cumulative / peak - 1).min())


def run_backtest_for_variant(
    variant: str,
    signals: Dict[str, pd.DataFrame],
    data_dir: str,
    top_n: int,
    rebalance_freq: int,
) -> dict:
    """Run BacktestEngine with enable_cost=True on pre-computed signals."""
    if not signals:
        raise ValueError(f"Variant {variant} has no signals")

    available_dates = sorted(signals.keys())
    engine = BacktestEngine(data_dir=data_dir)
    strategy = PrecomputedSignalStrategy(name=f"Composite_{variant}", signals=signals)
    return engine.run(
        start_date=available_dates[0],
        end_date=available_dates[-1],
        strategy=strategy,
        top_n=top_n,
        rebalance_freq=rebalance_freq,
        enable_cost=True,
        calculate_ic=True,
    )


def build_backtest_record(variant: str, report: dict, ls_df: pd.DataFrame) -> Dict:
    """Flatten a BacktestEngine report dict into a single CSV-friendly row."""
    record: Dict = {"variant": variant}

    returns = report.get("daily_returns")
    if isinstance(returns, pd.Series) and not returns.empty:
        record["start_date"] = returns.index[0]
        record["end_date"] = returns.index[-1]
    else:
        record["start_date"] = record["end_date"] = None

    for key in ["total_return", "annual_return", "annual_volatility", "sharpe_ratio",
                "max_drawdown", "calmar_ratio", "win_rate", "avg_turnover",
                "ic_mean", "ic_std", "ir", "ic_win_rate"]:
        record[key] = float(report.get(key, np.nan)) if key in report else np.nan

    if ls_df is not None and not ls_df.empty:
        ls_series = ls_df.set_index("date")["ls_ret"].astype(float)
        record.update({
            "ls_mean": ls_series.mean(),
            "ls_vol": ls_series.std(ddof=0),
            "ls_cum_return": (1 + ls_series).prod() - 1,
            "ls_max_drawdown": _series_max_drawdown(ls_series),
            "ls_win_rate": (ls_series > 0).mean(),
            "long_mean": ls_df["long_ret"].mean(),
            "short_mean": ls_df["short_ret"].mean(),
        })
    else:
        for k in ["ls_mean", "ls_vol", "ls_cum_return", "ls_max_drawdown",
                  "ls_win_rate", "long_mean", "short_mean"]:
            record[k] = np.nan

    return record


# ─────────────────────────────────────────────────────────────────────────────
# Export helpers
# ─────────────────────────────────────────────────────────────────────────────

def export_outputs(
    output_dir: Path,
    weights_ts: pd.DataFrame,
    contrib_summary: pd.DataFrame,
    backtest_compare: pd.DataFrame,
) -> None:
    ensure_dir(output_dir)
    if not weights_ts.empty:
        cols = ["variant", "date"] + [c for c in weights_ts.columns
                                       if c not in {"variant", "date"}]
        weights_ts[[c for c in cols if c in weights_ts.columns]].to_csv(
            output_dir / "weights_timeseries.csv", index=False)
    if not contrib_summary.empty:
        contrib_summary.to_csv(output_dir / "contribution_summary.csv", index=False)
    if not backtest_compare.empty:
        backtest_compare.to_csv(output_dir / "backtest_compare.csv", index=False)


def export_report(
    report_dir: Path,
    summary_df: pd.DataFrame,
    contrib_summary: pd.DataFrame,
    weights_ts: pd.DataFrame,
) -> None:
    ensure_dir(report_dir)
    summary_df.to_csv(report_dir / "summary.csv", index=False)

    perf_cols = ["variant", "start_date", "end_date", "total_return", "annual_return",
                 "annual_volatility", "sharpe_ratio", "max_drawdown", "calmar_ratio",
                 "win_rate", "avg_turnover"]
    ic_cols = ["variant", "ic_mean", "ic_std", "ir", "ic_win_rate"]
    ls_cols = ["variant", "ls_mean", "ls_vol", "ls_cum_return", "ls_max_drawdown",
               "ls_win_rate", "long_mean", "short_mean"]

    parts = [
        "<html><head><meta charset='utf-8'><title>Multifactor Report</title>",
        "<style>body{font-family:Arial,sans-serif;margin:24px}"
        "table{border-collapse:collapse;margin-bottom:24px}"
        "th,td{border:1px solid #ddd;padding:6px 10px;text-align:right}"
        "th{text-align:center;background:#f6f6f6}"
        "h2,h3{font-weight:600}</style></head><body>",
        "<h1>Multi-Factor Backtest Report</h1>",
        "<h2>Raw vs Industry-Neutralized Comparison</h2>",
    ]
    for title, cols in [("Performance Metrics", perf_cols),
                        ("IC Metrics", ic_cols),
                        ("Long-Short Analysis", ls_cols)]:
        avail = [c for c in cols if c in summary_df.columns]
        if avail:
            parts.append(f"<h3>{title}</h3>")
            parts.append(summary_df[avail].to_html(index=False, float_format="%.4f"))

    if not contrib_summary.empty:
        parts.append("<h2>Factor Contribution</h2>")
        parts.append(contrib_summary.to_html(index=False, float_format="%.4f"))

    if not weights_ts.empty and "weight_turnover" in weights_ts.columns:
        turnover = (weights_ts.groupby("variant")["weight_turnover"]
                    .agg(["mean", "std", "max"]).reset_index())
        parts.append("<h2>Weight Turnover Stability</h2>")
        parts.append(turnover.to_html(index=False, float_format="%.4f"))

    parts.append("</body></html>")
    (report_dir / "report.html").write_text("\n".join(parts), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run(
    data_dir: str = "./data",
    output_multifactor: str = "./outputs/multifactor",
    output_report: str = "./outputs/report",
    ret_col: str = "1vwap_pct",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_dates: Optional[int] = 260,
    lookback: int = 60,
    min_history: int = 40,
    top_n: int = 30,
    rebalance_freq: int = 5,
) -> None:
    """
    Full multi-factor rolling-weight backtest validation pipeline.

    Steps:
      1. Load Barra panel → build raw and industry-neutralized variants
      2. Rolling IC_IR weight estimation (no look-ahead)
      3. Build composite signals + attribution stats
      4. Run BacktestEngine (with costs) on each variant
      5. Export CSVs and HTML report
    """
    panel = load_real_panel(data_dir=data_dir, ret_col=ret_col,
                            start_date=start_date, end_date=end_date,
                            max_dates=max_dates)
    factor_cols = infer_factor_columns(panel)
    if not factor_cols:
        raise ValueError("No factor columns found in panel data")

    variants = {
        "raw": panel.copy(),
        "neutralized": industry_neutralize_by_date(panel, factor_cols, data_dir),
    }

    weights_frames, contrib_frames = [], []
    ls_by_variant: Dict[str, pd.DataFrame] = {}
    signals_by_variant: Dict[str, Dict[str, pd.DataFrame]] = {}

    for variant, variant_panel in variants.items():
        print(f"\n[{variant}] Computing rolling weights …")
        weights_df = compute_rolling_weights(
            variant_panel, factor_cols,
            lookback=lookback, min_history=min_history, metric="ic_ir")
        if weights_df.empty:
            print(f"[Skip] {variant}: insufficient history")
            continue

        weights_df["variant"] = variant
        weight_cols = list(factor_cols)
        weights_df["weight_turnover"] = weights_df[weight_cols].diff().abs().sum(axis=1)

        print(f"[{variant}] Building composite signals …")
        signals, contrib_df, ls_df = build_signals_and_stats(
            variant_panel, factor_cols, weights_df, top_n=top_n)
        if not signals:
            print(f"[Skip] {variant}: no valid signals")
            continue

        signals_by_variant[variant] = signals
        ls_df["variant"] = variant
        ls_by_variant[variant] = ls_df

        summary = summarize_contributions(weights_df, contrib_df, factor_cols, variant)
        if not summary.empty:
            contrib_frames.append(summary)
        weights_frames.append(weights_df)

    if not signals_by_variant:
        raise RuntimeError("No variants produced usable signals")

    backtest_records = []
    for variant, signals in signals_by_variant.items():
        print(f"\n[{variant}] Running backtest engine …")
        report = run_backtest_for_variant(
            variant, signals, data_dir, top_n, rebalance_freq)
        backtest_records.append(
            build_backtest_record(variant, report, ls_by_variant.get(variant, pd.DataFrame())))

    weights_ts = pd.concat(weights_frames, ignore_index=True) if weights_frames else pd.DataFrame()
    contrib_summary = pd.concat(contrib_frames, ignore_index=True) if contrib_frames else pd.DataFrame()
    backtest_compare = pd.DataFrame(backtest_records)

    export_outputs(Path(output_multifactor), weights_ts, contrib_summary, backtest_compare)
    export_report(Path(output_report), backtest_compare, contrib_summary, weights_ts)

    print(f"\n✅ Backtest validation complete.")
    print(f"   Outputs: {output_multifactor}")
    print(f"   Report:  {output_report}/report.html")
