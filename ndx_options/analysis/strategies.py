"""
strategies.py — Multi-strategy comparison framework.

Each named variant produces a standardized results dict that can be printed
side-by-side in a comparison table.

Variants
--------
  original       Actual fills from trades.json  — all spread groups
  bear_put_only  Actual fills, Bear Put direction only
  no_edt         Actual fills, Bear Put, same-day expiry only (no overnight EDT)
  prime_only     Actual fills, Bear Put, same-day, 10:00–10:30 entry
  gated          Simulated backtest: gate score ≥ 3 + Q-score ≥ 45
  no_gate        Simulated backtest: all gate/Q-score filters removed
  high_gate      Simulated backtest: gate score ≥ 4 only
  low_credit     Simulated backtest: credit 8–12 pt range only

Usage
-----
    from ndx_options.analysis.strategies import run_all, print_comparison
    results = run_all()
    print_comparison(results)
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, time
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

from ..config.settings import (
    ET, BACKTEST_DATA, TRADES_JSON, NDX_MULTIPLIER,
    PRIME_START, PRIME_END, GATE_MIN_PROCEED,
    BASE_CONTRACTS, PROFIT_TARGET_PCT, LOSS_STOP_MULT,
    MIN_CREDIT_PTS, MAX_CREDIT_PTS,
    QSCORE_ACCEPT,
)

MULT = 100  # NDX option multiplier (same as NDX_MULTIPLIER)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _pct(x: float) -> str:
    return f"{x:.1%}"

def _usd(x: float) -> str:
    return f"${x:>+,.0f}"

def _summarize(pnl_series: pd.Series) -> dict:
    """Standard stats dict from a series of per-trade P&L values."""
    if len(pnl_series) == 0:
        return {}
    wins   = pnl_series[pnl_series > 0]
    losses = pnl_series[pnl_series <= 0]
    n      = len(pnl_series)
    wr     = len(wins) / n
    avg_w  = wins.mean()   if len(wins)   > 0 else 0.0
    avg_l  = losses.mean() if len(losses) > 0 else 0.0
    total  = pnl_series.sum()
    pf     = abs(avg_w * len(wins) / (avg_l * len(losses))) if losses.any() and avg_l else 0.0

    # Sharpe (annualised, approx 252 trading days)
    daily_ret = pnl_series / 100_000      # assume $100k base
    sharpe    = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)
                 if daily_ret.std() > 0 else 0.0)

    # Max drawdown
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


# ── Actual-trades variants (parse trades.json) ─────────────────────────────────

def _load_spread_df(path: str | Path) -> pd.DataFrame:
    """
    Parse trades.json into one row per spread group.
    Groups by (date, account, expiry, option_type) and computes cash P&L
    as the net cash flow of all legs (−qty × price × MULT).
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

        # Cash P&L: selling a put → positive cash; buying a put → negative cash
        cash_pnl = (-grp["quantity"] * grp["price"] * MULT).sum()

        # Direction
        max_sell_K = sells["strike"].max()
        max_buy_K  = buys["strike"].max()
        if opt_type == "P":
            direction = "Bear Put" if max_sell_K > max_buy_K else "Bull Put"
        else:
            direction = "Bear Call" if max_sell_K < max_buy_K else "Bull Call"

        # EDT: any leg after 14:45 ET with next-day expiry
        try:
            exp_date = datetime.strptime(expiry, "%d%b%y").date()
            trd_date = pd.Timestamp(date_s).date()
            is_edt   = (
                any(grp["datetime"].dt.time > time(14, 45))
                and exp_date > trd_date
            )
        except Exception:
            is_edt = False

        entry_time = grp["datetime"].iloc[0].time()
        n_legs     = len(grp)
        n_contracts = int(sells["quantity"].abs().sum())

        spreads.append(dict(
            date=pd.Timestamp(date_s),
            account=account,
            expiry=expiry,
            option_type=opt_type,
            direction=direction,
            is_edt=is_edt,
            entry_time=entry_time,
            n_contracts=n_contracts,
            n_legs=n_legs,
            cash_pnl=cash_pnl,
        ))

    return pd.DataFrame(spreads).sort_values("date").reset_index(drop=True)


def _in_prime(t: time) -> bool:
    return PRIME_START <= t <= PRIME_END


