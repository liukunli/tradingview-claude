"""
backtest/engine.py — Replay OHLCV data through the full strategy.

Usage:
    python -m ndx_options.main backtest
    python -m ndx_options.main backtest --data ndx_spy_historical_data/ndx_1min.csv
    python -m ndx_options.main backtest --start 2026-01-12 --end 2026-04-24
"""

import json
import os
import sys
import numpy as np
import pandas as pd
from datetime import date, time
from typing import Optional

from ..config.settings import (
    NDX_MULTIPLIER,
    PRIME_START, PRIME_END, TIME_EXIT_ET,
    GATE_MIN_PROCEED, QSCORE_ACCEPT,
    BASE_CONTRACTS,
    PROFIT_TARGET_PCT, LOSS_STOP_MULT,
    MIN_CREDIT_PTS, MAX_CREDIT_PTS,
)
from ..strategy.signal_engine import (
    evaluate_gate, gate_action, select_strikes, compute_qscore,
    size_from_qscore, spread_value_pts, hard_override_avoid,
    compute_bar_metrics,
)
from .loader import load_ohlcv

# ── Optional PerformanceEvaluator ─────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_REPO_ROOT, "code"))
try:
    from quant_backtest.core.performance_evaluator import PerformanceEvaluator
    _HAVE_PERF = True
    print("✅ PerformanceEvaluator ready")
except ImportError:
    _HAVE_PERF = False


# ── Per-day simulation ────────────────────────────────────────────────────────

def simulate_day(day_bars: pd.DataFrame, verbose: bool = False,
                 no_gate: bool = False) -> Optional[dict]:
    """Simulate one trading day. Returns a trade dict or None."""
    open_bars = day_bars[day_bars["time_et"] >= time(9, 30)].reset_index(drop=True)
    if len(open_bars) < 5:
        return None

    trade_date = day_bars.iloc[0]["date"]

    for i, row in open_bars.iterrows():
        bar_time = row["time_et"]
        if bar_time < PRIME_START:
            continue
        if bar_time > PRIME_END:
            break

        ctx_bars = open_bars.iloc[: i + 1]
        m = compute_bar_metrics(ctx_bars)

        gate_score, gate_details = evaluate_gate(m, bar_time)
        action = gate_action(gate_score)

        if not no_gate:
            if action == "AVOID":
                continue
            if hard_override_avoid(m, bar_time):
                continue

        short_K, long_K = select_strikes(m["price"])
        q_score, _      = compute_qscore(m, bar_time, "Bear Put", short_K, is_0dte=True)

        if not no_gate and q_score < QSCORE_ACCEPT:
            continue

        bars_total     = len(open_bars)
        bars_remaining = bars_total - i
        credit_est = spread_value_pts(m["price"], short_K, long_K,
                                      max(bars_remaining, 10), m["sigma"])

        if not (MIN_CREDIT_PTS <= credit_est <= MAX_CREDIT_PTS):
            continue

        n = BASE_CONTRACTS if no_gate else size_from_qscore(BASE_CONTRACTS, q_score, gate_score)
        if n == 0:
            continue

        entry_price = m["price"]
        entry_bar_i = i
        credit_pts  = credit_est
        future_bars = open_bars.iloc[i + 1:].reset_index(drop=True)
        exit_reason = "time_exit"
        exit_price  = entry_price
        close_val   = 0.0

        for j, fbar in future_bars.iterrows():
            ft        = fbar["time_et"]
            ndx       = float(fbar["close"])
            bars_left = max(bars_total - entry_bar_i - j - 1, 1)
            sv = spread_value_pts(ndx, short_K, long_K, bars_left, m["sigma"])

            if ndx < short_K:
                exit_reason, close_val, exit_price = "ndx_stop", sv, ndx; break
            if sv >= credit_pts * LOSS_STOP_MULT:
                exit_reason, close_val, exit_price = "loss_stop", sv, ndx; break
            if sv <= credit_pts * PROFIT_TARGET_PCT:
                exit_reason, close_val, exit_price = "profit_target", sv, ndx; break
            if ft >= TIME_EXIT_ET:
                exit_reason, close_val, exit_price = "time_exit", sv, ndx; break
        else:
            close_val = 0.0

        pnl_pts = credit_pts - close_val
        pnl_usd = pnl_pts * NDX_MULTIPLIER * n

        if verbose:
            tag = "WIN" if pnl_usd > 0 else "LOSS"
            print(f"  {trade_date}  {bar_time}  NDX={entry_price:.0f}  "
                  f"{short_K}/{long_K}  credit={credit_pts:.2f}  "
                  f"exit={exit_reason}  P&L=${pnl_usd:+,.0f}  [{tag}]")

        return {
            "date": str(trade_date), "entry_time": str(bar_time),
            "entry_ndx": round(entry_price, 1),
            "short_K": short_K, "long_K": long_K,
            "credit_pts": round(credit_pts, 2), "close_val": round(close_val, 2),
            "pnl_pts": round(pnl_pts, 2), "pnl_usd": round(pnl_usd, 2),
            "contracts": n, "exit_reason": exit_reason,
            "gate_score": gate_score, "q_score": q_score,
            "trending": m["trending"], "day_range": round(m["day_range"], 1),
            "exit_ndx": round(exit_price, 1),
        }

    return None


# ── Full backtest ─────────────────────────────────────────────────────────────

