#!/usr/bin/env python3
"""
Per-day JSON + chart generator for NDX spread strategy comparison.

For each trading day:
  • trading_logs/viz/<date>.json  — real trades + strategy simulation side-by-side
  • trading_logs/viz/<date>.png   — candlestick chart with real AND strategy entry/exit overlaid

Run: python3 generate_daily_charts.py
"""

import json
import math
import datetime
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

import numpy as np
import pandas as pd
from scipy.stats import norm

warnings.filterwarnings("ignore")

BASE      = Path(__file__).parent
DATA_DIR  = BASE / "trading_logs"
OUT_DIR   = DATA_DIR / "viz"
OUT_DIR.mkdir(exist_ok=True)

# ─── Strategy constants ────────────────────────────────────────────────────────
N_CONTRACTS       = 3
SPREAD_WIDTH      = 50
NDX_MULT          = 100
ANNUAL_BARS       = 252 * 78   # 5-min bars/year during RTH
PRIME_START       = datetime.time(10, 0)
PRIME_END         = datetime.time(10, 30)
PROFIT_TARGET_PCT = 0.25               # exit when spread decays to 25% of credit
LOSS_STOP_MULT    = 2.0                # exit when spread = 2× credit
TIME_EXIT_ET      = datetime.time(14, 30)  # time exit at 14:30 ET

# ─── Colour palette ────────────────────────────────────────────────────────────
BG      = "#0f1117"
PANEL   = "#181c2a"
PANEL2  = "#1e2235"
GRID    = "#252a3d"
GRID2   = "#1a1f30"
TEXT    = "#d1d4dc"
TEXT2   = "#7a849e"
TEXT3   = "#4e5568"
UP      = "#26a69a"
DOWN    = "#ef5350"
VWAP_C  = "#ce93d8"

C_REAL_ENTRY = "#f5a623"   # orange  – real entry
C_REAL_EXIT  = "#7b61ff"   # violet  – real exit/scale
C_SIM_ENTRY  = "#00e676"   # bright green – strategy entry
C_SIM_STOP   = "#ff1744"   # bright red   – strategy stop exit
C_SIM_WIN    = "#00e676"   # green – strategy win zone
C_SIM_LOSS   = "#ff5252"   # red   – strategy loss zone
C_SIM_STRIKE = "#64ffda"   # teal  – strategy short strike

SPREAD_COLORS = ["#26a69a","#ef5350","#f5a623","#7b61ff","#00bcd4",
                 "#ff7043","#9ccc65","#f06292","#4fc3f7","#ffca28"]

# ─── Calendar helpers ─────────────────────────────────────────────────────────
MONTHS = {m: i+1 for i, m in enumerate(
    ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"]
)}
DST_START = datetime.datetime(2026, 3, 8, 7, 0)

def parse_exp(s: str) -> Optional[datetime.date]:
    try:
        return datetime.date(2000 + int(s[5:7]), MONTHS[s[2:5]], int(s[:2]))
    except:
        return None

def utc_str_to_et(s: str) -> datetime.datetime:
    dt = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M")
    return dt - datetime.timedelta(hours=4 if dt >= DST_START else 5)

# ─── Black-Scholes ─────────────────────────────────────────────────────────────
def bs_put(S, K, T, r=0.045, sigma=0.25):
    if T <= 1e-8:
        return max(K - S, 0.0)
    d1 = (math.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
    d2 = d1 - sigma*math.sqrt(T)
    return K*math.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1)

def spread_credit(S, sk, lk, bars_left, sigma):
    T = bars_left / ANNUAL_BARS
    return max(min(bs_put(S, sk, T, sigma=sigma) - bs_put(S, lk, T, sigma=sigma), 20.0), 0.0)

def spread_val(S, sk, lk, bars_left, sigma):
    T = bars_left / ANNUAL_BARS
    return max(min(bs_put(S, sk, T, sigma=sigma) - bs_put(S, lk, T, sigma=sigma), SPREAD_WIDTH), 0.0)

# ─── Data loading ──────────────────────────────────────────────────────────────
def load_price_data() -> pd.DataFrame:
    raw = json.load(open(DATA_DIR / "NDX_5min_2026.json"))
    df = pd.DataFrame(raw["bars"])
    df["et"]     = df["datetime_utc"].apply(utc_str_to_et)
    df["date"]   = df["et"].dt.date.astype(str)
    df["time_et"] = df["et"].dt.time
    df = df[(df["time_et"] >= datetime.time(9,30)) &
            (df["time_et"] <= datetime.time(16,0))].copy()
    return df.sort_values("et").reset_index(drop=True)

def load_trades() -> list:
    return json.load(open(DATA_DIR / "trades.json"))

# ─── Real spread reconstruction (from visualize_trades.py) ───────────────────
def to_dt(date_str, time_str):
    return datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")

