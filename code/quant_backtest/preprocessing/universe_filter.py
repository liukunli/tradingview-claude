"""
Standalone utility: filter raw factor files by tradability criteria.

Usage (CLI-style):
    from preprocessing.universe_filter import UniverseFilter
    uf = UniverseFilter()
    uf.filter_folder(
        date_path='./data/date.pkl',
        factor_dir='./factors/raw',
        data_daily_dir='./data/data_daily',
        data_ud_dir='./data/data_ud_new',
        output_dir='./factors/filtered',
        start_date='2020-01-02',
        end_date='2021-12-31',
    )
"""

import pickle
from pathlib import Path
from typing import Optional

import pandas as pd


class UniverseFilter:
    def __init__(
        self,
        min_price: float = 2.0,
        min_volume: float = 1e5,
        min_turnover: float = 0.0005,
        remove_st: bool = True,
    ):
        self.min_price    = min_price
        self.min_volume   = min_volume
        self.min_turnover = min_turnover
        self.remove_st    = remove_st

    def load_dates(self, date_path: str,
                   start_date: Optional[str] = None,
                   end_date: Optional[str] = None):
        with open(date_path, 'rb') as f:
            dates = pickle.load(f)
        if start_date:
            dates = [d for d in dates if d >= start_date]
        if end_date:
            dates = [d for d in dates if d <= end_date]
        return dates

    def _load_csv(self, path: Path, index_col: str = 'code') -> pd.DataFrame:
        df = pd.read_csv(path)
        if index_col in df.columns:
            df = df.set_index(index_col)
        return df

    def build_tradeable_mask(self, merged: pd.DataFrame) -> pd.Series:
        mask = pd.Series(True, index=merged.index)
        if 'paused' in merged.columns:
            mask &= merged['paused'] == 0
        if 'zt' in merged.columns:
            mask &= merged['zt'] == 0
        if 'dt' in merged.columns:
            mask &= merged['dt'] == 0
        if 'close' in merged.columns:
            mask &= merged['close'] >= self.min_price
        if 'volume' in merged.columns:
            mask &= merged['volume'] >= self.min_volume
        if 'turnover_ratio' in merged.columns:
            mask &= merged['turnover_ratio'] >= self.min_turnover
        if self.remove_st:
            if 'is_st' in merged.columns:
                mask &= merged['is_st'] == 0
            elif 'st' in merged.columns:
                mask &= merged['st'] == 0
            elif 'name' in merged.columns:
                mask &= ~merged['name'].astype(str).str.contains('ST', case=False, na=False)
        return mask

    def filter_factors_for_date(self, date: str, factor_dir: str,
                                 data_daily_dir: str, data_ud_dir: str,
                                 output_dir: str) -> dict:
        factor_file = Path(factor_dir)  / f'{date}.csv'
        daily_file  = Path(data_daily_dir) / f'{date}.csv'
        status_file = Path(data_ud_dir)    / f'{date}.csv'

        if not (factor_file.exists() and daily_file.exists() and status_file.exists()):
            return {'date': date, 'status': 'missing'}

        factor_df = self._load_csv(factor_file)
        daily_df  = self._load_csv(daily_file)
        status_df = self._load_csv(status_file)

        overlap = status_df.columns.intersection(daily_df.columns)
        if len(overlap):
            status_df = status_df.drop(columns=overlap)

        merged = daily_df.join(status_df, how='left')
        mask   = self.build_tradeable_mask(merged)

        common  = factor_df.index.intersection(mask.index)
        before  = len(common)
        filtered = factor_df.loc[common][mask.loc[common]]
        after    = filtered.shape[0]

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        filtered.to_csv(Path(output_dir) / f'{date}.csv')

        return {
            'date': date, 'status': 'ok',
            'before': before, 'after': after,
            'drop_rate': 1 - after / before if before else None,
        }

    def filter_folder(self, date_path: str, factor_dir: str,
                      data_daily_dir: str, data_ud_dir: str,
                      output_dir: str, start_date: Optional[str] = None,
                      end_date: Optional[str] = None) -> None:
        dates   = self.load_dates(date_path, start_date, end_date)
        records = []
        print(f"Universe filter: processing {len(dates)} days …")
        for date in dates:
            records.append(self.filter_factors_for_date(
                date, factor_dir, data_daily_dir, data_ud_dir, output_dir))
        summary = pd.DataFrame(records)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        summary.to_csv(out / 'universe_filter_summary.csv', index=False)
        print(f"Done → {output_dir}")
