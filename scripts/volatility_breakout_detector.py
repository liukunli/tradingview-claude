"""
1-Min Volatility Breakout Detector
- Computes rolling ATR on 1-min bars
- Identifies consolidation zones (low-vol squeezes)
- Flags previous breakouts from those zones
- Plots the last N sessions with annotations
"""

import argparse
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

SESSION_START = "09:30"
SESSION_END   = "16:00"
DATA_PATH     = "ndx_spy_historical_data/ndx_1min.csv"


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"]  - prev_close).abs(),
    ], axis=1).max(axis=1)


def load_data(path: str, rth_only: bool = True) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["datetime_et"])
    df = df.sort_values("datetime_et").reset_index(drop=True)
    if rth_only:
        t = df["datetime_et"].dt.time
        df = df[(t >= pd.Timestamp(SESSION_START).time()) &
                (t <= pd.Timestamp(SESSION_END).time())].copy()
    return df


def compute_volatility(df: pd.DataFrame, atr_period: int, vol_lookback: int,
                        range_lookback: int, squeeze_pct: float = 25.0) -> pd.DataFrame:
    df = df.copy()
    df["tr"]  = true_range(df)
    df["atr"] = df["tr"].rolling(atr_period).mean()

    def pct_rank(s):
        return s.rank(pct=True).iloc[-1] * 100

    df["atr_pct"] = (
        df["atr"]
        .rolling(vol_lookback)
        .apply(pct_rank, raw=False)
    )
    df["range_high"] = df["high"].rolling(range_lookback).max()
    df["range_low"]  = df["low"].rolling(range_lookback).min()

    in_squeeze = df["atr_pct"] <= squeeze_pct
    df["squeeze_bars"] = in_squeeze.groupby((~in_squeeze).cumsum()).cumcount()
    return df


def detect_breakouts(df: pd.DataFrame, squeeze_pct: float, breakout_pct: float,
                     min_consol_bars: int, range_lookback: int,
                     vol_lookback: int) -> pd.DataFrame:
    df = df.copy()
    breakouts = []
    start = range_lookback + vol_lookback

    for i in range(start, len(df)):
        row  = df.iloc[i]
        prev = df.iloc[i - 1]

        if prev["squeeze_bars"] < min_consol_bars:
            continue
        if row["atr_pct"] < breakout_pct:
            continue

        consol_high = prev["range_high"]
        consol_low  = prev["range_low"]

        direction = None
        if row["close"] > consol_high:
            direction = "up"
        elif row["close"] < consol_low:
            direction = "down"

        if direction:
            breakouts.append({
                "datetime":     row["datetime_et"],
                "close":        row["close"],
                "atr_pct":      row["atr_pct"],
                "consol_high":  consol_high,
                "consol_low":   consol_low,
                "squeeze_bars": int(prev["squeeze_bars"]),
                "direction":    direction,
            })

    return pd.DataFrame(breakouts)


def plot(df: pd.DataFrame, breakouts: pd.DataFrame, squeeze_pct: float,
         breakout_pct: float, min_consol_bars: int, plot_days: int, out_path: Path):
    dates      = df["datetime_et"].dt.date.unique()
    last_dates = sorted(dates)[-plot_days:]
    mask = df["datetime_et"].dt.date.isin(last_dates)
    sub  = df[mask].copy()
    bo   = breakouts[breakouts["datetime"].dt.date.isin(last_dates)].copy() if not breakouts.empty else pd.DataFrame()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 10), sharex=True,
                                    gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor("#0d1117")
    for ax in (ax1, ax2):
        ax.set_facecolor("#0d1117")
        ax.tick_params(colors="white")
        ax.spines[:].set_color("#333")

    ax1.plot(sub["datetime_et"], sub["close"], color="#58a6ff", linewidth=0.8, label="NDX 1-min")

    # shade squeeze zones
    in_sq   = sub["squeeze_bars"] >= min_consol_bars
    changes = in_sq.ne(in_sq.shift())
    sq_starts = sub[changes & in_sq]["datetime_et"].tolist()
    sq_ends   = sub[changes.shift(-1, fill_value=False) & in_sq]["datetime_et"].tolist()
    for s, e in zip(sq_starts, sq_ends):
        ax1.axvspan(s, e, alpha=0.15, color="#f0e68c")

    # breakout markers
    if not bo.empty:
        for _, b in bo.iterrows():
            color  = "#3fb950" if b["direction"] == "up" else "#f85149"
            marker = "^" if b["direction"] == "up" else "v"
            offset = b["close"] * (1.002 if b["direction"] == "up" else 0.998)
            ax1.scatter(b["datetime"], offset, color=color, marker=marker, s=120, zorder=5)
            ax1.annotate(
                f"BO {b['direction'].upper()}\n{b['squeeze_bars']}b",
                xy=(b["datetime"], b["close"]),
                xytext=(0, 20 if b["direction"] == "up" else -30),
                textcoords="offset points",
                fontsize=6, color=color, ha="center",
            )

    ax1.set_ylabel("Price", color="white")
    ax1.set_title(
        f"NDX 1-Min — Volatility Squeeze & Breakout Detection (last {plot_days} days)",
        color="white", fontsize=13,
    )
    handles = [
        plt.Line2D([0], [0], color="#58a6ff", label="NDX close"),
        plt.Rectangle((0,0), 1, 1, color="#f0e68c", alpha=0.3, label=f"Squeeze (ATR%ile ≤{squeeze_pct})"),
        plt.scatter([], [], color="#3fb950", marker="^", label="Breakout UP"),
        plt.scatter([], [], color="#f85149", marker="v", label="Breakout DOWN"),
    ]
    ax1.legend(handles=handles, facecolor="#161b22", labelcolor="white", fontsize=8)

    ax2.plot(sub["datetime_et"], sub["atr_pct"], color="#bc8cff", linewidth=0.7)
    ax2.axhline(squeeze_pct,  color="#f0e68c", linestyle="--", linewidth=0.8, alpha=0.7,
                label=f"Squeeze <{squeeze_pct}%")
    ax2.axhline(breakout_pct, color="#f85149", linestyle="--", linewidth=0.8, alpha=0.7,
                label=f"Breakout >{breakout_pct}%")
    ax2.fill_between(sub["datetime_et"], 0, sub["atr_pct"],
                     where=sub["atr_pct"] <= squeeze_pct,
                     alpha=0.3, color="#f0e68c")
    ax2.set_ylabel("ATR %ile", color="white")
    ax2.set_ylim(0, 100)
    ax2.legend(facecolor="#161b22", labelcolor="white", fontsize=8)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M"))
    plt.xticks(rotation=30, ha="right", color="white")

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"Chart saved → {out_path}")