def build_real_spreads(day_trades: list, date_str: str) -> list:
    by_key = defaultdict(list)
    for t in day_trades:
        if t.get("underlying") != "NDX":
            continue
        by_key[(t["expiry"], t["option_type"])].append(t)

    spreads, seen = [], set()
    for (exp, otype), legs in by_key.items():
        strikes = sorted(set(l["strike"] for l in legs))
        for i in range(len(strikes)-1):
            lo, hi = strikes[i], strikes[i+1]
            if hi - lo > 200:
                continue
            key = (exp, otype, lo, hi)
            if key in seen:
                continue
            seen.add(key)

            lo_legs = [l for l in legs if l["strike"] == lo]
            hi_legs = [l for l in legs if l["strike"] == hi]
            all_legs = sorted(lo_legs + hi_legs, key=lambda x: x["time"])

            lo_net = sum(l["quantity"] for l in lo_legs)
            if otype == "P":
                direction = "Bull Put" if lo_net > 0 else "Bear Put"
            else:
                direction = "Bear Call" if lo_net < 0 else "Bull Call"

            t_open  = to_dt(all_legs[0]["date"],  all_legs[0]["time"])
            t_close = to_dt(all_legs[-1]["date"], all_legs[-1]["time"])

            # If open == close (expired, no close leg), extend to 16:00
            trade_date = datetime.date.fromisoformat(date_str)
            eod = datetime.datetime.combine(trade_date, datetime.time(16, 0))
            if t_close == t_open:
                t_close = eod

            hold_min = (t_close - t_open).total_seconds() / 60
            net = sum(l["quantity"] * l["price"] * 100 for l in all_legs)
            times_seen = defaultdict(int)
            for l in all_legs:
                times_seen[l["time"]] += 1
            n_adds = len(times_seen) - 1

            exp_date = parse_exp(exp)
            td = trade_date
            dte = (exp_date - td).days if exp_date else None
            is_edt = (
                (t_open.hour > 14 or (t_open.hour == 14 and t_open.minute >= 45))
                and dte == 1
            )
            short_s = hi if otype == "P" else lo
            long_s  = lo if otype == "P" else hi

            # Max contracts traded
            qty = max(abs(l["quantity"]) for l in all_legs)

            spreads.append(dict(
                direction=direction, exp=exp, expiry_date=exp_date, dte=dte,
                type=otype, lo=lo, hi=hi, short_s=short_s, long_s=long_s,
                t_open=t_open, t_close=t_close, hold_min=hold_min, net=round(net, 0),
                n_adds=n_adds, is_edt=is_edt, qty=qty,
                legs=[{k: v for k,v in l.items()} for l in all_legs],
            ))
    return spreads

# ─── Strategy simulation (per day) ────────────────────────────────────────────
def day_metrics_at(day_df: pd.DataFrame, up_to_idx: int) -> dict:
    partial = day_df.iloc[:up_to_idx + 1]
    closes  = partial["close"].values
    log_ret = np.diff(np.log(closes)) if len(closes) > 1 else np.array([0.0])
    sigma   = max(math.sqrt(np.var(log_ret) * ANNUAL_BARS), 0.12) if len(log_ret) > 2 else 0.25

    day_high  = partial["high"].max()
    day_low   = partial["low"].min()
    day_range = day_high - day_low
    avg_bar   = (partial["high"] - partial["low"]).mean()
    trending  = day_range > 2.5 * avg_bar if avg_bar > 0 else False

    price     = day_df.iloc[up_to_idx]["close"]
    rng_pct   = (price - day_low) / day_range if day_range > 0 else 0.5
    mom_idx   = max(up_to_idx - 6, 0)
    mom_30    = price - day_df.iloc[mom_idx]["close"]

    vwap = (
        (partial["close"] * partial["volume"]).sum() / partial["volume"].sum()
        if partial["volume"].sum() > 0 else price
    )
    return dict(
        day_high=day_high, day_low=day_low, day_range=day_range,
        avg_bar=avg_bar, trending=trending, price=price,
        range_pct=rng_pct, mom_30=mom_30, vwap=vwap, sigma=sigma,
    )