def run_actual(
    name: str,
    description: str,
    trades_path: str | Path,
    direction_filter: Optional[str] = None,
    exclude_edt: bool = False,
    prime_only: bool = False,
) -> dict:
    """Generic runner for actual-trades variants."""
    spreads = _load_spread_df(trades_path)

    if direction_filter:
        spreads = spreads[spreads["direction"] == direction_filter]
    if exclude_edt:
        spreads = spreads[~spreads["is_edt"]]
    if prime_only:
        spreads = spreads[spreads["entry_time"].apply(_in_prime)]

    # Drop zero-P&L rows (open / unresolved positions)
    spreads = spreads[spreads["cash_pnl"] != 0].reset_index(drop=True)

    if spreads.empty:
        return dict(name=name, description=description, summary={}, trades=spreads)

    summary = _summarize(spreads["cash_pnl"])
    summary["filtered_days"] = 0
    return dict(name=name, description=description, summary=summary, trades=spreads)


# ── Simulated variants (run backtest.py engine) ────────────────────────────────

def run_simulated(
    name: str,
    description: str,
    data_path: str | Path,
    no_gate: bool = False,
    min_gate_score: int = GATE_MIN_PROCEED,
    min_qscore: int = QSCORE_ACCEPT,
    credit_min: float = MIN_CREDIT_PTS,
    credit_max: float = MAX_CREDIT_PTS,
    verbose: bool = False,
) -> dict:
    """
    Run a simulation variant through the backtest engine with custom parameters.
    Thin wrapper around backtest.simulate_day so we can vary individual knobs.
    """
    from .backtest import load_ndx_5min, compute_bar_metrics, spread_value_pts as _svp
    from ..config.settings import (
        PRIME_START, PRIME_END, TIME_EXIT_ET,
        PROFIT_TARGET_PCT, LOSS_STOP_MULT,
        BASE_CONTRACTS,
    )
    from ..core.signal_engine import (
        evaluate_gate, gate_action, hard_override_avoid,
        select_strikes, compute_qscore, size_from_qscore,
    )

    df = load_ndx_5min(str(data_path))
    trading_days = sorted(df["date"].unique())
    results = []

    for day in trading_days:
        day_bars = df[df["date"] == day].reset_index(drop=True)
        open_bars = day_bars[day_bars["time_et"] >= time(9, 30)].reset_index(drop=True)
        if len(open_bars) < 5:
            continue

        trade_date = day_bars.iloc[0]["date"]
        traded = False

        for i, row in open_bars.iterrows():
            bar_time = row["time_et"]
            if bar_time < PRIME_START:
                continue
            if bar_time > PRIME_END:
                break

            ctx_bars = open_bars.iloc[: i + 1]
            m = compute_bar_metrics(ctx_bars)

            gate_score, _ = evaluate_gate(m, bar_time)

            if not no_gate:
                if gate_action(gate_score) == "AVOID":
                    continue
                if gate_score < min_gate_score:
                    continue
                if hard_override_avoid(m, bar_time):
                    continue

            short_K, long_K = select_strikes(m["price"])
            q_score, _      = compute_qscore(m, bar_time, "Bear Put", short_K, is_0dte=True)

            if not no_gate and q_score < min_qscore:
                continue

            bars_total     = len(open_bars)
            bars_remaining = bars_total - i
            credit_est = _svp(m["price"], short_K, long_K,
                               max(bars_remaining, 10), m["sigma"])

            if not (credit_min <= credit_est <= credit_max):
                continue

            n = BASE_CONTRACTS if no_gate else size_from_qscore(BASE_CONTRACTS, q_score, gate_score)
            if n == 0:
                continue

            # Forward-simulate exits
            entry_price = m["price"]
            credit_pts  = credit_est
            future_bars = open_bars.iloc[i + 1:].reset_index(drop=True)
            exit_reason = "time_exit"
            exit_price  = entry_price
            close_val   = 0.0

            for j, fbar in future_bars.iterrows():
                ft        = fbar["time_et"]
                ndx       = float(fbar["close"])
                bars_left = max(bars_total - i - j - 1, 1)
                sv = _svp(ndx, short_K, long_K, bars_left, m["sigma"])

                if ndx < short_K:
                    exit_reason, close_val, exit_price = "ndx_stop", sv, ndx
                    break
                if sv >= credit_pts * LOSS_STOP_MULT:
                    exit_reason, close_val, exit_price = "loss_stop", sv, ndx
                    break
                if sv <= credit_pts * PROFIT_TARGET_PCT:
                    exit_reason, close_val, exit_price = "profit_target", sv, ndx
                    break
                if ft >= TIME_EXIT_ET:
                    exit_reason, close_val, exit_price = "time_exit", sv, ndx
                    break
            else:
                close_val = 0.0

            pnl_usd = (credit_pts - close_val) * NDX_MULTIPLIER * n

            if verbose:
                wr_str = "WIN" if pnl_usd > 0 else "LOSS"
                print(f"  {trade_date}  {bar_time}  NDX={entry_price:.0f}  "
                      f"{short_K}/{long_K}  credit={credit_pts:.2f}  "
                      f"exit={exit_reason}  P&L=${pnl_usd:+,.0f}  [{wr_str}]")

            results.append(dict(
                date=str(trade_date), cash_pnl=pnl_usd,
                gate_score=gate_score, q_score=q_score,
                exit_reason=exit_reason, credit_pts=credit_pts,
            ))
            traded = True
            break  # one trade per day

    if not results:
        return dict(name=name, description=description, summary={}, trades=pd.DataFrame())

    trades_df = pd.DataFrame(results)
    summary   = _summarize(trades_df["cash_pnl"])
    summary["filtered_days"] = len(trading_days) - len(trades_df)
    exit_counts = trades_df["exit_reason"].value_counts().to_dict()
    summary["exit_reasons"] = exit_counts

    return dict(name=name, description=description, summary=summary, trades=trades_df)


