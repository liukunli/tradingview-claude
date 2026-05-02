"""
Shared utilities for factor analysis (IC, z-scoring, grouping, weighting).
Merges helpers from 12课时/utils.py and day13/utils.py into one place.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd


# ─────────────────────────── I/O helpers ────────────────────────────────────

def ensure_dir(path: Union[str, Path]) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def load_dates(
    date_path: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[str]:
    with open(date_path, "rb") as f:
        dates = pickle.load(f)
    if start_date:
        dates = [d for d in dates if d >= start_date]
    if end_date:
        dates = [d for d in dates if d <= end_date]
    return dates


def list_available_dates(
    data_dir: Union[str, Path],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    barra_subdir: str = "data_barra",
    ret_subdir: str = "data_ret",
) -> List[str]:
    """Dates that have both Barra-exposure and return files."""
    data_path = Path(data_dir)
    with open(data_path / "date.pkl", "rb") as f:
        dates = pickle.load(f)
    result = []
    for date in dates:
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue
        if (data_path / barra_subdir / f"{date}.csv").exists() and \
           (data_path / ret_subdir   / f"{date}.csv").exists():
            result.append(date)
    return result


def infer_factor_cols(
    df: pd.DataFrame,
    exclude: Sequence[str] = ("code", "date"),
) -> List[str]:
    return [c for c in df.columns if c not in set(exclude)]


def infer_factor_columns(
    panel: pd.DataFrame,
    ret_col: str = "ret",
) -> List[str]:
    """Panel format: ignore date / asset / ret."""
    ignore = {"date", "asset", ret_col}
    return [c for c in panel.columns if c not in ignore]


def load_factor_frame(
    factor_dir: str,
    date: str,
    factor_cols: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    path = Path(factor_dir) / f"{date}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "code" in df.columns:
        df = df.set_index("code")
    cols = list(factor_cols) if factor_cols else infer_factor_cols(df)
    return df[cols].astype(float) if cols else pd.DataFrame()


def load_factor_series(
    factor_dir: str,
    date: str,
    factor_col: Optional[str] = None,
) -> pd.Series:
    df = load_factor_frame(factor_dir, date)
    if df.empty:
        return pd.Series(dtype=float)
    col = factor_col or df.columns[0]
    return df[col].astype(float) if col in df.columns else pd.Series(dtype=float)


def load_return_series(
    data_dir: str,
    date: str,
    ret_col: str = "1vwap_pct",
) -> pd.Series:
    path = Path(data_dir) / "data_ret" / f"{date}.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(path)
    if "code" not in df.columns or ret_col not in df.columns:
        return pd.Series(dtype=float)
    return df.set_index("code")[ret_col].astype(float)


def load_real_panel(
    data_dir: Union[str, Path] = "./data",
    ret_col: str = "1vwap_pct",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_dates: Optional[int] = None,
) -> pd.DataFrame:
    """
    Build a flat panel DataFrame from daily Barra-factor + return files.
    Columns: date, asset, <factor1>, <factor2>, …, ret
    """
    data_path = Path(data_dir)
    barra_dir = data_path / "data_barra"
    ret_dir   = data_path / "data_ret"
    frames: List[pd.DataFrame] = []

    for date in list_available_dates(data_dir, start_date, end_date):
        bdf = pd.read_csv(barra_dir / f"{date}.csv").rename(columns={"code": "asset"})
        rdf = pd.read_csv(ret_dir   / f"{date}.csv")
        if bdf.empty or ret_col not in rdf.columns:
            continue
        rdf = rdf.rename(columns={"code": "asset", ret_col: "ret"})[["asset", "ret"]]
        merged = pd.merge(bdf, rdf, on="asset", how="inner")
        merged["date"] = date
        frames.append(merged)
        if max_dates and len(frames) >= max_dates:
            break

    if not frames:
        raise ValueError("No panel data found – check data_dir and data_barra/data_ret sub-dirs.")
    return pd.concat(frames, ignore_index=True).dropna(subset=["ret"])


# ─────────────────────────── Math helpers ───────────────────────────────────

def align_series(factor: pd.Series, ret: pd.Series) -> pd.DataFrame:
    aligned = pd.concat([factor, ret], axis=1).dropna()
    if aligned.empty:
        return pd.DataFrame()
    aligned.columns = ["factor", "ret"]
    return aligned


def zscore_series(s: pd.Series) -> pd.Series:
    std = s.std()
    return (s - s.mean()) / std if std and not np.isnan(std) else s * 0.0


def zscore_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.apply(zscore_series, axis=0)


def zscore_by_date(
    panel: pd.DataFrame,
    factor_cols: Sequence[str],
) -> pd.DataFrame:
    out = panel.copy()
    out[list(factor_cols)] = out.groupby("date")[list(factor_cols)].transform(zscore_series)
    return out


def industry_neutralize_by_date(
    panel: pd.DataFrame,
    factor_cols: Sequence[str],
    data_dir: Union[str, Path],
) -> pd.DataFrame:
    """In-industry z-score by date; falls back to global z-score if missing."""
    data_path    = Path(data_dir)
    industry_dir = data_path / "data_industry"
    out          = panel.copy()

    for date in out["date"].unique():
        ind_file = industry_dir / f"{date}.csv"
        mask     = out["date"] == date
        if not ind_file.exists():
            for col in factor_cols:
                out.loc[mask, col] = zscore_series(out.loc[mask, col])
            continue
        ind_df = pd.read_csv(ind_file)
        if "code" not in ind_df.columns or "industry" not in ind_df.columns:
            continue
        tmp = out[mask].copy().merge(ind_df[["code", "industry"]],
                                     left_on="asset", right_on="code", how="left")
        for col in factor_cols:
            if col in tmp.columns:
                neu = tmp.groupby("industry")[col].transform(zscore_series)
                no_ind = tmp["industry"].isna()
                if no_ind.any():
                    neu[no_ind] = zscore_series(tmp.loc[no_ind, col])
                out.loc[mask, col] = neu.values
    return out


# ─────────────────────────── IC helpers ─────────────────────────────────────

def calc_ic(
    factor: pd.Series,
    ret: pd.Series,
    method: str = "spearman",
) -> float:
    aligned = align_series(factor, ret)
    if aligned.empty:
        return np.nan
    return aligned["factor"].corr(aligned["ret"], method=method)


def calc_ic_stats(ic_series: pd.Series) -> dict:
    clean = ic_series.dropna()
    if clean.empty:
        return {"ic_mean": np.nan, "ic_std": np.nan, "ic_ir": np.nan,
                "ic_win_rate": np.nan, "ic_t": np.nan, "n": 0}
    mean = clean.mean()
    std  = clean.std()
    ir   = mean / std if std else np.nan
    t    = mean / (std / np.sqrt(len(clean))) if std else np.nan
    return {"ic_mean": mean, "ic_std": std, "ic_ir": ir,
            "ic_win_rate": (clean > 0).mean(), "ic_t": t, "n": len(clean)}


def calc_ic_by_date(
    panel: pd.DataFrame,
    factor_col: str,
    ret_col: str = "ret",
) -> pd.Series:
    def _ic(df):
        return df[factor_col].corr(df[ret_col], method="spearman")
    return panel.groupby("date")[[factor_col, ret_col]].apply(_ic).dropna()


def calc_ic_summary(
    panel: pd.DataFrame,
    factor_col: str,
    ret_col: str = "ret",
) -> dict:
    return calc_ic_stats(calc_ic_by_date(panel, factor_col, ret_col))


# ─────────────────────────── Group helpers ──────────────────────────────────

def assign_groups(values: pd.Series, n_groups: int) -> pd.Series:
    ranks = values.rank(method="first")
    try:
        return pd.qcut(ranks, q=n_groups, labels=range(1, n_groups + 1)).astype(float)
    except ValueError:
        return pd.Series(index=values.index, dtype=float)


def group_returns_series(
    factor: pd.Series,
    ret: pd.Series,
    n_groups: int,
) -> Tuple[pd.Series, float]:
    """Returns (group_mean_rets indexed 1..n, monotonicity_score)."""
    aligned = align_series(factor, ret)
    if aligned.empty:
        return pd.Series(dtype=float), np.nan
    groups  = assign_groups(aligned["factor"], n_groups)
    grouped = aligned["ret"].groupby(groups).mean().reindex(range(1, n_groups + 1))
    mono    = grouped.corr(pd.Series(range(1, n_groups + 1)), method="spearman")
    return grouped, mono


def group_returns(
    panel: pd.DataFrame,
    factor_col: str,
    ret_col: str = "ret",
    n_groups: int = 10,
) -> pd.DataFrame:
    """Panel version: returns DataFrame[date, group1, group2, …]."""
    rows = []
    for date, df in panel.groupby("date"):
        if df[factor_col].nunique() < n_groups:
            continue
        ranks  = df[factor_col].rank(method="first")
        groups = pd.qcut(ranks, n_groups, labels=False) + 1
        grp    = df.assign(group=groups).groupby("group")[ret_col].mean()
        grp.name = date
        rows.append(grp)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ─────────────────────────── Weight helpers ─────────────────────────────────

def normalize_weights(raw: pd.Series) -> pd.Series:
    v     = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(lower=0).astype(float)
    total = v.sum()
    return v / total if total else pd.Series(1.0 / len(v), index=v.index)


def project_simplex(values: Sequence[float]) -> np.ndarray:
    v    = np.asarray(values, dtype=float)
    n    = v.size
    u    = np.sort(v)[::-1]
    css  = np.cumsum(u)
    rho  = np.nonzero(u * np.arange(1, n + 1) > css - 1)[0]
    th   = (css[rho[-1]] - 1) / (rho[-1] + 1) if len(rho) else 0.0
    proj = np.maximum(v - th, 0)
    return proj / proj.sum() if proj.sum() else np.full(n, 1.0 / n)


def cap_weights(weights: Sequence[float], cap: float) -> np.ndarray:
    w     = np.clip(np.asarray(weights, dtype=float), 0.0, cap)
    total = w.sum()
    return w / total if total else w


def ewma_smooth(weights: pd.DataFrame, alpha: float = 0.2) -> pd.DataFrame:
    return weights.ewm(alpha=alpha, adjust=False).mean()


def weight_turnover(weights: pd.DataFrame) -> pd.Series:
    return weights.diff().abs().sum(axis=1).fillna(0.0)


def time_split_dates(
    dates: Sequence[str],
    train_size: int,
    test_size: int,
    step: int,
) -> List[Tuple[List[str], List[str]]]:
    dates  = list(dates)
    splits = []
    start  = 0
    while start + train_size + test_size <= len(dates):
        splits.append((dates[start: start + train_size],
                       dates[start + train_size: start + train_size + test_size]))
        start += step
    return splits


def window_dates(dates: Sequence[str], window: int) -> Iterable[Sequence[str]]:
    for idx in range(len(dates)):
        start = max(0, idx - window)
        yield dates[start:idx]
