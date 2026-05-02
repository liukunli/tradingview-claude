"""
Utilities for Day12 factor evaluation and multi-factor modules.
Day12 因子评估和多因子模块的通用工具库。

Key assumptions
1) Factor files are cross-sectional CSVs keyed by `code` (one file per date).
2) Return files store forward returns aligned to the same date (e.g. 1vwap_pct).
3) Calculations are cross-sectional per date; time-series stats are built later.
关键假设
1) 因子文件是按日期存储的截面数据 (每行一只股票)，主键是 code。
2) 收益率文件存储的是同日对齐的“未来收益”（即 T日文件存的是 T到T+1 的收益）。
3) 核心计算（IC、分组）都是每日独立的截面计算。

Knowledge points
- Alignment: always join by code to avoid information leakage.
  对齐：必须通过股票代码 (code) 严格对齐，防止数据错位导致结果无效。
- Standardization: z-score removes scale, enabling fair multi-factor aggregation.
  标准化：Z-score 去除量纲，使得不同因子（如价格和换手率）可以加权合并。
- Grouping: quantile buckets approximate long-short portfolio sorts.
  分组：分位数分桶近似于多空组合构建。
- Simplex projection: converts arbitrary weights into non-negative sum-to-1.
  单纯形投影：将任意权重向量转换为“非负且和为1”的向量。
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd


def ensure_dir(path: str | Path) -> Path:
    # Create output directory if it does not exist.
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def list_available_dates(
    data_dir: Union[str, Path],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    exposure_subdir: str = "data_barra",
    ret_subdir: str = "data_ret",
) -> List[str]:
    """Return dates that have both exposure and return files available."""

    data_path = Path(data_dir)
    with open(data_path / "date.pkl", "rb") as f:
        dates = pickle.load(f)

    filtered = []
    for date in dates:
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue

        exposure_file = data_path / exposure_subdir / f"{date}.csv"
        ret_file = data_path / ret_subdir / f"{date}.csv"
        if exposure_file.exists() and ret_file.exists():
            filtered.append(date)

    return filtered


def load_real_panel(
    data_dir: Union[str, Path] = "./data",
    ret_col: str = "1vwap_pct",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_dates: Optional[int] = None,
) -> pd.DataFrame:
    """Build a panel of Barra exposures merged with forward returns."""

    data_path = Path(data_dir)
    barra_dir = data_path / "data_barra"
    ret_dir = data_path / "data_ret"

    frames: List[pd.DataFrame] = []
    for date in list_available_dates(data_dir, start_date, end_date):
        barra_file = barra_dir / f"{date}.csv"
        ret_file = ret_dir / f"{date}.csv"
        if not barra_file.exists() or not ret_file.exists():
            continue

        exposures = pd.read_csv(barra_file)
        if exposures.empty:
            continue
        exposures = exposures.rename(columns={"code": "asset"})
        exposures["date"] = date

        returns = pd.read_csv(ret_file)
        if ret_col not in returns.columns:
            continue
        returns = returns.rename(columns={"code": "asset", ret_col: "ret"})
        returns = returns[["asset", "ret"]]

        merged = pd.merge(exposures, returns, on="asset", how="inner")
        if merged.empty:
            continue
        merged["date"] = date
        frames.append(merged)

        if max_dates is not None and len(frames) >= max_dates:
            break

    if not frames:
        raise ValueError("No panel data could be loaded from the provided directory.")

    panel = pd.concat(frames, ignore_index=True)
    panel = panel.dropna(subset=["ret"])
    return panel


def infer_factor_columns(panel: pd.DataFrame, ret_col: str = "ret") -> List[str]:
    """Infer factor columns from a panel that contains date/asset/return columns."""

    ignore = {"date", "asset", ret_col}
    return [col for col in panel.columns if col not in ignore]


def load_dates(date_path: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[str]:
    # date.pkl is expected to be a list of sorted trading dates.
    with open(date_path, "rb") as f:
        dates = pickle.load(f)
    if start_date:
        dates = [d for d in dates if d >= start_date]
    if end_date:
        dates = [d for d in dates if d <= end_date]
    return dates


def infer_factor_cols(df: pd.DataFrame, exclude: Sequence[str] = ("code", "date")) -> List[str]:
    # Remove non-factor columns so downstream logic can be generic.
    return [col for col in df.columns if col not in set(exclude)]


def load_factor_frame(
    factor_dir: str,
    date: str,
    factor_cols: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    # Load factor cross-section for a date and return selected factor columns.
    file = Path(factor_dir) / f"{date}.csv"
    if not file.exists():
        return pd.DataFrame()
    df = pd.read_csv(file)
    if "code" in df.columns:
        df = df.set_index("code")
    cols = list(factor_cols) if factor_cols is not None else infer_factor_cols(df)
    if not cols:
        return pd.DataFrame()
    return df[cols].astype(float)


def load_factor_series(
    factor_dir: str,
    date: str,
    factor_col: Optional[str] = None,
) -> pd.Series:
    # Convenience wrapper: return one factor column as Series.
    # 便捷函数：只加载单列因子，返回 Series。
    df = load_factor_frame(factor_dir, date, None)
    if df.empty:
        return pd.Series(dtype=float)
    col = factor_col or df.columns[0]
    if col not in df.columns:
        return pd.Series(dtype=float)
    return df[col].astype(float)


def load_return_series(
    data_dir: str,
    date: str,
    ret_col: str = "1vwap_pct",
) -> pd.Series:
    # Returns are stored in data_ret/date.csv with forward return columns.
    file = Path(data_dir) / "data_ret" / f"{date}.csv"
    if not file.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(file)
    if "code" not in df.columns or ret_col not in df.columns:
        return pd.Series(dtype=float)
    df = df.set_index("code")
    return df[ret_col].astype(float)


def align_series(factor_series: pd.Series, ret_series: pd.Series) -> pd.DataFrame:
    # Align on code and drop missing values to avoid biased statistics.
    # 核心对齐逻辑：取交集并丢弃 NaN。
    aligned = pd.concat([factor_series, ret_series], axis=1).dropna()
    if aligned.empty:
        return pd.DataFrame()
    aligned.columns = ["factor", "ret"]
    return aligned


def zscore_series(series: pd.Series) -> pd.Series:
    # Cross-sectional z-score; if std is zero, return zeros to avoid infs.
    # 截面 Z-score: (x - mean) / std
    mean = series.mean()
    std = series.std()
    if std == 0 or np.isnan(std):
        return series * 0.0
    return (series - mean) / std


def zscore_frame(frame: pd.DataFrame) -> pd.DataFrame:
    # Apply z-score to each factor column independently.
    return frame.apply(zscore_series, axis=0)


def calc_ic(factor_series: pd.Series, ret_series: pd.Series, method: str = "spearman") -> float:
    # IC is simply the cross-sectional correlation between factor and return.
    # IC 计算本质就是两个 Series 的相关系数。
    aligned = align_series(factor_series, ret_series)
    if aligned.empty:
        return np.nan
    return aligned["factor"].corr(aligned["ret"], method=method)


def calc_ic_stats(ic_series: pd.Series) -> dict:
    # Summarize IC with mean/std/IR/win-rate/t-stat.
    clean = ic_series.dropna()
    if clean.empty:
        return {
            "ic_mean": np.nan,
            "ic_std": np.nan,
            "ic_ir": np.nan,
            "ic_win_rate": np.nan,
            "ic_t": np.nan,
            "n": 0,
        }
    mean = clean.mean()
    std = clean.std()
    ir = mean / std if std != 0 else np.nan
    win_rate = (clean > 0).mean()
    # t-value = mean / (std / sqrt(N))
    t_val = mean / (std / np.sqrt(len(clean))) if std != 0 else np.nan
    return {
        "ic_mean": mean,
        "ic_std": std,
        "ic_ir": ir,
        "ic_win_rate": win_rate,
        "ic_t": t_val,
        "n": len(clean),
    }


def assign_groups(values: pd.Series, n_groups: int) -> pd.Series:
    # Rank first to stabilize qcut when duplicates exist.
    # 技巧：先 Rank 再 qcut，可以有效处理大量相同值（如 0 值）导致的分组报错问题。
    ranks = values.rank(method="first")
    try:
        groups = pd.qcut(ranks, q=n_groups, labels=range(1, n_groups + 1))
    except ValueError:
        return pd.Series(index=values.index, dtype=float)
    return groups.astype(float)


def group_returns(factor_series: pd.Series, ret_series: pd.Series, n_groups: int) -> Tuple[pd.Series, float]:
    # Compute group mean returns and monotonicity (Spearman vs group index).
    # 计算分组收益和单调性得分。
    aligned = align_series(factor_series, ret_series)
    if aligned.empty:
        return pd.Series(dtype=float), np.nan
    groups = assign_groups(aligned["factor"], n_groups=n_groups)
    if groups.empty:
        return pd.Series(dtype=float), np.nan
    
    # 聚合每组的平均收益
    grouped = aligned["ret"].groupby(groups).mean()
    grouped = grouped.reindex(range(1, n_groups + 1))
    
    # 单调性：组号 (1,2,3...) 与 组收益 的相关性
    monotonicity = grouped.corr(pd.Series(range(1, n_groups + 1)), method="spearman")
    return grouped, monotonicity


def project_to_simplex(weights: np.ndarray) -> np.ndarray:
    # Projection to simplex: non-negative weights that sum to 1.
    # 经典算法：将任意实数向量投影到单纯形上 (Euclidean Projection to Simplex)。
    # 参考文献: Duchi et al. (2008) "Efficient Projections onto the L1-Ball"
    if weights.ndim != 1:
        raise ValueError("weights must be 1d")
    if weights.size == 0:
        return weights
    sorted_w = np.sort(weights)[::-1]
    cumsum = np.cumsum(sorted_w)
    rho = np.nonzero(sorted_w * np.arange(1, len(weights) + 1) > (cumsum - 1))[0]
    if len(rho) == 0:
        return np.full_like(weights, 1.0 / len(weights))
    rho = rho[-1]
    theta = (cumsum[rho] - 1) / (rho + 1)
    projected = np.maximum(weights - theta, 0)
    if projected.sum() == 0:
        return np.full_like(weights, 1.0 / len(weights))
    return projected / projected.sum()


def window_dates(dates: Sequence[str], window: int) -> Iterable[Sequence[str]]:
    # Yield rolling windows of past dates (exclusive of the current date).
    # 生成滚动窗口生成器，注意是 "Exclusive" (不包含 T 日)，防止未来函数。
    if window <= 0:
        for _ in dates:
            yield []
        return
    for idx in range(len(dates)):
        start = max(0, idx - window)
        yield dates[start:idx]
