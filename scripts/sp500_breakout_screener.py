"""
S&P 500 Volatility + Volume Breakout Screener
- Fetches recent 5-min bars for all 427 S&P 500 stocks via Alpaca
- Runs volatility squeeze + breakout detection on each
- Requires volume surge confirmation (≥ VOL_SURGE_MULT × rolling avg)
- Ranks and reports stocks with recent breakout signals
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

try:
    import requests
except ImportError:
    print("pip install requests", file=sys.stderr); sys.exit(1)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "vcp-screener", "scripts"))
from alpaca_client import _SP500

# ── Defaults ──────────────────────────────────────────────────────────────────
TIMEFRAME       = "5Min"
LOOKBACK_DAYS   = 5       # trading days of intraday data to fetch
ATR_PERIOD      = 10      # bars for rolling ATR
VOL_LOOKBACK    = 30      # bars to compute ATR percentile rank
RANGE_LOOKBACK  = 20      # bars to define consolidation range
SQUEEZE_PCT     = 30.0    # ATR percentile ≤ this = squeeze
BREAKOUT_PCT    = 70.0    # ATR percentile ≥ this = breakout expansion
MIN_CONSOL_BARS = 4       # min bars in squeeze before breakout qualifies
VOL_AVG_PERIOD  = 20      # bars for rolling volume average
VOL_SURGE_MULT  = 2.0     # breakout bar must have volume ≥ this × rolling avg
RECENCY_HOURS   = 24      # only flag breakouts within last N hours
BATCH_SIZE      = 100     # symbols per Alpaca API call
DATA_BASE_URL   = "https://data.alpaca.markets/v2"

SESSION_START = "09:30"
SESSION_END   = "16:00"

TIMEFRAME_YF_MAP = {
    "1Min": "1m", "5Min": "5m", "15Min": "15m", "30Min": "30m",
    "1Hour": "60m", "1Day": "1d",
}


# ── Alpaca intraday fetch ──────────────────────────────────────────────────────

def _alpaca_headers() -> dict:
    key    = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID", "")
    secret = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY", "")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def fetch_intraday_batch(symbols: list[str], days: int = LOOKBACK_DAYS,
                          timeframe: str = TIMEFRAME) -> dict[str, pd.DataFrame]:
    """Fetch intraday bars for a batch of symbols. Returns {symbol: DataFrame}."""
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days + 3)  # +3 for weekends
    params = {
        "symbols":   ",".join(symbols),
        "timeframe": timeframe,
        "start":     start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end":       end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit":     10000,
        "adjustment": "raw",
        "feed":      "iex",
    }

    results = {}
    next_token = None

    while True:
        if next_token:
            params["page_token"] = next_token

        try:
            r = requests.get(f"{DATA_BASE_URL}/stocks/bars",
                             headers=_alpaca_headers(), params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(1)
                continue
            if r.status_code != 200:
                break
            data = r.json()
        except Exception:
            break

        bars_dict = data.get("bars", {}) or {}
        for sym, bars in bars_dict.items():
            rows = [{
                "datetime_et": pd.Timestamp(b["t"]).tz_convert("America/New_York").tz_localize(None),
                "open":  b["o"], "high": b["h"], "low": b["l"],
                "close": b["c"], "volume": b["v"],
            } for b in bars]
            if sym in results:
                results[sym] = pd.concat([results[sym], pd.DataFrame(rows)], ignore_index=True)
            else:
                results[sym] = pd.DataFrame(rows)

        next_token = data.get("next_page_token")
        if not next_token:
            break

    # filter RTH only
    filtered = {}
    for sym, df in results.items():
        if df.empty:
            continue
        t = df["datetime_et"].dt.time
        df = df[(t >= pd.Timestamp(SESSION_START).time()) &
                (t <= pd.Timestamp(SESSION_END).time())].copy()
        df = df.sort_values("datetime_et").reset_index(drop=True)
        if len(df) >= (ATR_PERIOD + VOL_LOOKBACK + RANGE_LOOKBACK + MIN_CONSOL_BARS + 2):
            filtered[sym] = df
    return filtered


# ── yfinance fallback ─────────────────────────────────────────────────────────

def _last_trading_day():
    """Most recent weekday in UTC."""
    d = datetime.now(timezone.utc).date()
    while d.weekday() >= 5:          # Sat=5, Sun=6
        d -= timedelta(days=1)
    return d


def _iex_is_stale(data: dict) -> bool:
    """True if the fetched IEX data doesn't include the last trading day."""
    last_td = _last_trading_day()
    for df in data.values():
        if not df.empty and df["datetime_et"].max().date() >= last_td:
            return False
    return True


