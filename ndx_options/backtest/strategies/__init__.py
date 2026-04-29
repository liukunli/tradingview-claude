"""
backtest/strategies/ — Per-strategy files referenced from here.

    actual.py          original, bear_put_only, no_edt, prime_only
    simulated.py       gated, no_gate, high_gate, low_credit
    mean_reversion.py  mean_reversion
    registry.py        build_all, print_comparison, print_strategy_detail
"""

from .registry import build_all, print_comparison, print_strategy_detail

__all__ = ["build_all", "print_comparison", "print_strategy_detail"]
