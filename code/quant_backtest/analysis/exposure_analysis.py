"""
Factor risk-exposure analysis  (from 12课时/exposure_analysis.py).

Runs cross-sectional OLS regressions to detect how much of a factor's
variance is explained by known risk factors (size, industry, beta …).

High R² → the factor is mostly a disguised style bet, not pure alpha.
Low R²  → the factor carries idiosyncratic information.

Knowledge points
----------------
- R² > 0.6: most of the factor is explained by style → neutralise first.
- β_size > 0: positive size tilt (large-cap).
- β_size < 0: negative size tilt (small-cap).
- Industry dummies absorb sector-level price movements.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm

from analysis.utils import ensure_dir, load_dates

_SIZE_COLS = ["size", "ln_mktcap", "log_mktcap", "mktcap"]


class ExposureAnalyzer:

    def __init__(
        self,
        size_col: Optional[str] = None,
        extra_barra_cols: Optional[Iterable[str]] = None,
        industry_col: str = "industry",
    ):
        self.size_col        = size_col
        self.extra_barra_cols = list(extra_barra_cols) if extra_barra_cols else []
        self.industry_col    = industry_col

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _load(path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)
        if "code" in df.columns:
            df = df.set_index("code")
        return df

    def _infer_size_col(self, df: pd.DataFrame) -> str:
        for c in _SIZE_COLS:
            if c in df.columns:
                return c
        raise ValueError(f"No size column found in {df.columns.tolist()}")

    def _build_risk_matrix(
        self,
        barra_df: pd.DataFrame,
        industry_series: Optional[pd.Series] = None,
    ) -> pd.DataFrame:
        risk = pd.DataFrame(index=barra_df.index)

        size_col = self.size_col or self._infer_size_col(barra_df)
        size     = barra_df[size_col].astype(float)
        if size_col == "mktcap":
            size = np.log(size.replace(0, np.nan))
        risk["size"] = size

        for col in self.extra_barra_cols:
            if col in barra_df.columns:
                risk[col] = barra_df[col]

        if industry_series is not None:
            dummies = pd.get_dummies(industry_series, prefix="ind", drop_first=True)
            risk    = risk.join(dummies, how="left")

        risk = risk.replace([np.inf, -np.inf], np.nan).astype(float)
        return sm.add_constant(risk, has_constant="add")

    # ------------------------------------------------------------------ per-date

    def exposure_for_date(
        self,
        date: str,
        factor_dir: str,
        barra_dir: str,
        industry_dir: Optional[str] = None,
        factor_cols: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        ff = Path(factor_dir) / f"{date}.csv"
        bf = Path(barra_dir)  / f"{date}.csv"
        if not ff.exists() or not bf.exists():
            return pd.DataFrame()

        factor_df = self._load(ff)
        barra_df  = self._load(bf)

        ind_series = None
        if industry_dir:
            ip = Path(industry_dir) / f"{date}.csv"
            if ip.exists():
                ind_df    = self._load(ip)
                ic        = self.industry_col if self.industry_col in ind_df.columns else ind_df.columns[0]
                ind_series = ind_df[ic]

        X   = self._build_risk_matrix(barra_df, ind_series)
        cols = factor_cols or [c for c in factor_df.columns if c != "date"]

        rows = []
        for col in cols:
            data = pd.concat([factor_df[col], X], axis=1).dropna()
            if data.shape[0] <= X.shape[1]:
                continue
            y = pd.to_numeric(data[col], errors="coerce")
            x = data[X.columns]
            tmp = pd.concat([y, x], axis=1).dropna()
            if tmp.empty:
                continue
            res = sm.OLS(tmp[col], tmp[X.columns]).fit()
            row = {"date": date, "factor": col, "r2": res.rsquared}
            row.update({f"beta_{k}": v for k, v in res.params.items()})
            rows.append(row)

        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ batch

    def run_exposure_analysis(
        self,
        date_path: str,
        factor_dir: str,
        barra_dir: str,
        industry_dir: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> pd.DataFrame:
        dates  = load_dates(date_path, start_date, end_date)
        frames = []
        print(f"Exposure analysis: {len(dates)} dates …")
        for date in dates:
            df = self.exposure_for_date(date, factor_dir, barra_dir, industry_dir)
            if not df.empty:
                frames.append(df)

        if not frames:
            return pd.DataFrame()
        result = pd.concat(frames, ignore_index=True)

        if output_dir:
            out = ensure_dir(output_dir)
            result.to_csv(out / "exposure_coefficients.csv", index=False)
            r2_summary = result.groupby("factor")["r2"].mean().reset_index()
            r2_summary.to_csv(out / "exposure_r2_summary.csv", index=False)
            print(f"Exposure analysis done → {out}")

        return result
