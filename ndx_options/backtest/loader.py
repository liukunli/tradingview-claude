"""
backtest/loader.py — Historical OHLCV data loading.

Supports:
  - JSON format (legacy NDX_5min_2026.json with Unix timestamps)
  - CSV format (ndx_1min.csv / spx_1min.csv with PT timestamps, auto-resampled to 5-min)
"""

import json
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from ..config.settings import ET, BACKTEST_DATA

PT = ZoneInfo("America/Los_Angeles")


def load_ohlcv(path: Optional[str] = None) -> pd.DataFrame:
    """
    Load OHLCV data from JSON or CSV. Returns a DataFrame with columns:
    dt (ET-aware), date, time_et, open, high, low, close, volume
    — always at 5-min resolution.
    """
    path = path or BACKTEST_DATA
    if str(path).endswith(".csv"):
        return _load_csv_as_5min(path)
    return _load_json(path)


def _load_json(path: str) -> pd.DataFrame:
    with open(path) as f:
        raw = json.load(f)
    bars = raw if isinstance(raw, list) else raw.get("bars", raw.get("data", []))
    df   = pd.DataFrame(bars)
    df.columns = [c.lower() for c in df.columns]

    ts_col = next((c for c in ("time", "timestamp", "t") if c in df.columns), None)
    if ts_col:
        df["dt"] = pd.to_datetime(df[ts_col], unit="s", utc=True).dt.tz_convert(ET)
    df["date"]    = df["dt"].dt.date
    df["time_et"] = df["dt"].dt.time
    return df.sort_values("dt").reset_index(drop=True)


def _load_csv_as_5min(path: str) -> pd.DataFrame:
    """Read a 1-min OHLCV CSV (PT timestamps) and resample to 5-min in ET."""
    df = pd.read_csv(path)
    df["dt"] = (
        pd.to_datetime(df["datetime_et"])
        .dt.tz_localize(PT)
        .dt.tz_convert(ET)
    )
    df = df.sort_values("dt").set_index("dt")

    ohlcv = df[["open", "high", "low", "close", "volume"]].resample("5min").agg({
        "open":   "first",
        "high":   "max",
        "low":    "min",
        "close":  "last",
        "volume": "sum",
    }).dropna(subset=["open"])

    ohlcv = ohlcv.reset_index()
    ohlcv["date"]    = ohlcv["dt"].dt.date
    ohlcv["time_et"] = ohlcv["dt"].dt.time
    return ohlcv.sort_values("dt").reset_index(drop=True)
