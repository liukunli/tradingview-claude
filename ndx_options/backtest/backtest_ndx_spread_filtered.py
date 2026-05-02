#!/usr/bin/env python3
"""
NDX Bear Put Spread — Improved Strategy with All Filters
Applies all rules from ndx-spread-analysis.md:
  - Bear Put only (positive EV direction)
  - 10:00–10:30 ET prime window only
  - Go/No-Go gate ≥ 3 AND Q-Score ≥ 45
  - Flat 30-min momentum required (±10pt hard filter)
  - NDX in top 20% of intraday range required
  - Non-trending or range < 180pt required
  - No EDT (no 1DTE entries after 14:45)
  - Scale-in: up to 2 adds (hard cap)
  - Consecutive loss tracking: reduce to 1 contract after 2 losses
  - Strict stop-loss: close immediately if NDX breaks short strike
Compares: Improved vs Unfiltered Bear Put (10:00–10:30, no gate)
"""

import json
import math
import warnings
from datetime import date, time, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm
from typing import Optional

warnings.filterwarnings("ignore")

DATA_PATH = Path(
    "/Users/kunliliu/.claude/skills/tradingview-claude/trading_logs/NDX_5min_2026.json"
)
OUT_PATH = Path(
    "/Users/kunliliu/.claude/skills/tradingview-claude/trading_logs/backtest_filtered.png"
)

# ─── Strategy constants ────────────────────────────────────────────────────────
ANNUAL_BAR_COUNT = 252 * 78
SPREAD_WIDTH = 50
NDX_MULT = 100
BASE_CONTRACTS = 3          # starting size
MIN_CONTRACTS  = 1          # reduced size after 2 loss days

PRIME_START = time(10, 0)
PRIME_END   = time(10, 30)

PROFIT_TARGET_PCT = 0.25    # exit at 25% of credit remaining (75% captured)
LOSS_STOP_MULT    = 2.0     # exit when spread = 2× initial credit
TIME_EXIT_ET      = time(14, 30)

# Improved filter thresholds
MAX_FLAT_MOM      = 10.0    # ±10pt max 30-min momentum (hard filter)
MIN_RANGE_PCT     = 0.80    # must be in top 20% of range
MAX_TRENDING_MULT = 2.5     # day_range > 2.5 × avg_bar = trending
MAX_DAY_RANGE     = 180.0   # hard cap for risk flag (still tradeable but flagged)
QSCORE_MIN        = 45      # minimum Q-score to enter
GATE_MIN          = 3       # minimum gate score to enter

# Scale-in parameters
SCALE_IN_DROP    = 30.0     # add contracts if NDX drops Xpt from entry
MAX_ADDS         = 2        # hard cap on scale-ins
SCALE_ADD_LOTS   = [2, 1]   # contracts to add on each scale-in

# Consecutive loss tracking
LOSS_STREAK_THRESH = 2      # reduce size after this many consecutive losses


# ─── Black-Scholes ─────────────────────────────────────────────────────────────

def bs_put(S: float, K: float, T: float, r: float = 0.045, sigma: float = 0.25) -> float:
    if T <= 1e-8:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def spread_value(S, short_K, long_K, bars_remaining, sigma):
    T = max(bars_remaining, 1) / ANNUAL_BAR_COUNT
    val = bs_put(S, short_K, T, sigma=sigma) - bs_put(S, long_K, T, sigma=sigma)
    return max(min(val, SPREAD_WIDTH), 0.0)


# ─── Data loading ──────────────────────────────────────────────────────────────

def load_rth_bars(path: Path) -> pd.DataFrame:
    with open(path) as f:
        raw = json.load(f)
    df = pd.DataFrame(raw["bars"])
    df["dt_utc"] = pd.to_datetime(df["datetime_utc"], utc=True)
    df["dt_et"]  = df["dt_utc"].dt.tz_convert("US/Eastern")
    df["date_et"] = df["dt_et"].dt.date
    df["time_et"] = df["dt_et"].dt.time
    df = df[(df["time_et"] >= time(9, 30)) & (df["time_et"] <= time(16, 0))]
    df = df.sort_values("dt_et").reset_index(drop=True)
    return df


# ─── Day metrics ───────────────────────────────────────────────────────────────

