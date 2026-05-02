"""
day13 代码示例的共享辅助工具函数。
包含数据加载、预处理、因子分析和权重处理等常用功能。
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd


def ensure_dir(path: Union[str, Path]) -> Path:
    """
    确保目录存在，如果不存在则创建。
    
    Args:
        path: 目录路径。
        
    Returns:
        Path 对象。
    """
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def list_available_dates(
    data_dir: Union[str, Path],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[str]:
    """
    获取同时具有因子暴露(exposure)和收益率(return)文件的排序交易日期。
    
    Args:
        data_dir: 数据根目录。
        start_date: 开始日期 (可选)。
        end_date: 结束日期 (可选)。
        
    Returns:
        符合条件的日期列表。
    """
    data_path = Path(data_dir)
    # 从 date.pkl 加载所有日期
    with open(data_path / "date.pkl", "rb") as f:
        dates = pickle.load(f)

    filtered = []
    for date in dates:
        # 日期范围过滤
        if start_date and date < start_date:
            continue
        if end_date and date > end_date:
            continue

        # 检查两个必要的文件是否存在
        barra_file = data_path / "data_barra" / f"{date}.csv"
        ret_file = data_path / "data_ret" / f"{date}.csv"
        if barra_file.exists() and ret_file.exists():
            filtered.append(date)

    return filtered


def load_real_panel(
    data_dir: Union[str, Path] = "./data",
    ret_col: str = "1vwap_pct",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_dates: Optional[int] = None,
) -> pd.DataFrame:
    """
    从真实的 Barra 因子暴露数据和未来收益率数据构建面板 DataFrame (Panel Data)。
    
    Args:
        data_dir: 数据目录。
        ret_col: 要使用的收益率列名（如 1 天 VWAP 收益率）。
        start_date/end_date: 日期范围。
        max_dates: 最大读取天数（用于加速测试）。
        
    Returns:
        包含日期、资产 ID、各因子暴露和收益率的 DataFrame。
    """
    data_path = Path(data_dir)
    barra_dir = data_path / "data_barra"
    ret_dir = data_path / "data_ret"

    frames: List[pd.DataFrame] = []
    # 遍历所有可用日期并合并数据
    for date in list_available_dates(data_dir, start_date, end_date):
        barra_file = barra_dir / f"{date}.csv"
        ret_file = ret_dir / f"{date}.csv"
        if not barra_file.exists() or not ret_file.exists():
            continue

        # 加载因子暴露数据
        exposures = pd.read_csv(barra_file)
        if exposures.empty:
            continue

        exposures = exposures.rename(columns={"code": "asset"})
        exposures["date"] = date

        # 加载收益率数据
        returns = pd.read_csv(ret_file)
        if ret_col not in returns.columns:
            continue

        returns = returns.rename(columns={"code": "asset", ret_col: "ret"})
        returns = returns[["asset", "ret"]]

        # 按资产 ID (asset) 合并因子和收益率
        merged = pd.merge(exposures, returns, on="asset", how="inner")
        if merged.empty:
            continue

        merged["date"] = date
        frames.append(merged)

        if max_dates is not None and len(frames) >= max_dates:
            break

    if not frames:
        raise ValueError("无法加载真实的面板数据。请检查数据目录。")

    # 合并所有日期的数据
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.dropna(subset=["ret"]) # 确保收益率不为空
    return panel


def infer_factor_columns(panel: pd.DataFrame, ret_col: str = "ret") -> List[str]:
    """
    根据面板数据推断哪些列是因子列（排除日期、资产 ID 和收益率列）。
    """
    ignore = {"date", "asset", ret_col}
    return [col for col in panel.columns if col not in ignore]


def make_synthetic_panel(
    n_dates: int = 120,
    n_assets: int = 200,
    n_factors: int = 6,
    seed: int = 7,
) -> Tuple[pd.DataFrame, pd.Series]:
    """
    生成合成的模拟面板数据，用于算法测试。
    
    Returns:
        (panel_df, true_weights): 返回模拟面板和真实的因子权重。
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-02", periods=n_dates, freq="B")
    assets = [f"A{i:04d}" for i in range(n_assets)]
    factor_cols = [f"factor_{i + 1}" for i in range(n_factors)]

    # 随机生成一些“真实”的权重
    true_weights = rng.normal(size=n_factors)
    true_weights = true_weights / np.sum(np.abs(true_weights))

    frames = []
    for date in dates:
        # 生成正态分布的因子暴露
        exposures = rng.normal(size=(n_assets, n_factors))
        # 收益率 = 因子暴露 * 权重 + 噪声
        noise = rng.normal(scale=0.5, size=n_assets)
        ret = exposures @ true_weights + noise
        
        df = pd.DataFrame(exposures, columns=factor_cols)
        df["ret"] = ret
        df["date"] = date.strftime("%Y-%m-%d")
        df["asset"] = assets
        frames.append(df)

    panel = pd.concat(frames, ignore_index=True)
    return panel, pd.Series(true_weights, index=factor_cols, name="true_weight")


