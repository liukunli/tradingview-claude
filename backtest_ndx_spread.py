#!/usr/bin/env python3
"""
NDX Bear Put Spread Backtest
Rules from ndx-spread-analysis.md, applied to NDX_5min_2026.json
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
    "/Users/kunliliu/.claude/skills/tradingview-claude/trading_logs/backtest_results.png"
)

# ─── Strategy constants ────────────────────────────────────────────────────────
N_CONTRACTS = 3          # initial contracts per trade
SPREAD_WIDTH = 50        # $50 wide spread
NDX_MULT = 100           # NDX index × 100 = dollar value
ANNUAL_BAR_COUNT = 252 * 78  # 5-min bars per year during RTH

PRIME_START       = time(10, 0)
PRIME_END         = time(10, 30)
PROFIT_TARGET_PCT = 0.25   # exit when spread decays to 25% of credit (75% profit captured)
LOSS_STOP_MULT    = 2.0    # exit when spread reaches 2× initial credit
TIME_EXIT_ET      = time(14, 30)  # close at 14:30 ET if no earlier exit

# ─── Black-Scholes ─────────────────────────────────────────────────────────────

def bs_put(S: float, K: float, T: float, r: float = 0.045, sigma: float = 0.25) -> float:
    if T <= 1e-8:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

def spread_credit_pts(S, short_K, long_K, T_bars_remaining, sigma):
    """Credit received (index pts) for selling the put spread."""
    T = T_bars_remaining / ANNUAL_BAR_COUNT
    credit = bs_put(S, short_K, T, sigma=sigma) - bs_put(S, long_K, T, sigma=sigma)
    return max(min(credit, 20.0), 0.0)  # cap 0–20 pts

def spread_value_pts(S, short_K, long_K, T_bars_remaining, sigma):
    """Current value (cost to close) of the short spread."""
    T = T_bars_remaining / ANNUAL_BAR_COUNT
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
    df = df.sort_values("dt_et").reset_index(drop=True)
    # RTH: 9:30–16:00 ET
    df = df[(df["time_et"] >= time(9, 30)) & (df["time_et"] <= time(16, 0))].copy()
    df.reset_index(drop=True, inplace=True)
    return df

# ─── Per-day metrics ───────────────────────────────────────────────────────────

def day_metrics(day_bars: pd.DataFrame, up_to_idx: int) -> dict:
    partial = day_bars.iloc[: up_to_idx + 1]
    closes  = partial["close"].values
    log_ret = np.diff(np.log(closes)) if len(closes) > 1 else np.array([0.0])
    sigma   = max(math.sqrt(np.var(log_ret) * ANNUAL_BAR_COUNT), 0.12) if len(log_ret) > 2 else 0.25

    day_open   = day_bars.iloc[0]["open"]
    day_high   = partial["high"].max()
    day_low    = partial["low"].min()
    day_range  = day_high - day_low
    avg_bar_rng = (day_bars["high"] - day_bars["low"]).mean()
    trending   = (day_range > 2.5 * avg_bar_rng) if avg_bar_rng > 0 else False

    price = day_bars.iloc[up_to_idx]["close"]
    range_pct = (price - day_low) / day_range if day_range > 0 else 0.5

    # 30-min momentum: current close minus close 6 bars ago
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

# ─── Gate evaluation ───────────────────────────────────────────────────────────

def gate_score(m: dict, entry_time: time) -> tuple[int, dict]:
    # Gate condition 4: "Is day_range < 180pt OR not trending?" (OR, not AND)
    details = {
        "prime_window":   PRIME_START <= entry_time <= PRIME_END,
        "flat_momentum":  abs(m["mom_30"]) <= 10,
        "top_20_range":   m["range_pct"] >= 0.80,
        "small_or_calm":  (m["day_range"] < 180) or (not m["trending"]),
        "dte0":           True,
    }
    score = sum(details.values())
    return score, details

def q_score(m: dict, entry_time: time, otm_dist: float) -> int:
    s = 0
    if PRIME_START <= entry_time <= PRIME_END:
        s += 20
    elif entry_time < time(10, 0):
        s -= 10
    elif entry_time >= time(14, 45):
        s -= 25
    s += 15          # 0DTE
    s += 15          # Bear Put direction
    if otm_dist >= 100:
        s += 10
    elif otm_dist < 50:
        s -= 15
    if not m["trending"]:
        s += 10
    else:
        s -= 20
    s += 5           # ≤2 scale-ins planned
    return s

# ─── Day simulation ────────────────────────────────────────────────────────────

def simulate_day(day_bars: pd.DataFrame, use_gate: bool) -> Optional[dict]:
    # Find first bar in prime window
    prime = day_bars[
        (day_bars["time_et"] >= PRIME_START) & (day_bars["time_et"] <= PRIME_END)
    ]
    if prime.empty:
        return None

    entry_iloc = day_bars.index.get_loc(prime.index[0])
    m = day_metrics(day_bars, entry_iloc)
    entry_time  = day_bars.iloc[entry_iloc]["time_et"]
    entry_price = m["price"]
    entry_dt    = day_bars.iloc[entry_iloc]["dt_et"]

    score, details = gate_score(m, entry_time)

    base = dict(
        date=day_bars.iloc[0]["date_et"],
        gate_score=score,
        gate_details=details,
        metrics=m,
        entry_dt=entry_dt,
        entry_price=entry_price,
    )

    if use_gate:
        # Hard skip: gate score too low, range too explosive, or NDX not at top (Bear Put prerequisite)
        hard_skip = (
            score < 3
            or m["day_range"] > 250
            or not details["top_20_range"]   # Bear Put requires NDX in top 20% of range
        )
        if hard_skip:
            return {**base, "result": "skip",
                    "skip_reason": f"gate={score}, range={m['day_range']:.0f}pt, top20={details['top_20_range']}"}

    # ── Strike selection ────────────────────────────────────────────────────
    short_K = math.floor((entry_price - 100) / 50) * 50
    long_K  = short_K - SPREAD_WIDTH
    otm_dist = entry_price - short_K  # should be 100–150

    if use_gate and not (100 <= otm_dist <= 200):
        return {**base, "result": "skip", "skip_reason": f"OTM dist {otm_dist:.0f}pt out of 100-200 range"}

    # Bars remaining after entry through 16:00 close
    post = day_bars.iloc[entry_iloc + 1:].copy()
    total_bars_in_day = len(day_bars)
    bars_remaining_at_entry = total_bars_in_day - entry_iloc - 1

    sigma = m["sigma"]
    credit_pts = spread_credit_pts(entry_price, short_K, long_K, bars_remaining_at_entry, sigma)
    credit_dollar = credit_pts * NDX_MULT * N_CONTRACTS
    qs = q_score(m, entry_time, otm_dist)

    # ── Simulate position — check all exits on each bar ────────────────────
    # Exit priority: 1) NDX stop-loss  2) 2× credit loss-stop  3) profit target  4) 14:30 time-exit
    exit_reason = None
    exit_bar    = None
    exit_ndx    = None
    pnl_pts     = None

    for i, (_, bar) in enumerate(post.iterrows()):
        bars_here = bars_remaining_at_entry - i - 1

        # 1. Hard stop: NDX bar low crosses short strike
        if bar["low"] < short_K:
            ndx_x  = min(bar["low"], short_K - 1)
            sv     = spread_value_pts(ndx_x, short_K, long_K, max(bars_here, 1), sigma)
            pnl_pts = credit_pts - sv
            exit_reason = "stop_loss"
            exit_bar    = bar
            exit_ndx    = ndx_x
            break

        sv_close = spread_value_pts(bar["close"], short_K, long_K, max(bars_here, 1), sigma)

        # 2. Loss stop: spread value ≥ 2× initial credit
        if sv_close >= LOSS_STOP_MULT * credit_pts and credit_pts > 0:
            pnl_pts     = credit_pts - sv_close
            exit_reason = "loss_stop"
            exit_bar    = bar
            exit_ndx    = bar["close"]
            break

        # 3. Profit target: spread decayed to ≤ 25% of credit
        if credit_pts > 0 and sv_close <= PROFIT_TARGET_PCT * credit_pts:
            pnl_pts     = credit_pts - sv_close
            exit_reason = "profit_target"
            exit_bar    = bar
            exit_ndx    = bar["close"]
            break

        # 4. Time exit: close at 14:30 ET
        if bar["time_et"] >= TIME_EXIT_ET:
            pnl_pts     = credit_pts - sv_close
            exit_reason = "time_exit"
            exit_bar    = bar
            exit_ndx    = bar["close"]
            break

    else:
        # Held to expiry (16:00 ET) — value is intrinsic only
        eod_close = day_bars.iloc[-1]["close"]
        sv_eod    = max(min(short_K - eod_close, SPREAD_WIDTH), 0.0)
        pnl_pts   = credit_pts - sv_eod
        exit_reason = "expiry"
        exit_bar    = day_bars.iloc[-1]
        exit_ndx    = eod_close

    pnl_dollar = pnl_pts * NDX_MULT * N_CONTRACTS

    # Classify outcome for reporting
    if exit_reason in ("profit_target", "time_exit", "expiry") and pnl_pts > 0:
        outcome = exit_reason if exit_reason != "expiry" else "win"
    elif exit_reason == "stop_loss":
        outcome = "stop_loss"
    elif exit_reason == "loss_stop":
        outcome = "loss_stop"
    else:
        outcome = "loss"

    return {
        **base,
        "result":         "trade",
        "outcome":        outcome,
        "exit_reason":    exit_reason,
        "short_K":        short_K,
        "long_K":         long_K,
        "otm_dist":       otm_dist,
        "credit_pts":     credit_pts,
        "credit_dollar":  credit_dollar,
        "pnl_pts":        pnl_pts,
        "pnl_dollar":     pnl_dollar,
        "exit_ndx":       exit_ndx,
        "exit_dt":        exit_bar["dt_et"] if exit_bar is not None else None,
        "sigma":          sigma,
        "q_score":        qs,
    }

# ─── Full backtest ─────────────────────────────────────────────────────────────

def run_backtest(bars: pd.DataFrame, use_gate: bool) -> list[dict]:
    results = []
    for d in sorted(bars["date_et"].unique()):
        day_bars = bars[bars["date_et"] == d].copy().reset_index(drop=True)
        if len(day_bars) < 12:
            continue
        r = simulate_day(day_bars, use_gate)
        if r:
            results.append(r)
    return results

# ─── Plotting ──────────────────────────────────────────────────────────────────

def make_trade_df(results: list[dict]) -> pd.DataFrame:
    trades = [r for r in results if r.get("result") == "trade"]
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame(trades)
    df["date"] = pd.to_datetime(df["date"])
    df["entry_dt"] = pd.to_datetime(df["entry_dt"])
    df = df.sort_values("date").reset_index(drop=True)
    df["cumpnl"] = df["pnl_dollar"].cumsum()
    df["win"] = df["pnl_dollar"] > 0
    return df

def stats_summary(df: pd.DataFrame) -> dict:
    n = len(df)
    if n == 0:
        return {}
    n_win = df["win"].sum()
    wr = n_win / n
    avg = df["pnl_dollar"].mean()
    total = df["pnl_dollar"].sum()
    avg_win  = df[df["win"]]["pnl_dollar"].mean() if n_win > 0 else 0
    avg_loss = df[~df["win"]]["pnl_dollar"].mean() if (n - n_win) > 0 else 0
    ev = wr * avg_win + (1 - wr) * avg_loss
    return dict(n=n, n_win=int(n_win), wr=wr, avg=avg, total=total,
                avg_win=avg_win, avg_loss=avg_loss, ev=ev)

def plot_backtest(
    all_bars: pd.DataFrame,
    results_gate: list[dict],
    results_raw: list[dict],
):
    df_gate = make_trade_df(results_gate)
    df_raw  = make_trade_df(results_raw)
    st_gate = stats_summary(df_gate)
    st_raw  = stats_summary(df_raw)

    skips = [r for r in results_gate if r.get("result") == "skip"]

    fig = plt.figure(figsize=(22, 20))
    fig.suptitle(
        "NDX Bear Put Spread Backtest  ·  Jan–Apr 2026",
        fontsize=18, fontweight="bold", y=0.99,
    )
    gs = gridspec.GridSpec(4, 3, figure=fig, hspace=0.55, wspace=0.38)

    C_WIN  = "#27ae60"
    C_LOSS = "#e74c3c"
    C_SKIP = "#95a5a6"
    C_GATE = "#2980b9"
    C_RAW  = "#8e44ad"

    fmt_dollar = lambda x, _: f"${x:,.0f}"
    fmt_k      = lambda x, _: f"${x/1000:.0f}K"

    # ── 1. Cumulative P&L comparison ─────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :2])
    if not df_gate.empty:
        ax1.plot(df_gate["date"], df_gate["cumpnl"], color=C_GATE, lw=2.5,
                 label=f"Refined (gate≥3)  WR={st_gate['wr']:.0%}  Total=${st_gate['total']:,.0f}")
        ax1.fill_between(df_gate["date"], 0, df_gate["cumpnl"],
                         where=df_gate["cumpnl"] >= 0, alpha=0.15, color=C_GATE)
        ax1.fill_between(df_gate["date"], 0, df_gate["cumpnl"],
                         where=df_gate["cumpnl"] < 0, alpha=0.20, color=C_LOSS)
    if not df_raw.empty:
        ax1.plot(df_raw["date"], df_raw["cumpnl"], color=C_RAW, lw=2,
                 linestyle="--", alpha=0.8,
                 label=f"No filter (all 10:00–10:30)  WR={st_raw['wr']:.0%}  Total=${st_raw['total']:,.0f}")
    ax1.axhline(0, color="black", lw=0.8, ls="--", alpha=0.5)
    ax1.set_title("Cumulative P&L — Refined vs. Unfiltered", fontweight="bold")
    ax1.set_ylabel("P&L ($)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(fmt_dollar))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax1.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)

    # ── 2. Summary table ─────────────────────────────────────────────────────
    ax_tbl = fig.add_subplot(gs[0, 2])
    ax_tbl.axis("off")
    rows = [
        ["Metric", "Refined", "Unfiltered"],
        ["Trades",   str(st_gate.get("n",0)),   str(st_raw.get("n",0))],
        ["Win Rate", f"{st_gate.get('wr',0):.0%}", f"{st_raw.get('wr',0):.0%}"],
        ["Avg P&L",  f"${st_gate.get('avg',0):,.0f}", f"${st_raw.get('avg',0):,.0f}"],
        ["Avg Win",  f"${st_gate.get('avg_win',0):,.0f}", f"${st_raw.get('avg_win',0):,.0f}"],
        ["Avg Loss", f"${st_gate.get('avg_loss',0):,.0f}", f"${st_raw.get('avg_loss',0):,.0f}"],
        ["Total",    f"${st_gate.get('total',0):,.0f}", f"${st_raw.get('total',0):,.0f}"],
        ["EV/trade", f"${st_gate.get('ev',0):,.0f}", f"${st_raw.get('ev',0):,.0f}"],
        ["Skipped",  str(len(skips)), "—"],
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
                num = float(rows[r][1].replace("$","").replace(",","").replace("%",""))
                cell.set_facecolor("#d5f5e3" if num > 0 else "#fadbd8" if num < 0 else "#f8f9fa")
            except:
                pass
    ax_tbl.set_title("Strategy Summary", fontweight="bold", pad=10)

    # ── 3. Daily P&L bars — refined ─────────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, :2])
    if not df_gate.empty:
        colors = [C_WIN if w else C_LOSS for w in df_gate["win"]]
        ax3.bar(df_gate["date"], df_gate["pnl_dollar"], color=colors, alpha=0.85, width=0.8)
        # Mark stop-losses with X
        stops = df_gate[df_gate["outcome"] == "stop_loss"]
        for _, row in stops.iterrows():
            ax3.annotate("✕", (row["date"], row["pnl_dollar"]),
                         ha="center", va="top" if row["pnl_dollar"] < 0 else "bottom",
                         fontsize=9, color="#c0392b")
    ax3.axhline(0, color="black", lw=0.8, ls="--")
    ax3.set_title("Daily P&L per Trade — Refined Strategy (✕ = stop-loss triggered)", fontweight="bold")
    ax3.set_ylabel("P&L ($)")
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(fmt_dollar))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax3.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2))
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax3.grid(True, alpha=0.3, axis="y")
    ax3.legend(handles=[
        mpatches.Patch(color=C_WIN, label=f"Win ({st_gate.get('n_win',0)})"),
        mpatches.Patch(color=C_LOSS, label=f"Loss ({st_gate.get('n',0)-st_gate.get('n_win',0)})"),
    ])

    # ── 4. Exit reason breakdown ─────────────────────────────────────────────
    ax4 = fig.add_subplot(gs[1, 2])
    if not df_gate.empty:
        oc = df_gate["exit_reason"].value_counts() if "exit_reason" in df_gate.columns else df_gate["outcome"].value_counts()
        labels_map = {
            "win":          "Expiry Win",
            "expiry":       "Expiry Win",
            "profit_target":"Profit Target",
            "time_exit":    "Time Exit 14:30",
            "stop_loss":    "NDX Stop-Loss",
            "loss_stop":    "2× Credit Stop",
            "loss":         "Loss (other)",
        }
        pie_labels = [labels_map.get(k, k) for k in oc.index]
        def _exit_color(k):
            if k in ("win", "expiry", "profit_target", "time_exit"): return C_WIN
            if k in ("stop_loss", "loss_stop", "loss"):               return C_LOSS
            return "#e67e22"
        pie_colors = [_exit_color(k) for k in oc.index]
        ax4.pie(oc.values, labels=pie_labels, colors=pie_colors, autopct="%1.0f%%",
                startangle=90, textprops={"fontsize": 8})
    ax4.set_title("Exit Reason Breakdown\n(Refined)", fontweight="bold")

    # ── 5. Gate score histogram ───────────────────────────────────────────────
    ax5 = fig.add_subplot(gs[2, 0])
    all_scores = [r.get("gate_score", 0) for r in results_gate]
    score_vals, score_cnts = np.unique(all_scores, return_counts=True)
    bar_colors = ["#e74c3c" if s < 3 else "#f39c12" if s == 3 else "#27ae60"
                  for s in score_vals]
    ax5.bar(score_vals, score_cnts, color=bar_colors, alpha=0.85, edgecolor="white")
    for sv, sc in zip(score_vals, score_cnts):
        ax5.text(sv, sc + 0.2, str(sc), ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax5.set_title("Gate Score Distribution\n(0–2=AVOID  3=WATCH  4–5=PROCEED)", fontweight="bold")
    ax5.set_xlabel("Gate Score")
    ax5.set_ylabel("Days")
    ax5.set_xticks(range(6))
    ax5.grid(True, alpha=0.3, axis="y")

    # ── 6. Win rate by month ─────────────────────────────────────────────────
    ax6 = fig.add_subplot(gs[2, 1])
    if not df_gate.empty:
        df_gate["month"] = df_gate["date"].dt.to_period("M").astype(str)
        mth = df_gate.groupby("month").agg(
            n=("win", "count"), wins=("win", "sum"), pnl=("pnl_dollar", "sum")
        ).reset_index()
        mth["wr"] = mth["wins"] / mth["n"]
        x = np.arange(len(mth))
        mc = [C_WIN if p > 0 else C_LOSS for p in mth["pnl"]]
        ax6.bar(x, mth["wr"] * 100, color=mc, alpha=0.85, edgecolor="white")
        ax6.axhline(50, color="black", lw=1, ls="--", alpha=0.5)
        ax6.set_xticks(x)
        ax6.set_xticklabels(mth["month"], rotation=30, ha="right")
        for i, row in mth.iterrows():
            ax6.text(i, row["wr"] * 100 + 1.5,
                     f"{row['wr']:.0%}\n({row['n']}T ${row['pnl']/1000:.0f}K)",
                     ha="center", va="bottom", fontsize=8.5)
    ax6.set_title("Win Rate by Month\n(Refined Strategy)", fontweight="bold")
    ax6.set_ylabel("Win Rate (%)")
    ax6.set_ylim(0, 110)
    ax6.grid(True, alpha=0.3, axis="y")

    # ── 7. P&L distribution ─────────────────────────────────────────────────
    ax7 = fig.add_subplot(gs[2, 2])
    if not df_gate.empty:
        vmin, vmax = df_gate["pnl_dollar"].min(), df_gate["pnl_dollar"].max()
        bins = np.linspace(vmin - 0.1, vmax + 0.1, 22)
        wins_v  = df_gate[df_gate["win"]]["pnl_dollar"]
        losses_v = df_gate[~df_gate["win"]]["pnl_dollar"]
        ax7.hist(losses_v, bins=bins, color=C_LOSS, alpha=0.7, label="Loss")
        ax7.hist(wins_v,   bins=bins, color=C_WIN,  alpha=0.7, label="Win")
        ax7.axvline(0, color="black", lw=1, ls="--")
        avg_v = df_gate["pnl_dollar"].mean()
        ax7.axvline(avg_v, color="navy", lw=1.5, ls="-.",
                    label=f"Avg ${avg_v:,.0f}")
    ax7.set_title("P&L Distribution\n(Refined)", fontweight="bold")
    ax7.set_xlabel("P&L ($)")
    ax7.set_ylabel("Frequency")
    ax7.xaxis.set_major_formatter(plt.FuncFormatter(fmt_dollar))
    ax7.legend(fontsize=9)
    ax7.grid(True, alpha=0.3, axis="y")

    # ── 8. NDX price with trade annotations ─────────────────────────────────
    ax8 = fig.add_subplot(gs[3, :])
    # Plot daily close of NDX
    daily = all_bars.groupby("date_et").last().reset_index()
    daily["date"] = pd.to_datetime(daily["date_et"])
    ax8.plot(daily["date"], daily["close"], color="#2c3e50", lw=1.2, alpha=0.8, label="NDX close")

    if not df_gate.empty:
        wins_df  = df_gate[df_gate["win"]]
        losses_df = df_gate[~df_gate["win"]]
        if not wins_df.empty:
            ax8.scatter(wins_df["date"], wins_df["entry_price"],
                        marker="^", color=C_WIN, s=60, zorder=5, label="Entry (Win)")
        if not losses_df.empty:
            ax8.scatter(losses_df["date"], losses_df["entry_price"],
                        marker="v", color=C_LOSS, s=60, zorder=5, label="Entry (Loss)")
        # Draw short strike lines as small horizontal ticks
        for _, row in df_gate.iterrows():
            color = C_WIN if row["win"] else C_LOSS
            ax8.hlines(row["short_K"], row["date"] - pd.Timedelta(days=0.3),
                       row["date"] + pd.Timedelta(days=0.3),
                       colors=color, lw=1.5, alpha=0.6)

    # Mark gate-skip days
    if skips:
        skip_dates = pd.to_datetime([s["date"] for s in skips])
        skip_prices = [s["metrics"]["price"] for s in skips]
        ax8.scatter(skip_dates, skip_prices, marker="x", color=C_SKIP,
                    s=30, zorder=4, label="Skipped (gate)", alpha=0.7)

    ax8.set_title(
        "NDX Price + Trade Entries  (▲ win  ▼ loss  — short strike  × skipped)",
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

if __name__ == "__main__":
    print("Loading NDX 5-min RTH data...")
    bars = load_rth_bars(DATA_PATH)
    n_days = bars["date_et"].nunique()
    print(f"  {len(bars)} bars  |  {n_days} trading days  |  "
          f"{bars['date_et'].min()} → {bars['date_et'].max()}")

    print("\nRunning REFINED backtest (gate ≥ 3, Bear Put, 10:00–10:30 ET)...")
    results_gate = run_backtest(bars, use_gate=True)
    df_g = make_trade_df(results_gate)
    sg = stats_summary(df_g)
    print(f"  Trades: {sg.get('n',0)}  |  Wins: {sg.get('n_win',0)}  |  "
          f"WR: {sg.get('wr',0):.1%}  |  Avg P&L: ${sg.get('avg',0):,.0f}  |  "
          f"Total: ${sg.get('total',0):,.0f}")
    print(f"  Avg Win: ${sg.get('avg_win',0):,.0f}  |  Avg Loss: ${sg.get('avg_loss',0):,.0f}  |  "
          f"EV/trade: ${sg.get('ev',0):,.0f}")
    skips = [r for r in results_gate if r.get("result") == "skip"]
    print(f"  Days skipped by gate: {len(skips)}")

    # Print outcome breakdown
    if not df_g.empty:
        print(f"\n  Outcomes: {df_g['outcome'].value_counts().to_dict()}")

    print("\nRunning UNFILTERED backtest (all Bear Puts, 10:00–10:30 ET, no gate)...")
    results_raw = run_backtest(bars, use_gate=False)
    df_r = make_trade_df(results_raw)
    sr = stats_summary(df_r)
    print(f"  Trades: {sr.get('n',0)}  |  Wins: {sr.get('n_win',0)}  |  "
          f"WR: {sr.get('wr',0):.1%}  |  Avg P&L: ${sr.get('avg',0):,.0f}  |  "
          f"Total: ${sr.get('total',0):,.0f}")

    print("\nGenerating plots...")
    plot_backtest(bars, results_gate, results_raw)
