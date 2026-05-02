#!/usr/bin/env python3
"""Download Tesla (TSLA) 5-minute bars using yfinance (chunked to respect 60-day limit)."""

import yfinance as yf
import pandas as pd
from datetime import date, timedelta

print("Downloading ^NDX 1-minute bars for the last 7 days (Yahoo Finance limit for 1m)...")
ndx = yf.download('^NDX', period='7d', interval='1m', auto_adjust=False, progress=False)
if hasattr(ndx.columns, 'levels'):
    ndx.columns = ndx.columns.get_level_values(0)
ndx = ndx[['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']]
ndx = ndx[~ndx.index.duplicated()]
ndx.sort_index(inplace=True)

csv_path = '/tmp/NDX_1m_7d.csv'
ndx.to_csv(csv_path)
print(f"\nSaved {len(ndx)} total bars to {csv_path}\n")

print(f"{'Datetime':<28} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Volume':>12}")
print("-" * 86)
for dt, row in ndx.iterrows():
    print(f"{str(dt):<28} {row['Open']:>10.2f} {row['High']:>10.2f} {row['Low']:>10.2f} {row['Close']:>10.2f} {row['Volume']:>12.0f}")
