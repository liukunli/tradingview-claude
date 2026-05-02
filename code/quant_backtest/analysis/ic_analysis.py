"""
IC analysis toolkit  (from 12课时: ic_calculation + ic_decay + ic_stats).

Three capabilities
------------------
1. ICAnalyzer.compute_ic_series()  – daily Spearman + Pearson IC vs forward returns
2. ICAnalyzer.compute_ic_decay()   – IC at multiple hold horizons (1d, 5d, 10d …)
3. summarize_ic_stats()            – aggregate IC series into mean/std/IR/win-rate/t-stat

Knowledge points
----------------
- T-day factor vs T-day file = T→T+1 forward return (no look-ahead).
- Spearman IC ranks are robust to outliers; Pearson measures linearity.
- IC decay speed tells you the right rebalance frequency:
  fast decay → high-freq, slow decay → low-freq (cheaper trading costs).
- IC_IR = mean/std measures stability (like Sharpe for IC).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from analysis.utils import (
    calc_ic,
    calc_ic_stats,
    ensure_dir,
    load_dates,
    load_factor_series,
    load_return_series,
)


class ICAnalyzer:
    """Compute IC series, IC decay, and IC statistics from saved factor files."""

    def __init__(
        self,
        factor_col: Optional[str] = None,
        horizons: Optional[List[str]] = None,
    ):
        self.factor_col = factor_col
        self.horizons   = horizons or ["1vwap_pct", "5vwap_pct", "10vwap_pct"]

    # ----------------------------------------------------------------- IC series

    def compute_ic_series(
        self,
        date_path: str,
        factor_dir: str,
        data_dir: str,
        factor_col: Optional[str] = None,
        ret_col: str = "1vwap_pct",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Compute daily IC series: Spearman and Pearson.

        Returns DataFrame with columns: date, ic_spearman, ic_pearson, coverage.
        """
        dates   = load_dates(date_path, start_date, end_date)
        col     = factor_col or self.factor_col
        records = []

        for date in dates:
            factor = load_factor_series(factor_dir, date, factor_col=col)
            ret    = load_return_series(data_dir, date, ret_col=ret_col)
            if factor.empty or ret.empty:
                continue
            coverage = len(factor.dropna().index.intersection(ret.dropna().index))
            records.append({
                "date":         date,
                "ic_spearman":  calc_ic(factor, ret, method="spearman"),
                "ic_pearson":   calc_ic(factor, ret, method="pearson"),
                "coverage":     coverage,
            })

        df = pd.DataFrame(records)
        if output_dir:
            ensure_dir(output_dir)
            df.to_csv(Path(output_dir) / "ic_series.csv", index=False)
        return df

    # ----------------------------------------------------------------- IC decay

    def compute_ic_decay(
        self,
        date_path: str,
        factor_dir: str,
        ret_dir: str,
        factor_col: Optional[str] = None,
        horizons: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Compute IC at each hold horizon (1vwap_pct, 5vwap_pct, 10vwap_pct …).

        Returns DataFrame with columns: date, horizon, ic.
        A separate summary CSV is written with mean/std/IR per horizon.
        """
        horizons = horizons or self.horizons
        col      = factor_col or self.factor_col
        dates    = load_dates(date_path, start_date, end_date)
        records  = []

        for date in dates:
            factor = load_factor_series(factor_dir, date, factor_col=col)
            ret_path = Path(ret_dir) / f"{date}.csv"
            if factor.empty or not ret_path.exists():
                continue
            ret_df = pd.read_csv(ret_path)
            if "code" in ret_df.columns:
                ret_df = ret_df.set_index("code")

            for h in horizons:
                if h not in ret_df.columns:
                    continue
                ic = calc_ic(factor, ret_df[h].astype(float), method="spearman")
                records.append({"date": date, "horizon": h, "ic": ic})

        df = pd.DataFrame(records)
        if output_dir and not df.empty:
            out = ensure_dir(output_dir)
            df.to_csv(out / "ic_decay.csv", index=False)
            summary = df.groupby("horizon")["ic"].agg(["mean", "std"]).reset_index()
            summary["ir"] = summary["mean"] / summary["std"].replace(0, np.nan)
            summary.to_csv(out / "ic_decay_summary.csv", index=False)
        return df

    # ----------------------------------------------------------------- IC stats

    @staticmethod
    def summarize_ic_stats(
        ic_df: pd.DataFrame,
        output_dir: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Aggregate an IC series DataFrame (output of compute_ic_series)
        into mean/std/IR/win-rate/t-stat per IC column.
        """
        ic_cols = [c for c in ic_df.columns if c.startswith("ic_")]
        rows    = []
        for col in ic_cols:
            rows.append({"metric": col, **calc_ic_stats(ic_df[col])})
        result = pd.DataFrame(rows)
        if output_dir:
            ensure_dir(output_dir)
            result.to_csv(Path(output_dir) / "ic_summary.csv", index=False)
        return result