# ── Mean-reversion (CreditPut mimic) simulation ───────────────────────────────

def run_mean_reversion(
    name: str,
    description: str,
    data_path: str | Path,
    verbose: bool = False,
    # entry knobs
    min_drop_from_high_pct: float = 0.3,   # NDX must have pulled back ≥ 0.3% from day high
    entry_start: time = time(10, 0),        # earliest entry
    entry_end:   time = time(15, 0),        # latest entry
    short_offset: int = 100,                # short strike = current NDX + this (ITM put)
    spread_width: int = 50,                 # long strike = short - spread_width
    # exit knobs
    profit_target_pct: float = 0.25,        # close when spread ≤ 25% of credit
    loss_stop_mult:    float = 2.0,         # close when spread ≥ 2× credit
    time_exit_et: time = time(14, 30),
) -> dict:
    """
    Simulate the CreditPut mean-reversion strategy observed in trades.json:
      - Wait for NDX to pull back ≥ X% from the day's high
      - Sell a put spread where short strike = current NDX + offset (ITM put)
      - Profit from mean reversion back above the short strike
    """
    from .backtest import load_ndx_5min, compute_bar_metrics
    from ..core.signal_engine import spread_value_pts as _svp

    df = load_ndx_5min(str(data_path))
    trading_days = sorted(df["date"].unique())
    results = []

    for day in trading_days:
        day_bars = df[df["date"] == day].reset_index(drop=True)
        open_bars = day_bars[day_bars["time_et"] >= time(9, 30)].reset_index(drop=True)
        if len(open_bars) < 5:
            continue

        trade_date = day_bars.iloc[0]["date"]
        day_high   = float(open_bars["high"].max())  # rolling high will be used per-bar

        traded = False
        for i, row in open_bars.iterrows():
            bar_time = row["time_et"]
            if bar_time < entry_start:
                continue
            if bar_time > entry_end:
                break
            if traded:
                break

            ndx = float(row["close"])

            # Rolling day high up to this bar
            rolling_high = float(open_bars.iloc[: i + 1]["high"].max())
            drop_pct = (rolling_high - ndx) / rolling_high * 100

            if drop_pct < min_drop_from_high_pct:
                continue

            # Strike selection: short is ITM (above current NDX)
            short_K = round(ndx + short_offset)
            long_K  = short_K - spread_width

            bars_total     = len(open_bars)
            bars_remaining = max(bars_total - i, 10)

            # Estimate implied vol from bar context
            ctx = open_bars.iloc[: i + 1]
            m   = compute_bar_metrics(ctx)
            sigma = m["sigma"]

            credit_est = _svp(ndx, short_K, long_K, bars_remaining, sigma)
            if credit_est < 5.0:
                continue  # skip if no meaningful credit

            # Forward simulate exits
            future_bars  = open_bars.iloc[i + 1:].reset_index(drop=True)
            exit_reason  = "time_exit"
            close_val    = 0.0
            exit_ndx     = ndx

            for j, fbar in future_bars.iterrows():
                ft       = fbar["time_et"]
                fut_ndx  = float(fbar["close"])
                bars_left = max(bars_total - i - j - 1, 1)
                sv = _svp(fut_ndx, short_K, long_K, bars_left, sigma)

                if sv <= credit_est * profit_target_pct:
                    exit_reason, close_val, exit_ndx = "profit_target", sv, fut_ndx
                    break
                if sv >= credit_est * loss_stop_mult:
                    exit_reason, close_val, exit_ndx = "loss_stop", sv, fut_ndx
                    break
                if fut_ndx > short_K + spread_width:
                    # NDX well above both strikes — spread worthless
                    exit_reason, close_val, exit_ndx = "full_profit", 0.0, fut_ndx
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
                date=str(trade_date),
                entry_time=str(bar_time),
                entry_ndx=round(ndx, 1),
                short_K=short_K, long_K=long_K,
                drop_pct=round(drop_pct, 2),
                credit_pts=round(credit_est, 2),
                close_val=round(close_val, 2),
                exit_reason=exit_reason,
                exit_ndx=round(exit_ndx, 1),
                pnl_usd=round(pnl_usd, 2),
                cash_pnl=round(pnl_usd, 2),
            ))
            traded = True

    if not results:
        return dict(name=name, description=description, summary={}, trades=pd.DataFrame())

    trades_df = pd.DataFrame(results)
    summary   = _summarize(trades_df["cash_pnl"])
    summary["filtered_days"] = len(trading_days) - len(trades_df)
    summary["exit_reasons"]  = trades_df["exit_reason"].value_counts().to_dict()

    return dict(name=name, description=description, summary=summary, trades=trades_df)


