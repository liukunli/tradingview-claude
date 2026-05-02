"""
Factor turnover / stability analysis  (from 12课时/factor_turnover.py).

Measures how stable factor rankings are day-to-day.
Turnover proxy = 1 − RankIC(today, yesterday).

Knowledge points
----------------
- Rank autocorrelation close to 1.0 → factor barely changes → low turnover.
- Fundamental factors (P/E, B/P) typically have RankIC > 0.9.
- Price-based factors (reversal, WR) typically have RankIC < 0.7.
- Low RankIC → frequent rebalancing → high transaction costs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from analysis.utils import ensure_dir, load_dates, load_factor_series


class FactorTurnoverAnalyzer:

    def __init__(self, factor_col: Optional[str] = None):
        self.factor_col = factor_col

    @staticmethod
    def _rank_ic(a: pd.Series, b: pd.Series) -> float:
        aligned = pd.concat([a, b], axis=1).dropna()
        if aligned.empty:
            return np.nan
        return aligned.iloc[:, 0].corr(aligned.iloc[:, 1], method="spearman")

    def factor_turnover(
        self,
        date_path: str,
        factor_dir: str,
        factor_col: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Compute daily (1 − RankIC) as a turnover proxy.

        Returns DataFrame with columns: date, rank_ic, turnover, coverage.
        """
        col     = factor_col or self.factor_col
        dates   = load_dates(date_path, start_date, end_date)
        records = []
        prev    = None

        for date in dates:
            curr = load_factor_series(factor_dir, date, factor_col=col)
            if curr.empty:
                prev = None
                continue
            if prev is not None:
                ric  = self._rank_ic(prev, curr)
                records.append({
                    "date":     date,
                    "rank_ic":  ric,
                    "turnover": 1 - ric if not np.isnan(ric) else np.nan,
                    "coverage": prev.dropna().shape[0],
                })
            prev = curr

        df = pd.DataFrame(records)
        if output_dir and not df.empty:
            out = ensure_dir(output_dir)
            df.to_csv(out / "factor_turnover.csv", index=False)
            summary = df[["rank_ic", "turnover"]].agg(["mean", "std"]).T.reset_index()
            summary.columns = ["stat", "mean", "std"]
            summary.to_csv(out / "factor_turnover_summary.csv", index=False)
        return df
