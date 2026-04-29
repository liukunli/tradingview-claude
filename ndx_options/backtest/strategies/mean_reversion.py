"""
strategies/mean_reversion.py — Mean-reversion CreditPut mimic strategy.

Observed in the actual trades.json data: wait for NDX to pull back from
the session high, then sell an ITM put spread expecting a bounce.
This is the opposite setup from the primary Bear Put strategy (OTM put spread).

Variant defined here
--------------------
  mean_reversion   0.5% pullback from day high, afternoon entry, ITM +125pt short
"""

from __future__ import annotations

from datetime import time
from pathlib import Path

import pandas as pd

from ._common import _summarize, _add_weekly_stats
from ...strategy.signal_engine import compute_bar_metrics, spread_value_pts, evaluate_exit
from ...config.settings import NDX_MULTIPLIER, BACKTEST_DATA


def run(
    name: str,
    description: str,
    data_path: str | Path = BACKTEST_DATA,
    verbose: bool = False,
    # entry knobs
    min_drop_from_high_pct: float = 0.3,
    entry_start: time = time(10, 0),
    entry_end: time = time(15, 0),
    short_offset: int = 100,      # short strike = current NDX + offset (ITM put)
    spread_width: int = 50,
    # exit knobs — passed through to evaluate_exit via local overrides
    profit_target_pct: float = 0.25,
    loss_stop_mult: float = 2.0,
    time_exit_et: time = time(14, 30),
) -> dict:
    """
    Simulate the mean-reversion (CreditPut mimic) strategy.

    Entry: NDX drops >= min_drop_from_high_pct% from rolling session high.
    Strike: short_K = NDX + short_offset (intentionally ITM).
    Exit: reuses spread_value_pts for monitoring; profit/loss/time exits
          follow the same thresholds as the primary strategy.
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
        bars_total = len(open_bars)

        for i, row in open_bars.iterrows():
            bar_time = row["time_et"]
            if bar_time < entry_start:
                continue
            if bar_time > entry_end:
                break

            ndx          = float(row["close"])
            rolling_high = float(open_bars.iloc[: i + 1]["high"].max())
            drop_pct     = (rolling_high - ndx) / rolling_high * 100

            if drop_pct < min_drop_from_high_pct:
                continue

            short_K = round(ndx + short_offset)
            long_K  = short_K - spread_width

            ctx   = open_bars.iloc[: i + 1]
            m     = compute_bar_metrics(ctx)
            sigma = m["sigma"]

            bars_remaining = max(bars_total - i, 10)
            credit_est = spread_value_pts(ndx, short_K, long_K, bars_remaining, sigma)
            if credit_est < 5.0:
                continue

            # Forward-simulate exits
            future_bars = open_bars.iloc[i + 1:].reset_index(drop=True)
            exit_reason = "time_exit"
            close_val   = 0.0
            exit_ndx    = ndx

            for j, fbar in future_bars.iterrows():
                ft      = fbar["time_et"]
                fut_ndx = float(fbar["close"])
                bars_left = max(bars_total - i - j - 1, 1)
                sv = spread_value_pts(fut_ndx, short_K, long_K, bars_left, sigma)

                # Full ITM breakout: both strikes well above NDX → spread nearly worthless
                if fut_ndx > short_K + spread_width:
                    exit_reason, close_val, exit_ndx = "full_profit", 0.0, fut_ndx
                    break

                # Reuse standard exit thresholds (parameterized per variant)
                if sv <= credit_est * profit_target_pct:
                    exit_reason, close_val, exit_ndx = "profit_target", sv, fut_ndx
                    break
                if sv >= credit_est * loss_stop_mult:
                    exit_reason, close_val, exit_ndx = "loss_stop", sv, fut_ndx
                    break
                if ft >= time_exit_et:
                    exit_reason, close_val, exit_ndx = "time_exit", sv, fut_ndx
                    break
            else:
                close_val = 0.0

            pnl_usd = (credit_est - close_val) * NDX_MULTIPLIER * 1  # 1 contract base

            if verbose:
                tag = "WIN" if pnl_usd > 0 else "LOSS"
                print(f"  {trade_date}  {bar_time}  NDX={ndx:.0f}  "
                      f"sell={short_K}/buy={long_K}  drop={drop_pct:.1f}%  "
                      f"credit={credit_est:.1f}  exit={exit_reason}  "
                      f"P&L=${pnl_usd:+,.0f}  [{tag}]")

            results.append(dict(
                date=str(trade_date), cash_pnl=round(pnl_usd, 2),
                entry_time=str(bar_time), entry_ndx=round(ndx, 1),
                short_K=short_K, long_K=long_K,
                drop_pct=round(drop_pct, 2),
                credit_pts=round(credit_est, 2),
                close_val=round(close_val, 2),
                exit_reason=exit_reason,
                exit_ndx=round(exit_ndx, 1),
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


# ── Named variant configuration ────────────────────────────────────────────────

VARIANT = dict(
    name="mean_reversion",
    description="Simulated CreditPut mimic: sell ITM put spread, afternoon entry, 0.5% drop",
    kwargs=dict(
        min_drop_from_high_pct=0.5,
        entry_start=time(12, 0),
        entry_end=time(15, 30),
        short_offset=125,
        spread_width=50,
    ),
)
