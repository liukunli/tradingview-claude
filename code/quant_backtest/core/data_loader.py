import pandas as pd
import pickle
from pathlib import Path
from typing import List


class DataLoader:
    """Loads daily market data from the local data directory."""

    def __init__(self, data_dir: str = './data'):
        self.data_dir = Path(data_dir)

        with open(self.data_dir / 'date.pkl', 'rb') as f:
            all_trade_dates = pickle.load(f)

        self.trade_dates = [
            date for date in all_trade_dates
            if (self.data_dir / 'data_daily' / f'{date}.csv').exists()
        ]

        print(f"✅ DataLoader ready  |  {len(self.trade_dates)} trading days found")
        if not self.trade_dates:
            print("⚠️  No daily data found – check data_dir path")

    def get_all_dates(self) -> List[str]:
        return self.trade_dates

    def get_daily_data(self, date: str) -> pd.DataFrame:
        """OHLCV + market cap for a single day."""
        path = self.data_dir / 'data_daily' / f'{date}.csv'
        return pd.read_csv(path) if path.exists() else pd.DataFrame()

    def get_daily_returns(self, date: str) -> pd.DataFrame:
        """Forward returns (1vwap_pct, 5vwap_pct, 10vwap_pct)."""
        path = self.data_dir / 'data_ret' / f'{date}.csv'
        return pd.read_csv(path) if path.exists() else pd.DataFrame()

    def get_daily_status(self, date: str) -> pd.DataFrame:
        """Trade status: paused, limit-up (zt), limit-down (dt), ST flag."""
        path = self.data_dir / 'data_ud_new' / f'{date}.csv'
        return pd.read_csv(path) if path.exists() else pd.DataFrame()
