import yfinance as yf

import pandas as pd
from data_loader import DataLoader
from factor_calculator import FactorCalculator


class SignalGenerator:

    def fetch_ndx_1min_data(period='1d'):
        """
        获取 NDX 1分钟K线数据（近1天或指定周期）
        Args:
            period: yfinance 支持的周期，如 '1d', '5d', '1mo'
        Returns:
            pd.DataFrame: 1分钟K线数据
        """
        ticker = '^NDX'
        df = yf.download(ticker, interval='1m', period=period, progress=False)
        if not df.empty:
            df.reset_index(inplace=True)
        return df
    def __init__(self, data_loader: DataLoader, factor_calculator: FactorCalculator):
        """
        初始化信号生成器


        # ========== 仅获取 NDX 1分钟数据 ==========
        if __name__ == '__main__':
            def fetch_ndx_1min_data(period='1d'):
                """
                Fetch 1-minute bar data for NDX (NASDAQ 100 Index) using yfinance.
                Args:
                    period (str): Period to fetch, e.g. '1d', '5d', '1mo'.
                Returns:
                    pd.DataFrame: 1-minute bar data.
                """
                import yfinance as yf
                df = yf.download('^NDX', interval='1m', period=period, progress=False)
                if not df.empty:
                    df.reset_index(inplace=True)
                return df

            print("\nFetching NDX 1-minute bar data (last 1 day)...")
            ndx_1min_df = fetch_ndx_1min_data(period='1d')
            if not ndx_1min_df.empty:
                print(ndx_1min_df.head())
                print(f"Total {len(ndx_1min_df)} rows of 1-minute data fetched.")
            else:
                print("No NDX 1-minute data fetched.")
        import yfinance as yf
        df = yf.download('^NDX', interval='1m', period=period, progress=False)
        if not df.empty:
            df.reset_index(inplace=True)
        return df

    print("\n获取 NDX 1分钟K线数据（近一天）...")
    ndx_1min_df = fetch_ndx_1min_data(period='1d')
    if not ndx_1min_df.empty:
        print(ndx_1min_df.head())
        print(f"共获取 {len(ndx_1min_df)} 条1分钟数据")
    else:
        print("未能获取到NDX 1分钟数据")
