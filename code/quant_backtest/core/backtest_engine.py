import numpy as np
import pandas as pd
from typing import List, Optional

from core.data_loader import DataLoader
from core.portfolio_manager import PortfolioManager
from core.performance_evaluator import PerformanceEvaluator
from core.strategy_base import Strategy


class BacktestEngine:
    """
    Facade that wires DataLoader → Strategy → PortfolioManager → PerformanceEvaluator.

    Backtest timeline:
      T-day close  →  calculate_factor  →  (if rebalance day) queue signal
      T+1 open     →  execute queued signal
      T+1 returns  →  settle P&L
    """

    def __init__(
        self,
        data_dir: str = './data',
        initial_capital: float = 1_000_000.0,
        commission_rate: float = 0.0003,
        slippage_rate: float = 0.001,
        stamp_duty: float = 0.001,
        risk_free_rate: float = 0.03,
    ):
        print("=" * 60)
        print("🚀 Initialising BacktestEngine")
        print("=" * 60)
        self.loader    = DataLoader(data_dir)
        self.portfolio = PortfolioManager(initial_capital, commission_rate,
                                          slippage_rate, stamp_duty)
        self.evaluator = PerformanceEvaluator(risk_free_rate)
        print("=" * 60)
        print("✅ BacktestEngine ready")
        print("=" * 60)

    def run(
        self,
        start_date: str,
        end_date: str,
        strategy: Strategy,
        top_n: int = 50,
        rebalance_freq = 'month_start',
        enable_cost: bool = True,
        calculate_ic: bool = True,
        n_groups: int = 5,
    ) -> dict:
        print(f"\n{'='*60}")
        print(f"📅 {start_date} → {end_date}  |  strategy={strategy.name}")
        print(f"   top_n={top_n}  rebalance={rebalance_freq}  cost={'on' if enable_cost else 'off'}")
        print(f"{'='*60}")

        trade_dates    = self.loader.get_all_dates()
        backtest_dates = [d for d in trade_dates if start_date <= d <= end_date]
        print(f"✅ {len(backtest_dates)} trading days in range")

        metrics = self._run_loop(backtest_dates, strategy, top_n,
                                 rebalance_freq, enable_cost, calculate_ic, n_groups)

        returns_series    = pd.Series(metrics['daily_returns'],
                                      index=metrics['return_dates'])
        cumulative        = (1 + returns_series).cumprod()
        report            = self.evaluator.generate_report(cumulative, returns_series)

        if calculate_ic and metrics['ic_list']:
            ic_series          = pd.Series(metrics['ic_list'], index=metrics['ic_dates'])
            stats              = self.evaluator.calculate_ic_ir(ic_series)
            report.update(stats)
            report['ic_series'] = ic_series

        trade_stats            = self.portfolio.get_statistics()
        report['total_cost']   = trade_stats['total_cost']
        report['trade_count']  = trade_stats['trade_count']
        report['avg_turnover'] = (np.mean(metrics['turnover_list'])
                                  if metrics['turnover_list'] else 0.0)

        report['group_returns']    = (pd.DataFrame(metrics['group_rows'])
                                      if metrics['group_rows'] else pd.DataFrame())
        report['group_ls_returns'] = (pd.Series(metrics['group_ls'],
                                                 index=metrics['group_ls_dates'])
                                      if metrics['group_ls'] else pd.Series(dtype=float))
        report['cumulative_returns'] = cumulative
        report['daily_returns']      = returns_series

        print(f"\n✅ Backtest complete  |  {len(returns_series)} days recorded")
        return report

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _run_loop(self, backtest_dates, strategy, top_n,
                  rebalance_freq, enable_cost, calculate_ic, n_groups) -> dict:
        m = {
            'daily_returns': [], 'return_dates': [],
            'ic_list': [],       'ic_dates': [],
            'turnover_list': [],
            'group_rows': [],    'group_ls': [], 'group_ls_dates': [],
        }
        pending_signal = None

        for i, date in enumerate(backtest_dates):
            # --- open: execute previous signal ---
            is_rebalance, rebalance_info = False, None
            if pending_signal is not None:
                is_rebalance    = True
                rebalance_info  = self.portfolio.rebalance(pending_signal)
                m['turnover_list'].append(rebalance_info['turnover'])
                if i < 6:
                    print(f"  {date} | top3={pending_signal[:3]} | "
                          f"turnover={rebalance_info['turnover']:.1%} | "
                          f"cost={rebalance_info['total_cost']:,.0f}")
                pending_signal = None

            # --- close: get forward returns & settle P&L ---
            ret_df = self.loader.get_daily_returns(date)
            if not ret_df.empty:
                ret_df = ret_df.set_index('code')

            port_ret = self._settle(ret_df, enable_cost, is_rebalance, rebalance_info)
            m['daily_returns'].append(port_ret)
            m['return_dates'].append(date)
            self.portfolio.update_capital(port_ret)

            # --- close: compute factor ---
            factor_df = strategy.calculate_factor(date, self.loader)

            if factor_df is not None and not factor_df.empty:
                if calculate_ic:
                    self._record_ic(date, ret_df, factor_df, m)
                if n_groups > 1:
                    self._record_groups(date, ret_df, factor_df, n_groups, m)

                if self._should_rebalance(i, date, backtest_dates, rebalance_freq):
                    sig = strategy.generate_signal(factor_df, top_n)
                    if sig:
                        pending_signal = sig

        return m

    def _settle(self, ret_df, enable_cost, is_rebalance, rebalance_info) -> float:
        if ret_df is None or ret_df.empty:
            return 0.0
        port_ret = self.portfolio.compute_portfolio_return(ret_df['1vwap_pct'])
        if enable_cost and is_rebalance and rebalance_info:
            port_ret -= rebalance_info['total_cost'] / self.portfolio.current_capital
        return port_ret

    def _should_rebalance(self, i, date, dates, freq) -> bool:
        if isinstance(freq, str):
            f = freq.lower()
            if f in ('m', 'month_start'):
                return i == 0 or dates[i - 1][:7] != date[:7]
            if f in ('month_end', 'month_last'):
                return i < len(dates) - 1 and dates[i + 1][:7] != date[:7]
            return False
        return i % int(freq) == 0

    def _record_ic(self, date, ret_df, factor_df, m):
        if ret_df is None or ret_df.empty:
            return
        ic = self.evaluator.calculate_ic(
            factor_df.set_index('code')['factor_value'],
            ret_df['1vwap_pct'],
        )
        if not np.isnan(ic):
            m['ic_list'].append(ic)
            m['ic_dates'].append(date)

    def _record_groups(self, date, ret_df, factor_df, n_groups, m):
        if ret_df is None or ret_df.empty:
            return
        merged = (factor_df[['code', 'factor_value']].dropna()
                  .set_index('code')
                  .join(ret_df[['1vwap_pct']], how='inner')
                  .dropna())
        if len(merged) < n_groups:
            return
        try:
            merged['group'] = pd.qcut(merged['factor_value'], q=n_groups,
                                      labels=False, duplicates='drop')
        except ValueError:
            return
        if merged['group'].nunique() < n_groups:
            return
        grp = merged.groupby('group')['1vwap_pct'].mean()
        for g, r in grp.items():
            m['group_rows'].append({'date': date, 'group': int(g), 'ret': float(r)})
        m['group_ls'].append(float(grp.iloc[-1] - grp.iloc[0]))
        m['group_ls_dates'].append(date)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def print_report(self, report: dict):
        print(f"\n{'='*60}")
        print("📊 Backtest Report")
        print(f"{'='*60}")
        print(f"  Total return:      {report['total_return']*100:>8.2f}%")
        print(f"  Annual return:     {report['annual_return']*100:>8.2f}%")
        print(f"  Annual volatility: {report['annual_volatility']*100:>8.2f}%")
        print(f"  Sharpe ratio:      {report['sharpe_ratio']:>8.2f}")
        print(f"  Max drawdown:      {report['max_drawdown']*100:>8.2f}%")
        print(f"  Calmar ratio:      {report['calmar_ratio']:>8.2f}")
        print(f"  Win rate:          {report['win_rate']*100:>8.2f}%")

        if 'ic_mean' in report:
            print(f"\n{'─'*60}")
            print("  IC Analysis")
            print(f"{'─'*60}")
            print(f"  IC mean:           {report['ic_mean']:>8.4f}")
            print(f"  IC std:            {report['ic_std']:>8.4f}")
            print(f"  IR (IC/std):       {report['ir']:>8.4f}")
            print(f"  IC win rate:       {report['ic_win_rate']*100:>8.2f}%")

        print(f"\n{'─'*60}")
        print("  Trading Stats")
        print(f"{'─'*60}")
        print(f"  Total cost:        {report['total_cost']:>10,.0f} CNY")
        print(f"  Trade count:       {report['trade_count']:>10,}")
        print(f"  Avg turnover:      {report['avg_turnover']*100:>8.2f}%")

        gls = report.get('group_ls_returns')
        if gls is not None and not gls.empty:
            print(f"\n{'─'*60}")
            print("  Group L/S")
            print(f"{'─'*60}")
            print(f"  Avg L/S return:    {gls.mean()*100:>8.2f}%")
            print(f"  L/S std:           {gls.std()*100:>8.2f}%")
            print(f"  Periods:           {len(gls):>8,}")

        cumret = report['cumulative_returns']
        print(f"\n{'─'*60}")
        print("  Cumulative NAV (first 3 / last 3)")
        print(f"{'─'*60}")
        for d in cumret.index[:3]:
            print(f"    {d}  {cumret[d]:.4f}")
        print("    ...")
        for d in cumret.index[-3:]:
            print(f"    {d}  {cumret[d]:.4f}")
        print(f"{'='*60}\n")