def _yf_to_standard(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Convert a yfinance OHLCV frame to screener-standard format."""
    df = df.dropna(subset=["Close"]).copy()
    if df.empty:
        return None
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_convert("America/New_York").tz_localize(None)
    df.index = idx
    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low",
                             "Close": "close", "Volume": "volume"})
    t = df.index.time
    df = df[(t >= pd.Timestamp(SESSION_START).time()) &
            (t <= pd.Timestamp(SESSION_END).time())][["open","high","low","close","volume"]].copy()
    df.index.name = "datetime_et"
    df = df.reset_index().sort_values("datetime_et").reset_index(drop=True)
    return df


def fetch_yfinance_batch(symbols: list[str], days: int = LOOKBACK_DAYS,
                          timeframe: str = TIMEFRAME) -> dict[str, pd.DataFrame]:
    try:
        import yfinance as yf
    except ImportError:
        print("  [yfinance not installed — pip install yfinance]", file=sys.stderr)
        return {}

    interval = TIMEFRAME_YF_MAP.get(timeframe, "5m")
    period   = f"{min(days + 5, 59)}d"
    min_bars = ATR_PERIOD + VOL_LOOKBACK + RANGE_LOOKBACK + MIN_CONSOL_BARS + 2
    results  = {}

    for i in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[i:i + BATCH_SIZE]
        print(f"  yfinance batch {i//BATCH_SIZE + 1}: {batch[0]}..{batch[-1]}", end=" ", flush=True)
        try:
            raw = yf.download(
                batch, period=period, interval=interval,
                auto_adjust=False, progress=False, threads=True,
            )
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            continue

        if raw.empty:
            print("→ 0")
            continue

        got = 0
        if isinstance(raw.columns, pd.MultiIndex):
            # Determine which level holds the ticker names
            lvl = 1 if raw.columns.get_level_values(1)[0] in batch else 0
            for sym in batch:
                try:
                    df = raw.xs(sym, axis=1, level=lvl).copy()
                    df = _yf_to_standard(df)
                    if df is not None and len(df) >= min_bars:
                        results[sym] = df
                        got += 1
                except (KeyError, Exception):
                    continue
        else:
            # Single-ticker download
            sym = batch[0]
            df = _yf_to_standard(raw.copy())
            if df is not None and len(df) >= min_bars:
                results[sym] = df
                got = 1

        print(f"→ {got} symbols")
        time.sleep(0.5)

    return results


# ── Volatility + breakout logic (same as 1-min detector) ─────────────────────

def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift(1)
    return pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev).abs(),
        (df["low"]  - prev).abs(),
    ], axis=1).max(axis=1)


def compute_volatility(df: pd.DataFrame, squeeze_pct: float = SQUEEZE_PCT) -> pd.DataFrame:
    df = df.copy()
    df["tr"]  = true_range(df)
    df["atr"] = df["tr"].rolling(ATR_PERIOD).mean()

    def pct_rank(s):
        return s.rank(pct=True).iloc[-1] * 100

    df["atr_pct"]    = df["atr"].rolling(VOL_LOOKBACK).apply(pct_rank, raw=False)
    df["range_high"] = df["high"].rolling(RANGE_LOOKBACK).max()
    df["range_low"]  = df["low"].rolling(RANGE_LOOKBACK).min()
    df["vol_avg"]    = df["volume"].rolling(VOL_AVG_PERIOD).mean()

    in_squeeze       = df["atr_pct"] <= squeeze_pct
    df["squeeze_bars"] = in_squeeze.groupby((~in_squeeze).cumsum()).cumcount()
    return df


def detect_breakouts(df: pd.DataFrame, breakout_pct: float = BREAKOUT_PCT,
                     min_consol_bars: int = MIN_CONSOL_BARS,
                     vol_surge_mult: float = VOL_SURGE_MULT) -> list[dict]:
    breakouts = []
    start = RANGE_LOOKBACK + VOL_LOOKBACK + ATR_PERIOD

    for i in range(start, len(df)):
        row  = df.iloc[i]
        prev = df.iloc[i - 1]

        if prev["squeeze_bars"] < min_consol_bars:
            continue
        if row["atr_pct"] < breakout_pct:
            continue

        vol_ratio = row["volume"] / row["vol_avg"] if row["vol_avg"] > 0 else 0
        if vol_ratio < vol_surge_mult:
            continue

        direction = None
        if row["close"] > prev["range_high"]:
            direction = "up"
        elif row["close"] < prev["range_low"]:
            direction = "down"

        if direction:
            breakouts.append({
                "datetime":     row["datetime_et"],
                "close":        row["close"],
                "atr_pct":      row["atr_pct"],
                "vol_ratio":    round(vol_ratio, 2),
                "consol_high":  prev["range_high"],
                "consol_low":   prev["range_low"],
                "squeeze_bars": int(prev["squeeze_bars"]),
                "direction":    direction,
            })
    return breakouts


# ── Main screener ─────────────────────────────────────────────────────────────

def run_screener(symbols: list[tuple], recency_hours: int, out_md: str, out_json: str,
                 timeframe: str = TIMEFRAME, lookback_days: int = LOOKBACK_DAYS,
                 squeeze_pct: float = SQUEEZE_PCT, breakout_pct: float = BREAKOUT_PCT,
                 min_consol_bars: int = MIN_CONSOL_BARS,
                 vol_surge_mult: float = VOL_SURGE_MULT):
    sym_list = [s[0] for s in symbols]
    sym_meta = {s[0]: {"name": s[1], "sector": s[2]} for s in symbols}

    all_results = []
    cutoff = datetime.now() - timedelta(hours=recency_hours)

    # ── Phase 1: fetch from IEX ───────────────────────────────────────────────
    batches = [sym_list[i:i+BATCH_SIZE] for i in range(0, len(sym_list), BATCH_SIZE)]
    print(f"Fetching {timeframe} bars for {len(sym_list)} symbols in {len(batches)} batches (IEX)...")
    all_bars: dict[str, pd.DataFrame] = {}
    for idx, batch in enumerate(batches):
        print(f"  Batch {idx+1}/{len(batches)}: {batch[0]}..{batch[-1]}", end=" ", flush=True)
        batch_data = fetch_intraday_batch(batch, days=lookback_days, timeframe=timeframe)
        all_bars.update(batch_data)
        print(f"→ {len(batch_data)} symbols with data")
        time.sleep(0.3)

    # ── Phase 2: fall back to yfinance if IEX is stale ───────────────────────
    if _iex_is_stale(all_bars):
        last_td = _last_trading_day()
        iex_latest = max(
            (df["datetime_et"].max().date() for df in all_bars.values() if not df.empty),
            default="N/A",
        )
        print(f"\n  IEX latest bar: {iex_latest} | expected: {last_td}")
        print(f"  IEX data is stale — falling back to yfinance for {len(sym_list)} symbols...")
        all_bars = fetch_yfinance_batch(sym_list, days=lookback_days, timeframe=timeframe)
        print(f"  yfinance total: {len(all_bars)} symbols with data")

    # ── Phase 3: detect breakouts ─────────────────────────────────────────────
    for sym, df in all_bars.items():
        try:
            df = compute_volatility(df, squeeze_pct=squeeze_pct)
            breakouts = detect_breakouts(df, breakout_pct=breakout_pct,
                                         min_consol_bars=min_consol_bars,
                                         vol_surge_mult=vol_surge_mult)
        except Exception:
            continue

        if not breakouts:
            continue

        recent = [b for b in breakouts if b["datetime"] >= cutoff]
        if not recent:
            continue

        latest = recent[-1]
        all_results.append({
            "symbol":       sym,
            "name":         sym_meta.get(sym, {}).get("name", ""),
            "sector":       sym_meta.get(sym, {}).get("sector", ""),
            "datetime":     latest["datetime"],
            "direction":    latest["direction"],
            "close":        latest["close"],
            "atr_pct":      latest["atr_pct"],
            "vol_ratio":    latest["vol_ratio"],
            "squeeze_bars": latest["squeeze_bars"],
            "consol_high":  latest["consol_high"],
            "consol_low":   latest["consol_low"],
            "total_breakouts": len(breakouts),
            "recent_breakouts": len(recent),
        })

    if not all_results:
        print("\nNo breakouts detected in the lookback window.")
        return

    df_res = pd.DataFrame(all_results)
    df_res = df_res.sort_values(["direction", "vol_ratio"], ascending=[True, False])

    _print_report(df_res)
    _save_markdown(df_res, out_md)
    _save_json(df_res, out_json)


def _print_report(df: pd.DataFrame):
    up   = df[df["direction"] == "up"]
    down = df[df["direction"] == "down"]

    print(f"\n{'='*80}")
    print(f"  S&P 500 VOLATILITY BREAKOUT SCREENER — {len(df)} stocks with recent signals")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*80}")

    for label, subset in [("▲ BREAKOUT UP", up), ("▼ BREAKOUT DOWN", down)]:
        if subset.empty:
            continue
        print(f"\n{label} — {len(subset)} stocks")
        print(f"{'Symbol':<7} {'Name':<28} {'Sector':<24} {'Time':<18} {'Close':>9} {'ATR%':>6} {'Vol×':>6} {'SqBars':>7}")
        print("-" * 108)
        for _, r in subset.iterrows():
            print(f"{r['symbol']:<7} {r['name'][:27]:<28} {r['sector'][:23]:<24} "
                  f"{str(r['datetime'])[:16]:<18} {r['close']:>9.2f} "
                  f"{r['atr_pct']:>6.1f} {r['vol_ratio']:>6.1f} {r['squeeze_bars']:>7}")

    by_sector = df.groupby("sector").size().sort_values(ascending=False)
    print(f"\nSector distribution:")
    for sector, count in by_sector.items():
        print(f"  {sector:<30} {count}")


def _save_markdown(df: pd.DataFrame, path: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# S&P 500 Volatility Breakout Screener\n",
        f"**Generated:** {now}  \n",
        f"**Timeframe:** {TIMEFRAME} bars | **Lookback:** {LOOKBACK_DAYS} days\n\n",
        f"**Total signals:** {len(df)} stocks\n\n",
        "---\n\n",
    ]
    for direction, label in [("up", "▲ Breakout UP"), ("down", "▼ Breakout DOWN")]:
        sub = df[df["direction"] == direction]
        if sub.empty:
            continue
        lines.append(f"## {label} — {len(sub)} stocks\n\n")
        lines.append("| Symbol | Name | Sector | Time | Close | ATR% | Vol× | Sq.Bars |\n")
        lines.append("|--------|------|--------|------|-------|------|------|--------|\n")
        for _, r in sub.iterrows():
            lines.append(f"| {r['symbol']} | {r['name']} | {r['sector']} | "
                         f"{str(r['datetime'])[:16]} | {r['close']:.2f} | "
                         f"{r['atr_pct']:.1f} | {r['vol_ratio']:.1f} | {r['squeeze_bars']} |\n")
        lines.append("\n")

    with open(path, "w") as f:
        f.writelines(lines)
    print(f"Markdown saved → {path}")


def _save_json(df: pd.DataFrame, path: str):
    import json
    records = df.copy()
    records["datetime"] = records["datetime"].astype(str)
    with open(path, "w") as f:
        json.dump(records.to_dict(orient="records"), f, indent=2)
    print(f"JSON saved → {path}")


def main():
    parser = argparse.ArgumentParser(description="S&P 500 Volatility Breakout Screener")
    parser.add_argument("--timeframe",    default=TIMEFRAME,       help="Bar size: 1Min, 5Min, 15Min")
    parser.add_argument("--lookback",     default=LOOKBACK_DAYS,   type=int, help="Days of history to fetch")
    parser.add_argument("--recency",      default=RECENCY_HOURS,   type=int, help="Only show breakouts within N hours")
    parser.add_argument("--squeeze-pct",  default=SQUEEZE_PCT,     type=float)
    parser.add_argument("--breakout-pct", default=BREAKOUT_PCT,    type=float)
    parser.add_argument("--min-consol",   default=MIN_CONSOL_BARS, type=int)
    parser.add_argument("--vol-surge",    default=VOL_SURGE_MULT,  type=float,
                        help="Volume must be ≥ this × rolling avg to confirm breakout (default: %(default)s)")
    parser.add_argument("--out-dir",      default="scripts/reports")
    parser.add_argument("--universe",     nargs="+", help="Override with specific symbols")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.universe:
        symbols = [(s, s, "Custom") for s in args.universe]
    else:
        symbols = list(_SP500)

    run_screener(
        symbols,
        timeframe=args.timeframe,
        lookback_days=args.lookback,
        recency_hours=args.recency,
        squeeze_pct=args.squeeze_pct,
        breakout_pct=args.breakout_pct,
        min_consol_bars=args.min_consol,
        vol_surge_mult=args.vol_surge,
        out_md=f"{args.out_dir}/sp500_breakout_{ts}.md",
        out_json=f"{args.out_dir}/sp500_breakout_{ts}.json",
    )


if __name__ == "__main__":
    main()
