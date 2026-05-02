"""
Standalone utility: winsorise, standardise, and fill missing values
in factor CSV files before feeding them into the backtest.

Usage:
    from preprocessing.factor_preprocessor import FactorPreprocessor
    fp = FactorPreprocessor(fill_method='median', standardize='zscore',
                            winsorize=True, n_sigma=3.0)
    fp.preprocess_folder(
        factor_dir='./factors/raw',
        output_dir='./factors/preprocessed',
    )
"""

from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

_SKIP_COLS = {'code', 'date', 'industry'}


class FactorPreprocessor:
    """
    Pipeline: winsorise → fill NaN → standardise.

    Parameters
    ----------
    factor_cols   : explicit list of columns to process; None = auto-detect
    fill_method   : 'median' | 'zero' | 'industry_median' | 'drop'
    standardize   : 'zscore' | 'rank' | 'minmax' | 'robust'
    winsorize     : whether to clip outliers (3σ by default)
    n_sigma       : sigma multiplier for winsorisation
    industry_col  : column name carrying industry labels
    """

    def __init__(
        self,
        factor_cols: Optional[List[str]] = None,
        fill_method: str = 'median',
        standardize: str = 'zscore',
        winsorize: bool = True,
        n_sigma: float = 3.0,
        industry_col: str = 'industry',
    ):
        self.factor_cols  = list(factor_cols) if factor_cols else None
        self.fill_method  = fill_method
        self.standardize  = standardize
        self.winsorize    = winsorize
        self.n_sigma      = n_sigma
        self.industry_col = industry_col

    # ----------------------------------------------------------------- helpers

    def _infer_factor_cols(self, df: pd.DataFrame,
                           factor_cols=None) -> List[str]:
        cols = factor_cols or self.factor_cols
        if cols:
            return list(cols)
        skip = _SKIP_COLS | {self.industry_col}
        return [c for c in df.columns if c not in skip]

    def winsorize_series(self, s: pd.Series,
                         n_sigma: Optional[float] = None) -> pd.Series:
        mean, std = s.mean(), s.std()
        if pd.isna(std) or std == 0:
            return s
        sigma = self.n_sigma if n_sigma is None else n_sigma
        return s.clip(mean - sigma * std, mean + sigma * std)

    def standardize_series(self, s: pd.Series,
                            method: Optional[str] = None) -> pd.Series:
        m = method or self.standardize
        if m == 'zscore':
            std = s.std()
            return (s - s.mean()) / std if std else s - s.mean()
        if m == 'rank':
            return s.rank(pct=True)
        if m == 'minmax':
            lo, hi = s.min(), s.max()
            return (s - lo) / (hi - lo) if hi != lo else s * 0
        if m == 'robust':
            med = s.median()
            mad = (s - med).abs().median()
            return (s - med) / mad if mad else s - med
        raise ValueError(f'Unknown standardize method: {m}')

    def fill_missing_series(self, s: pd.Series, method: Optional[str] = None,
                             industry_series: Optional[pd.Series] = None) -> pd.Series:
        m = method or self.fill_method
        if m == 'zero':
            return s.fillna(0)
        if m == 'median':
            return s.fillna(s.median())
        if m == 'industry_median':
            if industry_series is None:
                return s.fillna(s.median())
            df = pd.DataFrame({'value': s, 'industry': industry_series})
            grp_med = df.groupby('industry')['value'].transform('median')
            return df['value'].fillna(grp_med).fillna(s.median())
        raise ValueError(f'Unknown fill method: {m}')

    # ----------------------------------------------------------------- main API

    def preprocess_factor_df(
        self,
        df: pd.DataFrame,
        factor_cols=None,
        industry_series: Optional[pd.Series] = None,
    ) -> pd.DataFrame:
        cols = self._infer_factor_cols(df, factor_cols)
        if self.fill_method == 'drop':
            df = df.dropna(subset=cols)
        out = df.copy()
        for col in cols:
            s = out[col].replace([np.inf, -np.inf], np.nan)
            if self.winsorize:
                s = self.winsorize_series(s)
            if self.fill_method != 'drop':
                s = self.fill_missing_series(s, industry_series=industry_series)
            out[col] = self.standardize_series(s)
        return out

    def preprocess_folder(
        self,
        factor_dir: str,
        output_dir: str,
        industry_dir: Optional[str] = None,
    ) -> None:
        src = Path(factor_dir)
        dst = Path(output_dir)
        dst.mkdir(parents=True, exist_ok=True)
        files = sorted(src.glob('*.csv'))
        if not files:
            print(f'No CSV files found in {src}')
            return
        for fp in files:
            df = pd.read_csv(fp)
            if 'code' in df.columns:
                df = df.set_index('code')
            ind_series = None
            if industry_dir:
                ind_file = Path(industry_dir) / fp.name
                if ind_file.exists():
                    ind_df = pd.read_csv(ind_file)
                    if 'code' in ind_df.columns:
                        ind_df = ind_df.set_index('code')
                    col = self.industry_col if self.industry_col in ind_df.columns else ind_df.columns[0]
                    ind_series = ind_df[col]
            processed = self.preprocess_factor_df(df, industry_series=ind_series)
            processed.to_csv(dst / fp.name)
        print(f'Preprocessing done → {dst}')
