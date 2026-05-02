#!/usr/bin/env python3
"""Plot NDX 5-min intraday chart with VWAP, EMAs, RSI, MACD, Volume."""

import warnings
warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from datetime import datetime, date
import sys

# ── fetch ──────────────────────────────────────────────────────────────────
print("Fetching NDX 5-min data...", flush=True)
ticker = yf.Ticker("^NDX")
df = ticker.history(period="2d", interval="5m")
if df.empty:
    print("ERROR: No data returned for ^NDX", file=sys.stderr)
    sys.exit(1)

df.index = df.index.tz_convert("America/New_York")

# Keep only the last trading day (today or most recent session)
last_date = df.index.normalize().max()
df = df[df.index.normalize() == last_date].copy()
print(f"  Got {len(df)} bars for {last_date.date()}", flush=True)

# ── indicators ─────────────────────────────────────────────────────────────
# VWAP  (reset each day)
df["tp"] = (df["High"] + df["Low"] + df["Close"]) / 3
df["cum_tvp"] = (df["tp"] * df["Volume"]).cumsum()
df["cum_vol"] = df["Volume"].cumsum()
df["VWAP"] = df["cum_tvp"] / df["cum_vol"]

# EMA 9 / EMA 20
df["EMA9"]  = df["Close"].ewm(span=9,  adjust=False).mean()
df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()

# RSI 14
delta = df["Close"].diff()
gain  = delta.clip(lower=0)
loss  = -delta.clip(upper=0)
avg_gain = gain.ewm(com=13, adjust=False).mean()
avg_loss = loss.ewm(com=13, adjust=False).mean()
rs = avg_gain / avg_loss.replace(0, np.nan)
df["RSI"] = 100 - 100 / (1 + rs)

# MACD (12-26-9)
ema12 = df["Close"].ewm(span=12, adjust=False).mean()
ema26 = df["Close"].ewm(span=26, adjust=False).mean()
df["MACD"]   = ema12 - ema26
df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
df["Hist"]   = df["MACD"] - df["Signal"]

# ── plot ───────────────────────────────────────────────────────────────────
DARK_BG   = "#131722"
PANEL_BG  = "#1e222d"
GRID_CLR  = "#2a2e39"
TEXT_CLR  = "#d1d4dc"
UP_CLR    = "#26a69a"
DN_CLR    = "#ef5350"
VWAP_CLR  = "#9b59b6"
EMA9_CLR  = "#3498db"
EMA20_CLR = "#f39c12"
VOL_CLR   = "#555f6e"

plt.rcParams.update({
    "figure.facecolor":  DARK_BG,
    "axes.facecolor":    PANEL_BG,
    "axes.edgecolor":    GRID_CLR,
    "axes.labelcolor":   TEXT_CLR,
    "xtick.color":       TEXT_CLR,
    "ytick.color":       TEXT_CLR,
    "xtick.labelcolor":  TEXT_CLR,
    "ytick.labelcolor":  TEXT_CLR,
    "text.color":        TEXT_CLR,
    "grid.color":        GRID_CLR,
    "grid.linewidth":    0.4,
})

fig = plt.figure(figsize=(18, 14), facecolor=DARK_BG)
gs = GridSpec(5, 1, figure=fig,
              height_ratios=[4, 1.2, 1, 1, 1],
              hspace=0.04)

ax_price  = fig.add_subplot(gs[0])
ax_vol    = fig.add_subplot(gs[1], sharex=ax_price)
ax_rsi    = fig.add_subplot(gs[2], sharex=ax_price)
ax_macd   = fig.add_subplot(gs[3], sharex=ax_price)
ax_hist   = fig.add_subplot(gs[4], sharex=ax_price)

x = np.arange(len(df))

# ─ Candlesticks ─
for i, (idx, row) in enumerate(df.iterrows()):
    color = UP_CLR if row["Close"] >= row["Open"] else DN_CLR
    # wick
    ax_price.plot([i, i], [row["Low"], row["High"]], color=color, lw=0.8, zorder=2)
    # body
    body_lo = min(row["Open"], row["Close"])
    body_hi = max(row["Open"], row["Close"])
    ax_price.bar(i, body_hi - body_lo, bottom=body_lo,
                 color=color, width=0.7, zorder=3)

# Overlays
ax_price.plot(x, df["VWAP"],  color=VWAP_CLR,  lw=1.4, label="VWAP",  zorder=4)
ax_price.plot(x, df["EMA9"],  color=EMA9_CLR,  lw=1.0, label="EMA 9", zorder=4, ls="--")
ax_price.plot(x, df["EMA20"], color=EMA20_CLR, lw=1.0, label="EMA 20",zorder=4, ls="--")