def day_metrics(day_bars: pd.DataFrame, up_to_idx: int) -> dict:
    partial = day_bars.iloc[: up_to_idx + 1]
    closes  = partial["close"].values
    log_ret = np.diff(np.log(closes)) if len(closes) > 1 else np.array([0.0])
    sigma   = max(math.sqrt(np.var(log_ret) * ANNUAL_BAR_COUNT), 0.12) if len(log_ret) > 2 else 0.25

    day_open    = day_bars.iloc[0]["open"]
    day_high    = partial["high"].max()
    day_low     = partial["low"].min()
    day_range   = day_high - day_low
    avg_bar_rng = (day_bars["high"] - day_bars["low"]).mean()
    trending    = (day_range > MAX_TRENDING_MULT * avg_bar_rng) if avg_bar_rng > 0 else False

    price     = day_bars.iloc[up_to_idx]["close"]
    range_pct = (price - day_low) / day_range if day_range > 0 else 0.5

    mom_idx = max(up_to_idx - 6, 0)
    mom_30  = price - day_bars.iloc[mom_idx]["close"]

    vwap = (
        (partial["close"] * partial["volume"]).sum() / partial["volume"].sum()
        if partial["volume"].sum() > 0 else price
    )

    return dict(
        day_open=day_open, day_high=day_high, day_low=day_low,
        day_range=day_range, avg_bar_rng=avg_bar_rng, trending=trending,
        price=price, range_pct=range_pct, mom_30=mom_30, vwap=vwap,
        sigma=sigma,
    )


# ─── Gate & Q-Score ────────────────────────────────────────────────────────────

def gate_score(m: dict, entry_time: time) -> tuple[int, dict]:
    details = {
        "prime_window":  PRIME_START <= entry_time <= PRIME_END,
        "flat_momentum": abs(m["mom_30"]) <= MAX_FLAT_MOM,
        "top_20_range":  m["range_pct"] >= MIN_RANGE_PCT,
        "small_or_calm": (m["day_range"] < MAX_DAY_RANGE) or (not m["trending"]),
        "dte0":          True,
    }
    return sum(details.values()), details


def q_score(m: dict, entry_time: time, otm_dist: float) -> int:
    s = 0
    if PRIME_START <= entry_time <= PRIME_END:
        s += 20
    elif entry_time < time(10, 0):
        s -= 10
    elif entry_time >= time(14, 45):
        s -= 25
    s += 15   # 0DTE
    s += 15   # Bear Put
    if otm_dist >= 100:
        s += 10
    elif otm_dist < 50:
        s -= 15
    if not m["trending"]:
        s += 10
    else:
        s -= 20
    s += 5    # ≤2 scale-ins planned
    return s


# ─── Hard filter check (improved) ──────────────────────────────────────────────

def hard_filters_pass(m: dict, entry_time: time, score: int,
                      details: dict, qs: int) -> tuple[bool, str]:
    """All conditions that cause an immediate skip, even at gate ≥ 3."""
    if score < GATE_MIN:
        return False, f"gate={score} < {GATE_MIN}"
    if not details["prime_window"]:
        return False, "outside prime window 10:00–10:30"
    if not details["flat_momentum"]:
        return False, f"momentum {m['mom_30']:.1f}pt not flat (threshold ±{MAX_FLAT_MOM}pt)"
    if not details["top_20_range"]:
        return False, f"NDX not in top 20% (range_pct={m['range_pct']:.1%})"
    if m["trending"] and m["day_range"] > MAX_DAY_RANGE:
        return False, f"trending + range {m['day_range']:.0f}pt > {MAX_DAY_RANGE}pt"
    if qs < QSCORE_MIN:
        return False, f"Q-score={qs} < {QSCORE_MIN}"
    if m["day_range"] > 250:
        return False, f"day range {m['day_range']:.0f}pt > 250pt hard cap"
    return True, ""


# ─── Scale-in simulation ───────────────────────────────────────────────────────

