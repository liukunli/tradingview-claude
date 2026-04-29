"""
strategies/registry.py — Strategy registry, comparison table, and detail report.

build_all()            : run all variants and return results dict
print_comparison()     : side-by-side comparison table
print_strategy_detail(): full trade-by-trade report for one variant
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ...config.settings import TRADES_JSON, BACKTEST_DATA
from .actual import run as _run_actual, VARIANTS as _ACTUAL_VARIANTS
from .simulated import run as _run_simulated, VARIANTS as _SIM_VARIANTS
from .mean_reversion import run as _run_mr, VARIANT as _MR_VARIANT


# ── Build all variants ─────────────────────────────────────────────────────────

def build_all(
    trades_path: str | Path = TRADES_JSON,
    data_path:   str | Path = BACKTEST_DATA,
    verbose: bool = False,
) -> dict[str, dict]:
    """Run every registered strategy variant and return a results dict."""
    tp = Path(trades_path)
    dp = Path(data_path)
    results = {}

    print("Building strategy variants…")

    for spec in _ACTUAL_VARIANTS:
        name, desc = spec["name"], spec["description"]
        print(f"  [{name}]  {desc}")
        results[name] = _run_actual(name=name, description=desc, trades_path=tp, **spec["kwargs"])

    print(f"  [{_MR_VARIANT['name']}]  {_MR_VARIANT['description']}")
    results[_MR_VARIANT["name"]] = _run_mr(
        name=_MR_VARIANT["name"],
        description=_MR_VARIANT["description"],
        data_path=dp, verbose=verbose,
        **_MR_VARIANT["kwargs"],
    )

    for spec in _SIM_VARIANTS:
        name, desc = spec["name"], spec["description"]
        print(f"  [{name}]  {desc}")
        results[name] = _run_simulated(name=name, description=desc,
                                       data_path=dp, verbose=verbose, **spec["kwargs"])

    return results


# ── Comparison table ───────────────────────────────────────────────────────────

_COLS = [
    ("n",             "Trades",    lambda v: str(v)),
    ("win_rate",      "WR",        lambda v: f"{v:.1%}"),
    ("total_pnl",     "Total P&L", lambda v: f"{v/100_000*100:>+.1f}%"),
    ("avg_pnl",       "Avg/trade", lambda v: f"${v:>+,.0f}"),
    ("avg_win",       "Avg Win",   lambda v: f"${v:>+,.0f}"),
    ("avg_loss",      "Avg Loss",  lambda v: f"${v:>+,.0f}"),
    ("profit_factor", "PF",        lambda v: f"{v:.2f}"),
    ("sharpe",        "Sharpe",    lambda v: f"{v:.3f}"),
    ("max_dd_pct",    "MaxDD%",    lambda v: f"{v:.1f}%"),
    ("pnl_per_week",  "P&L/wk",   lambda v: f"{v/100_000*100:>+.2f}%"),
    ("worst_week",    "WorstWk",   lambda v: f"{v/100_000*100:>+.2f}%"),
    ("filtered_days", "Filtered",  lambda v: str(v)),
]


def print_comparison(results: dict[str, dict]):
    """Print a side-by-side comparison table for all strategy variants."""
    names = list(results.keys())
    col_w = 14

    print()
    print("=" * (20 + col_w * len(names)))
    print("STRATEGY COMPARISON")
    print("=" * (20 + col_w * len(names)))

    print(f"{'':20s}", end="")
    for n in names:
        print(f"{n:>{col_w}s}", end="")
    print()

    print(f"{'':20s}", end="")
    for n in names:
        desc  = results[n].get("description", "")
        words = desc.split()
        short = " ".join(words[:3]) + "…" if len(words) > 3 else desc
        print(f"{short:>{col_w}s}", end="")
    print()

    print("-" * (20 + col_w * len(names)))

    for key, label, fmt in _COLS:
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

    sim_names = [n for n in names if "exit_reasons" in results[n].get("summary", {})]
    if sim_names:
        print("\nExit breakdown (simulated variants):")
        all_exits: set = set()
        for n in sim_names:
            all_exits |= set(results[n]["summary"]["exit_reasons"].keys())
        for ex in sorted(all_exits):
            print(f"  {ex:20s}", end="")
            for n in sim_names:
                cnt   = results[n]["summary"]["exit_reasons"].get(ex, 0)
                total = results[n]["summary"]["n"]
                print(f"  {cnt:>3d}/{total:<3d}", end="")
            print()


# ── Single-strategy detail report ─────────────────────────────────────────────

def print_strategy_detail(result: dict, initial_capital: float = 100_000):
    """Print a full trade-by-trade report for one strategy variant."""
    name    = result["name"]
    desc    = result["description"]
    summary = result.get("summary", {})
    trades  = result.get("trades", pd.DataFrame())

    if trades.empty or not summary:
        print(f"\n[{name}]  No trades found.")
        return

    pnl_col = "pnl_usd" if "pnl_usd" in trades.columns else "cash_pnl"

    trades = trades.copy().reset_index(drop=True)
    trades["equity"] = initial_capital + trades[pnl_col].cumsum()

    final_equity = trades["equity"].iloc[-1]
    ret_pct      = (final_equity - initial_capital) / initial_capital * 100
    peak         = trades["equity"].cummax()
    max_dd_usd   = (trades["equity"] - peak).min()
    max_dd_pct   = (max_dd_usd / peak.max()) * 100

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

    is_actual = "cash_pnl" in trades.columns and "direction" in trades.columns

    print(f"  {'#':>3}  {'Date':<12} {'Time':<9}", end="")
    if is_actual:
        print(f"  {'Direction':<12} {'Contracts':>9} {'P&L':>10}  {'Equity':>10}  Result")
    else:
        print(f"  {'NDX':>6}  {'Spread':<14} {'Credit':>7} {'Exit':<14} {'P&L':>10}  {'Equity':>10}  Result")
    print("  " + "-" * (width - 2))

    for i, row in trades.iterrows():
        pnl        = row[pnl_col]
        eq         = row["equity"]
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

    print()
    print("  " + "-" * (width - 2))
    n      = summary.get("n", 0)
    wins   = summary.get("wins", 0)
    losses = summary.get("losses", 0)
    wr     = summary.get("win_rate", 0)
    total  = summary.get("total_pnl", 0)
    avg_w  = summary.get("avg_win", 0)
    avg_l  = summary.get("avg_loss", 0)
    pf     = summary.get("profit_factor", 0)
    sharpe = summary.get("sharpe", summary.get("sharpe_ratio", 0))
    max_dd = summary.get("max_dd_pct", summary.get("max_drawdown_pct", abs(max_dd_pct)))

    print(f"  {'trades':<26} {n}  ({wins}W / {losses}L)")
    print(f"  {'win_rate':<26} {wr:.1%}")
    print(f"  {'total_pnl':<26} ${total:>+,.0f}")
    print(f"  {'avg_win':<26} ${avg_w:>+,.0f}")
    print(f"  {'avg_loss':<26} ${avg_l:>+,.0f}")
    print(f"  {'profit_factor':<26} {pf:.2f}")
    print(f"  {'sharpe':<26} {sharpe:.3f}")
    print(f"  {'max_drawdown_pct':<26} {max_dd:.2f}%")

    exit_r = summary.get("exit_reasons", {})
    if exit_r:
        print(f"\n  Exit breakdown:")
        for ex, cnt in sorted(exit_r.items(), key=lambda x: -x[1]):
            print(f"    {ex:<22} {cnt}")

    print("=" * width)
