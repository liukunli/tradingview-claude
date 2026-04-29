"""
strategies/actual.py — Actual-trades analysis variants.

Parses trades.json and applies direction / EDT / time-window filters.
No simulation — uses real fills from the live trading log.

Variants defined here
---------------------
  original       All spreads, all directions
  bear_put_only  Bear Put spreads only
  no_edt         Bear Put, same-day expiry (strips overnight EDT positions)
  prime_only     Bear Put, same-day, 10:00–10:30 ET entry window
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from ._common import _load_spread_df, _summarize, _add_weekly_stats, _in_prime
from ...config.settings import TRADES_JSON


def run(
    name: str,
    description: str,
    trades_path: str | Path = TRADES_JSON,
    direction_filter: Optional[str] = None,
    exclude_edt: bool = False,
    prime_only: bool = False,
) -> dict:
    """
    Run an actual-trades variant.

    Parameters
    ----------
    direction_filter : "Bear Put" | "Bull Put" | None (all directions)
    exclude_edt      : drop overnight / EDT positions
    prime_only       : keep only entries in the 10:00–10:30 prime window
    """
    spreads = _load_spread_df(trades_path)

    if direction_filter:
        spreads = spreads[spreads["direction"] == direction_filter]
    if exclude_edt:
        spreads = spreads[~spreads["is_edt"]]
    if prime_only:
        spreads = spreads[spreads["entry_time"].apply(_in_prime)]

    spreads = spreads[spreads["cash_pnl"] != 0].reset_index(drop=True)

    if spreads.empty:
        return dict(name=name, description=description, summary={}, trades=spreads)

    summary = _summarize(spreads["cash_pnl"])
    summary["filtered_days"] = 0
    _add_weekly_stats(summary, spreads)
    return dict(name=name, description=description, summary=summary, trades=spreads)


# ── Named variant configurations ───────────────────────────────────────────────

VARIANTS = [
    dict(
        name="original",
        description="All actual trades from trades.json (all directions)",
        kwargs=dict(direction_filter=None, exclude_edt=False, prime_only=False),
    ),
    dict(
        name="bear_put_only",
        description="Actual trades — Bear Put spreads only",
        kwargs=dict(direction_filter="Bear Put", exclude_edt=False, prime_only=False),
    ),
    dict(
        name="no_edt",
        description="Actual trades — Bear Put, same-day expiry (no overnight EDT)",
        kwargs=dict(direction_filter="Bear Put", exclude_edt=True, prime_only=False),
    ),
    dict(
        name="prime_only",
        description="Actual trades — Bear Put, same-day, prime window 10:00–10:30 only",
        kwargs=dict(direction_filter="Bear Put", exclude_edt=True, prime_only=True),
    ),
]
