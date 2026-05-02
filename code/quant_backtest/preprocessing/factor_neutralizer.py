"""
OLS-based factor neutralization  (from 12课时/factor_neutralization.py).

Removes the portion of a factor that is explained by known risk factors
(market cap / size, industry, and optional extra Barra columns) using
cross-sectional OLS regression.  The residuals become the neutralized factor.

Factor_raw = β1·Size + β2·Industry_dummies + β3·OtherRisk + ε
Factor_neutral = ε

Knowledge points
----------------
- Market cap must be log-transformed before regression (log-normal distribution).
- Industry dummies require drop_first=True to avoid the multicollinearity trap.
- Sample size N must be >> feature count K; otherwise the regression is meaningless.
- R² of the regression tells you how much style bias was removed.

Requires: statsmodels
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm

_SIZE_COL_CANDIDATES = ["size", "ln_mktcap", "log_mktcap", "mktcap"]


class FactorNeutralizer:

    def __init__(
        self,
        size_col: Optional[str] = None,
        extra_barra_cols: Optional[Iterable[str]] = None,
        industry_col: str = "industry",
    ):
        self.size_col         = size_col
        self.extra_barra_cols = list(extra_barra_cols) if extra_barra_cols else []
        self.industry_col     = industry_col

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _load(path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)
        if "code" in df.columns:
            df = df.set_index("code")
        return df

    def _infer_size_col(self, df: pd.DataFrame) -> str:
        for c in _SIZE_COL_CANDIDATES:
            if c in df.columns:
                return c
        raise ValueError(f"No size column found in {df.columns.tolist()}")

    def _build_size_series(self, barra_df: pd.DataFrame) -> pd.Series:
        col = self.size_col or self._infer_size_col(barra_df)
        s   = barra_df[col].astype(float)
        if col == "mktcap":
            s = np.log(s.replace(0, np.nan))
        return s.rename("size")

    def _build_risk_matrix(
        self,
        barra_df: pd.DataFrame,
        industry_series: Optional[pd.Series] = None,
    ) -> pd.DataFrame:
        risk         = pd.DataFrame(index=barra_df.index)
        risk["size"] = self._build_size_series(barra_df)

        for col in self.extra_barra_cols:
            if col in barra_df.columns:
                risk[col] = barra_df[col]

        if industry_series is not None:
            dummies = pd.get_dummies(industry_series, prefix="ind", drop_first=True)
            risk    = risk.join(dummies, how="left")

        risk = risk.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
        return sm.add_constant(risk, has_constant="add")

    # ------------------------------------------------------------------ core OLS

    def neutralize_factor_df(
        self,
        factor_df: pd.DataFrame,
        risk_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        OLS-neutralize every column in factor_df against risk_df.
        Returns a DataFrame of residuals with the same shape as factor_df.
        """
        num_factors  = factor_df.apply(pd.to_numeric, errors="coerce")
        num_factors  = num_factors.replace([np.inf, -np.inf], np.nan).dropna(axis=1, how="all")
        factor_cols  = list(num_factors.columns)
        if not factor_cols:
            return pd.DataFrame(index=factor_df.index)

        aligned = num_factors.join(risk_df, how="inner")
        result  = pd.DataFrame(index=aligned.index, columns=factor_cols, dtype=float)

        for col in factor_cols:
            data = aligned[[col] + list(risk_df.columns)].dropna()
            if data.shape[0] <= len(risk_df.columns) + 1:
                continue
            y    = data[col]
            x    = data[risk_df.columns]
            resid = sm.OLS(y, x).fit().resid
            result.loc[data.index, col] = resid

        return result

    # ------------------------------------------------------------------ batch

    def neutralize_folder(
        self,
        factor_dir: str,
        barra_dir: str,
        output_dir: str,
        industry_dir: Optional[str] = None,
    ) -> None:
        """
        Neutralize every CSV in factor_dir against the corresponding Barra file.
        Results are written to output_dir with the same filenames.
        """
        src = Path(factor_dir)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        files = sorted(src.glob("*.csv"))
        print(f"Neutralising {len(files)} files …")

        for fp in files:
            bf = Path(barra_dir) / fp.name
            if not bf.exists():
                continue

            factor_df = self._load(fp)
            barra_df  = self._load(bf)

            ind_series = None
            if industry_dir:
                ip = Path(industry_dir) / fp.name
                if ip.exists():
                    ind_df    = self._load(ip)
                    ic        = self.industry_col if self.industry_col in ind_df.columns else ind_df.columns[0]
                    ind_series = ind_df[ic]

            risk_df    = self._build_risk_matrix(barra_df, ind_series)
            neutralized = self.neutralize_factor_df(factor_df, risk_df)
            neutralized.to_csv(out / fp.name)

        print(f"Neutralization done → {out}")