# ── Named strategy registry ────────────────────────────────────────────────────

def build_all(
    trades_path: str | Path = TRADES_JSON,
    data_path:   str | Path = BACKTEST_DATA,
    verbose: bool = False,
) -> dict[str, dict]:
    """Build and return all named strategy results."""
    tp = Path(trades_path)
    dp = Path(data_path)

    print("Building strategy variants…")
    results = {}

    variants = [
        # ── Actual-trades variants ──────────────────────────────────────────
        dict(
            fn="actual",
            name="original",
            description="All actual trades from trades.json (all directions)",
            kwargs=dict(direction_filter=None, exclude_edt=False, prime_only=False),
        ),
        dict(
            fn="actual",
            name="bear_put_only",
            description="Actual trades — Bear Put spreads only",
            kwargs=dict(direction_filter="Bear Put", exclude_edt=False, prime_only=False),
        ),
        dict(
            fn="actual",
            name="no_edt",
            description="Actual trades — Bear Put, same-day expiry (no overnight EDT)",
            kwargs=dict(direction_filter="Bear Put", exclude_edt=True, prime_only=False),
        ),
        dict(
            fn="actual",
            name="prime_only",
            description="Actual trades — Bear Put, same-day, prime window 10:00–10:30 only",
            kwargs=dict(direction_filter="Bear Put", exclude_edt=True, prime_only=True),
        ),
        # ── Mean-reversion (mimics CreditPut from actual trades) ───────────
        dict(
            fn="mean_reversion",
            name="mean_reversion",
            description="Simulated CreditPut mimic: sell ITM put spread, afternoon entry, 0.5% drop",
            kwargs=dict(
                min_drop_from_high_pct=0.5,
                entry_start=time(12, 0),
                entry_end=time(15, 30),
                short_offset=125,
                spread_width=50,
            ),
        ),
        # ── Simulated variants ──────────────────────────────────────────────
        dict(
            fn="sim",
            name="gated",
            description="Simulated: gate score ≥ 3 + Q-score ≥ 45 (standard rules)",
            kwargs=dict(no_gate=False, min_gate_score=3, min_qscore=45),
        ),
        dict(
            fn="sim",
            name="no_gate",
            description="Simulated: all gate/Q-score filters removed",
            kwargs=dict(no_gate=True),
        ),
        dict(
            fn="sim",
            name="high_gate",
            description="Simulated: gate score ≥ 4 only (stricter entry)",
            kwargs=dict(no_gate=False, min_gate_score=4, min_qscore=45),
        ),
        dict(
            fn="sim",
            name="low_credit",
            description="Simulated: credit 8–12 pt range only (low-vol premium)",
            kwargs=dict(no_gate=False, min_gate_score=3, min_qscore=45,
                        credit_min=8.0, credit_max=12.0),
        ),
    ]

    for spec in variants:
        name = spec["name"]
        desc = spec["description"]
        print(f"  [{name}]  {desc}")
        if spec["fn"] == "actual":
            results[name] = run_actual(
                name=name, description=desc,
                trades_path=tp, **spec["kwargs"]
            )
        elif spec["fn"] == "mean_reversion":
            results[name] = run_mean_reversion(
                name=name, description=desc,
                data_path=dp, verbose=verbose, **spec["kwargs"]
            )
        else:
            results[name] = run_simulated(
                name=name, description=desc,
                data_path=dp, verbose=verbose, **spec["kwargs"]
            )

    return results


