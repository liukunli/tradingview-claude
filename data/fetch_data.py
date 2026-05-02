#!/usr/bin/env python3
"""
fetch_data.py — Download historical OHLCV data via yfinance.

Usage:
    python3 fetch_data.py TSLA
    python3 fetch_data.py TSLA --start 2024-01-01 --end 2026-05-01
    python3 fetch_data.py TSLA --interval 5m --period 30d
    python3 fetch_data.py TSLA AAPL NVDA --start 2025-01-01
    python3 fetch_data.py NDX=F --start 2026-01-01          # NDX futures proxy
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import yfinance as yf


INTERVALS = ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo']

# Max lookback per interval (yfinance limitation)
INTERVAL_MAX_PERIOD = {
    '1m':  '7d',
    '2m':  '60d',
    '5m':  '60d',
    '15m': '60d',
    '30m': '60d',
    '60m': '730d',
    '90m': '60d',
    '1h':  '730d',
}


def fetch(ticker: str, start, end, interval: str, period) -> pd.DataFrame:
    t = yf.Ticker(ticker)

    if start or end:
        df = t.history(start=start, end=end, interval=interval, auto_adjust=True)
    else:
        p = period or INTERVAL_MAX_PERIOD.get(interval, 'max')
        df = t.history(period=p, interval=interval, auto_adjust=True)

    if df.empty:
        print(f"  WARNING: no data for {ticker}", file=sys.stderr)
        return df

    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert('America/New_York').tz_localize(None)

    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df.columns = ['open', 'high', 'low', 'close', 'volume']
    df.index.name = 'datetime'
    return df


def save(df: pd.DataFrame, ticker: str, interval: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{ticker.replace('=', '_').replace('^', '')}_{interval}.csv"
    path = out_dir / fname
    df.to_csv(path)
    return path


def main():
    p = argparse.ArgumentParser(description='Download OHLCV via yfinance')
    p.add_argument('tickers', nargs='+', help='Ticker symbols (e.g. TSLA AAPL)')
    p.add_argument('--start',    default=None, help='Start date YYYY-MM-DD')
    p.add_argument('--end',      default=None, help='End date   YYYY-MM-DD')
    p.add_argument('--interval', default='1d', choices=INTERVALS, help='Bar size (default: 1d)')
    p.add_argument('--period',   default=None, help='Lookback period e.g. 30d, 1y, max')
    p.add_argument('--out-dir',  default='data', help='Output directory (default: data/)')
    p.add_argument('--no-save',  action='store_true', help='Print to stdout instead of saving')
    args = p.parse_args()

    out_dir = Path(args.out_dir)

    for ticker in args.tickers:
        print(f"Fetching {ticker}  interval={args.interval} ...", end=' ', flush=True)
        df = fetch(ticker, args.start, args.end, args.interval, args.period)
        if df.empty:
            continue

        if args.no_save:
            print(f"\n{df.tail(5).to_string()}\n")
        else:
            path = save(df, ticker, args.interval, out_dir)
            print(f"{len(df)} bars → {path}")


if __name__ == '__main__':
    main()
