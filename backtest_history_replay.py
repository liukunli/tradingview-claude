#!/usr/bin/env python3
"""
NDX Spread History Replay
Reconstructs actual trade history from trades.json using FIFO P&L.
Shows the full picture: all directions, scale-ins, EDT, worst days.
"""

import json
import warnings
from collections import defaultdict
from datetime import datetime, time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

TRADES_PATH = Path(
    "/Users/kunliliu/.claude/skills/tradingview-claude/trading_logs/trades.json"
)
NDX_PATH = Path(
    "/Users/kunliliu/.claude/skills/tradingview-claude/trading_logs/NDX_5min_2026.json"
)
OUT_PATH = Path(
    "/Users/kunliliu/.claude/skills/tradingview-claude/trading_logs/history_replay.png"
)
MULT = 100  # NDX option multiplier


# ─── Data loading ──────────────────────────────────────────────────────────────

def load_trades(path: Path) -> pd.DataFrame:
    with open(path) as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df["datetime"] = pd.to_datetime(df["date"] + " " + df["time"])
    df["date_dt"] = pd.to_datetime(df["date"])
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


def load_ndx_daily(path: Path) -> pd.DataFrame:
    with open(path) as f:
        raw = json.load(f)
    bars = pd.DataFrame(raw["bars"])
    bars["dt_utc"] = pd.to_datetime(bars["datetime_utc"], utc=True)
    bars["dt_et"] = bars["dt_utc"].dt.tz_convert("US/Eastern")
    bars["date_et"] = bars["dt_et"].dt.date
    bars["time_et"] = bars["dt_et"].dt.time
    bars = bars[(bars["time_et"] >= time(9, 30)) & (bars["time_et"] <= time(16, 0))]
    daily = bars.groupby("date_et").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).reset_index()
    daily["date_et"] = pd.to_datetime(daily["date_et"])
    return daily


# ─── P&L computation (FIFO) ────────────────────────────────────────────────────

