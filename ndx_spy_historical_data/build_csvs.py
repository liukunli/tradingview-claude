#!/usr/bin/env python3
"""
Reorganize historical zip files into 4 clean CSVs:
  ndx_1min.csv, ndx_1hour.csv, spx_1min.csv, spx_1hour.csv

Source timestamps are China time (UTC+8); output is converted to US/Eastern.
Columns: datetime_et, open, high, low, close, volume
"""

import io
import os
import zipfile
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

HERE   = Path(__file__).parent
ET     = ZoneInfo("America/Los_Angeles")
CN     = ZoneInfo("Asia/Shanghai")

RENAME = {
    "时间":  "datetime_et",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "收盘价": "close",
    "成交量": "volume",
    "代码":  "symbol",
}

KEEP = ["datetime_et", "open", "high", "low", "close", "volume"]


def read_zip(zpath: Path) -> pd.DataFrame:
    frames = []
    with zipfile.ZipFile(zpath) as zf:
        for name in zf.namelist():
            raw = zf.read(name)
            df  = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
            df.columns = [c.strip() for c in df.columns]
            df = df.rename(columns=RENAME)
            if "symbol" not in df.columns or "datetime_et" not in df.columns:
                continue
            df["datetime_et"] = (
                pd.to_datetime(df["datetime_et"])
                .dt.tz_localize(CN)
                .dt.tz_convert(ET)
                .dt.strftime("%Y-%m-%d %H:%M")
            )
            frames.append(df[["symbol"] + KEEP])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def collect(timeframe_dir: Path, symbol: str) -> pd.DataFrame:
    frames = []
    for zpath in sorted(timeframe_dir.rglob("*.zip")):
        try:
            df = read_zip(zpath)
        except Exception as e:
            print(f"  SKIP {zpath.name}: {e}")
            continue
        sub = df[df["symbol"] == symbol][KEEP]
        if not sub.empty:
            frames.append(sub)
    if not frames:
        return pd.DataFrame(columns=KEEP)
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates("datetime_et").sort_values("datetime_et").reset_index(drop=True)
    return out


JOBS = [
    ("1 min",  "NDX", "ndx_1min.csv"),
    ("1 min",  "SPX", "spx_1min.csv"),
    ("60 min", "NDX", "ndx_1hour.csv"),
    ("60 min", "SPX", "spx_1hour.csv"),
]

for folder, sym, fname in JOBS:
    print(f"Building {fname} …", end=" ", flush=True)
    df = collect(HERE / folder, sym)
    out_path = HERE / fname
    df.to_csv(out_path, index=False)
    print(f"{len(df):,} rows → {out_path.name}")

print("Done.")
