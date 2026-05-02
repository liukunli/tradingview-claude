import pandas as pd
from typing import List, Tuple


class PortfolioManager:
    """Manages holdings, capital, and transaction costs."""

    def __init__(
        self,
        initial_capital: float = 1_000_000.0,
        commission_rate: float = 0.0003,
        slippage_rate: float = 0.001,
        stamp_duty: float = 0.001,
    ):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.stamp_duty = stamp_duty

        self.current_holdings: List[str] = []
        self.current_weights: dict = {}

        self.total_commission = 0.0
        self.total_slippage = 0.0
        self.total_stamp_duty = 0.0
        self.trade_count = 0

        print(f"✅ PortfolioManager  |  capital={initial_capital:,.0f}  "
              f"comm={commission_rate*10000:.1f}bps  slip={slippage_rate*100:.2f}%")

    def calculate_turnover(
        self,
        old_holdings: List[str],
        new_holdings: List[str],
    ) -> Tuple[List[str], List[str], float]:
        old_set, new_set = set(old_holdings), set(new_holdings)
        to_sell = list(old_set - new_set)
        to_buy  = list(new_set - old_set)
        if old_holdings:
            turnover = (len(to_buy) + len(to_sell)) / (2 * len(old_holdings))
        else:
            turnover = 1.0
        return to_buy, to_sell, turnover

    def calculate_trade_cost(self, trade_value: float, is_buy: bool) -> float:
        commission = trade_value * self.commission_rate
        slippage   = trade_value * self.slippage_rate
        stamp      = trade_value * self.stamp_duty if not is_buy else 0.0

        self.total_commission += commission
        self.total_slippage   += slippage
        self.total_stamp_duty += stamp
        return commission + slippage + stamp

    def rebalance(self, new_holdings: List[str], equal_weight: bool = True) -> dict:
        to_buy, to_sell, turnover = self.calculate_turnover(
            self.current_holdings, new_holdings
        )
        weight = 1.0 / len(new_holdings) if (equal_weight and new_holdings) else 0.0
        total_cost = 0.0

        # Sell cost
        for stock in to_sell:
            w = self.current_weights.get(
                stock,
                1.0 / len(self.current_holdings) if self.current_holdings else 0.0,
            )
            total_cost += self.calculate_trade_cost(self.current_capital * w, is_buy=False)

        # Buy cost
        for _ in to_buy:
            total_cost += self.calculate_trade_cost(self.current_capital * weight, is_buy=True)

        self.current_holdings = new_holdings.copy()
        self.current_weights  = {c: weight for c in new_holdings} if equal_weight else {}
        self.trade_count     += len(to_buy) + len(to_sell)

        return {'to_buy': to_buy, 'to_sell': to_sell,
                'turnover': turnover, 'total_cost': total_cost,
                'weight_per_stock': weight}

    def compute_portfolio_return(self, returns: pd.Series) -> float:
        """Equal-weight return with drift update."""
        if not self.current_holdings:
            return 0.0

        weights = (self.current_weights.copy()
                   if self.current_weights
                   else {c: 1.0 / len(self.current_holdings) for c in self.current_holdings})

        portfolio_ret = sum(w * returns.get(code, 0.0) for code, w in weights.items())

        # Drift weights forward
        updated = {c: w * (1 + returns.get(c, 0.0)) for c, w in weights.items()}
        total = sum(updated.values())
        if total > 0:
            self.current_weights = {c: w / total for c, w in updated.items()}

        return portfolio_ret

    def update_capital(self, daily_return: float):
        self.current_capital *= (1 + daily_return)

    def get_statistics(self) -> dict:
        return {
            'initial_capital':  self.initial_capital,
            'current_capital':  self.current_capital,
            'total_commission': self.total_commission,
            'total_slippage':   self.total_slippage,
            'total_stamp_duty': self.total_stamp_duty,
            'total_cost':       self.total_commission + self.total_slippage + self.total_stamp_duty,
            'trade_count':      self.trade_count,
        }