def compute_fifo_pnl(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-execution realized P&L using FIFO matching.
    Returns a DataFrame of realized P&L events with date, account, direction, pnl.
    """
    records = []
    # separate by account
    for account, adf in df.groupby("account"):
        pos = defaultdict(list)  # symbol → [(qty_remaining, cost_price), ...]

        for _, row in adf.iterrows():
            sym = row["symbol"]
            qty = row["quantity"]
            price = row["price"]
            opt_type = row["option_type"]
            strike = row["strike"]
            expiry = row["expiry"]
            trade_date = row["date"]
            trade_time = row["time"]

            # Determine if this extends or reduces a position
            current_net = sum(q for q, _ in pos[sym])

            if qty == 0:
                continue

            if (current_net >= 0 and qty > 0) or (current_net <= 0 and qty < 0):
                # Extending/opening position
                pos[sym].append((qty, price))
            else:
                # Reducing/closing position
                close_remaining = abs(qty)
                realized = 0.0
                while close_remaining > 0 and pos[sym]:
                    open_qty, open_price = pos[sym][0]
                    sign = 1 if open_qty > 0 else -1
                    matched = min(close_remaining, abs(open_qty))
                    # For a long (sign=1): P&L = (close_price - open_price) * matched * MULT
                    # For a short (sign=-1): P&L = (open_price - close_price) * matched * MULT
                    realized += sign * matched * (price - open_price) * MULT
                    close_remaining -= matched
                    remaining = abs(open_qty) - matched
                    pos[sym][0] = (sign * remaining, open_price) if remaining > 0 else None
                    if pos[sym][0] is None:
                        pos[sym].pop(0)
                if realized != 0:
                    # Determine spread direction from symbol context
                    direction = _infer_direction(sym, qty, current_net, opt_type)
                    records.append({
                        "date": trade_date,
                        "account": account,
                        "symbol": sym,
                        "strike": strike,
                        "expiry": expiry,
                        "option_type": opt_type,
                        "direction": direction,
                        "pnl": realized,
                        "trade_time": trade_time,
                        "is_edt": _is_edt(trade_time, expiry, trade_date),
                    })

    return pd.DataFrame(records)


def _infer_direction(symbol: str, qty: float, net_before: float, opt_type: str) -> str:
    """Infer spread direction from the closing leg characteristics."""
    if opt_type == "P":
        if net_before > 0:  # closing a long put (we bought puts = bearish)
            return "bear_put_long_leg"
        else:  # closing a short put (we sold puts = premium collection)
            return "bear_put_short_leg"
    else:
        if net_before > 0:
            return "bull_call_long_leg"
        else:
            return "bear_call_short_leg"


def _is_edt(trade_time: str, expiry: str, trade_date: str) -> bool:
    """Detect EDT: entry after 14:45 ET for next-day expiry."""
    try:
        t = datetime.strptime(trade_time, "%H:%M:%S").time()
        if t < time(14, 45):
            return False
        exp_date = datetime.strptime(expiry, "%d%b%y").date()
        trd_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
        return exp_date > trd_date
    except Exception:
        return False


# ─── Spread-level grouping ─────────────────────────────────────────────────────

def build_spread_df(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Group individual legs into spreads by (date, account, expiry, option_type)."""
    spreads = []
    for (date, account, expiry, opt_type), grp in trades_df.groupby(
        ["date", "account", "expiry", "option_type"]
    ):
        grp = grp.copy().sort_values("datetime")
        sells = grp[grp["quantity"] < 0]
        buys  = grp[grp["quantity"] > 0]

        if sells.empty or buys.empty:
            continue

        # Net cash flow as a proxy for P&L (using price × qty × MULT)
        cash = (-grp["quantity"] * grp["price"] * MULT).sum()

        # Determine direction: compare highest-K sell vs buy
        max_sell_K = sells["strike"].max()
        max_buy_K  = buys["strike"].max()

        if opt_type == "P":
            direction = "Bear Put" if max_sell_K > max_buy_K else "Bull Put"
        else:
            direction = "Bear Call" if max_sell_K < max_buy_K else "Bull Call"

        first_time = grp["datetime"].iloc[0].time()
        is_edt = (
            any(grp["datetime"].dt.time > time(14, 45))
            and datetime.strptime(expiry, "%d%b%y").date()
               > pd.Timestamp(date).date()
        )
        n_contracts = int(sells["quantity"].abs().sum())

        spreads.append({
            "date": pd.Timestamp(date),
            "account": account,
            "expiry": expiry,
            "option_type": opt_type,
            "direction": direction,
            "is_edt": is_edt,
            "entry_time": first_time,
            "n_contracts": n_contracts,
            "n_legs": len(grp),
            "n_scale_ins": max(0, len(grp) // 2 - 1),
            "cash_pnl": cash,  # rough P&L from cash flows
        })

    df = pd.DataFrame(spreads)
    if df.empty:
        return df
    df = df.sort_values("date").reset_index(drop=True)
    df["win"] = df["cash_pnl"] > 0
    df["cum_pnl"] = df["cash_pnl"].cumsum()
    return df


# ─── Statistics ────────────────────────────────────────────────────────────────

def stats(df: pd.DataFrame, col: str = "cash_pnl") -> dict:
    if df.empty:
        return {}
    n = len(df)
    wins = df[df[col] > 0]
    losses = df[df[col] <= 0]
    wr = len(wins) / n
    avg_win  = wins[col].mean() if len(wins) > 0 else 0
    avg_loss = losses[col].mean() if len(losses) > 0 else 0
    return dict(
        n=n, n_win=len(wins), wr=wr,
        avg=df[col].mean(), total=df[col].sum(),
        avg_win=avg_win, avg_loss=avg_loss,
        ev=wr * avg_win + (1 - wr) * avg_loss,
    )


# ─── Plotting ──────────────────────────────────────────────────────────────────

def plot_history(spreads: pd.DataFrame, ndx_daily: pd.DataFrame):
    fig = plt.figure(figsize=(24, 22))
    fig.suptitle(
        "NDX Spread Strategy — Actual Trade History Replay  ·  Jan–Apr 2026",
        fontsize=18, fontweight="bold", y=0.995,
    )
    gs = gridspec.GridSpec(4, 3, figure=fig, hspace=0.52, wspace=0.38)

    C = {"Bear Put": "#27ae60", "Bull Put": "#e74c3c",
         "Bear Call": "#e67e22", "Bull Call": "#8e44ad",
         "win": "#2ecc71", "loss": "#e74c3c"}

    fmt_k = lambda x, _: f"${x/1000:.0f}K"

    # ── 1. Cumulative P&L by direction ─────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :2])
    directions = spreads["direction"].unique()
    cum_all = spreads.sort_values("date").copy()
    cum_all["cum_all"] = cum_all["cash_pnl"].cumsum()
    ax1.plot(cum_all["date"], cum_all["cum_all"], color="black", lw=2.5,
             label=f"Total  WR={len(cum_all[cum_all.cash_pnl>0])/len(cum_all):.0%}  "
                   f"Total=${cum_all['cash_pnl'].sum():,.0f}")
    ax1.fill_between(cum_all["date"], 0, cum_all["cum_all"],
                     where=cum_all["cum_all"] >= 0, alpha=0.12, color="#27ae60")
    ax1.fill_between(cum_all["date"], 0, cum_all["cum_all"],
                     where=cum_all["cum_all"] < 0, alpha=0.18, color="#e74c3c")
    for d in directions:
        sub = spreads[spreads["direction"] == d].sort_values("date").copy()
        sub["cum"] = sub["cash_pnl"].cumsum()
        st = stats(sub)
        ax1.plot(sub["date"], sub["cum"], color=C.get(d, "gray"), lw=1.5,
                 linestyle="--", alpha=0.75,
                 label=f"{d}  WR={st.get('wr',0):.0%}  ${st.get('total',0):,.0f}")
    ax1.axhline(0, color="black", lw=0.8, ls="--", alpha=0.5)
    ax1.set_title("Cumulative P&L — Total & By Direction", fontweight="bold")
    ax1.set_ylabel("P&L ($)")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(fmt_k))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax1.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2))
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax1.legend(fontsize=8.5, loc="upper left")
    ax1.grid(True, alpha=0.3)

    # ── 2. Summary table by direction ────────────────────────────────────────
    ax_tbl = fig.add_subplot(gs[0, 2])
    ax_tbl.axis("off")
    rows = [["Direction", "N", "WR", "Avg P&L", "Total"]]
    dir_order = ["Bear Put", "Bull Put", "Bear Call", "Bull Call"]
    for d in dir_order:
        sub = spreads[spreads["direction"] == d]
        st = stats(sub)
        if st:
            rows.append([d, str(st["n"]),
                         f"{st['wr']:.0%}",
                         f"${st['avg']:,.0f}",
                         f"${st['total']:,.0f}"])
    # Total
    st_all = stats(spreads)
    rows.append(["TOTAL", str(st_all.get("n",0)),
                 f"{st_all.get('wr',0):.0%}",
                 f"${st_all.get('avg',0):,.0f}",
                 f"${st_all.get('total',0):,.0f}"])

    tbl = ax_tbl.table(rows[1:], colLabels=rows[0], loc="center", cellLoc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)
    tbl.scale(1.1, 1.65)
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#2c3e50")
            cell.set_text_props(color="white", fontweight="bold")
        elif c == 0 and r > 0:
            dir_name = rows[r][0]
            cell.set_facecolor({
                "Bear Put": "#d5f5e3", "Bull Put": "#fadbd8",
                "Bear Call": "#fdebd0", "Bull Call": "#e8daef",
                "TOTAL": "#d6eaf8"
            }.get(dir_name, "white"))
    ax_tbl.set_title("Performance by Direction", fontweight="bold", pad=10)

    # ── 3. Daily P&L bars ────────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, :2])
    daily = spreads.groupby("date")["cash_pnl"].sum().reset_index()
    colors = [C["win"] if p > 0 else C["loss"] for p in daily["cash_pnl"]]
    ax3.bar(daily["date"], daily["cash_pnl"], color=colors, alpha=0.85, width=0.8)
    # Mark EDT days
    edt_days = spreads[spreads["is_edt"]]["date"].unique()
    for ed in edt_days:
        d_pnl = daily[daily["date"] == ed]["cash_pnl"].values
        if len(d_pnl):
            ax3.annotate("E", (ed, d_pnl[0]),
                         ha="center",
                         va="bottom" if d_pnl[0] > 0 else "top",
                         fontsize=7, color="#7f8c8d", fontweight="bold")
    ax3.axhline(0, color="black", lw=0.8, ls="--")
    ax3.set_title("Daily P&L — All Directions  (E = EDT/overnight trade)", fontweight="bold")
    ax3.set_ylabel("P&L ($)")
    ax3.yaxis.set_major_formatter(plt.FuncFormatter(fmt_k))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax3.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2))
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax3.grid(True, alpha=0.3, axis="y")
    ax3.legend(handles=[
        mpatches.Patch(color=C["win"], label=f"Win ({(daily['cash_pnl']>0).sum()})"),
        mpatches.Patch(color=C["loss"], label=f"Loss ({(daily['cash_pnl']<=0).sum()})"),
    ])

    # ── 4. Win rate by direction (bar chart) ─────────────────────────────────
    ax4 = fig.add_subplot(gs[1, 2])
    dir_stats = {}
    for d in dir_order:
        sub = spreads[spreads["direction"] == d]
        st = stats(sub)
        if st and st["n"] > 0:
            dir_stats[d] = st
    if dir_stats:
        labels = list(dir_stats.keys())
        wrs = [dir_stats[d]["wr"] * 100 for d in labels]
        evs = [dir_stats[d]["ev"] for d in labels]
        bar_colors = [C.get(d, "gray") for d in labels]
        x = np.arange(len(labels))
        bars_wr = ax4.bar(x, wrs, color=bar_colors, alpha=0.8, edgecolor="white")
        ax4.axhline(50, color="black", lw=1, ls="--", alpha=0.4)
        ax4.set_xticks(x)
        ax4.set_xticklabels([l.replace(" ", "\n") for l in labels], fontsize=9)
        for i, (d, wr, ev) in enumerate(zip(labels, wrs, evs)):
            ax4.text(i, wr + 1, f"{wr:.0f}%\nEV ${ev:,.0f}",
                     ha="center", va="bottom", fontsize=8)
    ax4.set_title("Win Rate & EV by Direction", fontweight="bold")
    ax4.set_ylabel("Win Rate (%)")
    ax4.set_ylim(0, 100)
    ax4.grid(True, alpha=0.3, axis="y")

    # ── 5. Scale-in behavior ─────────────────────────────────────────────────
    ax5 = fig.add_subplot(gs[2, 0])
    scale_groups = spreads.groupby("n_scale_ins")["cash_pnl"].agg(
        count="count", mean="mean", wr=lambda x: (x > 0).mean()
    ).reset_index()
    bar_colors5 = ["#27ae60" if m > 0 else "#e74c3c" for m in scale_groups["mean"]]
    ax5.bar(scale_groups["n_scale_ins"], scale_groups["mean"],
            color=bar_colors5, alpha=0.8, edgecolor="white")
    for _, row in scale_groups.iterrows():
        ax5.text(row["n_scale_ins"], row["mean"] + (200 if row["mean"] >= 0 else -200),
                 f"N={int(row['count'])}\n{row['wr']:.0%} WR",
                 ha="center", va="bottom" if row["mean"] >= 0 else "top", fontsize=8)
    ax5.axhline(0, color="black", lw=0.8, ls="--")
    ax5.set_title("Avg P&L by Scale-In Count\n(0=no adds, 1=one add, etc.)", fontweight="bold")
    ax5.set_xlabel("# Scale-Ins")
    ax5.set_ylabel("Avg P&L ($)")
    ax5.yaxis.set_major_formatter(plt.FuncFormatter(fmt_k))
    ax5.grid(True, alpha=0.3, axis="y")

    # ── 6. Entry timing ──────────────────────────────────────────────────────
    ax6 = fig.add_subplot(gs[2, 1])
    def time_bucket(t):
        m = t.hour * 60 + t.minute if hasattr(t, "hour") else 999
        if m < 9 * 60 + 30: return "pre"
        if m < 10 * 60:      return "9:30–10:00"
        if m <= 10 * 60 + 30: return "★10:00–10:30"
        if m < 12 * 60:      return "10:30–12:00"
        if m < 14 * 60:      return "12:00–14:00"
        if m < 15 * 60:      return "14:00–15:00"
        return "EDT 15:00+"

    spreads["bucket"] = spreads["entry_time"].apply(time_bucket)
    bucket_order = ["9:30–10:00", "★10:00–10:30", "10:30–12:00",
                    "12:00–14:00", "14:00–15:00", "EDT 15:00+"]
    bucket_stats = spreads.groupby("bucket")["cash_pnl"].agg(
        count="count", mean="mean", wr=lambda x: (x > 0).mean()
    ).reindex(bucket_order).dropna()
    bucket_colors = ["#27ae60" if m > 0 else "#e74c3c" for m in bucket_stats["mean"]]
    x6 = np.arange(len(bucket_stats))
    ax6.bar(x6, bucket_stats["mean"], color=bucket_colors, alpha=0.8, edgecolor="white")
    ax6.axhline(0, color="black", lw=0.8, ls="--")
    ax6.set_xticks(x6)
    ax6.set_xticklabels(
        [b.replace("★", "") for b in bucket_stats.index],
        rotation=30, ha="right", fontsize=8
    )
    for i, (idx, row) in enumerate(bucket_stats.iterrows()):
        ax6.text(i, row["mean"] + (100 if row["mean"] >= 0 else -100),
                 f"N={int(row['count'])}\n{row['wr']:.0%}",
                 ha="center", va="bottom" if row["mean"] >= 0 else "top", fontsize=7.5)
    ax6.set_title("Avg P&L by Entry Time Window\n(★ = prime window)", fontweight="bold")
    ax6.set_ylabel("Avg P&L ($)")
    ax6.yaxis.set_major_formatter(plt.FuncFormatter(fmt_k))
    ax6.grid(True, alpha=0.3, axis="y")

    # ── 7. EDT vs Non-EDT ────────────────────────────────────────────────────
    ax7 = fig.add_subplot(gs[2, 2])
    edt_grp = spreads.groupby("is_edt")["cash_pnl"].agg(
        count="count", mean="mean", total="sum", wr=lambda x: (x > 0).mean()
    )
    edt_labels = {False: "Non-EDT\n(same-day)", True: "EDT\n(overnight)"}
    for i, (is_edt, row) in enumerate(edt_grp.iterrows()):
        color = "#e74c3c" if row["mean"] < 0 else "#27ae60"
        ax7.bar(i, row["mean"], color=color, alpha=0.8, edgecolor="white", width=0.5)
        ax7.text(i, row["mean"] + (200 if row["mean"] >= 0 else -200),
                 f"N={int(row['count'])}\n{row['wr']:.0%} WR\n${row['total']:,.0f}",
                 ha="center", va="bottom" if row["mean"] >= 0 else "top", fontsize=9)
    ax7.set_xticks([0, 1])
    ax7.set_xticklabels([edt_labels[False], edt_labels[True]], fontsize=10)
    ax7.axhline(0, color="black", lw=0.8, ls="--")
    ax7.set_title("EDT vs Non-EDT Performance", fontweight="bold")
    ax7.set_ylabel("Avg P&L ($)")
    ax7.yaxis.set_major_formatter(plt.FuncFormatter(fmt_k))
    ax7.grid(True, alpha=0.3, axis="y")

    # ── 8. NDX price with trade overlays ────────────────────────────────────
    ax8 = fig.add_subplot(gs[3, :])
    if ndx_daily is not None and not ndx_daily.empty:
        ax8.plot(ndx_daily["date_et"], ndx_daily["close"],
                 color="#2c3e50", lw=1.2, alpha=0.9, label="NDX close")
        ax8.fill_between(ndx_daily["date_et"], ndx_daily["low"], ndx_daily["high"],
                         alpha=0.08, color="#2c3e50")

    for d in dir_order:
        sub = spreads[spreads["direction"] == d]
        if sub.empty:
            continue
        wins_s  = sub[sub["cash_pnl"] > 0]
        losses_s = sub[sub["cash_pnl"] <= 0]
        marker = {"Bear Put": "^", "Bull Put": "v", "Bear Call": "D", "Bull Call": "s"}[d]
        if not wins_s.empty:
            ax8.scatter(wins_s["date"], [None]*len(wins_s), marker=marker,
                        color=C.get(d, "gray"), s=50, zorder=5,
                        label=f"{d} Win", alpha=0.85)
        if not losses_s.empty:
            ax8.scatter(losses_s["date"], [None]*len(losses_s), marker=marker,
                        color=C.get(d, "gray"), s=50, zorder=5,
                        edgecolors="red", linewidth=1.5, label=f"{d} Loss", alpha=0.85)

    # Overlay P&L as colored regions on the price chart
    daily2 = spreads.groupby("date")["cash_pnl"].sum().reset_index()
    if ndx_daily is not None:
        for _, drow in daily2.iterrows():
            color = "#27ae60" if drow["cash_pnl"] > 0 else "#e74c3c"
            ax8.axvline(drow["date"], color=color, alpha=0.18, lw=6)

    ax8.set_title("NDX Price Timeline  (green/red shading = winning/losing trading days)", fontweight="bold")
    ax8.set_ylabel("NDX Level")
    ax8.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax8.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=1))
    plt.setp(ax8.xaxis.get_majorticklabels(), rotation=45, ha="right")
    ax8.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax8.grid(True, alpha=0.25)

    plt.savefig(OUT_PATH, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"\nPlot saved → {OUT_PATH}")
    plt.close(fig)