def simulate_strategy(day_df: pd.DataFrame, date_str: str) -> dict:
    """Return strategy simulation result for the day."""
    trade_date = datetime.date.fromisoformat(date_str)
    eod_dt = datetime.datetime.combine(trade_date, datetime.time(16, 0))

    prime_bars = day_df[
        (day_df["time_et"] >= PRIME_START) & (day_df["time_et"] <= PRIME_END)
    ]
    if prime_bars.empty:
        return {"taken": False, "skip_reason": "No bars in prime window"}

    entry_iloc = day_df.index.get_loc(prime_bars.index[0])
    m           = day_metrics_at(day_df, entry_iloc)
    entry_time  = day_df.iloc[entry_iloc]["time_et"]
    entry_price = m["price"]
    entry_dt    = day_df.iloc[entry_iloc]["et"]

    # Gate scoring
    gate = {
        "prime_window":  PRIME_START <= entry_time <= PRIME_END,
        "flat_momentum": abs(m["mom_30"]) <= 10,
        "top_20_range":  m["range_pct"] >= 0.80,
        "small_or_calm": (m["day_range"] < 180) or (not m["trending"]),
        "dte0":          True,
    }
    score = sum(gate.values())

    # Q-score
    qs = 50
    if PRIME_START <= entry_time <= PRIME_END: qs += 20
    elif entry_time < datetime.time(10, 0):    qs -= 10
    elif entry_time >= datetime.time(14, 45):  qs -= 25
    qs += 15   # 0DTE
    qs += 15   # Bear Put direction
    qs += 5    # ≤2 scale-ins planned
    if not m["trending"]:  qs += 10
    else:                  qs -= 20

    # Hard skip
    skip = None
    if score < 3:
        skip = f"Gate score {score}/5 < 3"
    elif m["day_range"] > 250:
        skip = f"Day range {m['day_range']:.0f}pt > 250pt hard override"
    elif not gate["top_20_range"]:
        skip = f"NDX at {m['range_pct']:.0%} of range, not top 20% — Bear Put not viable"

    if skip:
        return {
            "taken": False, "skip_reason": skip,
            "gate_score": score, "gate_details": gate,
            "entry_time": str(entry_time), "entry_ndx": round(entry_price, 1),
            "metrics": {k: round(v, 2) if isinstance(v, float) else v
                        for k, v in m.items() if k != "sigma"},
        }

    # Strike selection
    short_K = math.floor((entry_price - 100) / 50) * 50
    long_K  = short_K - SPREAD_WIDTH
    otm_dist = entry_price - short_K
    qs += 10 if otm_dist >= 100 else (-15 if otm_dist < 50 else 0)
    qs = max(0, min(100, qs))

    # Bars remaining
    total_bars = len(day_df)
    bars_left  = total_bars - entry_iloc - 1
    sigma      = m["sigma"]
    credit_pts = spread_credit(entry_price, short_K, long_K, bars_left, sigma)

    # Simulate post-entry — check all exits on every bar
    post = day_df.iloc[entry_iloc + 1:].copy()
    exit_reason = None
    exit_dt     = None
    exit_ndx    = None
    pnl_pts     = None

    for i, (_, bar) in enumerate(post.iterrows()):
        bars_here = bars_left - i - 1

        # 1. Hard stop: NDX bar low crosses short strike
        if bar["low"] < short_K:
            ndx_x   = min(bar["low"], short_K - 1)
            sv      = spread_val(ndx_x, short_K, long_K, max(bars_here, 1), sigma)
            pnl_pts = credit_pts - sv
            exit_reason = "stop_loss"
            exit_dt     = bar["et"]
            exit_ndx    = ndx_x
            break

        sv_close = spread_val(bar["close"], short_K, long_K, max(bars_here, 1), sigma)

        # 2. Loss stop: spread = 2× credit
        if credit_pts > 0 and sv_close >= LOSS_STOP_MULT * credit_pts:
            pnl_pts     = credit_pts - sv_close
            exit_reason = "loss_stop"
            exit_dt     = bar["et"]
            exit_ndx    = bar["close"]
            break

        # 3. Profit target: spread decayed to ≤ 25% of credit
        if credit_pts > 0 and sv_close <= PROFIT_TARGET_PCT * credit_pts:
            pnl_pts     = credit_pts - sv_close
            exit_reason = "profit_target"
            exit_dt     = bar["et"]
            exit_ndx    = bar["close"]
            break

        # 4. Time exit at 14:30 ET
        if bar["time_et"] >= TIME_EXIT_ET:
            pnl_pts     = credit_pts - sv_close
            exit_reason = "time_exit"
            exit_dt     = bar["et"]
            exit_ndx    = bar["close"]
            break

    else:
        # Held to expiry — intrinsic value only
        eod_close   = day_df.iloc[-1]["close"]
        sv_eod      = max(min(short_K - eod_close, SPREAD_WIDTH), 0.0)
        pnl_pts     = credit_pts - sv_eod
        exit_reason = "expiry"
        exit_dt     = eod_dt
        exit_ndx    = eod_close

    pnl_dollar = pnl_pts * NDX_MULT * N_CONTRACTS

    if exit_reason in ("profit_target", "time_exit") and pnl_pts > 0:
        outcome = exit_reason
    elif exit_reason == "expiry":
        outcome = "win" if pnl_pts > 0 else "loss"
    elif exit_reason == "stop_loss":
        outcome = "stop_loss"
    elif exit_reason == "loss_stop":
        outcome = "loss_stop"
    else:
        outcome = "loss"

    return {
        "taken":          True,
        "gate_score":     int(score),
        "gate_details":   {k: bool(v) for k, v in gate.items()},
        "q_score":        int(qs),
        "entry_time":     str(entry_time),
        "entry_ndx":      round(entry_price, 1),
        "entry_dt":       entry_dt,
        "short_strike":   short_K,
        "long_strike":    long_K,
        "otm_dist":       round(otm_dist, 1),
        "credit_pts":     round(credit_pts, 2),
        "credit_dollar":  round(credit_pts * NDX_MULT * N_CONTRACTS, 0),
        "n_contracts":    N_CONTRACTS,
        "outcome":        outcome,
        "exit_reason":    exit_reason,
        "stop_triggered": exit_reason == "stop_loss",
        "stop_time":      str(exit_dt.time()) if exit_reason == "stop_loss" else None,
        "stop_ndx":       round(exit_ndx, 1) if exit_reason == "stop_loss" else None,
        "exit_time":      str(exit_dt.time()) if exit_dt else None,
        "exit_ndx":       round(exit_ndx, 1),
        "exit_dt":        exit_dt,
        "pnl_pts":        round(pnl_pts, 2),
        "pnl_dollar":     round(pnl_dollar, 0),
        "metrics": {
            "day_range":  round(float(m["day_range"]), 1),
            "avg_bar":    round(float(m["avg_bar"]), 1),
            "trending":   bool(m["trending"]),
            "range_pct":  round(float(m["range_pct"]), 3),
            "mom_30":     round(float(m["mom_30"]), 1),
            "vwap":       round(float(m["vwap"]), 1),
            "sigma":      round(float(sigma), 4),
        },
    }