def zscore_by_date(panel: pd.DataFrame, factor_cols: Sequence[str]) -> pd.DataFrame:
    """
    按日期进行截面 Z-Score 标准化。

    原理: (x - mean) / std。使每个日期下因子的均值为 0，标准差为 1。
    这是线性模型处理不同量纲因子所必须的预处理步骤。
    """
    out = panel.copy()

    def _zscore(series: pd.Series) -> pd.Series:
        std = series.std(ddof=0)
        if std == 0 or np.isnan(std):
            return series * 0.0
        return (series - series.mean()) / std

    out[list(factor_cols)] = out.groupby("date")[list(factor_cols)].transform(_zscore)
    return out


def industry_neutralize_by_date(
    panel: pd.DataFrame,
    factor_cols: Sequence[str],
    data_dir: Union[str, Path],
) -> pd.DataFrame:
    """
    按日期进行行业中性化处理（行业内Z-Score标准化）。

    原理：在每个日期的每个行业内部，对因子做 (x - industry_mean) / industry_std。
    这样可以消除行业间的系统性差异，提取纯粹的Alpha信号。

    Args:
        panel: 包含因子数据的面板
        factor_cols: 需要中性化的因子列
        data_dir: 数据目录（用于加载行业分类数据）

    Returns:
        行业中性化后的面板数据
    """
    data_path = Path(data_dir)
    industry_dir = data_path / "data_industry"

    if not industry_dir.exists():
        print(f"[Warning] Industry data directory not found: {industry_dir}")
        print("[Warning] Falling back to simple zscore without industry neutralization")
        return zscore_by_date(panel, factor_cols)

    out = panel.copy()

    def _industry_zscore(series: pd.Series) -> pd.Series:
        """行业内Z-Score标准化"""
        std = series.std(ddof=0)
        if std == 0 or np.isnan(std):
            return series * 0.0
        return (series - series.mean()) / std

    # 按日期分组处理
    for date in out["date"].unique():
        industry_file = industry_dir / f"{date}.csv"
        if not industry_file.exists():
            # 如果没有行业数据，使用全市场zscore
            mask = out["date"] == date
            for col in factor_cols:
                out.loc[mask, col] = _industry_zscore(out.loc[mask, col])
            continue

        # 加载行业分类数据
        industry_df = pd.read_csv(industry_file)
        if "code" not in industry_df.columns or "industry" not in industry_df.columns:
            continue

        # 合并行业信息到panel
        date_mask = out["date"] == date
        date_data = out[date_mask].copy()
        date_data = date_data.merge(
            industry_df[["code", "industry"]],
            left_on="asset",
            right_on="code",
            how="left"
        )

        # 对每个因子进行行业内标准化
        for col in factor_cols:
            if col in date_data.columns:
                neutralized = date_data.groupby("industry")[col].transform(_industry_zscore)
                # 对于没有行业信息的股票，使用全市场zscore
                no_industry_mask = date_data["industry"].isna()
                if no_industry_mask.any():
                    neutralized[no_industry_mask] = _industry_zscore(
                        date_data.loc[no_industry_mask, col]
                    )
                out.loc[date_mask, col] = neutralized.values

    return out


def calc_ic_by_date(
    panel: pd.DataFrame, factor_col: str, ret_col: str = "ret"
) -> pd.Series:
    """
    按日期计算因子的信息系数 (IC, Information Coefficient)。
    这里使用 Spearman 秩相关系数，对离群值不敏感。
    """
    def _ic(df: pd.DataFrame) -> float:
        if df[factor_col].std(ddof=0) == 0 or df[ret_col].std(ddof=0) == 0:
            return np.nan
        return df[factor_col].corr(df[ret_col], method="spearman")

    return panel.groupby("date")[[factor_col, ret_col]].apply(_ic).dropna()


def calc_ic_summary(
    panel: pd.DataFrame, factor_col: str, ret_col: str = "ret"
) -> dict:
    """
    计算因子的 IC 统计指标：均值、标准差和信息比率 (IR)。
    """
    ic_series = calc_ic_by_date(panel, factor_col, ret_col)
    ic_mean = ic_series.mean() if not ic_series.empty else np.nan
    ic_std = ic_series.std(ddof=0) if not ic_series.empty else np.nan
    # ICIR = IC 均值 / IC 标准差，衡量因子的稳定性
    ic_ir = ic_mean / ic_std if ic_std and ic_std != 0 else np.nan
    return {"ic_mean": ic_mean, "ic_std": ic_std, "ic_ir": ic_ir}


def normalize_weights(raw: pd.Series) -> pd.Series:
    """
    将原始权重归一化。
    处理无穷值、空值，并确保权重非负且总和为 1。
    """
    values = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    values = values.clip(lower=0) # 确保不出现负权重
    total = values.sum()
    if total == 0:
        return pd.Series(1.0 / len(values), index=values.index)
    return values / total