def simulate_with_scale_ins(
    post_bars: pd.DataFrame,
    entry_price: float,
    short_K: float,
    long_K: float,
    bars_remaining_at_entry: int,
    sigma: float,
    initial_contracts: int,
) -> dict:
    """
    Simulate a Bear Put spread with up to MAX_ADDS scale-in opportunities.
    Returns exit details and total P&L.
    """
    total_bars = bars_remaining_at_entry
    legs = [{"contracts": initial_contracts, "credit": 0.0, "short_K": short_K, "long_K": long_K}]

    # Initial credit
    legs[0]["credit"] = spread_value(entry_price, short_K, long_K, total_bars, sigma)

    adds_done = 0
    scale_triggers = [entry_price - (i + 1) * SCALE_IN_DROP for i in range(MAX_ADDS)]

    exit_reason = None
    exit_ndx = None
    exit_bar = None
    total_pnl = 0.0

    # Track scale-in triggers
    triggered = [False] * MAX_ADDS

    for i, (_, bar) in enumerate(post_bars.iterrows()):
        bars_here = total_bars - i - 1

        # Check scale-in opportunities first
        for k in range(MAX_ADDS):
            if not triggered[k] and adds_done < MAX_ADDS:
                if bar["low"] <= scale_triggers[k]:
                    # Add at new lower strikes
                    new_short_K = short_K - (k + 1) * SPREAD_WIDTH
                    new_long_K  = new_short_K - SPREAD_WIDTH
                    add_credit  = spread_value(bar["close"], new_short_K, new_long_K,
                                               max(bars_here, 1), sigma)
                    add_contracts = SCALE_ADD_LOTS[k] if k < len(SCALE_ADD_LOTS) else 1
                    legs.append({
                        "contracts": add_contracts,
                        "credit": add_credit,
                        "short_K": new_short_K,
                        "long_K": new_long_K,
                    })
                    triggered[k] = True
                    adds_done += 1

        # Hard stop: if NDX breaks the ORIGINAL short strike
        if bar["low"] < short_K:
            # Close all legs at intrinsic value
            for leg in legs:
                sv = max(min(leg["short_K"] - min(bar["low"], leg["short_K"] - 1),
                             SPREAD_WIDTH), 0.0)
                total_pnl += (leg["credit"] - sv) * NDX_MULT * leg["contracts"]
            exit_reason = "stop_loss"
            exit_ndx    = min(bar["low"], short_K - 1)
            exit_bar    = bar
            break

        # Check each leg for loss stop and profit target
        all_profit = True
        any_loss_stop = False

        for leg in legs:
            sv = spread_value(bar["close"], leg["short_K"], leg["long_K"],
                              max(bars_here, 1), sigma)
            # 2× credit loss stop
            if leg["credit"] > 0 and sv >= LOSS_STOP_MULT * leg["credit"]:
                any_loss_stop = True
            # Profit target check
            if not (leg["credit"] > 0 and sv <= PROFIT_TARGET_PCT * leg["credit"]):
                all_profit = False

        if any_loss_stop:
            for leg in legs:
                sv = spread_value(bar["close"], leg["short_K"], leg["long_K"],
                                  max(bars_here, 1), sigma)
                total_pnl += (leg["credit"] - sv) * NDX_MULT * leg["contracts"]
            exit_reason = "loss_stop"
            exit_ndx    = bar["close"]
            exit_bar    = bar
            break

        if all_profit:
            for leg in legs:
                sv = spread_value(bar["close"], leg["short_K"], leg["long_K"],
                                  max(bars_here, 1), sigma)
                total_pnl += (leg["credit"] - sv) * NDX_MULT * leg["contracts"]
            exit_reason = "profit_target"
            exit_ndx    = bar["close"]
            exit_bar    = bar
            break

        # Time exit: 14:30 ET
        if bar["time_et"] >= TIME_EXIT_ET:
            for leg in legs:
                sv = spread_value(bar["close"], leg["short_K"], leg["long_K"],
                                  max(bars_here, 1), sigma)
                total_pnl += (leg["credit"] - sv) * NDX_MULT * leg["contracts"]
            exit_reason = "time_exit"
            exit_ndx    = bar["close"]
            exit_bar    = bar
            break

    else:
        # Held to expiry
        eod_close = post_bars.iloc[-1]["close"] if not post_bars.empty else entry_price
        for leg in legs:
            sv = max(min(leg["short_K"] - eod_close, SPREAD_WIDTH), 0.0)
            total_pnl += (leg["credit"] - sv) * NDX_MULT * leg["contracts"]
        exit_reason = "expiry"
        exit_ndx    = eod_close
        exit_bar    = post_bars.iloc[-1] if not post_bars.empty else None

    total_credit = sum(l["credit"] * NDX_MULT * l["contracts"] for l in legs)
    total_contracts = sum(l["contracts"] for l in legs)

    return dict(
        pnl=total_pnl,
        exit_reason=exit_reason,
        exit_ndx=exit_ndx,
        exit_dt=exit_bar["dt_et"] if exit_bar is not None else None,
        n_scale_ins=adds_done,
        legs=legs,
        total_credit=total_credit,
        total_contracts=total_contracts,
    )