def run_backtest(start: Optional[str] = None, end: Optional[str] = None,
                 data_path: Optional[str] = None, verbose: bool = False,
                 no_gate: bool = False) -> dict:
    df = load_ohlcv(data_path)

    if start:
        df = df[df["date"] >= date.fromisoformat(start)]
    if end:
        df = df[df["date"] <= date.fromisoformat(end)]

    trading_days = sorted(df["date"].unique())
    results = []

    for day in trading_days:
        day_bars = df[df["date"] == day].reset_index(drop=True)
        res = simulate_day(day_bars, verbose=verbose, no_gate=no_gate)
        if res:
            results.append(res)

    if not results:
        print("No trades generated in this date range.")
        return {}

    trades_df = pd.DataFrame(results)
    trades_df["cumulative_pnl"] = trades_df["pnl_usd"].cumsum()

    wins      = (trades_df["pnl_usd"] > 0).sum()
    losses    = (trades_df["pnl_usd"] <= 0).sum()
    total_pnl = trades_df["pnl_usd"].sum()
    win_rate  = wins / len(trades_df)
    avg_win   = trades_df[trades_df["pnl_usd"] > 0]["pnl_usd"].mean() if wins > 0 else 0
    avg_loss  = trades_df[trades_df["pnl_usd"] <= 0]["pnl_usd"].mean() if losses > 0 else 0

    initial_capital = 100_000
    equity_curve    = pd.Series(initial_capital + trades_df["cumulative_pnl"].values)
    peak_equity     = equity_curve.cummax()
    final_equity    = equity_curve.iloc[-1]

    summary = {
        "period":        f"{trading_days[0]} → {trading_days[-1]}",
        "trading_days":  len(trading_days),
        "trades":        len(trades_df),
        "wins":          int(wins),
        "losses":        int(losses),
        "win_rate":      round(win_rate, 4),
        "total_pnl":     round(total_pnl, 2),
        "avg_pnl":       round(total_pnl / len(trades_df), 2),
        "avg_win":       round(avg_win, 2),
        "avg_loss":      round(avg_loss, 2),
        "profit_factor": round(abs(avg_win * wins / (avg_loss * losses)), 2)
                         if losses and avg_loss else 0,
        "max_trade_pnl": round(trades_df["pnl_usd"].max(), 2),
        "min_trade_pnl": round(trades_df["pnl_usd"].min(), 2),
        "exit_reasons":  trades_df["exit_reason"].value_counts().to_dict(),
        "filtered_days": len(trading_days) - len(trades_df),
        "initial_capital":  initial_capital,
        "final_equity":     round(final_equity, 2),
        "total_return_pct": round((final_equity - initial_capital) / initial_capital * 100, 2),
        "max_drawdown_usd": round((equity_curve - peak_equity).min(), 2),
    }

    if _HAVE_PERF and len(trades_df) > 5:
        returns = equity_curve.pct_change().dropna()
        pe      = PerformanceEvaluator(risk_free_rate=0.045)
        rpt     = pe.generate_report(equity_curve / equity_curve.iloc[0], returns)
        summary.update({
            "sharpe_ratio":      round(rpt.get("sharpe_ratio", 0), 3),
            "calmar_ratio":      round(rpt.get("calmar_ratio", 0), 3),
            "max_drawdown_pct":  round(rpt.get("max_drawdown", 0) * 100, 2),
            "annual_return_pct": round(rpt.get("annual_return", 0) * 100, 2),
        })

    return {"summary": summary, "trades": results}


# ── Save result to results/ ───────────────────────────────────────────────────

def save_result(result: dict, label: str = "backtest") -> str:
    """Save backtest result JSON to results/ folder. Returns file path."""
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "results")
    os.makedirs(results_dir, exist_ok=True)
    ts   = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(results_dir, f"{label}_{ts}.json")
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    return path


# ── Improvement proposals ─────────────────────────────────────────────────────

def propose_improvements(summary: dict, trades: list[dict]) -> list[str]:
    proposals = []
    df = pd.DataFrame(trades)
    if df.empty:
        return ["No trades to analyze."]

    exit_counts = df["exit_reason"].value_counts()
    stop_count  = exit_counts.get("ndx_stop", 0) + exit_counts.get("loss_stop", 0)
    if stop_count > 0.3 * len(df):
        proposals.append(
            f"HIGH STOP RATE: {stop_count}/{len(df)} exits were stops "
            f"({stop_count/len(df):.0%}). Consider widening OTM distance "
            f"from {MIN_CREDIT_PTS:.0f}pt to 130pt minimum or tightening trending filter."
        )

    trending_trades = df[df["trending"]]
    if len(trending_trades) > 0:
        trend_wr = (trending_trades["pnl_usd"] > 0).mean()
        if trend_wr < 0.3:
            proposals.append(
                f"TRENDING REGIME: {len(trending_trades)} trades on trending days, "
                f"{trend_wr:.0%} WR. Add hard filter: skip if day_range > 150pt before 10:00."
            )

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

    if "q_score" in df.columns:
        high_q = df[df["q_score"] >= 65]
        mid_q  = df[(df["q_score"] >= 45) & (df["q_score"] < 65)]
        if len(high_q) >= 3 and len(mid_q) >= 3:
            proposals.append(
                f"Q-SCORE SPLIT: High(≥65) → {(high_q['pnl_usd']>0).mean():.0%} WR "
                f"avg ${high_q['pnl_usd'].mean():+,.0f}  |  "
                f"Acceptable(45–64) → {(mid_q['pnl_usd']>0).mean():.0%} WR "
                f"avg ${mid_q['pnl_usd'].mean():+,.0f}"
            )

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
        proposals.append("No significant improvement opportunities identified.")
    return proposals