def project_simplex(values: Sequence[float]) -> np.ndarray:
    """
    将向量投影到概率单纯形 (Probability Simplex)。
    
    数学目标: 寻找一个向量 w，使得 ||w - v||^2 最小 (欧几里得距离最近)，且满足约束:
    1. sum(w) = 1  (所有权重之和为 1)
    2. w_i >= 0    (所有权重非负，即不允许做空)
    
    该算法常用于投资组合优化中，当我们需要将一组原始因子得分或模型输出转换为合法的权重分布时。
    """
    v = np.asarray(values, dtype=float)
    n = v.size
    if n == 0:
        return v
    
    # 1. 将输入向量按降序排列: u_1 >= u_2 >= ... >= u_n
    u = np.sort(v)[::-1]
    
    # 2. 计算排序后向量的累计和: cssv_j = sum(u_1...u_j)
    cssv = np.cumsum(u)
    
    # 3. 寻找满足 u_j - (1/j)*(cssv_j - 1) > 0 的最大索引 rho
    # 这一步本质上是在寻找一个“水位线”，超过这个水位的元素将被保留并平移，低于水位的将被截断为 0
    # 我们利用公式: rho = max {j | u_j + (1/j)(1 - sum(u_1...u_j)) > 0}
    rho = np.nonzero(u * np.arange(1, n + 1) > (cssv - 1))[0]
    
    if len(rho) == 0:
        # 如果没有找到符合条件的索引（理论上对于非空输入不会发生），设阈值为 0
        theta = 0.0
    else:
        # 取最大的符合条件的索引
        rho = rho[-1]
        # 4. 根据 rho 计算拉格朗日乘子 (截断阈值) theta
        # theta = (sum(u_1...u_rho) - 1) / rho
        theta = (cssv[rho] - 1) / (rho + 1)
    
    # 5. 最终投影结果为 max(v_i - theta, 0)
    # 这保证了所有元素非负，且通过减去 theta 的平移，使得剩余非零元素的总和恰好为 1
    return np.maximum(v - theta, 0.0)


def cap_weights(weights: Sequence[float], cap: float) -> np.ndarray:
    """
    限制权重的上限值 (Weight Capping)，并重新归一化。
    
    在量化配置中，为了防止某个因子或资产的权重过大导致“把鸡蛋放在一个篮子里”的风险，
    通常会对单一权重的上限做出限制（例如：任何因子的权重不得超过 30%）。
    
    Args:
        weights: 原始权重序列。
        cap: 允许的最大权重比例 (0 到 1 之间)。
        
    Returns:
        裁剪并重新归一化后的权重数组。
    """
    # 1. 使用 clip 将所有权重限制在 [0, cap] 范围内
    # 如果某个权重超过了 cap，它会被强制设定为 cap
    w = np.clip(np.asarray(weights, dtype=float), 0.0, cap)
    
    # 2. 计算裁剪后的总和
    total = w.sum()
    
    # 3. 重新归一化 (Re-normalization)
    # 因为裁剪掉了一部分权重，导致总和小于 1，所以需要按比例放大，使总和重新回到 1
    if total == 0:
        return w
    return w / total


def ewma_smooth(weights: pd.DataFrame, alpha: float = 0.2) -> pd.DataFrame:
    """
    使用指数加权移动平均 (EWMA) 对权重时间序列进行平滑。
    可以有效降低调仓频率和换手率。
    """
    return weights.ewm(alpha=alpha, adjust=False).mean()


def weight_turnover(weights: pd.DataFrame) -> pd.Series:
    """
    计算权重的时间序列换手率 (Turnover)。
    定义为相邻两个周期权重差值的绝对值之和。
    """
    return weights.diff().abs().sum(axis=1).fillna(0.0)


def time_split_dates(
    dates: Sequence[str], train_size: int, test_size: int, step: int
) -> List[Tuple[List[str], List[str]]]:
    """
    生成滚动窗口的时间序列分割 (Rolling Window Time Split)。
    
    Args:
        dates: 日期序列。
        train_size: 训练集长度。
        test_size: 测试集长度。
        step: 步长。
        
    Returns:
        包含 (train_dates, test_dates) 元组的列表。
    """
    dates = list(dates)
    splits = []
    start = 0
    while start + train_size + test_size <= len(dates):
        train = dates[start : start + train_size]
        test = dates[start + train_size : start + train_size + test_size]
        splits.append((train, test))
        start += step
    return splits


def group_returns(
    panel: pd.DataFrame,
    factor_col: str,
    ret_col: str = "ret",
    n_groups: int = 10,
) -> pd.DataFrame:
    """
    计算因子的分组单调性。
    将资产按因子值从小到大分成 n_groups 组，并计算每组的平均收益。
    
    用于检验因子是否具有线性预测能力。
    """
    results = []
    for date, df in panel.groupby("date"):
        if df[factor_col].nunique() < n_groups:
            continue
        # 使用 rank 避免处理相同值的冲突
        ranks = df[factor_col].rank(method="first")
        groups = pd.qcut(ranks, n_groups, labels=False) + 1
        grouped = df.assign(group=groups).groupby("group")[ret_col].mean()
        grouped.name = date
        results.append(grouped)
    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results)