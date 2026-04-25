"""
backtest.py — Replay NDX_5min_2026.json through the full strategy.

Uses PerformanceEvaluator patterns from code/quant_backtest for Sharpe, Calmar,
max drawdown, IC/IR, and win-rate metrics.

Usage:
    python -m ndx_options.analysis.backtest
    python -m ndx_options.analysis.backtest --start 2026-01-12 --end 2026-04-17
"""

import argparse
import json
import math
import os
import sys
import numpy as np
import pandas as pd
from datetime import date, datetime, time
from typing import Optional

from ..config.settings import (
    ET, BACKTEST_DATA, NDX_MULTIPLIER, SPREAD_WIDTH,
    PRIME_START, PRIME_END, TIME_EXIT_ET,
    MAX_FLAT_MOM, MIN_RANGE_PCT, MAX_DAY_RANGE,
    GATE_MIN_PROCEED, QSCORE_ACCEPT,
    BASE_CONTRACTS, MAX_SCALE_INS, SCALE_IN_DROP,
    PROFIT_TARGET_PCT, LOSS_STOP_MULT,
    MIN_CREDIT_PTS, MAX_CREDIT_PTS,
    BS_RISK_FREE, BS_DEFAULT_SIGMA, ANNUAL_BARS_5MIN,
)
from ..core.signal_engine import (
    evaluate_gate, gate_action, select_strikes, compute_qscore,
    size_from_qscore, spread_value_pts, hard_override_avoid,
)
from ..core.market_data import compute_bar_metrics

# ── Add quant_backtest to path ────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "code"))
try:
    from quant_backtest.core.performance_evaluator import PerformanceEvaluator
    _HAVE_PERF = True
except ImportError:
    _HAVE_PERF = False


# ── Data loading ──────────────────────────────────────────────────────────────

def load_ndx_5min(path: Optional[str] = None) -> pd.DataFrame:
    path = path or BACKTEST_DATA
    with open(path) as f:
        raw = json.load(f)

    bars = raw if isinstance(raw, list) else raw.get("bars", raw.get("data", []))
    df   = pd.DataFrame(bars)
    df.columns = [c.lower() for c in df.columns]

    ts_col = next((c for c in ("time", "timestamp", "t") if c in df.columns), None)
    if ts_col:
        df["dt"] = pd.to_datetime(df[ts_col], unit="s", utc=True).dt.tz_convert(ET)
    df["date"] = df["dt"].dt.date
    df["time_et"] = df["dt"].dt.time
    return df.sort_values("dt").reset_index(drop=True)


# ── Per-day simulation ────────────────────────────────────────────────────────

def simulate_day(day_bars: pd.DataFrame, verbose: bool = False) -> Optional[dict]:
    """
    Simulate one trading day through the full strategy gate + execution.
    Returns a trade result dict or None (no trade).
    """
    # Day context: bars from 9:30 onward
    open_bars = day_bars[day_bars["time_et"] >= time(9, 30)].reset_index(drop=True)
    if len(open_bars) < 5:
        return None

    trade_date = day_bars.iloc[0]["date"]

    # Simulate bar-by-bar evaluation at prime window
    for i, row in open_bars.iterrows():
        bar_time = row["time_et"]

        if bar_time < PRIME_START:
            continue
        if bar_time > PRIME_END:
            break

        # Use all bars from open to this point as context
        ctx_bars = open_bars.iloc[: i + 1]
        m = compute_bar_metrics(ctx_bars)

        gate_score, gate_details = evaluate_gate(m, bar_time)
        action = gate_action(gate_score)

        if action == "AVOID":
            continue
        if hard_override_avoid(m, bar_time):
            continue

        short_K, long_K = select_strikes(m["price"])
        q_score, _      = compute_qscore(m, bar_time, "Bear Put", short_K, is_0dte=True)

        if q_score < QSCORE_ACCEPT:
            continue

        bars_total = len(open_bars)
        bars_remaining = bars_total - i
        credit_est = spread_value_pts(m["price"], short_K, long_K,
                                      max(bars_remaining, 10), m["sigma"])

        if not (MIN_CREDIT_PTS <= credit_est <= MAX_CREDIT_PTS):
            continue

        n = size_from_qscore(BASE_CONTRACTS, q_score, gate_score)
        if n == 0:
            continue

        # ── Entry confirmed ────────────────────────────────────────────────
        entry_price = m["price"]
        entry_bar_i = i
        credit_pts  = credit_est

        # ── Simulate forward: check exits ─────────────────────────────────
        future_bars = open_bars.iloc[i + 1:].reset_index(drop=True)
        exit_reason = "time_exit"
        exit_price  = entry_price
        close_val   = 0.0

        for j, fbar in future_bars.iterrows():
            ft   = fbar["time_et"]
            ndx  = float(fbar["close"])
            bars_left = max(bars_total - entry_bar_i - j - 1, 1)

            sv = spread_value_pts(ndx, short_K, long_K, bars_left, m["sigma"])

            if ndx < short_K:
                exit_reason = "ndx_stop"
                close_val   = sv
                exit_price  = ndx
                break
            if sv >= credit_pts * LOSS_STOP_MULT:
                exit_reason = "loss_stop"
                close_val   = sv
                exit_price  = ndx
                break
            if sv <= credit_pts * PROFIT_TARGET_PCT:
                exit_reason = "profit_target"
                close_val   = sv
                exit_price  = ndx
                break
            if ft >= TIME_EXIT_ET:
                exit_reason = "time_exit"
                close_val   = sv
                exit_price  = ndx
                break
        else:
            close_val = 0.0  # expired worthless

        pnl_pts = credit_pts - close_val
        pnl_usd = pnl_pts * NDX_MULTIPLIER * n

        result = {
            "date":         str(trade_date),
            "entry_time":   str(bar_time),
            "entry_ndx":    round(entry_price, 1),
            "short_K":      short_K,
            "long_K":       long_K,
            "credit_pts":   round(credit_pts, 2),
            "close_val":    round(close_val, 2),
            "pnl_pts":      round(pnl_pts, 2),
            "pnl_usd":      round(pnl_usd, 2),
            "contracts":    n,
            "exit_reason":  exit_reason,
            "gate_score":   gate_score,
            "q_score":      q_score,
            "trending":     m["trending"],
            "day_range":    round(m["day_range"], 1),
            "exit_ndx":     round(exit_price, 1),
        }

        if verbose:
            wr_str = "WIN" if pnl_usd > 0 else "LOSS"
            print(f"  {trade_date}  {bar_time}  NDX={entry_price:.0f}  "
                  f"{short_K}/{long_K}  credit={credit_pts:.2f}  "
                  f"exit={exit_reason}  P&L=${pnl_usd:+,.0f}  [{wr_str}]")

        return result   # first valid trade per day

    return None