# ─── JSON export ──────────────────────────────────────────────────────────────
def _serial(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, datetime.time):
        return str(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    return str(obj)

def build_day_json(date_str, day_df, real_spreads, strategy) -> dict:
    sess_close = day_df.iloc[-1]["close"] if not day_df.empty else None
    sess_open  = day_df.iloc[0]["open"]   if not day_df.empty else None
    sess_high  = day_df["high"].max()     if not day_df.empty else None
    sess_low   = day_df["low"].min()      if not day_df.empty else None
    sess_range = (sess_high - sess_low)   if sess_high else None
    avg_bar    = (day_df["high"] - day_df["low"]).mean() if not day_df.empty else None

    real_out = []
    for i, sp in enumerate(real_spreads):
        legs_out = []
        for l in sp["legs"]:
            legs_out.append({
                "time":      l["time"],
                "account":   l.get("account"),
                "symbol":    l["symbol"],
                "strike":    l["strike"],
                "qty":       l["quantity"],
                "price":     l["price"],
                "pnl":       l["realized_pl"],
            })
        real_out.append({
            "id":           i,
            "direction":    sp["direction"],
            "short_strike": sp["short_s"],
            "long_strike":  sp["long_s"],
            "expiry":       sp["exp"],
            "dte":          sp["dte"],
            "is_edt":       sp["is_edt"],
            "n_contracts":  int(sp["qty"]),
            "n_adds":       sp["n_adds"],
            "entry_time":   sp["t_open"].strftime("%H:%M:%S"),
            "exit_time":    sp["t_close"].strftime("%H:%M:%S"),
            "hold_min":     round(sp["hold_min"], 0),
            "pnl":          sp["net"],
            "legs":         legs_out,
        })

    # Strip internal datetime objects from strategy before JSON serialise
    strat_out = {k: v for k, v in strategy.items()
                 if k not in ("entry_dt", "exit_dt", "stop_dt")}

    return {
        "date":       date_str,
        "ndx_session": {
            "open":       round(sess_open,  1) if sess_open  else None,
            "high":       round(sess_high,  1) if sess_high  else None,
            "low":        round(sess_low,   1) if sess_low   else None,
            "close":      round(sess_close, 1) if sess_close else None,
            "range":      round(sess_range, 1) if sess_range else None,
            "avg_bar":    round(avg_bar,    1) if avg_bar    else None,
            "direction":  "UP" if (sess_close and sess_open and sess_close >= sess_open) else "DOWN",
            "regime":     "TRENDING" if (sess_range and avg_bar and sess_range > 2.5*avg_bar) else "RANGE_BOUND",
        },
        "real_trades":  real_out,
        "strategy":     strat_out,
    }

# ─── Chart drawing helpers ────────────────────────────────────────────────────
def draw_candles(ax, day_df):
    bw = (mdates.date2num(datetime.datetime(2000,1,2))
        - mdates.date2num(datetime.datetime(2000,1,1))) * (3.6 / (24*60))
    for _, r in day_df.iterrows():
        x   = mdates.date2num(r["et"])
        o,h,l,c = r["open"], r["high"], r["low"], r["close"]
        col = UP if c >= o else DOWN
        ax.plot([x,x],[l,h], color=col, lw=0.9, zorder=2, solid_capstyle="butt")
        ax.add_patch(Rectangle((x-bw/2, min(o,c)), bw, max(abs(c-o),0.5),
                               facecolor=col, edgecolor="none", zorder=3))

def nearest_bar_close(day_df, dt):
    if day_df.empty:
        return None
    diffs = (day_df["et"] - dt).abs()
    return day_df.loc[diffs.idxmin(), "close"]

# ─── Per-day chart ────────────────────────────────────────────────────────────
def make_chart(date_str, day_df, real_spreads, strategy, day_json):
    trade_date = datetime.date.fromisoformat(date_str)
    eod_dt     = datetime.datetime.combine(trade_date, datetime.time(16, 0))

    sess_o  = day_df.iloc[0]["open"]    if not day_df.empty else 0
    sess_h  = day_df["high"].max()      if not day_df.empty else 0
    sess_l  = day_df["low"].min()       if not day_df.empty else 0
    sess_c  = day_df.iloc[-1]["close"]  if not day_df.empty else 0
    sess_rng= sess_h - sess_l
    avg_bar = (day_df["high"] - day_df["low"]).mean() if not day_df.empty else 0
    trending = sess_rng > 2.5 * avg_bar if avg_bar > 0 else False

    vol = day_df["volume"].sum()
    vwap_s = (day_df["close"] * day_df["volume"]).cumsum() / day_df["volume"].cumsum()

    # Figure layout: price | rationale | volume
    fig = plt.figure(figsize=(20, 11.25), dpi=96, facecolor=BG)
    gs  = fig.add_gridspec(3, 1, height_ratios=[6.0, 0.9, 1.6],
                           hspace=0.0, left=0.06, right=0.976, top=0.92, bottom=0.04)
    ax     = fig.add_subplot(gs[0])
    ax_rat = fig.add_subplot(gs[1], sharex=ax)
    ax_vol = fig.add_subplot(gs[2], sharex=ax)

    for a in (ax, ax_rat, ax_vol):
        a.set_facecolor(BG)
        a.tick_params(colors=TEXT2, labelsize=8)
        for sp in a.spines.values():
            sp.set_edgecolor(GRID)

    # Session phase shading
    PHASES = [
        (datetime.time(9,30),  datetime.time(10,0),  "#161c2c"),
        (datetime.time(10,0),  datetime.time(10,30), "#192038"),
        (datetime.time(10,30), datetime.time(12,0),  "#0f1117"),
        (datetime.time(12,0),  datetime.time(14,0),  "#141820"),
        (datetime.time(14,0),  datetime.time(15,0),  "#0f1117"),
        (datetime.time(15,0),  datetime.time(16,0),  "#161c2c"),
    ]
    for t0, t1, fc in PHASES:
        x0 = mdates.date2num(datetime.datetime.combine(trade_date, t0))
        x1 = mdates.date2num(datetime.datetime.combine(trade_date, t1))
        for a in (ax, ax_rat, ax_vol):
            a.axvspan(x0, x1, facecolor=fc, alpha=1.0, zorder=0)

    # Prime window highlight
    p0 = mdates.date2num(datetime.datetime.combine(trade_date, PRIME_START))
    p1 = mdates.date2num(datetime.datetime.combine(trade_date, PRIME_END))
    ax.axvspan(p0, p1, facecolor="#26a69a", alpha=0.06, zorder=0)
    ax.text((p0+p1)/2, 0.993, "★ Prime 10:00–10:30",
            transform=ax.get_xaxis_transform(),
            color="#26a69a", fontsize=6, ha="center", va="top", alpha=0.8)

    # Candles
    draw_candles(ax, day_df)

    # VWAP
    xarr = day_df["et"].map(mdates.date2num).values
    ax.plot(xarr, vwap_s, color=VWAP_C, lw=1.0, ls="--", alpha=0.55, zorder=4)
    ax_vol.plot(xarr, vwap_s, color=VWAP_C, lw=0.7, alpha=0.4, zorder=4)

    # Volume
    bw_v = mdates.date2num(datetime.datetime(2000,1,1,0,3,30)) \
         - mdates.date2num(datetime.datetime(2000,1,1,0,0,0))
    for _, r in day_df.iterrows():
        col = UP if r["close"] >= r["open"] else DOWN
        ax_vol.bar(mdates.date2num(r["et"]), r["volume"],
                   width=bw_v, color=col, alpha=0.6, linewidth=0)
    ax_vol.set_ylabel("Vol", color=TEXT2, fontsize=7)
    ax_vol.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x,_: f"{x/1e6:.0f}M"))
    ax_vol.yaxis.set_major_locator(mticker.MaxNLocator(3))

    # ── Y range ───────────────────────────────────────────────────────────────
    all_strikes = [s for sp in real_spreads for s in [sp["lo"], sp["hi"]]]
    if strategy.get("taken"):
        all_strikes += [strategy["short_strike"], strategy["long_strike"]]
    data_lo = min(sess_l, min(all_strikes) if all_strikes else sess_l)
    data_hi = max(sess_h, max(all_strikes) if all_strikes else sess_h)
    pad     = (data_hi - data_lo) * 0.25
    ax.set_ylim(data_lo - pad*0.2, data_hi + pad + pad*1.2)
    ylim    = ax.get_ylim()

    legend_handles = []

    # ── Real spread bands ─────────────────────────────────────────────────────
    for idx, sp in enumerate(real_spreads):
        sc  = SPREAD_COLORS[idx % len(SPREAD_COLORS)]
        win = sp["net"] > 0
        x0  = mdates.date2num(sp["t_open"]  - datetime.timedelta(minutes=4))
        x1  = mdates.date2num(sp["t_close"] + datetime.timedelta(minutes=4))
        if x1 <= x0:
            x0 = mdates.date2num(day_df["et"].min() - datetime.timedelta(minutes=5))
            x1 = mdates.date2num(eod_dt + datetime.timedelta(minutes=5))

        bh = max(sp["hi"] - sp["lo"], 1)
        ax.add_patch(Rectangle((x0, sp["lo"]), x1-x0, bh,
                               facecolor=sc, alpha=0.14 if win else 0.07, edgecolor="none", zorder=2))
        ax.add_patch(Rectangle((x0, sp["lo"]), x1-x0, bh, facecolor="none",
                               edgecolor=sc, lw=0.9,
                               linestyle=(0,(6,2)) if win else (0,(3,3)),
                               alpha=0.7, zorder=3))
        ax.hlines(sp["short_s"], x0, x1, colors=sc, lw=1.2, linestyles="--", alpha=0.9, zorder=4)
        ax.hlines(sp["long_s"],  x0, x1, colors=sc, lw=0.7, linestyles=":",  alpha=0.7, zorder=4)

        # Strike labels
        x_lbl = mdates.date2num(day_df["et"].min() - datetime.timedelta(minutes=3))
        ax.text(x_lbl, sp["short_s"], f"{sp['short_s']:,.0f} ─S",
                color=sc, fontsize=6.2, va="center", ha="right", zorder=6)
        ax.text(x_lbl, sp["long_s"],  f"{sp['long_s']:,.0f} ─L",
                color=sc, fontsize=5.8, va="center", ha="right", zorder=6, alpha=0.7)

        # Callout box
        x_mid      = (x0 + x1) / 2
        y_span     = ylim[1] - ylim[0]
        n_sp       = max(len(real_spreads), 1)
        headroom_t = ylim[1] - y_span*0.004
        headroom_b = data_hi + pad*0.08
        slot_h     = (headroom_t - headroom_b) / n_sp
        cy         = headroom_t - slot_h*(idx + 0.5)

        entry_ndx = nearest_bar_close(day_df, sp["t_open"]) or sess_o
        sign = "+" if sp["net"] >= 0 else ""
        dte_s = f"{sp['dte']}DTE" if sp["dte"] is not None else "?DTE"
        if sp["is_edt"]: dte_s += " EDT"
        hold_s = f"{sp['hold_min']:.0f}min" if sp["hold_min"] < 120 else f"{sp['hold_min']/60:.1f}h"

        txt = (f"REAL  {sp['direction']}  {sp['qty']:.0f}ct  "
               f"{dte_s}  {hold_s}  ${sign}{sp['net']:,.0f}\n"
               f"Short {sp['short_s']:,.0f}P / Long {sp['long_s']:,.0f}P  +{sp['n_adds']} adds")
        ax.annotate(txt,
            xy=(mdates.date2num(sp["t_open"]), entry_ndx),
            xytext=(x_mid, cy),
            color=sc, fontsize=6.2, va="center", ha="center", fontfamily="monospace",
            arrowprops=dict(arrowstyle="-|>", color=sc, alpha=0.4, lw=0.7, mutation_scale=5),
            bbox=dict(boxstyle="round,pad=0.32", fc=PANEL2, ec=sc, alpha=0.95, lw=1.0),
            zorder=11)

        sign2 = "+" if sp["net"] >= 0 else ""
        legend_handles.append(mpatches.Patch(facecolor=sc, alpha=0.8,
            label=f"REAL  {sp['direction']:10s} {sp['short_s']:>7,.0f}/{sp['long_s']:>7,.0f} "
                  f"{dte_s:9s} ${sign2}{sp['net']:>9,.0f}  {hold_s}  +{sp['n_adds']}"))

    # ── Real trade leg markers ─────────────────────────────────────────────────
    all_legs = []
    for sp in real_spreads:
        all_legs.extend(sp["legs"])
    # Deduplicate by time (each timestamp = one transaction, mark once)
    seen_times = set()
    for leg in sorted(all_legs, key=lambda x: x["time"]):
        if leg["time"] in seen_times:
            continue
        seen_times.add(leg["time"])
        try:
            leg_dt = to_dt(leg["date"], leg["time"])
        except:
            continue
        ndx_px = nearest_bar_close(day_df, leg_dt)
        if ndx_px is None:
            continue
        xn = mdates.date2num(leg_dt)
        ax.axvline(xn, color=C_REAL_ENTRY, lw=1.2, ls="--", alpha=0.4, zorder=8)
        ax.scatter(xn, ndx_px, marker="D", color=C_REAL_ENTRY, s=36,
                   zorder=9, edgecolors="white", linewidths=0.5)

    # ── Strategy simulation overlay ────────────────────────────────────────────
    if strategy.get("taken"):
        sk      = strategy["short_strike"]
        lk      = strategy["long_strike"]
        entry_dt = strategy["entry_dt"]
        exit_dt  = strategy["exit_dt"]
        outcome  = strategy["outcome"]
        win      = outcome == "win"
        sc_sim   = C_SIM_WIN if win else C_SIM_LOSS

        x0_sim = mdates.date2num(entry_dt)
        x1_sim = mdates.date2num(exit_dt)
        if x1_sim <= x0_sim:
            x1_sim = mdates.date2num(eod_dt)

        # Strategy band (between strikes, translucent)
        ax.add_patch(Rectangle((x0_sim, lk), x1_sim-x0_sim, sk-lk,
                               facecolor=sc_sim, alpha=0.12, edgecolor="none", zorder=2))
        ax.add_patch(Rectangle((x0_sim, lk), x1_sim-x0_sim, sk-lk,
                               facecolor="none", edgecolor=C_SIM_STRIKE, lw=1.5,
                               linestyle=(0,(8,3)), alpha=0.9, zorder=3))

        # Strategy short strike dashed line
        ax.hlines(sk, x0_sim, x1_sim, colors=C_SIM_STRIKE, lw=1.6,
                  linestyles="--", alpha=1.0, zorder=5)
        ax.hlines(lk, x0_sim, x1_sim, colors=C_SIM_STRIKE, lw=0.8,
                  linestyles=":", alpha=0.7, zorder=5)

        # Strike labels on right
        x_rlbl = mdates.date2num(eod_dt + datetime.timedelta(minutes=2))
        ax.text(x_rlbl, sk, f"◀ SIM {sk:,.0f}", color=C_SIM_STRIKE,
                fontsize=6.5, va="center", ha="left", zorder=7)
        ax.text(x_rlbl, lk, f"◀ {lk:,.0f}",     color=C_SIM_STRIKE,
                fontsize=5.8, va="center", ha="left", zorder=7, alpha=0.7)

        # Entry marker
        entry_ndx_price = strategy["entry_ndx"]
        ax.axvline(x0_sim, color=C_SIM_ENTRY, lw=1.8, ls="-", alpha=0.7, zorder=9)
        ax.scatter(x0_sim, entry_ndx_price, marker="^", color=C_SIM_ENTRY, s=100,
                   zorder=10, edgecolors="white", linewidths=0.8)

        # Exit marker — colour and shape varies by exit type
        exit_ndx_px = nearest_bar_close(day_df, exit_dt) or strategy["exit_ndx"]
        exit_reason = strategy.get("exit_reason", "")
        if exit_reason == "stop_loss":
            ax.axvline(x1_sim, color=C_SIM_STOP, lw=1.8, ls="-", alpha=0.7, zorder=9)
            ax.scatter(x1_sim, exit_ndx_px, marker="X", color=C_SIM_STOP, s=120,
                       zorder=10, edgecolors="white", linewidths=0.8)
        elif exit_reason == "loss_stop":
            ax.axvline(x1_sim, color="#ff6d00", lw=1.8, ls="-", alpha=0.7, zorder=9)
            ax.scatter(x1_sim, exit_ndx_px, marker="X", color="#ff6d00", s=120,
                       zorder=10, edgecolors="white", linewidths=0.8)
        elif exit_reason == "profit_target":
            ax.axvline(x1_sim, color=C_SIM_ENTRY, lw=1.5, ls="--", alpha=0.7, zorder=9)
            ax.scatter(x1_sim, exit_ndx_px, marker="*", color=C_SIM_ENTRY, s=180,
                       zorder=10, edgecolors="white", linewidths=0.8)
        elif exit_reason == "time_exit":
            ax.axvline(x1_sim, color="#ffeb3b", lw=1.5, ls="--", alpha=0.7, zorder=9)
            ax.scatter(x1_sim, exit_ndx_px, marker="s", color="#ffeb3b", s=100,
                       zorder=10, edgecolors="white", linewidths=0.8)
        else:  # expiry
            ax.scatter(x1_sim, exit_ndx_px, marker="s", color=C_SIM_ENTRY, s=80,
                       zorder=10, edgecolors="white", linewidths=0.8)

        # Callout box for strategy
        y_span    = ylim[1] - ylim[0]
        qs        = strategy.get("q_score", 0)
        pnl_d     = strategy["pnl_dollar"]
        sign_s    = "+" if pnl_d >= 0 else ""
        gate_txt  = " ".join(["✓" if v else "✗" for v in strategy["gate_details"].values()])
        strat_txt = (f"STRATEGY  Bear Put  {N_CONTRACTS}ct  0DTE  Q{qs}\n"
                     f"Short {sk:,.0f}P / Long {lk:,.0f}P  OTM {strategy['otm_dist']:.0f}pt\n"
                     f"Gate {strategy['gate_score']}/5 [{gate_txt}]\n"
                     f"Credit ${strategy['credit_dollar']:,.0f}  →  {outcome.upper()}  "
                     f"{sign_s}${abs(pnl_d):,.0f}")

        cx = (x0_sim + min(x1_sim, mdates.date2num(eod_dt))) / 2
        cy_strat = ylim[0] + y_span*0.09   # near bottom
        ax.annotate(strat_txt,
            xy=(x0_sim, entry_ndx_price),
            xytext=(cx, cy_strat),
            color=C_SIM_STRIKE, fontsize=6.2, va="center", ha="center",
            fontfamily="monospace",
            arrowprops=dict(arrowstyle="-|>", color=C_SIM_STRIKE, alpha=0.5,
                            lw=0.9, mutation_scale=6),
            bbox=dict(boxstyle="round,pad=0.35", fc=BG, ec=C_SIM_STRIKE,
                      alpha=0.95, lw=1.2),
            zorder=12)

        sign_l = "+" if pnl_d >= 0 else ""
        legend_handles.append(mpatches.Patch(facecolor=C_SIM_STRIKE, alpha=0.7,
            label=f"STRATEGY  Bear Put       {sk:>7,.0f}/{lk:>7,.0f} 0DTE        "
                  f"{sign_l}${abs(pnl_d):>9,.0f}  Q{qs:3d}  gate={strategy['gate_score']}/5"))

    elif not strategy.get("taken"):
        # Show skip reason as annotation
        skip_x  = (mdates.date2num(datetime.datetime.combine(trade_date, PRIME_START)) +
                   mdates.date2num(datetime.datetime.combine(trade_date, PRIME_END))) / 2
        skip_y  = ylim[0] + (ylim[1]-ylim[0])*0.07
        ax.text(skip_x, skip_y, f"STRATEGY: SKIP\n{strategy.get('skip_reason','—')}",
                color=TEXT3, fontsize=6.2, ha="center", va="bottom",
                fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.3", fc=BG, ec=TEXT3, alpha=0.85, lw=0.8),
                zorder=11)
        legend_handles.append(mpatches.Patch(facecolor=TEXT3, alpha=0.5,
            label=f"STRATEGY  SKIP  gate={strategy.get('gate_score','?')}/5  "
                  f"{strategy.get('skip_reason','')}"))

    # ── Rationale strip ───────────────────────────────────────────────────────
    ax_rat.set_ylim(0, 1); ax_rat.set_yticks([])
    ax_rat.tick_params(bottom=False, labelbottom=False)
    for sp in ax_rat.spines.values():
        sp.set_visible(False)
    ax_rat.set_facecolor(PANEL)

    real_pnl  = sum(sp["net"] for sp in real_spreads)
    strat_pnl = strategy.get("pnl_dollar", 0) if strategy.get("taken") else 0
    sg = strategy.get("gate_score", "—")
    line1 = (f"Real: {len(real_spreads)} spread(s) ${real_pnl:+,.0f}   "
             f"Strategy: {'TRADE' if strategy.get('taken') else 'SKIP'} "
             f"gate={sg}/5  ${strat_pnl:+,.0f}")
    rc  = "#ef5350" if trending else "#26a69a"
    regime_txt = (f"{'TRENDING' if trending else 'RANGE-BOUND'}"
                  f"  {'UP' if sess_c>=sess_o else 'DOWN'}"
                  f"  {sess_rng:.0f}pt range")

    ax_rat.text(0.010, 0.80, line1, transform=ax_rat.transAxes,
                color=TEXT, fontsize=8.0, va="top", fontweight="bold")
    ax_rat.text(0.992, 0.5, regime_txt, transform=ax_rat.transAxes,
                color=rc, fontsize=8.0, va="center", ha="right", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.32", fc=BG, ec=rc, lw=1.2, alpha=0.96))

    # ── Axes cosmetics ────────────────────────────────────────────────────────
    for a in (ax, ax_vol):
        a.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        a.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        a.xaxis.set_minor_locator(mdates.MinuteLocator(byminute=[0,15,30,45]))
    ax_vol.tick_params(axis="x", colors=TEXT2, labelsize=8)

    xlo = mdates.date2num(day_df["et"].min() - datetime.timedelta(minutes=15)) if not day_df.empty else 0
    xhi = mdates.date2num(eod_dt + datetime.timedelta(minutes=10))
    ax.set_xlim(xlo, xhi)
    ax.grid(True, which="major", color=GRID,  lw=0.5, zorder=1)
    ax.grid(True, which="minor", color=GRID2, lw=0.2, alpha=0.5, zorder=1)
    ax_vol.grid(True, color=GRID, lw=0.3, zorder=1)
    ax.set_ylabel("NDX", color=TEXT2, fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"{x:,.0f}"))
    ax.tick_params(axis="y", colors=TEXT2, labelsize=8)
    plt.setp(ax.get_xticklabels(), visible=False)
    plt.setp(ax_rat.get_xticklabels(), visible=False)

    # Legend
    legend_handles += [
        mpatches.Patch(color=C_REAL_ENTRY, label="Real entry ◆"),
        mpatches.Patch(color=C_SIM_ENTRY,  label="Strategy entry ▲ / profit-target ★"),
        mpatches.Patch(color="#ffeb3b",    label="Strategy time-exit 14:30 ■"),
        mpatches.Patch(color=C_SIM_STOP,   label="Strategy NDX stop ✕"),
        mpatches.Patch(color="#ff6d00",    label="Strategy 2× loss stop ✕"),
        mpatches.Patch(color=VWAP_C,       label="VWAP"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=6.5,
              facecolor=PANEL, edgecolor=GRID, labelcolor=TEXT,
              framealpha=0.95, ncol=1, handlelength=0.85,
              borderpad=0.5, columnspacing=0.6)

    # Title
    dow = trade_date.strftime("%A")
    strat_label = (f"Strategy: {strategy['outcome'].upper()} ${strategy['pnl_dollar']:+,.0f}"
                   if strategy.get("taken") else f"Strategy: SKIP (gate {strategy.get('gate_score','?')}/5)")
    fig.suptitle(
        f"NDX 5-min  ·  {date_str} ({dow})  ·  "
        f"Real: {len(real_spreads)} spread(s) ${real_pnl:+,.0f}   {strat_label}",
        color=TEXT, fontsize=10.5, y=0.955, fontweight="bold",
    )

    out_png = OUT_DIR / f"{date_str}.png"
    fig.savefig(out_png, dpi=96, facecolor=BG)
    plt.close(fig)
    return out_png

# ─── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Loading data...")
    price_df = load_price_data()
    trades   = load_trades()
    ndx_dates = sorted(price_df["date"].unique())

    by_day = defaultdict(list)
    for t in trades:
        by_day[t["date"]].append(t)

    print(f"NDX trading days: {len(ndx_dates)}")
    print(f"Days with real trades: {len([d for d in ndx_dates if d in by_day])}")
    print(f"Generating {len(ndx_dates)} JSON + chart files...\n")

    n_trade = n_skip = 0
    for date_str in ndx_dates:
        day_df      = price_df[price_df["date"] == date_str].copy().reset_index(drop=True)
        day_trades  = by_day.get(date_str, [])
        real_spreads = build_real_spreads(day_trades, date_str) if day_trades else []
        strategy     = simulate_strategy(day_df, date_str)

        # Attach datetime objects for chart use (not serialised to JSON)
        trade_date = datetime.date.fromisoformat(date_str)
        if strategy.get("taken"):
            eod_dt = datetime.datetime.combine(trade_date, datetime.time(16, 0))
            entry_t = datetime.datetime.combine(
                trade_date,
                datetime.time(*[int(x) for x in strategy["entry_time"].split(":")[:2]])
            )
            strategy["entry_dt"] = entry_t

            if strategy["stop_triggered"] and strategy["stop_time"]:
                parts = strategy["stop_time"].split(":")
                stop_t = datetime.datetime.combine(
                    trade_date,
                    datetime.time(*[int(x) for x in parts[:2]])
                )
                strategy["stop_dt"] = stop_t
                strategy["exit_dt"] = stop_t
            else:
                strategy["exit_dt"] = eod_dt

        # Export JSON
        day_json = build_day_json(date_str, day_df, real_spreads, strategy)
        json_path = OUT_DIR / f"{date_str}.json"
        with open(json_path, "w") as f:
            json.dump(day_json, f, indent=2, default=_serial)

        # Draw chart
        out_png = make_chart(date_str, day_df, real_spreads, strategy, day_json)

        taken = strategy.get("taken", False)
        outcome = strategy.get("outcome", "") if taken else "skip"
        pnl = strategy.get("pnl_dollar", 0) if taken else 0
        real_n = len(real_spreads)
        real_pnl = sum(sp["net"] for sp in real_spreads)

        if taken:
            n_trade += 1
        else:
            n_skip += 1

        print(f"  {date_str}  real={real_n} (${real_pnl:+,.0f})  "
              f"strategy={'TRADE' if taken else 'SKIP'} {outcome} ${pnl:+,.0f}"
              f"  → {out_png.name}")

    print(f"\nDone.  {len(ndx_dates)} charts  |  "
          f"{n_trade} strategy trades  |  {n_skip} skipped")
    print(f"Output: {OUT_DIR}")
