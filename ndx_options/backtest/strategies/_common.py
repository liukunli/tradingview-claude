"""
strategies/_common.py — Shared helpers for all strategy variants.

Provides: _summarize, _add_weekly_stats, _load_spread_df, _in_prime
"""

from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

from ...config.settings import PRIME_START, PRIME_END

MULT = 100  # NDX option multiplier ($100/pt)


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _pct(x: float) -> str:
    return f"{x:.1%}"

def _usd(x: float) -> str:
    return f"${x:>+,.0f}"


# ── Weekly stats ───────────────────────────────────────────────────────────────

def _add_weekly_stats(summary: dict, trades_df: pd.DataFrame) -> None:
    """Compute pnl_per_week and worst_week. Mutates summary in-place."""
    if trades_df.empty:
        return
    dates = pd.to_datetime(trades_df["date"])
    weekly = trades_df.copy()
    weekly["week"] = dates.dt.to_period("W")
    by_week = weekly.groupby("week")["cash_pnl"].sum()
    n_weeks = len(by_week)
    total   = summary.get("total_pnl", 0)
    summary["pnl_per_week"] = round(total / n_weeks, 2) if n_weeks else 0
    summary["worst_week"]   = round(by_week.min(), 2)   if n_weeks else 0


# ── Standard stats dict ────────────────────────────────────────────────────────

def _summarize(pnl_series: pd.Series) -> dict:
    """Compute standard performance stats from a per-trade P&L series."""
    if len(pnl_series) == 0:
        return {}
    wins   = pnl_series[pnl_series > 0]
    losses = pnl_series[pnl_series <= 0]
    n      = len(pnl_series)
    wr     = len(wins) / n
    avg_w  = wins.mean()   if len(wins)   > 0 else 0.0
    avg_l  = losses.mean() if len(losses) > 0 else 0.0
    total  = pnl_series.sum()
    pf     = abs(avg_w * len(wins) / (avg_l * len(losses))) \
             if losses.any() and avg_l else 0.0

    daily_ret = pnl_series / 100_000
    sharpe = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)
              if daily_ret.std() > 0 else 0.0)

    equity = 100_000 + pnl_series.cumsum()
    peak   = equity.cummax()
    dd     = ((equity - peak) / peak).min()

    return dict(
        n=n, wins=int(len(wins)), losses=int(len(losses)),
        win_rate=wr, total_pnl=total,
        avg_pnl=total / n,
        avg_win=avg_w, avg_loss=avg_l,
        profit_factor=round(pf, 2),
        sharpe=round(sharpe, 3),
        max_dd_pct=round(abs(dd) * 100, 2),
    )


# ── trades.json parser ─────────────────────────────────────────────────────────

def _load_spread_df(path: str | Path) -> pd.DataFrame:
    """
    Parse trades.json → one row per spread group.
    Groups by (date, account, expiry, option_type) and computes
    cash P&L as the net cash flow of all legs.
    """
    with open(path) as f:
        raw = json.load(f)

    df = pd.DataFrame(raw)
    df["datetime"] = pd.to_datetime(df["date"] + " " + df["time"])
    df = df.sort_values("datetime").reset_index(drop=True)

    spreads = []
    for (date_s, account, expiry, opt_type), grp in df.groupby(
        ["date", "account", "expiry", "option_type"], sort=False
    ):
        grp = grp.sort_values("datetime")
        sells = grp[grp["quantity"] < 0]
        buys  = grp[grp["quantity"] > 0]
        if sells.empty or buys.empty:
            continue

        cash_pnl = (-grp["quantity"] * grp["price"] * MULT).sum()

        max_sell_K = sells["strike"].max()
        max_buy_K  = buys["strike"].max()
        if opt_type == "P":
            direction = "Bear Put" if max_sell_K > max_buy_K else "Bull Put"
        else:
            direction = "Bear Call" if max_sell_K < max_buy_K else "Bull Call"

        try:
            exp_date = datetime.strptime(expiry, "%d%b%y").date()
            trd_date = pd.Timestamp(date_s).date()
            is_edt = (
                any(grp["datetime"].dt.time > time(14, 45))
                and exp_date > trd_date
            )
        except Exception:
            is_edt = False

        spreads.append(dict(
            date=pd.Timestamp(date_s),
            account=account,
            expiry=expiry,
            option_type=opt_type,
            direction=direction,
            is_edt=is_edt,
            entry_time=grp["datetime"].iloc[0].time(),
            n_contracts=int(sells["quantity"].abs().sum()),
            n_legs=len(grp),
            cash_pnl=cash_pnl,
        ))

    return pd.DataFrame(spreads).sort_values("date").reset_index(drop=True)


def _in_prime(t: time) -> bool:
    return PRIME_START <= t <= PRIME_END