# ── Full backtest ─────────────────────────────────────────────────────────────

def run_backtest(start: Optional[str] = None, end: Optional[str] = None,
                 data_path: Optional[str] = None, verbose: bool = False) -> dict:
    df = load_ndx_5min(data_path)

    if start:
        df = df[df["date"] >= date.fromisoformat(start)]
    if end:
        df = df[df["date"] <= date.fromisoformat(end)]

    trading_days = sorted(df["date"].unique())
    results = []

    for day in trading_days:
        day_bars = df[df["date"] == day].reset_index(drop=True)
        res = simulate_day(day_bars, verbose=verbose)
        if res:
            results.append(res)

    if not results:
        print("No trades generated in this date range.")
        return {}

    trades_df = pd.DataFrame(results)
    trades_df["cumulative_pnl"] = trades_df["pnl_usd"].cumsum()

    wins       = (trades_df["pnl_usd"] > 0).sum()
    losses     = (trades_df["pnl_usd"] <= 0).sum()
    total_pnl  = trades_df["pnl_usd"].sum()
    win_rate   = wins / len(trades_df)
    avg_win    = trades_df[trades_df["pnl_usd"] > 0]["pnl_usd"].mean() if wins > 0 else 0
    avg_loss   = trades_df[trades_df["pnl_usd"] <= 0]["pnl_usd"].mean() if losses > 0 else 0

    summary = {
        "period":      f"{trading_days[0]} → {trading_days[-1]}",
        "trading_days": len(trading_days),
        "trades":      len(trades_df),
        "wins":        int(wins),
        "losses":      int(losses),
        "win_rate":    round(win_rate, 4),
        "total_pnl":   round(total_pnl, 2),
        "avg_pnl":     round(total_pnl / len(trades_df), 2),
        "avg_win":     round(avg_win, 2),
        "avg_loss":    round(avg_loss, 2),
        "profit_factor": round(abs(avg_win * wins / (avg_loss * losses)), 2) if losses and avg_loss else 0,
        "max_trade_pnl":  round(trades_df["pnl_usd"].max(), 2),
        "min_trade_pnl":  round(trades_df["pnl_usd"].min(), 2),
        "exit_reasons": trades_df["exit_reason"].value_counts().to_dict(),
        "filtered_days": len(trading_days) - len(trades_df),
    }

    # PerformanceEvaluator metrics (Sharpe, Calmar, max DD)
    if _HAVE_PERF and len(trades_df) > 5:
        initial_capital = 100_000
        equity_curve    = pd.Series(initial_capital + trades_df["cumulative_pnl"].values)
        returns         = equity_curve.pct_change().dropna()

        pe = PerformanceEvaluator(risk_free_rate=0.045)
        report = pe.generate_report(equity_curve / equity_curve.iloc[0], returns)

        summary.update({
            "sharpe_ratio":      round(report.get("sharpe_ratio", 0), 3),
            "calmar_ratio":      round(report.get("calmar_ratio", 0), 3),
            "max_drawdown_pct":  round(report.get("max_drawdown", 0) * 100, 2),
            "annual_return_pct": round(report.get("annual_return", 0) * 100, 2),
        })
    else:
        # Fallback manual calculation
        cum_pnl = trades_df["pnl_usd"].values
        peak    = np.maximum.accumulate(cum_pnl)
        dd      = cum_pnl - peak
        summary["max_drawdown_usd"] = round(float(dd.min()), 2)

    return {"summary": summary, "trades": results}