# ─── Day simulation ────────────────────────────────────────────────────────────

def simulate_day(day_bars: pd.DataFrame, use_filters: bool,
                 loss_streak: int = 0) -> Optional[dict]:
    prime = day_bars[
        (day_bars["time_et"] >= PRIME_START) & (day_bars["time_et"] <= PRIME_END)
    ]
    if prime.empty:
        return None

    entry_iloc   = day_bars.index.get_loc(prime.index[0])
    m            = day_metrics(day_bars, entry_iloc)
    entry_time   = day_bars.iloc[entry_iloc]["time_et"]
    entry_price  = m["price"]
    entry_dt     = day_bars.iloc[entry_iloc]["dt_et"]

    score, details = gate_score(m, entry_time)

    short_K  = math.floor((entry_price - 100) / 50) * 50
    long_K   = short_K - SPREAD_WIDTH
    otm_dist = entry_price - short_K
    qs       = q_score(m, entry_time, otm_dist)

    base = dict(
        date=day_bars.iloc[0]["date_et"],
        entry_dt=entry_dt,
        entry_price=entry_price,
        gate_score=score,
        gate_details=details,
        q_score=qs,
        metrics=m,
        short_K=short_K,
        long_K=long_K,
        otm_dist=otm_dist,
    )

    if use_filters:
        ok, reason = hard_filters_pass(m, entry_time, score, details, qs)
        if not ok:
            return {**base, "result": "skip", "skip_reason": reason}
        # Consecutive loss adjustment
        n_contracts = MIN_CONTRACTS if loss_streak >= LOSS_STREAK_THRESH else BASE_CONTRACTS
    else:
        # Unfiltered: only require gate ≥ 3 and NDX in top 20% for Bear Put
        if score < GATE_MIN or not details["top_20_range"]:
            return {**base, "result": "skip",
                    "skip_reason": f"gate={score} or not top20%"}
        n_contracts = BASE_CONTRACTS

    if not (100 <= otm_dist <= 200):
        return {**base, "result": "skip",
                "skip_reason": f"OTM dist {otm_dist:.0f}pt out of range"}

    sigma = m["sigma"]
    bars_remaining = len(day_bars) - entry_iloc - 1
    post = day_bars.iloc[entry_iloc + 1:].copy()

    if use_filters:
        result = simulate_with_scale_ins(
            post, entry_price, short_K, long_K, bars_remaining, sigma, n_contracts
        )
    else:
        # Unfiltered: single-leg, no scale-ins, same exit rules
        credit = spread_value(entry_price, short_K, long_K, bars_remaining, sigma)
        pnl_pts = 0.0
        exit_reason = exit_ndx = exit_dt = None

        for i, (_, bar) in enumerate(post.iterrows()):
            bh = bars_remaining - i - 1
            if bar["low"] < short_K:
                sv = spread_value(min(bar["low"], short_K - 1), short_K, long_K,
                                  max(bh, 1), sigma)
                pnl_pts = credit - sv
                exit_reason, exit_ndx, exit_dt = "stop_loss", min(bar["low"], short_K - 1), bar["dt_et"]
                break
            sv_c = spread_value(bar["close"], short_K, long_K, max(bh, 1), sigma)
            if credit > 0 and sv_c >= LOSS_STOP_MULT * credit:
                pnl_pts = credit - sv_c
                exit_reason, exit_ndx, exit_dt = "loss_stop", bar["close"], bar["dt_et"]
                break
            if credit > 0 and sv_c <= PROFIT_TARGET_PCT * credit:
                pnl_pts = credit - sv_c
                exit_reason, exit_ndx, exit_dt = "profit_target", bar["close"], bar["dt_et"]
                break
            if bar["time_et"] >= TIME_EXIT_ET:
                pnl_pts = credit - sv_c
                exit_reason, exit_ndx, exit_dt = "time_exit", bar["close"], bar["dt_et"]
                break
        else:
            eod = day_bars.iloc[-1]["close"]
            pnl_pts = credit - max(min(short_K - eod, SPREAD_WIDTH), 0.0)
            exit_reason, exit_ndx, exit_dt = "expiry", eod, day_bars.iloc[-1]["dt_et"]

        result = dict(
            pnl=pnl_pts * NDX_MULT * n_contracts,
            exit_reason=exit_reason, exit_ndx=exit_ndx, exit_dt=exit_dt,
            n_scale_ins=0, total_credit=credit * NDX_MULT * n_contracts,
            total_contracts=n_contracts,
        )

    return {
        **base,
        "result":           "trade",
        "outcome":          "win" if result["pnl"] > 0 else "loss",
        "exit_reason":      result["exit_reason"],
        "exit_ndx":         result["exit_ndx"],
        "exit_dt":          result["exit_dt"],
        "pnl_dollar":       result["pnl"],
        "n_scale_ins":      result["n_scale_ins"],
        "total_credit":     result["total_credit"],
        "total_contracts":  result["total_contracts"],
        "n_contracts_base": n_contracts,
    }


