from abc import ABC, abstractmethod
import pandas as pd


class Strategy(ABC):
    """
    Abstract base for all strategies.

    Every strategy must implement:
      - calculate_factor(date, data_loader) → DataFrame[code, date, factor_value]
      - generate_signal(factor_df, top_n)   → list[str]   (stock codes)
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def calculate_factor(self, date: str, data_loader, **kwargs) -> pd.DataFrame:
        pass

    @abstractmethod
    def generate_signal(self, factor_df: pd.DataFrame, top_n: int = 10) -> list:
        pass