# ── Improvement proposals ─────────────────────────────────────────────────────

def propose_improvements(summary: dict, trades: list[dict]) -> list[str]:
    """
    Analyze backtest results and suggest strategy refinements.
    Institutional-style: data-driven, quantified, actionable.
    """
    proposals = []
    df = pd.DataFrame(trades)

    if df.empty:
        return ["No trades to analyze."]

    win_rate = summary.get("win_rate", 0)
    profit_factor = summary.get("profit_factor", 0)

    # Exit reason analysis
    exit_counts = df["exit_reason"].value_counts()
    stop_count  = exit_counts.get("ndx_stop", 0) + exit_counts.get("loss_stop", 0)
    if stop_count > 0.3 * len(df):
        proposals.append(
            f"HIGH STOP RATE: {stop_count}/{len(df)} exits were stops "
            f"({stop_count/len(df):.0%}). Consider widening OTM distance "
            f"from {MIN_CREDIT_PTS:.0f}pt to 130pt minimum or tightening trending filter."
        )

    # Trending day filter
    trending_trades = df[df["trending"]]
    if len(trending_trades) > 0:
        trend_wr = (trending_trades["pnl_usd"] > 0).mean()
        if trend_wr < 0.3:
            proposals.append(
                f"TRENDING REGIME: {len(trending_trades)} trades on trending days, "
                f"{trend_wr:.0%} WR. Add hard filter: skip if day_range > 150pt before 10:00."
            )

    # Gate score analysis
    if "gate_score" in df.columns:
        for gs in [3, 4, 5]:
            sub = df[df["gate_score"] == gs]
            if len(sub) >= 3:
                wr = (sub["pnl_usd"] > 0).mean()
                proposals.append(
                    f"GATE SCORE {gs}: {len(sub)} trades, {wr:.0%} WR, "
                    f"avg ${sub['pnl_usd'].mean():+,.0f}. "
                    + ("→ Prioritize." if wr > 0.6 else "→ Consider size reduction.")
                )

    # Q-Score analysis
    if "q_score" in df.columns:
        high_q  = df[df["q_score"] >= 65]
        mid_q   = df[(df["q_score"] >= 45) & (df["q_score"] < 65)]
        if len(high_q) >= 3 and len(mid_q) >= 3:
            proposals.append(
                f"Q-SCORE SPLIT: High(≥65) → {(high_q['pnl_usd']>0).mean():.0%} WR "
                f"avg ${high_q['pnl_usd'].mean():+,.0f}  |  "
                f"Acceptable(45–64) → {(mid_q['pnl_usd']>0).mean():.0%} WR "
                f"avg ${mid_q['pnl_usd'].mean():+,.0f}"
            )

    # Credit range
    if "credit_pts" in df.columns:
        for lo, hi in [(5, 8), (8, 12), (12, 20)]:
            sub = df[(df["credit_pts"] >= lo) & (df["credit_pts"] < hi)]
            if len(sub) >= 3:
                wr = (sub["pnl_usd"] > 0).mean()
                proposals.append(
                    f"CREDIT {lo}–{hi}pt: {len(sub)} trades, {wr:.0%} WR, "
                    f"avg ${sub['pnl_usd'].mean():+,.0f}"
                )

    if not proposals:
        proposals.append("No significant improvement opportunities identified — strategy performing within expected parameters.")

    return proposals


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NDX Spread Backtest")
    parser.add_argument("--start",   default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end",     default=None, help="End date YYYY-MM-DD")
    parser.add_argument("--data",    default=None, help="Path to NDX_5min JSON")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--improve", action="store_true", help="Show improvement proposals")
    args = parser.parse_args()

    results = run_backtest(args.start, args.end, args.data, args.verbose)
    if not results:
        sys.exit(1)

    summary = results["summary"]
    trades  = results["trades"]

    print("\n" + "="*55)
    print(f"NDX BEAR PUT BACKTEST RESULTS")
    print("="*55)
    for k, v in summary.items():
        if k != "exit_reasons":
            print(f"  {k:<25} {v}")
    print("\n  Exit reasons:")
    for r, c in summary.get("exit_reasons", {}).items():
        print(f"    {r:<25} {c}")

    if args.improve:
        print("\n" + "="*55)
        print("IMPROVEMENT PROPOSALS")
        print("="*55)
        for i, p in enumerate(propose_improvements(summary, trades), 1):
            print(f"\n{i}. {p}")