# ─── Main ──────────────────────────────────────────────────────────────────────

def print_summary(spreads: pd.DataFrame):
    st = stats(spreads)
    print(f"\n{'='*60}")
    print("HISTORY REPLAY SUMMARY")
    print(f"{'='*60}")
    print(f"Total spreads: {st.get('n',0)}")
    print(f"Win Rate:      {st.get('wr',0):.1%}")
    print(f"Avg P&L:       ${st.get('avg',0):,.0f}")
    print(f"Avg Win:       ${st.get('avg_win',0):,.0f}")
    print(f"Avg Loss:      ${st.get('avg_loss',0):,.0f}")
    print(f"EV/trade:      ${st.get('ev',0):,.0f}")
    print(f"Total P&L:     ${st.get('total',0):,.0f}")
    print()

    print("By direction:")
    for d in ["Bear Put", "Bull Put", "Bear Call", "Bull Call"]:
        sub = spreads[spreads["direction"] == d]
        if sub.empty:
            continue
        s = stats(sub)
        print(f"  {d:12s}: N={s['n']:3d}  WR={s['wr']:.0%}  "
              f"Avg=${s['avg']:>8,.0f}  Total=${s['total']:>10,.0f}")

    print()
    print("EDT trades:")
    edt = spreads[spreads["is_edt"]]
    non_edt = spreads[~spreads["is_edt"]]
    se = stats(edt)
    sn = stats(non_edt)
    print(f"  EDT:     N={se.get('n',0):3d}  WR={se.get('wr',0):.0%}  "
          f"Avg=${se.get('avg',0):>8,.0f}  Total=${se.get('total',0):>10,.0f}")
    print(f"  Non-EDT: N={sn.get('n',0):3d}  WR={sn.get('wr',0):.0%}  "
          f"Avg=${sn.get('avg',0):>8,.0f}  Total=${sn.get('total',0):>10,.0f}")

    print()
    print("Worst 5 days:")
    daily = spreads.groupby("date")["cash_pnl"].sum().reset_index()
    worst = daily.nsmallest(5, "cash_pnl")
    for _, row in worst.iterrows():
        print(f"  {row['date'].strftime('%Y-%m-%d')}:  ${row['cash_pnl']:>10,.0f}")

    print()
    print("Scale-in behavior:")
    sg = spreads.groupby("n_scale_ins").agg(
        count=("cash_pnl", "count"),
        wr=("cash_pnl", lambda x: (x > 0).mean()),
        avg=("cash_pnl", "mean"),
    )
    for idx, row in sg.iterrows():
        print(f"  {idx} adds: N={int(row['count']):3d}  WR={row['wr']:.0%}  "
              f"Avg=${row['avg']:>8,.0f}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    print("Loading trades...")
    trades = load_trades(TRADES_PATH)
    print(f"  {len(trades)} legs  |  {trades['account'].nunique()} accounts  |  "
          f"{trades['date'].min()} → {trades['date'].max()}")

    print("Loading NDX daily data...")
    try:
        ndx_daily = load_ndx_daily(NDX_PATH)
        print(f"  {len(ndx_daily)} trading days")
    except Exception as e:
        print(f"  NDX data unavailable: {e}")
        ndx_daily = None

    print("Building spread-level P&L...")
    spreads = build_spread_df(trades)
    print(f"  {len(spreads)} spread groups identified")

    print_summary(spreads)

    print("Generating history replay plot...")
    plot_history(spreads, ndx_daily)
