"""
backtest/attribution.py — Comprehensive P&L attribution for the bear put strategy.

Breaks down performance by every meaningful dimension:
  • Time bucket      (prime / mid-morning / lunch / afternoon)
  • Gate score       (3 / 4 / 5)
  • Q-score tier     (Acceptable 45-64 / High ≥65)
  • Regime           (trending / range-bound)
  • Credit bucket    (low <8pt / medium 8-12pt / high >12pt)
  • Exit reason      (profit_target / time_exit / ndx_stop / loss_stop / time_stop_loss)
  • Month
  • Day of week
  • Greeks P&L       (theta decay / delta / vega / residual / gamma)

Usage:
    from ndx_options.backtest.attribution import run_attribution
    run_attribution(trades_list)          # prints full report
    df = attribution_dataframe(trades)    # returns DataFrame for further analysis
"""

from __future__ import annotations

from datetime import time
from typing import Sequence

import numpy as np
import pandas as pd


# ── Internal helpers ──────────────────────────────────────────────────────────

def _section(title: str, width: int = 72):
    print()
    print("─" * width)
    print(f"  {title}")
    print("─" * width)


def _table(df: pd.DataFrame, pnl_col: str = "pnl_usd",
           label_col: str = "label", initial_capital: float = 100_000):
    """Print a standard performance breakdown table."""
    print(f"  {'Bucket':<22} {'Trades':>7} {'WR':>7} {'Avg P&L':>10}"
          f"  {'Total P&L':>12}  {'% Capital':>9}")
    print(f"  {'─'*22} {'─'*7} {'─'*7} {'─'*10}  {'─'*12}  {'─'*9}")
    for _, row in df.iterrows():
        pct = row["total"] / initial_capital * 100
        print(f"  {str(row[label_col]):<22} {int(row['n']):>7} "
              f"{row['wr']:>7.1%} {row['avg']:>+10,.0f}  "
              f"${row['total']:>+11,.0f}  {pct:>+9.2f}%")


