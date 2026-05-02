import numpy as np
import pandas as pd


class PerformanceEvaluator:
    """Computes standard backtest performance metrics."""

    def __init__(self, risk_free_rate: float = 0.03):
        self.risk_free_rate = risk_free_rate
        print("✅ PerformanceEvaluator ready")

    def calculate_max_drawdown(self, cumulative_returns: pd.Series) -> dict:
        running_max = cumulative_returns.cummax()
        drawdown    = (cumulative_returns - running_max) / running_max
        max_dd      = drawdown.min()
        max_dd_idx  = drawdown.idxmin()
        max_dd_start = cumulative_returns[:max_dd_idx].idxmax()
        return {
            'max_drawdown':    abs(max_dd),
            'max_dd_start':    max_dd_start,
            'max_dd_end':      max_dd_idx,
            'drawdown_series': drawdown,
        }

    def calculate_sharpe_ratio(self, returns: pd.Series, periods_per_year: int = 252) -> float:
        annual_return     = returns.mean() * periods_per_year
        annual_volatility = returns.std() * np.sqrt(periods_per_year)
        if annual_volatility > 0:
            return (annual_return - self.risk_free_rate) / annual_volatility
        return 0.0

    def calculate_calmar_ratio(self, cumulative_returns: pd.Series,
                               returns: pd.Series, periods_per_year: int = 252) -> float:
        annual_return = returns.mean() * periods_per_year
        max_dd        = self.calculate_max_drawdown(cumulative_returns)['max_drawdown']
        return annual_return / max_dd if max_dd > 0 else 0.0

    def calculate_ic(self, factor_values: pd.Series, next_returns: pd.Series,
                     method: str = 'spearman') -> float:
        common = factor_values.index.intersection(next_returns.index)
        if len(common) < 10:
            return np.nan
        f = factor_values.loc[common]
        r = next_returns.loc[common]
        valid = f.notna() & r.notna()
        f, r  = f[valid], r[valid]
        if len(f) < 10:
            return np.nan
        return f.corr(r, method=method)

    def calculate_ic_ir(self, ic_series: pd.Series) -> dict:
        clean = ic_series.dropna()
        if len(clean) == 0:
            return {'ic_mean': np.nan, 'ic_std': np.nan, 'ir': np.nan, 'ic_win_rate': np.nan}
        ic_mean = clean.mean()
        ic_std  = clean.std()
        return {
            'ic_mean':     ic_mean,
            'ic_std':      ic_std,
            'ir':          ic_mean / ic_std if ic_std > 0 else 0.0,
            'ic_win_rate': (clean > 0).sum() / len(clean),
        }

    def generate_report(self, cumulative_returns: pd.Series, returns: pd.Series) -> dict:
        total_return      = cumulative_returns.iloc[-1] - 1
        annual_return     = returns.mean() * 252
        annual_volatility = returns.std() * np.sqrt(252)
        max_dd_info       = self.calculate_max_drawdown(cumulative_returns)

        return {
            'total_return':      total_return,
            'annual_return':     annual_return,
            'annual_volatility': annual_volatility,
            'max_drawdown':      max_dd_info['max_drawdown'],
            'max_dd_start':      max_dd_info['max_dd_start'],
            'max_dd_end':        max_dd_info['max_dd_end'],
            'sharpe_ratio':      self.calculate_sharpe_ratio(returns),
            'calmar_ratio':      self.calculate_calmar_ratio(cumulative_returns, returns),
            'win_rate':          (returns > 0).sum() / len(returns),
            'best_day':          returns.max(),
            'worst_day':         returns.min(),
        }
