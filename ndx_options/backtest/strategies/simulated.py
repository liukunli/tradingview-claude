"""
strategies/simulated.py — Simulated Bear Put Spread variants.

Replays OHLCV data through the strategy engine.  Uses the same
evaluate_entry / evaluate_exit functions as the live trading session,
so backtest and live are guaranteed to share identical entry/exit logic.

Variants defined here
---------------------
  gated       gate score >= 3,  Q-score >= 45  (standard rules)
  no_gate     all gate/Q-score filters removed
  high_gate   gate score >= 4 only (stricter entry)
  low_credit  credit 8–12 pt range only (low-vol premium capture)
"""

from __future__ import annotations

from datetime import time
from pathlib import Path

import pandas as pd

from ._common import _summarize, _add_weekly_stats
from ...strategy.signal_engine import (
    evaluate_entry, evaluate_exit,
    compute_bar_metrics, spread_value_pts,
    hard_override_avoid, gate_action, size_from_qscore,
)
from ...config.settings import (
    PRIME_START, PRIME_END,
    GATE_MIN_PROCEED, QSCORE_ACCEPT,
    MIN_CREDIT_PTS, MAX_CREDIT_PTS,
    BASE_CONTRACTS, NDX_MULTIPLIER,
    BACKTEST_DATA,
)


def run(
    name: str,
    description: str,
    data_path: str | Path = BACKTEST_DATA,
    no_gate: bool = False,
    min_gate_score: int = GATE_MIN_PROCEED,
    min_qscore: int = QSCORE_ACCEPT,
    credit_min: float = MIN_CREDIT_PTS,
    credit_max: float = MAX_CREDIT_PTS,
    verbose: bool = False,
) -> dict:
    """
    Simulate a Bear Put Spread variant on historical OHLCV data.

    Entry decision uses evaluate_entry (same function as live trading).
    Exit decision uses evaluate_exit (same function as live trading).
    Additional variant-specific filters (min_gate_score, credit range)
    are applied after evaluate_entry returns the computed values.
    """
    from ..loader import load_ohlcv

    df = load_ohlcv(str(data_path))
    trading_days = sorted(df["date"].unique())
    results = []

    for day in trading_days:
        day_bars  = df[df["date"] == day].reset_index(drop=True)
        open_bars = day_bars[day_bars["time_et"] >= time(9, 30)].reset_index(drop=True)
        if len(open_bars) < 5:
            continue

        trade_date = day_bars.iloc[0]["date"]

        for i, row in open_bars.iterrows():
            bar_time = row["time_et"]
            if bar_time < PRIME_START:
                continue
            if bar_time > PRIME_END:
                break

            ctx_bars       = open_bars.iloc[: i + 1]
            m              = compute_bar_metrics(ctx_bars)
            bars_total     = len(open_bars)
            bars_remaining = bars_total - i

            # Compute all entry metrics (no_gate=True to always get raw values;
            # variant-specific gate/Q-score filters applied below)
            entry = evaluate_entry(m, bar_time, bars_remaining, no_gate=True)
            gate_score = entry["gate_score"]
            q_score    = entry["q_score"]
            short_K    = entry["short_K"]
            long_K     = entry["long_K"]
            credit_pts = entry["credit_pts"]

            # Variant-specific gate and Q-score filters
            if not no_gate:
                if gate_action(gate_score) == "AVOID":
                    continue
                if hard_override_avoid(m, bar_time):
                    continue
                if gate_score < min_gate_score:
                    continue
                if q_score < min_qscore:
                    continue

            # Variant-specific credit range filter
            if not (credit_min <= credit_pts <= credit_max):
                continue

            n = BASE_CONTRACTS if no_gate else size_from_qscore(BASE_CONTRACTS, q_score, gate_score)
            if n == 0:
                continue

            # Forward-simulate exits using the same evaluate_exit as live trading
            entry_price = m["price"]
            future_bars = open_bars.iloc[i + 1:].reset_index(drop=True)
            exit_reason = "time_exit"
            exit_price  = entry_price
            close_val   = 0.0

            for j, fbar in future_bars.iterrows():
                ndx       = float(fbar["close"])
                bars_left = max(bars_total - i - j - 1, 1)
                sv        = spread_value_pts(ndx, short_K, long_K, bars_left, m["sigma"])
                hours_open = j * 5 / 60  # 5-min bars → hours

                reason = evaluate_exit(ndx, short_K, credit_pts, sv, fbar["time_et"], hours_open)
                if reason:
                    exit_reason, close_val, exit_price = reason, sv, ndx
                    break
            else:
                close_val = 0.0

            pnl_usd = (credit_pts - close_val) * NDX_MULTIPLIER * n

            if verbose:
                tag = "WIN" if pnl_usd > 0 else "LOSS"
                print(f"  {trade_date}  {bar_time}  NDX={entry_price:.0f}  "
                      f"{short_K}/{long_K}  credit={credit_pts:.2f}  "
                      f"exit={exit_reason}  P&L=${pnl_usd:+,.0f}  [{tag}]")

            results.append(dict(
                date=str(trade_date), cash_pnl=pnl_usd,
                entry_time=str(bar_time), entry_ndx=round(entry_price, 1),
                short_K=short_K, long_K=long_K,
                credit_pts=round(credit_pts, 2),
                gate_score=gate_score, q_score=q_score,
                exit_reason=exit_reason,
            ))
            break  # one trade per day

    if not results:
        return dict(name=name, description=description, summary={}, trades=pd.DataFrame())

    trades_df = pd.DataFrame(results)
    summary   = _summarize(trades_df["cash_pnl"])
    summary["filtered_days"] = len(trading_days) - len(trades_df)
    summary["exit_reasons"]  = trades_df["exit_reason"].value_counts().to_dict()
    _add_weekly_stats(summary, trades_df)
    return dict(name=name, description=description, summary=summary, trades=trades_df)


# ── Named variant configurations ───────────────────────────────────────────────

VARIANTS = [
    dict(
        name="gated",
        description="Simulated: gate score >= 3 + Q-score >= 45 (standard rules)",
        kwargs=dict(no_gate=False, min_gate_score=3, min_qscore=45),
    ),
    dict(
        name="no_gate",
        description="Simulated: all gate/Q-score filters removed",
        kwargs=dict(no_gate=True),
    ),
    dict(
        name="high_gate",
        description="Simulated: gate score >= 4 only (stricter entry)",
        kwargs=dict(no_gate=False, min_gate_score=4, min_qscore=45),
    ),
    dict(
        name="low_credit",
        description="Simulated: credit 8-12 pt range only (low-vol premium)",
        kwargs=dict(no_gate=False, min_gate_score=3, min_qscore=45,
                    credit_min=8.0, credit_max=12.0),
    ),
]