def _bucket_stats(trades_df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """Aggregate P&L stats by a grouping column."""
    rows = []
    for label, grp in trades_df.groupby(group_col, sort=False):
        pnl = grp["pnl_usd"]
        rows.append({
            "label": label,
            "n":     len(grp),
            "wr":    (pnl > 0).mean(),
            "avg":   pnl.mean(),
            "total": pnl.sum(),
        })
    return pd.DataFrame(rows).sort_values("total", ascending=False).reset_index(drop=True)


# ── Dimension classifiers ─────────────────────────────────────────────────────

def _time_bucket(t: str) -> str:
    try:
        h, m, *_ = str(t).split(":")
        minutes = int(h) * 60 + int(m)
    except Exception:
        return "Unknown"
    if minutes < 10 * 60:
        return "Pre-prime (<10:00)"
    if minutes <= 10 * 60 + 30:
        return "Prime (10:00–10:30)"
    if minutes < 12 * 60:
        return "Mid-morning (10:30–12:00)"
    if minutes < 14 * 60:
        return "Lunch (12:00–14:00)"
    return "Afternoon (14:00–)"


def _credit_bucket(pts: float) -> str:
    if pts < 8:
        return "Low (<8pt)"
    if pts < 12:
        return "Medium (8–12pt)"
    return "High (≥12pt)"


def _qscore_tier(q: float) -> str:
    if q >= 65:
        return "High (≥65)"
    if q >= 45:
        return "Acceptable (45–64)"
    return "Poor (<45)"


# ── Greeks P&L attribution ─────────────────────────────────────────────────────

def _greeks_attribution(trades_df: pd.DataFrame,
                         initial_capital: float = 100_000) -> None:
    """
    Decompose total P&L into:
      Theta P&L  = theta_entry × hours_held × (1/24)  [time decay captured]
      Delta P&L  = delta_entry × ΔNDX × 100           [directional move]
      Vega P&L   = vega_entry  × Δσ_approx × 100      [vol change, approx]
      Residual   = actual - theta - delta - vega        [gamma + model error]
    """
    required = {"delta_entry", "theta_entry", "vega_entry", "entry_ndx",
                "exit_ndx", "pnl_usd"}
    if not required.issubset(trades_df.columns):
        print("  [Greeks attribution skipped — fields not in trade data]")
        return

    df = trades_df.copy()

    # Approximate hours held (default 2h if not tracked)
    hours_held = 2.0

    # Delta P&L: position delta × index move × multiplier
    df["delta_pnl"] = df["delta_entry"] * (df["exit_ndx"] - df["entry_ndx"]) * 100

    # Theta P&L: theta_entry is pts/calendar_day; convert to session hold (2h ≈ 0.083 day)
    df["theta_pnl"] = df["theta_entry"] * (hours_held / 24) * 100 * df.get("contracts", 1)

    # Vega P&L: approximate σ change as 0 (we don't track realised vol change in backtest)
    df["vega_pnl"] = 0.0

    # Residual (gamma, model error, spread)
    df["residual_pnl"] = df["pnl_usd"] - df["delta_pnl"] - df["theta_pnl"]

    total = df["pnl_usd"].sum()
    comp = {
        "Delta P&L (directional)": df["delta_pnl"].sum(),
        "Theta P&L (time decay)":  df["theta_pnl"].sum(),
        "Vega P&L":                df["vega_pnl"].sum(),
        "Residual (gamma + other)":df["residual_pnl"].sum(),
    }

    print()
    print(f"  {'Component':<30} {'USD':>12}  {'% of total':>10}")
    print(f"  {'─'*30} {'─'*12}  {'─'*10}")
    for name, val in comp.items():
        pct = val / total * 100 if total != 0 else 0
        print(f"  {name:<30} ${val:>+11,.0f}  {pct:>+9.1f}%")
    print(f"  {'Total P&L':<30} ${total:>+11,.0f}  {'100.0%':>10}")

    # Greeks profile summary
    print()
    print(f"  Avg entry Greeks (per-contract):")
    print(f"    delta  = {df['delta_entry'].mean():+.4f}  "
          f"(positive → benefits from NDX rally)")
    print(f"    theta  = {df['theta_entry'].mean():+.4f} pt/day  "
          f"(positive → earns time decay)")
    print(f"    vega   = {df['vega_entry'].mean():+.4f} pt/1%σ  "
          f"(negative → short vol position)")
    print(f"    gamma  = {df['gamma_entry'].mean():+.6f}  "
          f"(negative → short gamma / large moves hurt)")


# ── Main attribution report ───────────────────────────────────────────────────

def run_attribution(trades: Sequence[dict],
                    initial_capital: float = 100_000,
                    label: str = ""):
    """
    Print a full multi-dimensional P&L attribution report.

    Parameters
    ----------
    trades          : list of trade dicts from run_backtest() or simulate_day()
    initial_capital : starting capital for % return calculations
    label           : optional title suffix
    """
    if not trades:
        print("[Attribution] No trades to analyse.")
        return

    df = pd.DataFrame(trades)
    total_pnl = df["pnl_usd"].sum()
    n = len(df)
    wr = (df["pnl_usd"] > 0).mean()

    title = f"P&L ATTRIBUTION REPORT{' — ' + label if label else ''}"
    width = 72
    print()
    print("=" * width)
    print(f"  {title}")
    print(f"  {n} trades  |  WR {wr:.1%}  |  Total ${total_pnl:+,.0f}  "
          f"({total_pnl/initial_capital*100:+.1f}%  of capital)")
    print("=" * width)

    # ── Time bucket ──────────────────────────────────────────────────────────
    _section("BY TIME OF ENTRY")
    df["_time_bucket"] = df["entry_time"].apply(_time_bucket)
    _table(_bucket_stats(df, "_time_bucket"), label_col="label")

    # ── Gate score ───────────────────────────────────────────────────────────
    if "gate_score" in df.columns:
        _section("BY GATE SCORE")
        df["_gate"] = df["gate_score"].apply(lambda g: f"Gate {int(g)}")
        _table(_bucket_stats(df, "_gate"), label_col="label")

    # ── Q-score tier ─────────────────────────────────────────────────────────
    if "q_score" in df.columns:
        _section("BY Q-SCORE TIER")
        df["_q_tier"] = df["q_score"].apply(_qscore_tier)
        _table(_bucket_stats(df, "_q_tier"), label_col="label")

    # ── Market regime ────────────────────────────────────────────────────────
    if "trending" in df.columns:
        _section("BY MARKET REGIME")
        df["_regime"] = df["trending"].apply(
            lambda t: "Trending (day_range > 2.5×avg_bar)" if t else "Range-bound")
        _table(_bucket_stats(df, "_regime"), label_col="label")

    # ── Credit bucket ────────────────────────────────────────────────────────
    if "credit_pts" in df.columns:
        _section("BY CREDIT RECEIVED")
        df["_credit"] = df["credit_pts"].apply(_credit_bucket)
        _table(_bucket_stats(df, "_credit"), label_col="label")

    # ── Exit reason ──────────────────────────────────────────────────────────
    if "exit_reason" in df.columns:
        _section("BY EXIT REASON")
        _table(_bucket_stats(df, "exit_reason"), label_col="label")

    # ── Month ────────────────────────────────────────────────────────────────
    _section("BY MONTH")
    df["_month"] = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)
    _table(_bucket_stats(df, "_month"), label_col="label")

    # ── Day of week ──────────────────────────────────────────────────────────
    _section("BY DAY OF WEEK")
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    df["_dow"] = pd.to_datetime(df["date"]).dt.dayofweek.apply(lambda d: days[d])
    _table(_bucket_stats(df, "_dow"), label_col="label")

    # ── Greeks P&L attribution ────────────────────────────────────────────────
    if "delta_entry" in df.columns:
        _section("GREEKS P&L ATTRIBUTION")
        _greeks_attribution(df, initial_capital=initial_capital)

    # ── Consecutive run analysis ──────────────────────────────────────────────
    _section("STREAK ANALYSIS")
    pnl_sign = (df["pnl_usd"] > 0).astype(int).tolist()
    max_win_streak  = max_consecutive(pnl_sign, 1)
    max_loss_streak = max_consecutive(pnl_sign, 0)
    print(f"  Longest win streak:  {max_win_streak}")
    print(f"  Longest loss streak: {max_loss_streak}")

    # Realistic cost impact
    if "txn_cost_usd" in df.columns and df["txn_cost_usd"].sum() > 0:
        _section("TRANSACTION COST IMPACT")
        gross = df["pnl_usd"].sum() + df["txn_cost_usd"].sum()
        net   = df["pnl_usd"].sum()
        drag  = df["txn_cost_usd"].sum()
        print(f"  Gross P&L (no costs): ${gross:>+12,.0f}  "
              f"({gross/initial_capital*100:+.1f}%)")
        print(f"  Transaction costs:    ${-drag:>+12,.0f}  "
              f"({-drag/initial_capital*100:+.1f}%)")
        print(f"  Net P&L:              ${net:>+12,.0f}  "
              f"({net/initial_capital*100:+.1f}%)")
        print(f"  Cost drag per trade:  ${drag/n:>+12,.0f}")

    print()
    print("=" * width)