def print_summary(breakouts: pd.DataFrame):
    if breakouts.empty:
        print("No breakouts detected.")
        return
    print(f"\n{'='*72}")
    print(f"  VOLATILITY BREAKOUT SUMMARY — {len(breakouts)} events detected")
    print(f"{'='*72}")
    print(f"{'Date/Time':<22} {'Dir':<6} {'Close':>10} {'ATR%':>7} "
          f"{'Sq.Bars':>8} {'ConsolHigh':>12} {'ConsolLow':>11}")
    print("-" * 72)
    for _, r in breakouts.tail(30).iterrows():
        arrow = "▲" if r["direction"] == "up" else "▼"
        print(f"{str(r['datetime']):<22} {arrow:<6} {r['close']:>10.2f} "
              f"{r['atr_pct']:>7.1f} {r['squeeze_bars']:>8} "
              f"{r['consol_high']:>12.2f} {r['consol_low']:>11.2f}")
    print(f"\nUp breakouts  : {(breakouts['direction']=='up').sum()}")
    print(f"Down breakouts: {(breakouts['direction']=='down').sum()}")
    print(f"Avg squeeze duration: {breakouts['squeeze_bars'].mean():.1f} bars")


def main():
    parser = argparse.ArgumentParser(description="1-Min Volatility Breakout Detector")
    parser.add_argument("--data",         default=DATA_PATH)
    parser.add_argument("--plot-days",    default=5,    type=int)
    parser.add_argument("--atr-period",   default=20,   type=int,   help="ATR smoothing bars")
    parser.add_argument("--vol-lookback", default=60,   type=int,   help="Percentile rank window")
    parser.add_argument("--range-lookback", default=30, type=int,   help="Consolidation range window")
    parser.add_argument("--squeeze-pct",  default=25.0, type=float, help="ATR percentile = squeeze")
    parser.add_argument("--breakout-pct", default=75.0, type=float, help="ATR percentile = breakout")
    parser.add_argument("--min-consol",   default=10,   type=int,   help="Min bars in squeeze")
    parser.add_argument("--no-plot",      action="store_true")
    parser.add_argument("--out",          default="scripts/volatility_breakout.png")
    args = parser.parse_args()

    print(f"Loading {args.data} ...")
    df = load_data(args.data)
    print(f"  {len(df):,} RTH bars ({df['datetime_et'].dt.date.nunique()} trading days)")

    print("Computing volatility ...")
    df = compute_volatility(df, args.atr_period, args.vol_lookback,
                            args.range_lookback, args.squeeze_pct)

    print("Detecting breakouts ...")
    breakouts = detect_breakouts(
        df, args.squeeze_pct, args.breakout_pct,
        args.min_consol, args.range_lookback, args.vol_lookback,
    )
    print(f"  {len(breakouts)} breakout events found")

    print_summary(breakouts)

    if not args.no_plot:
        plot(df, breakouts, args.squeeze_pct, args.breakout_pct,
             args.min_consol, args.plot_days, Path(args.out))


if __name__ == "__main__":
    main()
