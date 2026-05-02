import pandas as pd
from core.strategy_base import Strategy


class MomentumStrategy(Strategy):
    """Buy the top-N stocks by N-day return (trend-following)."""

    def __init__(self, period: int = 20):
        super().__init__(name=f'Momentum_{period}')
        self.period = period

    def calculate_factor(self, date: str, data_loader, **kwargs) -> pd.DataFrame:
        dates = data_loader.get_all_dates()
        if date not in dates:
            return pd.DataFrame()
        idx = dates.index(date)
        if idx < self.period:
            return pd.DataFrame()

        past_date    = dates[idx - self.period]
        current_data = data_loader.get_daily_data(date)
        past_data    = data_loader.get_daily_data(past_date)
        if current_data.empty or past_data.empty:
            return pd.DataFrame()

        merged = pd.merge(
            current_data[['code', 'close']],
            past_data[['code', 'close']],
            on='code', suffixes=('_now', '_past'),
        )
        merged['factor_value'] = merged['close_now'] / merged['close_past'] - 1
        merged['date'] = date
        return merged[['code', 'date', 'factor_value']]

    def generate_signal(self, factor_df: pd.DataFrame, top_n: int = 10) -> list:
        if factor_df.empty:
            return []
        return (factor_df.sort_values('factor_value', ascending=False)
                .head(top_n)['code'].tolist())


class ReversalStrategy(Strategy):
    """Buy the top-N stocks by worst N-day return (mean-reversion)."""

    def __init__(self, period: int = 5):
        super().__init__(name=f'Reversal_{period}')
        self.period = period

    def calculate_factor(self, date: str, data_loader, **kwargs) -> pd.DataFrame:
        dates = data_loader.get_all_dates()
        if date not in dates:
            return pd.DataFrame()
        idx = dates.index(date)
        if idx < self.period:
            return pd.DataFrame()

        past_date    = dates[idx - self.period]
        current_data = data_loader.get_daily_data(date)
        past_data    = data_loader.get_daily_data(past_date)
        if current_data.empty or past_data.empty:
            return pd.DataFrame()

        merged = pd.merge(
            current_data[['code', 'close']],
            past_data[['code', 'close']],
            on='code', suffixes=('_now', '_past'),
        )
        merged['factor_value'] = merged['close_now'] / merged['close_past'] - 1
        merged['date'] = date
        return merged[['code', 'date', 'factor_value']]

    def generate_signal(self, factor_df: pd.DataFrame, top_n: int = 10) -> list:
        if factor_df.empty:
            return []
        return (factor_df.sort_values('factor_value', ascending=True)
                .head(top_n)['code'].tolist())