# ─── Full backtest ─────────────────────────────────────────────────────────────

def run_backtest(bars: pd.DataFrame, use_filters: bool) -> list[dict]:
    results = []
    loss_streak = 0
    for d in sorted(bars["date_et"].unique()):
        day_bars = bars[bars["date_et"] == d].copy().reset_index(drop=True)
        if len(day_bars) < 12:
            continue
        r = simulate_day(day_bars, use_filters, loss_streak=loss_streak)
        if r:
            results.append(r)
            if r.get("result") == "trade":
                if r["pnl_dollar"] <= 0:
                    loss_streak += 1
                else:
                    loss_streak = 0
    return results


def make_trade_df(results: list[dict]) -> pd.DataFrame:
    trades = [r for r in results if r.get("result") == "trade"]
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["cumpnl"] = df["pnl_dollar"].cumsum()
    df["win"] = df["pnl_dollar"] > 0
    return df


def stats_summary(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    n = len(df)
    n_win = df["win"].sum()
    wr = n_win / n
    avg_win  = df[df["win"]]["pnl_dollar"].mean() if n_win > 0 else 0
    avg_loss = df[~df["win"]]["pnl_dollar"].mean() if (n - n_win) > 0 else 0
    return dict(n=n, n_win=int(n_win), wr=wr,
                avg=df["pnl_dollar"].mean(), total=df["pnl_dollar"].sum(),
                avg_win=avg_win, avg_loss=avg_loss,
                ev=wr * avg_win + (1 - wr) * avg_loss)


# ─── Plotting ──────────────────────────────────────────────────────────────────

def plot_results(all_bars, results_filtered, results_raw):
    df_f = make_trade_df(results_filtered)
    df_r = make_trade_df(results_raw)
    sf   = stats_summary(df_f)
    sr   = stats_summary(df_r)
    skips = [r for r in results_filtered if r.get("result") == "skip"]

    fig = plt.figure(figsize=(24, 22))
    fig.suptitle(
        "NDX Bear Put — Improved (All Filters) vs Unfiltered  ·  Jan–Apr 2026",
        fontsize=18, fontweight="bold", y=0.995,
    )
    gs = gridspec.GridSpec(4, 3, figure=fig, hspace=0.55, wspace=0.38)

    C_WIN  = "#27ae60"
    C_LOSS = "#e74c3c"
    C_SKIP = "#95a5a6"
    C_FILT = "#2980b9"
    C_RAW  = "#8e44ad"

    fmt_k = lambda x, _: f"${x/1000:.0f}K"

    # ── 1. Cumulative P&L ────────────────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :2])
    if not df_f.empty:
        ax1.plot(df_f["date"], df_f["cumpnl"], color=C_FILT, lw=2.5,
                 label=f"Improved (all filters)  WR={sf['wr']:.0%}  Total=${sf['total']:,.0f}")
        ax1.fill_between(df_f["date"], 0, df_f["cumpnl"],
                         where=df_f["cumpnl"] >= 0, alpha=0.15, color=C_FILT)
        ax1.fill_between(df_f["date"], 0, df_f["cumpnl"],
                         where=df_f["cumpnl"] < 0, alpha=0.20, color=C_LOSS)
    if not df_r.empty:
        ax1.plot(df_r["date"], df_r["cumpnl"], color=C_RAW, lw=2, linestyle="--", alpha=0.8,
                 label=f"Unfiltered Bear Put  WR={sr['wr']:.0%}  Total=${sr['total']:,.0f}")
    ax1.axhline(0, color="black", lw=0.8, ls="--", alpha=0.5)
    ax1.set_title("Cumulative P&L — Improved Filters vs Unfiltered", fontweight="bold")
    ax1.set_ylabel("P&L ($)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(fmt_k))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax1.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax1.legend(fontsize=9.5)
    ax1.grid(True, alpha=0.3)

    # ── 2. Summary table ─────────────────────────────────────────────────────
    ax_tbl = fig.add_subplot(gs[0, 2])
    ax_tbl.axis("off")
    rows = [
        ["Metric", "Improved", "Unfiltered"],
        ["Trades",      str(sf.get("n", 0)),           str(sr.get("n", 0))],
        ["Win Rate",    f"{sf.get('wr', 0):.0%}",       f"{sr.get('wr', 0):.0%}"],
        ["Avg P&L",     f"${sf.get('avg', 0):,.0f}",    f"${sr.get('avg', 0):,.0f}"],
        ["Avg Win",     f"${sf.get('avg_win', 0):,.0f}", f"${sr.get('avg_win', 0):,.0f}"],
        ["Avg Loss",    f"${sf.get('avg_loss', 0):,.0f}", f"${sr.get('avg_loss', 0):,.0f}"],
        ["EV/trade",    f"${sf.get('ev', 0):,.0f}",      f"${sr.get('ev', 0):,.0f}"],
        ["Total P&L",   f"${sf.get('total', 0):,.0f}",   f"${sr.get('total', 0):,.0f}"],
        ["Skipped",     str(len(skips)), "—"],
    ]
    tbl = ax_tbl.table(rows[1:], colLabels=rows[0], loc="center", cellLoc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9.5)
    tbl.scale(1.15, 1.7)
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#2c3e50")
            cell.set_text_props(color="white", fontweight="bold")
        elif c == 1:
            try:
                num = float(rows[r][1].replace("$", "").replace(",", "").replace("%", ""))
                cell.set_facecolor("#d5f5e3" if num > 0 else "#fadbd8" if num < 0 else "#f8f9fa")
            except Exception:
                pass
    ax_tbl.set_title("Strategy Comparison", fontweight="bold", pad=10)

    # ── 3. Daily P&L — Improved ──────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, :2])
    if not df_f.empty:
        colors3 = [C_WIN if w else C_LOSS for w in df_f["win"]]
        ax3.bar(df_f["date"], df_f["pnl_dollar"], color=colors3, alpha=0.85, width=0.8)
        # Mark scale-in trades
        scaled = df_f[df_f["n_scale_ins"] > 0]
        for _, row in scaled.iterrows():
            ax3.annotate(f"+{int(row['n_scale_ins'])}",
                         (row["date"], row["pnl_dollar"]),
                         ha="center",
                         va="bottom" if row["pnl_dollar"] > 0 else "top",
                         fontsize=7.5, color="#2c3e50")
        stops = df_f[df_f["exit_reason"] == "stop_loss"]
        for _, row in stops.iterrows():
            ax3.annotate("✕", (row["date"], row["pnl_dollar"]),
                         ha="center", va="top" if row["pnl_dollar"] < 0 else "bottom",
                         fontsize=10, color="#c0392b")
    ax3.axhline(0, color="black", lw=0.8, ls="--")
    ax3.set_title("Daily P&L — Improved Strategy  (✕=stop-loss  +N=scale-ins)", fontweight="bold")
    ax3.set_ylabel("P&L ($)")
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(fmt_k))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax3.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2))
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax3.grid(True, alpha=0.3, axis="y")
    ax3.legend(handles=[
        mpatches.Patch(color=C_WIN,  label=f"Win ({sf.get('n_win',0)})"),
        mpatches.Patch(color=C_LOSS, label=f"Loss ({sf.get('n',0)-sf.get('n_win',0)})"),
    ])

    # ── 4. Exit reason pie ───────────────────────────────────────────────────
    ax4 = fig.add_subplot(gs[1, 2])
    if not df_f.empty and "exit_reason" in df_f.columns:
        oc = df_f["exit_reason"].value_counts()
        labels_map = {
            "expiry": "Expiry Win",
            "profit_target": "Profit Target",
            "time_exit": "Time Exit 14:30",
            "stop_loss": "NDX Stop-Loss",
            "loss_stop": "2× Credit Stop",
        }
        pie_labels = [labels_map.get(k, k) for k in oc.index]
        def ec(k):
            return C_WIN if k in ("expiry", "profit_target", "time_exit") else C_LOSS
        ax4.pie(oc.values, labels=pie_labels,
                colors=[ec(k) for k in oc.index],
                autopct="%1.0f%%", startangle=90,
                textprops={"fontsize": 8})
    ax4.set_title("Exit Reason\n(Improved)", fontweight="bold")

    # ── 5. Skip reason analysis ──────────────────────────────────────────────
    ax5 = fig.add_subplot(gs[2, 0])
    if skips:
        reasons = [s.get("skip_reason", "unknown").split("(")[0].strip()
                   for s in skips]
        from collections import Counter
        rc = Counter(reasons)
        # Group similar reasons
        grouped = {}
        for k, v in rc.items():
            if "momentum" in k:            gk = "Momentum not flat"
            elif "top20" in k or "20%" in k: gk = "Not top 20% of range"
            elif "gate" in k:              gk = "Gate score < 3"
            elif "Q-score" in k:           gk = "Q-score < 45"
            elif "window" in k:            gk = "Outside prime window"
            elif "trending" in k:          gk = "Trending + range > 180pt"
            elif "OTM" in k:               gk = "OTM out of range"
            else:                          gk = k[:30]
            grouped[gk] = grouped.get(gk, 0) + v
        keys = sorted(grouped, key=grouped.get, reverse=True)
        vals = [grouped[k] for k in keys]
        bar_colors5 = plt.cm.Set2(np.linspace(0, 0.8, len(keys)))
        ax5.barh(range(len(keys)), vals, color=bar_colors5, alpha=0.85)
        ax5.set_yticks(range(len(keys)))
        ax5.set_yticklabels(keys, fontsize=8.5)
        for i, v in enumerate(vals):
            ax5.text(v + 0.2, i, str(v), va="center", fontsize=8.5)
        ax5.set_title(f"Skip Reasons\n({len(skips)} days filtered out)", fontweight="bold")
        ax5.set_xlabel("Days Skipped")
        ax5.grid(True, alpha=0.3, axis="x")

    # ── 6. Gate score distribution ────────────────────────────────────────────
    ax6 = fig.add_subplot(gs[2, 1])
    all_scores = [r.get("gate_score", 0) for r in results_filtered]
    qscores    = [r.get("q_score", 0) for r in results_filtered if r.get("result") == "trade"]
    sv, sc = np.unique(all_scores, return_counts=True)
    bc = ["#e74c3c" if s < GATE_MIN else "#f39c12" if s == GATE_MIN else "#27ae60" for s in sv]
    ax6.bar(sv, sc, color=bc, alpha=0.85, edgecolor="white")
    for v, c in zip(sv, sc):
        ax6.text(v, c + 0.2, str(c), ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax6.set_title(f"Gate Score Distribution\n(<{GATE_MIN}=AVOID  {GATE_MIN}=WATCH  >{GATE_MIN}=PROCEED)",
                  fontweight="bold")
    ax6.set_xlabel("Gate Score")
    ax6.set_ylabel("Days")
    ax6.set_xticks(range(6))
    ax6.grid(True, alpha=0.3, axis="y")
    if qscores:
        ax6b = ax6.twinx()
        ax6b.hist(qscores, bins=10, color=C_FILT, alpha=0.35, label="Q-Score (trades)")
        ax6b.axvline(QSCORE_MIN, color="navy", lw=1.5, ls="--",
                     label=f"Q≥{QSCORE_MIN} threshold")
        ax6b.set_ylabel("Q-Score freq")
        ax6b.legend(fontsize=8, loc="upper left")

    # ── 7. Scale-in P&L analysis ─────────────────────────────────────────────
    ax7 = fig.add_subplot(gs[2, 2])
    if not df_f.empty and "n_scale_ins" in df_f.columns:
        sg = df_f.groupby("n_scale_ins").agg(
            count=("pnl_dollar", "count"),
            mean=("pnl_dollar", "mean"),
            wr=("win", "mean"),
        ).reset_index()
        bar_col7 = [C_WIN if m > 0 else C_LOSS for m in sg["mean"]]
        ax7.bar(sg["n_scale_ins"], sg["mean"], color=bar_col7, alpha=0.85, edgecolor="white")
        for _, row in sg.iterrows():
            ax7.text(row["n_scale_ins"],
                     row["mean"] + (200 if row["mean"] >= 0 else -200),
                     f"N={int(row['count'])}\n{row['wr']:.0%}",
                     ha="center",
                     va="bottom" if row["mean"] >= 0 else "top",
                     fontsize=8.5)
        ax7.axhline(0, color="black", lw=0.8, ls="--")
        ax7.set_title("Avg P&L by # Scale-Ins\n(Improved strategy, cap=2)", fontweight="bold")
        ax7.set_xlabel("Scale-ins added")
        ax7.set_ylabel("Avg P&L ($)")
        ax7.yaxis.set_major_formatter(plt.FuncFormatter(fmt_k))
        ax7.grid(True, alpha=0.3, axis="y")

    # ── 8. NDX price with trade entries ─────────────────────────────────────
    ax8 = fig.add_subplot(gs[3, :])
    daily_close = all_bars.groupby("date_et").last().reset_index()
    daily_close["date"] = pd.to_datetime(daily_close["date_et"])
    ax8.plot(daily_close["date"], daily_close["close"], color="#2c3e50", lw=1.2, alpha=0.8,
             label="NDX close")

    if not df_f.empty:
        wins_f   = df_f[df_f["win"]]
        losses_f = df_f[~df_f["win"]]
        if not wins_f.empty:
            ax8.scatter(wins_f["date"], wins_f["entry_price"],
                        marker="^", color=C_WIN, s=65, zorder=5, label="Entry (Win)")
        if not losses_f.empty:
            ax8.scatter(losses_f["date"], losses_f["entry_price"],
                        marker="v", color=C_LOSS, s=65, zorder=5, label="Entry (Loss)")
        for _, row in df_f.iterrows():
            clr = C_WIN if row["win"] else C_LOSS
            ax8.hlines(row["short_K"],
                       row["date"] - pd.Timedelta(days=0.3),
                       row["date"] + pd.Timedelta(days=0.3),
                       colors=clr, lw=1.8, alpha=0.65)

    if skips:
        skip_dates  = pd.to_datetime([s["date"] for s in skips])
        skip_prices = [s["metrics"]["price"] for s in skips]
        ax8.scatter(skip_dates, skip_prices, marker="x", color=C_SKIP,
                    s=35, zorder=4, alpha=0.7, label="Skipped (filtered)")

    ax8.set_title(
        "NDX Price + Trade Entries  (▲ win  ▼ loss  — short strike  × skipped by filter)",
        fontweight="bold",
    )
    ax8.set_ylabel("NDX Level")
    ax8.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax8.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=1))
    plt.setp(ax8.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax8.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax8.legend(fontsize=9, ncol=4)
    ax8.grid(True, alpha=0.25)

    plt.savefig(OUT_PATH, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"\nPlot saved → {OUT_PATH}")
    plt.close(fig)


# ─── Main ──────────────────────────────────────────────────────────────────────

def print_summary(label: str, results: list, bars: pd.DataFrame):
    df = make_trade_df(results)
    st = stats_summary(df)
    skips = [r for r in results if r.get("result") == "skip"]
    print(f"\n{'─'*55}")
    print(f"  {label}")
    print(f"{'─'*55}")
    print(f"  Trades:   {st.get('n',0):3d}  |  Wins: {st.get('n_win',0):3d}  |  WR: {st.get('wr',0):.1%}")
    print(f"  Avg P&L:  ${st.get('avg',0):>8,.0f}  |  EV:   ${st.get('ev',0):>8,.0f}")
    print(f"  Avg Win:  ${st.get('avg_win',0):>8,.0f}  |  Avg Loss: ${st.get('avg_loss',0):>8,.0f}")
    print(f"  Total:    ${st.get('total',0):>10,.0f}")
    print(f"  Skipped:  {len(skips)}")
    if not df.empty and "n_scale_ins" in df.columns:
        avg_adds = df["n_scale_ins"].mean()
        print(f"  Avg scale-ins: {avg_adds:.2f}")
    if not df.empty and "exit_reason" in df.columns:
        print(f"  Exits: {df['exit_reason'].value_counts().to_dict()}")


if __name__ == "__main__":
    print("Loading NDX 5-min RTH data...")
    bars = load_rth_bars(DATA_PATH)
    n_days = bars["date_et"].nunique()
    print(f"  {len(bars)} bars  |  {n_days} trading days  |  "
          f"{bars['date_et'].min()} → {bars['date_et'].max()}")

    print("\nRunning IMPROVED backtest (all filters from ndx-spread-analysis.md)...")
    results_filtered = run_backtest(bars, use_filters=True)
    print_summary("IMPROVED — All Filters Applied", results_filtered, bars)

    print("\nRunning UNFILTERED backtest (Bear Put at 10:00–10:30, gate≥3, no extra filters)...")
    results_raw = run_backtest(bars, use_filters=False)
    print_summary("UNFILTERED — Bear Put, 10:00–10:30 only", results_raw, bars)

    print("\nGenerating comparison plot...")
    plot_results(bars, results_filtered, results_raw)