# ── Single-strategy detail report ────────────────────────────────────────────

def print_strategy_detail(result: dict, initial_capital: float = 100_000):
    """Print a full trade-by-trade report for one strategy variant."""
    name    = result["name"]
    desc    = result["description"]
    summary = result.get("summary", {})
    trades  = result.get("trades", pd.DataFrame())

    if trades.empty or not summary:
        print(f"\n[{name}]  No trades found.")
        return

    # Determine P&L column
    pnl_col = "pnl_usd" if "pnl_usd" in trades.columns else "cash_pnl"

    # Running equity
    trades = trades.copy().reset_index(drop=True)
    trades["equity"] = initial_capital + trades[pnl_col].cumsum()

    final_equity = trades["equity"].iloc[-1]
    ret_pct      = (final_equity - initial_capital) / initial_capital * 100
    peak         = trades["equity"].cummax()
    max_dd_usd   = (trades["equity"] - peak).min()
    max_dd_pct   = (max_dd_usd / peak.max()) * 100

    # ── Header ────────────────────────────────────────────────────────────────
    width = 70
    print()
    print("=" * width)
    print(f"  STRATEGY: {name.upper()}")
    print(f"  {desc}")
    print("=" * width)
    arrow = "▲" if final_equity >= initial_capital else "▼"
    print(f"  {'starting_capital':<26} ${initial_capital:>12,.0f}")
    print(f"  {'final_equity':<26} ${final_equity:>12,.0f}  {arrow} {ret_pct:+.2f}%")
    print(f"  {'max_drawdown':<26} ${max_dd_usd:>12,.0f}  ({abs(max_dd_pct):.2f}%)")
    print()

    # ── Trade list ────────────────────────────────────────────────────────────
    is_actual = "cash_pnl" in trades.columns and "direction" in trades.columns

    print(f"  {'#':>3}  {'Date':<12} {'Time':<9}", end="")
    if is_actual:
        print(f"  {'Direction':<12} {'Contracts':>9} {'P&L':>10}  {'Equity':>10}  Result")
    else:
        print(f"  {'NDX':>6}  {'Spread':<14} {'Credit':>7} {'Exit':<14} {'P&L':>10}  {'Equity':>10}  Result")
    print("  " + "-" * (width - 2))

    for i, row in trades.iterrows():
        pnl    = row[pnl_col]
        eq     = row["equity"]
        result_str = "WIN" if pnl > 0 else "LOSS"

        if is_actual:
            date_s = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])
            time_s = str(row.get("entry_time", ""))[:8]
            direc  = str(row.get("direction", ""))
            n      = int(row.get("n_contracts", 0))
            print(f"  {i+1:>3}  {date_s:<12} {time_s:<9}  {direc:<12} {n:>9}  "
                  f"${pnl:>+9,.0f}  ${eq:>9,.0f}  {result_str}")
        else:
            date_s  = str(row.get("date", ""))
            time_s  = str(row.get("entry_time", ""))[:8]
            ndx     = row.get("entry_ndx", 0)
            short_k = int(row.get("short_K", 0))
            long_k  = int(row.get("long_K", 0))
            credit  = row.get("credit_pts", 0)
            exit_r  = str(row.get("exit_reason", ""))
            print(f"  {i+1:>3}  {date_s:<12} {time_s:<9}"
                  f"  {ndx:>6.0f}  {short_k}/{long_k:<9}  {credit:>6.2f}"
                  f"  {exit_r:<14} ${pnl:>+9,.0f}  ${eq:>9,.0f}  {result_str}")

    # ── Summary block ─────────────────────────────────────────────────────────
    print()
    print("  " + "-" * (width - 2))
    n       = summary.get("n", 0)
    wins    = summary.get("wins", 0)
    losses  = summary.get("losses", 0)
    wr      = summary.get("win_rate", 0)
    total   = summary.get("total_pnl", summary.get("total", 0))
    avg_w   = summary.get("avg_win", 0)
    avg_l   = summary.get("avg_loss", 0)
    pf      = summary.get("profit_factor", 0)
    sharpe  = summary.get("sharpe", summary.get("sharpe_ratio", 0))
    max_dd  = summary.get("max_dd_pct", summary.get("max_drawdown_pct", abs(max_dd_pct)))

    print(f"  {'trades':<26} {n}  ({wins}W / {losses}L)")
    print(f"  {'win_rate':<26} {wr:.1%}")
    print(f"  {'total_pnl':<26} ${total:>+,.0f}")
    print(f"  {'avg_win':<26} ${avg_w:>+,.0f}")
    print(f"  {'avg_loss':<26} ${avg_l:>+,.0f}")
    print(f"  {'profit_factor':<26} {pf:.2f}")
    print(f"  {'sharpe':<26} {sharpe:.3f}")
    print(f"  {'max_drawdown_pct':<26} {max_dd:.2f}%")

    # exit breakdown for simulated variants
    exit_r = summary.get("exit_reasons", {})
    if exit_r:
        print(f"\n  Exit breakdown:")
        for ex, cnt in sorted(exit_r.items(), key=lambda x: -x[1]):
            print(f"    {ex:<22} {cnt}")

    print("=" * width)


