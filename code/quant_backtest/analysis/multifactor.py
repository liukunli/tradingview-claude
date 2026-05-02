"""
Multi-factor combination and objective scoring  (from day13).

Two classes
-----------
MultifactorWeighter
    Computes factor weights under four schemes and builds composite signals.
    Schemes: equal | IC-weighted | ICIR-weighted | return-spread-weighted

ObjectiveScorer
    Evaluates factors under three objectives:
      1. IC_IR  (stability)
      2. Risk-adjusted L/S return  (Sharpe-like)
      3. Mixed  (0.5 × IC_IR + 0.5 × risk-adjusted)

Knowledge points
----------------
- Z-score normalise all factors before combining (removes scale differences).
- IC weighting: better predictors get more weight.
- ICIR weighting: stable predictors get more weight.
- Return-spread weighting: directly rewards L/S profitability.
- Mixed objective avoids being dominated by a single metric.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from analysis.utils import (
    calc_ic_summary,
    ensure_dir,
    group_returns,
    infer_factor_columns,
    load_real_panel,
    normalize_weights,
    zscore_by_date,
)


# ─────────────────────────────────────────────────────────────────────────────
# MultifactorWeighter
# ─────────────────────────────────────────────────────────────────────────────

class MultifactorWeighter:
    """
    Compute composite factor signals under four weighting schemes.

    Parameters
    ----------
    n_groups : int
        Quantile groups for return-spread calculation.
    """

    def __init__(self, n_groups: int = 10):
        self.n_groups = n_groups

    def _compute_metrics(
        self,
        panel: pd.DataFrame,
        factor_cols: List[str],
        ret_col: str = "ret",
    ) -> pd.DataFrame:
        rows = []
        for col in factor_cols:
            stats    = calc_ic_summary(panel, col, ret_col)
            grp      = group_returns(panel, col, ret_col=ret_col, n_groups=self.n_groups)
            ret_mean = np.nan
            if not grp.empty and self.n_groups in grp.columns:
                ret_mean = (grp[self.n_groups] - grp[1]).mean()
            rows.append({"factor": col,
                         "ic_mean": stats["ic_mean"],
                         "ic_ir":   stats["ic_ir"],
                         "ret_mean": ret_mean})
        return pd.DataFrame(rows).set_index("factor")

    def _build_weights(
        self,
        metrics: pd.DataFrame,
        factor_cols: List[str],
    ) -> Dict[str, pd.Series]:
        return {
            "equal":  normalize_weights(pd.Series(1.0, index=factor_cols)),
            "ic":     normalize_weights(metrics["ic_mean"]),
            "ic_ir":  normalize_weights(metrics["ic_ir"]),
            "ret":    normalize_weights(metrics["ret_mean"]),
        }

    def _build_composites(
        self,
        panel: pd.DataFrame,
        factor_cols: List[str],
        weights_by_method: Dict[str, pd.Series],
    ) -> Dict[str, pd.DataFrame]:
        composites = {}
        for name, weights in weights_by_method.items():
            w   = weights.reindex(factor_cols).fillna(0.0)
            sig = panel[factor_cols].values @ w.values
            df  = panel[["date", "asset"]].copy()
            df["composite"] = sig
            composites[name] = df
        return composites

    def run(
        self,
        data_dir: str = "./data",
        ret_horizon: str = "1vwap_pct",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_dates: Optional[int] = 240,
        output_dir: Optional[str] = None,
    ) -> Dict[str, pd.DataFrame]:
        """
        Full pipeline: load → z-score → metrics → weights → composites.

        Returns dict with keys: 'metrics', 'weights', 'composite_equal',
        'composite_ic', 'composite_ic_ir', 'composite_ret'.
        """
        panel       = load_real_panel(data_dir, ret_horizon, start_date, end_date, max_dates)
        factor_cols = infer_factor_columns(panel)
        if not factor_cols:
            raise ValueError("No factor columns found in panel data.")

        panel   = zscore_by_date(panel, factor_cols)
        panel   = panel.dropna(subset=factor_cols + ["ret"])
        metrics = self._compute_metrics(panel, factor_cols)
        wb      = self._build_weights(metrics, factor_cols)
        composites = self._build_composites(panel, factor_cols, wb)

        result = {"metrics": metrics.reset_index(),
                  "weights": pd.DataFrame(wb).T}
        result.update({f"composite_{k}": v for k, v in composites.items()})

        if output_dir:
            out = ensure_dir(output_dir)
            result["metrics"].to_csv(out / "factor_metrics.csv", index=False)
            result["weights"].to_csv(out / "weights_by_method.csv", index_label="method")
            for k, df in composites.items():
                df.to_csv(out / f"composite_{k}.csv", index=False)
            print(f"MultifactorWeighter done → {out}")

        return result


# ─────────────────────────────────────────────────────────────────────────────
# ObjectiveScorer
# ─────────────────────────────────────────────────────────────────────────────

class ObjectiveScorer:
    """
    Evaluate factors along three optimisation objectives:
      1. IC_IR  – stability of predictive signal
      2. Risk-adjusted L/S return  – mean(LS) / std(LS)
      3. Mixed  – equal blend of the two
    """

    def __init__(self, n_groups: int = 10):
        self.n_groups = n_groups

    def run(
        self,
        data_dir: str = "./data",
        ret_horizon: str = "1vwap_pct",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_dates: Optional[int] = 240,
        output_dir: Optional[str] = None,
    ) -> pd.DataFrame:
        panel       = load_real_panel(data_dir, ret_horizon, start_date, end_date, max_dates)
        factor_cols = infer_factor_columns(panel)
        if not factor_cols:
            raise ValueError("No factor columns found.")

        panel = zscore_by_date(panel, factor_cols)
        panel = panel.dropna(subset=factor_cols + ["ret"])
        rows  = []

        for col in factor_cols:
            stats = calc_ic_summary(panel, col, "ret")
            grp   = group_returns(panel, col, ret_col="ret", n_groups=self.n_groups)

            if grp.empty or self.n_groups not in grp.columns:
                ret_mean = ret_vol = np.nan
            else:
                ls       = grp[self.n_groups] - grp[1]
                ret_mean = ls.mean()
                ret_vol  = ls.std(ddof=0)

            ic_ir     = stats["ic_ir"]
            score_ret = ret_mean / ret_vol if ret_vol and ret_vol != 0 else np.nan
            score_mix = (0.5 * (ic_ir or 0) + 0.5 * (score_ret or 0)
                         if not np.isnan(score_ret or np.nan) else ic_ir)

            rows.append({
                "factor":           col,
                "ic_ir":            ic_ir,
                "ls_mean":          ret_mean,
                "ls_vol":           ret_vol,
                "score_return_adj": score_ret,
                "score_mix":        score_mix,
            })

        result = pd.DataFrame(rows).sort_values("score_mix", ascending=False)

        if output_dir:
            out = ensure_dir(output_dir)
            result.to_csv(out / "objective_scores.csv", index=False)
            print(f"ObjectiveScorer done → {out}")

        return result
