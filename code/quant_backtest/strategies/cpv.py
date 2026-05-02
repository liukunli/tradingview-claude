import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional

from core.strategy_base import Strategy


class CPVStrategy(Strategy):
    """
    CPV (Candle-Price-Volume) factor strategy.

    Reproduces the Huatai Securities quant research paper:
    "CPV因子：价量自相关性的量化挖掘".

    Factor components
    -----------------
    U  – upper-shadow ratio  (high selling pressure → bearish)
    B  – body ratio          (strong directional move)
    L  – lower-shadow ratio  (strong support → bullish)
    WR – Williams %R         (mean of recent closes vs high-low range)
    TREND – WR_short - WR_long  (short-term momentum in WR)

    Combined as:  CPV = w_U·U + w_B·B + w_L·L + w_WR·WR + w_TREND·TREND
    then market-cap and (optionally) industry neutralised.
    """

    def __init__(
        self,
        data_dir: str = './data',
        candle_window_short: int = 5,
        candle_window_long: int = 20,
        wr_window_short: int = 5,
        wr_window_long: int = 20,
        min_avg_volume: float = 5e5,
        liquidity_window: int = 20,
        min_stock_count: int = 200,
        weights: Optional[Dict[str, float]] = None,
        outlier_method: str = 'sigma',
        outlier_param: float = 3.0,
        neutralize_industry: bool = True,
        min_listed_days: int = 252,
        min_listed_coverage: float = 0.8,
        use_long_candle: bool = True,
    ):
        super().__init__(name='CPV_UBL')
        self.data_dir            = Path(data_dir)
        self.candle_window_short = candle_window_short
        self.candle_window_long  = candle_window_long
        self.wr_window_short     = wr_window_short
        self.wr_window_long      = wr_window_long
        self.min_avg_volume      = min_avg_volume
        self.liquidity_window    = liquidity_window
        self.min_stock_count     = min_stock_count
        self.weights             = weights or {'U': 1, 'B': 1, 'L': 1, 'WR': 1, 'TREND': 1}
        self.outlier_method      = outlier_method
        self.outlier_param       = outlier_param
        self.neutralize_industry = neutralize_industry
        self.min_listed_days     = min_listed_days
        self.min_listed_coverage = min_listed_coverage
        self.use_long_candle     = use_long_candle

        # Caches to avoid repeated disk I/O
        self.trade_dates:   Optional[List[str]] = None
        self.date_to_idx:   Dict[str, int]      = {}
        self.daily_cache:   Dict[str, pd.DataFrame] = {}
        self.status_cache:  Dict[str, pd.DataFrame] = {}
        self.barra_cache:   Dict[str, pd.DataFrame] = {}
        self.industry_cache: Dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------ utils

    @staticmethod
    def _zscore(s: pd.Series) -> pd.Series:
        s = s.astype(float)
        std = s.std()
        if std == 0 or np.isnan(std):
            return s * 0.0
        return (s - s.mean()) / (std + 1e-8)

    def _clip_outliers(self, df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
        if df.empty:
            return df
        method = (self.outlier_method or '').lower()
        for col in cols:
            if col not in df.columns:
                continue
            s = df[col].astype(float)
            if method == 'quantile':
                q = float(self.outlier_param)
                df[col] = s.clip(s.quantile(q), s.quantile(1 - q))
            else:
                mean, std = s.mean(), s.std()
                if std == 0 or np.isnan(std):
                    continue
                n = float(self.outlier_param)
                df[col] = s.clip(mean - n * std, mean + n * std)
        return df

    def _ensure_trade_dates(self, data_loader):
        if self.trade_dates is None:
            self.trade_dates = data_loader.get_all_dates()
            self.date_to_idx = {d: i for i, d in enumerate(self.trade_dates)}

    def _get_daily(self, data_loader, date: str) -> pd.DataFrame:
        if date not in self.daily_cache:
            df = data_loader.get_daily_data(date)
            if not df.empty:
                base_cols  = ['code', 'open', 'high', 'low', 'close', 'volume', 'date']
                cap_cols   = ['market_cap', 'total_mv', 'mkt_cap', 'mv', 'circ_mv', 'float_mv']
                keep       = [c for c in base_cols + cap_cols if c in df.columns]
                df         = df[keep].copy()
                df['time'] = pd.to_datetime(df['date'] if 'date' in df.columns else date)
            self.daily_cache[date] = df
        return self.daily_cache[date]

    def _get_status(self, data_loader, date: str) -> pd.DataFrame:
        if date not in self.status_cache:
            self.status_cache[date] = data_loader.get_daily_status(date)
        return self.status_cache[date]

    def _get_barra(self, date: str) -> pd.DataFrame:
        if date not in self.barra_cache:
            path = self.data_dir / 'data_barra' / f'{date}.csv'
            self.barra_cache[date] = pd.read_csv(path) if path.exists() else pd.DataFrame()
        return self.barra_cache[date]

    def _get_industry(self, date: str) -> pd.DataFrame:
        if date not in self.industry_cache:
            path = self.data_dir / 'data_industry' / f'{date}.csv'
            self.industry_cache[date] = pd.read_csv(path) if path.exists() else pd.DataFrame()
        return self.industry_cache[date]

    # ----------------------------------------------------------------- universe

    def _get_stock_pool(self, date: str, data_loader) -> List[str]:
        daily = self._get_daily(data_loader, date)
        if daily is None or daily.empty:
            return []
        stocks = daily['code'].tolist()

        # Filter halted / limit-hit / ST
        status = self._get_status(data_loader, date)
        if status is not None and not status.empty:
            st = status.copy()
            if 'st' in st.columns:
                st = st[st['st'] == 0]
            tradable = st[(st['paused'] == 0) & (st['zt'] == 0) & (st['dt'] == 0)]
            tradable_set = set(tradable['code'])
            stocks = [s for s in stocks if s in tradable_set]

        idx = self.date_to_idx.get(date)
        if idx is None:
            return []

        # Listing-age filter
        min_days = max(self.candle_window_long, self.wr_window_long, self.min_listed_days)
        if idx >= min_days:
            eligible_dates = self.trade_dates[idx - min_days: idx]
            counts: Dict[str, int] = {}
            for d in eligible_dates:
                df = self._get_daily(data_loader, d)
                if df is None or df.empty:
                    continue
                for code in df['code']:
                    counts[code] = counts.get(code, 0) + 1
            min_required = int(min_days * self.min_listed_coverage)
            stocks = [s for s in stocks if counts.get(s, 0) >= min_required]

        if idx <= self.liquidity_window:
            return stocks

        # Liquidity filter
        hist = self.trade_dates[idx - self.liquidity_window: idx]
        vol_frames = []
        stock_set  = set(stocks)
        for d in hist:
            df = self._get_daily(data_loader, d)
            if df is None or df.empty:
                continue
            sub = df[df['code'].isin(stock_set)][['code', 'volume']]
            if not sub.empty:
                vol_frames.append(sub)
        if vol_frames:
            avg_vol = pd.concat(vol_frames).groupby('code')['volume'].mean()
            stocks  = avg_vol[avg_vol >= self.min_avg_volume].index.tolist()

        return stocks

    def _load_panel(self, date: str, stocks: List[str],
                    data_loader, window: int) -> pd.DataFrame:
        idx = self.date_to_idx.get(date)
        if idx is None or idx < window:
            return pd.DataFrame()

        use_dates  = self.trade_dates[idx - window + 1: idx + 1]
        stock_set  = set(stocks)
        frames     = []
        for d in use_dates:
            df = self._get_daily(data_loader, d)
            if df is None or df.empty:
                continue
            sub = df[df['code'].isin(stock_set)].copy()
            if not sub.empty:
                if 'time' not in sub.columns:
                    sub['time'] = pd.to_datetime(d)
                frames.append(sub)

        if not frames:
            return pd.DataFrame()
        panel  = pd.concat(frames).sort_values(['code', 'time'])
        counts = panel.groupby('code').size()
        valid  = counts[counts >= window].index
        return panel[panel['code'].isin(valid)]

    # ----------------------------------------------------------------- neutralize

    def _neutralize(self, factor_df: pd.DataFrame, date: str) -> pd.DataFrame:
        if factor_df.empty:
            return factor_df

        df = factor_df.copy()

        # Size factor: prefer actual market cap, fall back to barra size
        cap_col = next((c for c in ['market_cap','total_mv','mkt_cap','mv','circ_mv','float_mv']
                        if c in df.columns), None)
        if cap_col:
            df['size_factor'] = np.log(df[cap_col].astype(float).replace(0, np.nan))
        else:
            barra = self._get_barra(date)
            if not barra.empty and 'size' in barra.columns:
                df = df.join(barra.set_index('code')['size'].rename('size_factor'))

        if self.neutralize_industry:
            ind = self._get_industry(date)
            if not ind.empty and 'industry' in ind.columns:
                df = df.join(ind.set_index('code')['industry'].rename('industry'))

        drop_cols = ['CPV']
        if 'size_factor' in df.columns:
            drop_cols.append('size_factor')
        if self.neutralize_industry and 'industry' in df.columns:
            drop_cols.append('industry')

        df = df.dropna(subset=drop_cols)
        if df.empty:
            return pd.DataFrame()

        X_parts = [np.ones(len(df))]
        if 'size_factor' in df.columns:
            X_parts.append(df['size_factor'].values)
        if self.neutralize_industry and 'industry' in df.columns:
            dummies = pd.get_dummies(df['industry'], drop_first=True)
            if not dummies.empty:
                X_parts.append(dummies.values)

        X = np.column_stack(X_parts)
        y = df['CPV'].values
        try:
            coef  = np.linalg.lstsq(X, y, rcond=None)[0]
            resid = y - X.dot(coef)
        except Exception:
            resid = y - y.mean()

        df['CPV_neu'] = self._zscore(pd.Series(resid, index=df.index))
        return df

    # ----------------------------------------------------------------- interface

    def calculate_factor(self, date: str, data_loader, **kwargs) -> pd.DataFrame:
        self._ensure_trade_dates(data_loader)

        stocks = self._get_stock_pool(date, data_loader)
        if len(stocks) < self.min_stock_count:
            return pd.DataFrame()

        max_window = max(self.candle_window_long, self.wr_window_long)
        panel      = self._load_panel(date, stocks, data_loader, max_window)
        if panel.empty:
            return pd.DataFrame()

        df        = panel.copy()
        df['hl']  = (df['high'] - df['low']).replace(0, 0.001)
        df['upper'] = df['high'] - df[['open','close']].max(axis=1)
        df['lower'] = df[['open','close']].min(axis=1) - df['low']
        df['body']  = (df['close'] - df['open']).abs()

        grp = df.groupby('code', group_keys=False)
        for w in [self.candle_window_short, self.candle_window_long]:
            for col in ('upper', 'lower', 'body', 'hl'):
                df[f'{col}_mean_{w}'] = grp[col].rolling(w).mean().reset_index(level=0, drop=True)
            df[f'U_{w}'] = df[f'upper_mean_{w}'] / df[f'hl_mean_{w}']
            df[f'B_{w}'] = df[f'body_mean_{w}']  / df[f'hl_mean_{w}']
            df[f'L_{w}'] = df[f'lower_mean_{w}']  / df[f'hl_mean_{w}']

        df['wr']       = (df['close'] - df['low']) / df['hl'] * 100
        df['wr_s']     = grp['wr'].rolling(self.wr_window_short).mean().reset_index(level=0, drop=True)
        df['wr_l']     = grp['wr'].rolling(self.wr_window_long).mean().reset_index(level=0,  drop=True)
        df['wr_trend'] = df['wr_s'] - df['wr_l']

        latest     = df.groupby('code').tail(1).set_index('code')
        factor_raw = pd.DataFrame(index=latest.index)
        for sfx, w in [('5', self.candle_window_short), ('20', self.candle_window_long)]:
            factor_raw[f'U{sfx}'] = latest[f'U_{w}']
            factor_raw[f'B{sfx}'] = latest[f'B_{w}']
            factor_raw[f'L{sfx}'] = latest[f'L_{w}']
        factor_raw['WR']    = latest['wr_l']
        factor_raw['TREND'] = latest['wr_trend']
        for cap in ['market_cap','total_mv','mkt_cap','mv','circ_mv','float_mv']:
            if cap in latest.columns:
                factor_raw[cap] = latest[cap]
                break

        factor_raw = self._clip_outliers(factor_raw, ['U5','B5','L5','U20','B20','L20','WR','TREND'])

        z = {col: self._zscore(factor_raw[col])
             for col in ['U5','B5','L5','U20','B20','L20','WR','TREND']
             if col in factor_raw.columns}

        factor = pd.DataFrame(index=latest.index)
        if self.use_long_candle:
            factor['U'] = (z['U5'] + z['U20']) / 2
            factor['B'] = (z['B5'] + z['B20']) / 2
            factor['L'] = (z['L5'] + z['L20']) / 2
        else:
            factor['U'] = z['U5']
            factor['B'] = z['B5']
            factor['L'] = z['L5']
        factor['WR']    = z['WR']
        factor['TREND'] = z['TREND']

        w      = self.weights
        total  = sum(w.values()) or 1
        factor['CPV'] = (
            w['U'] * factor['U'] + w['B'] * factor['B'] + w['L'] * factor['L'] +
            w['WR'] * factor['WR'] + w['TREND'] * factor['TREND']
        ) / total

        # Carry market-cap columns through for neutralisation
        for cap in ['market_cap','total_mv','mkt_cap','mv','circ_mv','float_mv']:
            if cap in factor_raw.columns:
                factor[cap] = factor_raw[cap]
                break

        factor = self._clip_outliers(factor, ['CPV'])
        factor = self._neutralize(factor, date)

        if factor.empty or 'CPV_neu' not in factor.columns:
            return pd.DataFrame()

        result = (factor[['CPV_neu']]
                  .rename(columns={'CPV_neu': 'factor_value'})
                  .dropna(subset=['factor_value'])
                  .reset_index())
        result['date'] = date
        return result[['code', 'date', 'factor_value']]

    def generate_signal(self, factor_df: pd.DataFrame, top_n: int = 50) -> list:
        if factor_df.empty or 'factor_value' not in factor_df.columns:
            return []
        return (factor_df.sort_values('factor_value', ascending=False)
                .head(top_n)['code'].tolist())