def max_consecutive(seq: list[int], val: int) -> int:
    """Return length of longest consecutive run of val in seq."""
    best = cur = 0
    for x in seq:
        cur = cur + 1 if x == val else 0
        best = max(best, cur)
    return best


def attribution_dataframe(trades: Sequence[dict]) -> pd.DataFrame:
    """
    Return an enriched DataFrame with all attribution columns added.
    Useful for custom analysis or export to Excel / parquet.
    """
    df = pd.DataFrame(trades)
    if df.empty:
        return df

    df["time_bucket"]  = df["entry_time"].apply(_time_bucket)
    df["credit_bucket"]= df.get("credit_pts", pd.Series()).apply(
        lambda v: _credit_bucket(v) if pd.notna(v) else "")
    df["q_tier"]       = df.get("q_score", pd.Series()).apply(
        lambda v: _qscore_tier(v) if pd.notna(v) else "")
    df["regime"]       = df.get("trending", pd.Series(False)).apply(
        lambda t: "trending" if t else "range_bound")
    df["month"]        = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)
    df["dow"]          = pd.to_datetime(df["date"]).dt.day_name()
    df["is_win"]       = (df["pnl_usd"] > 0).astype(int)
    df["equity"]       = 100_000 + df["pnl_usd"].cumsum()

    return df