# ── Comparison table ───────────────────────────────────────────────────────────

def print_comparison(results: dict[str, dict]):
    """Print a side-by-side comparison table of all strategy variants."""
    COLS = [
        ("n",             "Trades",    lambda v: str(v)),
        ("win_rate",      "WR",        lambda v: f"{v:.1%}"),
        ("total_pnl",     "Total P&L", lambda v: f"${v:>+,.0f}"),
        ("avg_pnl",       "Avg/trade", lambda v: f"${v:>+,.0f}"),
        ("avg_win",       "Avg Win",   lambda v: f"${v:>+,.0f}"),
        ("avg_loss",      "Avg Loss",  lambda v: f"${v:>+,.0f}"),
        ("profit_factor", "PF",        lambda v: f"{v:.2f}"),
        ("sharpe",        "Sharpe",    lambda v: f"{v:.3f}"),
        ("max_dd_pct",    "MaxDD%",    lambda v: f"{v:.1f}%"),
        ("filtered_days", "Filtered",  lambda v: str(v)),
    ]

    names = list(results.keys())
    col_w = 14

    # Header
    print()
    print("=" * (20 + col_w * len(names)))
    print("STRATEGY COMPARISON")
    print("=" * (20 + col_w * len(names)))

    # Strategy names row
    print(f"{'':20s}", end="")
    for n in names:
        print(f"{n:>{col_w}s}", end="")
    print()

    # Description row (truncated)
    print(f"{'':20s}", end="")
    for n in names:
        desc = results[n].get("description", "")
        words = desc.split()
        short = " ".join(words[:3]) + "…" if len(words) > 3 else desc
        print(f"{short:>{col_w}s}", end="")
    print()

    print("-" * (20 + col_w * len(names)))

    # Metric rows
    for key, label, fmt in COLS:
        print(f"{label:20s}", end="")
        for n in names:
            s = results[n].get("summary", {})
            if not s or key not in s:
                print(f"{'—':>{col_w}s}", end="")
            else:
                try:
                    print(f"{fmt(s[key]):>{col_w}s}", end="")
                except Exception:
                    print(f"{'err':>{col_w}s}", end="")
        print()

    print("=" * (20 + col_w * len(names)))

    # Exit breakdown (simulated variants only)
    sim_names = [n for n in names if "exit_reasons" in results[n].get("summary", {})]
    if sim_names:
        print("\nExit breakdown (simulated variants):")
        all_exits = set()
        for n in sim_names:
            all_exits |= set(results[n]["summary"]["exit_reasons"].keys())
        for ex in sorted(all_exits):
            print(f"  {ex:20s}", end="")
            for n in sim_names:
                cnt = results[n]["summary"]["exit_reasons"].get(ex, 0)
                total = results[n]["summary"]["n"]
                print(f"  {cnt:>3d}/{total:<3d}", end="")
            print()