ax_price.set_facecolor(PANEL_BG)
ax_price.grid(True, alpha=0.4)
ax_price.set_ylabel("NDX", color=TEXT_CLR, fontsize=10)

leg = ax_price.legend(loc="upper left", fontsize=8,
                      facecolor=PANEL_BG, edgecolor=GRID_CLR,
                      labelcolor=TEXT_CLR)

# Price stats annotation
o = df["Open"].iloc[0];  c = df["Close"].iloc[-1]
h = df["High"].max();    l = df["Low"].min()
chg = (c - o) / o * 100
arrow = "▲" if chg >= 0 else "▼"
chg_color = UP_CLR if chg >= 0 else DN_CLR
ax_price.set_title(
    f"NDX  |  {last_date.date()}  |  5-min  "
    f"O:{o:,.0f}  H:{h:,.0f}  L:{l:,.0f}  C:{c:,.0f}  "
    f"{arrow} {chg:+.2f}%",
    color=TEXT_CLR, fontsize=11, pad=8
)

# ─ Volume ─
vol_colors = [UP_CLR if df["Close"].iloc[i] >= df["Open"].iloc[i] else DN_CLR
              for i in range(len(df))]
ax_vol.bar(x, df["Volume"], color=vol_colors, width=0.7, alpha=0.7)
ax_vol.set_facecolor(PANEL_BG)
ax_vol.grid(True, alpha=0.4)
ax_vol.set_ylabel("Vol", color=TEXT_CLR, fontsize=8)
ax_vol.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v/1e6:.1f}M"))

# ─ RSI ─
ax_rsi.plot(x, df["RSI"], color="#e74c3c", lw=1.2)
ax_rsi.axhline(70, color=DN_CLR, lw=0.6, ls="--", alpha=0.7)
ax_rsi.axhline(50, color=TEXT_CLR, lw=0.4, ls=":", alpha=0.5)
ax_rsi.axhline(30, color=UP_CLR,  lw=0.6, ls="--", alpha=0.7)
ax_rsi.fill_between(x, df["RSI"], 70, where=(df["RSI"] >= 70),
                    color=DN_CLR, alpha=0.15)
ax_rsi.fill_between(x, df["RSI"], 30, where=(df["RSI"] <= 30),
                    color=UP_CLR, alpha=0.15)
ax_rsi.set_ylim(0, 100)
ax_rsi.set_facecolor(PANEL_BG)
ax_rsi.grid(True, alpha=0.4)
ax_rsi.set_ylabel("RSI", color=TEXT_CLR, fontsize=8)
ax_rsi.set_yticks([30, 50, 70])

# ─ MACD line + signal ─
ax_macd.plot(x, df["MACD"],   color=EMA9_CLR,  lw=1.2, label="MACD")
ax_macd.plot(x, df["Signal"], color=EMA20_CLR, lw=1.0, label="Signal", ls="--")
ax_macd.axhline(0, color=TEXT_CLR, lw=0.4, ls=":", alpha=0.5)
ax_macd.set_facecolor(PANEL_BG)
ax_macd.grid(True, alpha=0.4)
ax_macd.set_ylabel("MACD", color=TEXT_CLR, fontsize=8)
ax_macd.legend(loc="upper left", fontsize=7, facecolor=PANEL_BG,
               edgecolor=GRID_CLR, labelcolor=TEXT_CLR)

# ─ MACD Histogram ─
hist_colors = [UP_CLR if v >= 0 else DN_CLR for v in df["Hist"]]
ax_hist.bar(x, df["Hist"], color=hist_colors, width=0.7, alpha=0.8)
ax_hist.axhline(0, color=TEXT_CLR, lw=0.4, ls=":", alpha=0.5)
ax_hist.set_facecolor(PANEL_BG)
ax_hist.grid(True, alpha=0.4)
ax_hist.set_ylabel("Hist", color=TEXT_CLR, fontsize=8)

# ─ X-axis labels (time) ─
step = max(1, len(df) // 10)
ticks = x[::step]
labels = [df.index[i].strftime("%H:%M") for i in ticks]
ax_hist.set_xticks(ticks)
ax_hist.set_xticklabels(labels, fontsize=8, rotation=0)
for ax in [ax_price, ax_vol, ax_rsi, ax_macd]:
    plt.setp(ax.get_xticklabels(), visible=False)

# ─ Save ─
out = f"/Users/kunliliu/Documents/GitHub/tradingview-claude/trading_logs/viz/ndx_5min_{last_date.date()}_intraday.png"
plt.savefig(out, dpi=140, bbox_inches="tight", facecolor=DARK_BG)
print(f"Saved → {out}", flush=True)
