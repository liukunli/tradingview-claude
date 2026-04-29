"""
risk_manager.py — Pre-trade risk checks, circuit breakers, and adaptive sizing.

Three layers of risk control:
  1. Hard limits   — daily loss, circuit breaker, Greeks exposure
  2. Soft limits   — consecutive-loss reduction, Kelly-based sizing
  3. Adaptive      — VaR-scaled position size using rolling P&L history
"""

import logging
import math
from datetime import date
from typing import Optional

from ..config.settings import (
    MAX_DAILY_LOSS_USD, MAX_CONSECUTIVE_LOSSES, CIRCUIT_BREAKER_LOSSES,
    MAX_SCALE_INS, MAX_100PT_RULE, SPREAD_WIDTH, NDX_MULTIPLIER,
    MIN_CONTRACTS, BASE_CONTRACTS,
    MAX_DELTA_EQUIV, MAX_DOLLAR_VEGA,
    KELLY_FRACTION, KELLY_MIN_TRADES,
)
from .signal_engine import Greeks

log = logging.getLogger("ndx.risk")


class RiskManager:
    """
    Tracks intraday risk state and enforces hard limits.

    Instantiate once per strategy instance; call ``new_day()`` at session start.
    P&L history accumulates across sessions for Kelly and VaR computation.
    """

    def __init__(self, initial_capital: float = 100_000):
        self.initial_capital = initial_capital
        self.pnl_history: list[float] = []   # per-trade P&L across all sessions
        self._reset()

    def _reset(self):
        self.session_date:      Optional[date] = None
        self.daily_pnl_usd:    float = 0.0
        self.consecutive_losses: int = 0
        self.trades_today:      int = 0
        self.scale_in_count:    int = 0
        self.halted:            bool = False
        self.halt_reason:       str = ""
        self.entry_ndx:         Optional[float] = None
        self._position_greeks:  Optional[Greeks] = None

    def new_day(self, today: date):
        """Reset intraday state; preserve cross-session P&L history."""
        if self.session_date != today:
            self._reset()
            self.session_date = today
            log.info(f"Risk manager reset for {today}  "
                     f"(Kelly history: {len(self.pnl_history)} trades)")

    # ── Pre-trade checks ──────────────────────────────────────────────────────

    def pre_trade_check(self, action: str = "entry") -> tuple[bool, str]:
        """Return (ok, reason). Call before placing any order."""
        if self.halted:
            return False, f"Trading halted: {self.halt_reason}"

        if self.daily_pnl_usd <= -MAX_DAILY_LOSS_USD:
            self._halt(f"Daily loss limit hit: ${self.daily_pnl_usd:,.0f}")
            return False, self.halt_reason

        if self.consecutive_losses >= CIRCUIT_BREAKER_LOSSES:
            self._halt(f"{self.consecutive_losses} consecutive losses — circuit breaker")
            return False, self.halt_reason

        if action == "scale_in" and self.scale_in_count >= MAX_SCALE_INS:
            return False, f"Max scale-ins reached ({MAX_SCALE_INS})"

        return True, "ok"

    def check_greeks_limits(self, greeks: Greeks) -> tuple[bool, str]:
        """
        Validate that adding a position with these Greeks stays within limits.
        Call after evaluate_entry, before order placement.
        """
        current = self._position_greeks or Greeks(0, 0, 0, 0)
        new_delta = current.delta + greeks.delta
        new_vega  = current.vega  + greeks.vega

        abs_delta_usd = abs(new_delta) * NDX_MULTIPLIER
        if abs_delta_usd > MAX_DELTA_EQUIV * NDX_MULTIPLIER:
            return False, (f"Delta limit: |{new_delta:.2f}| × $100 = "
                           f"${abs_delta_usd:,.0f} > ${MAX_DELTA_EQUIV * NDX_MULTIPLIER:,.0f}")

        dollar_vega = abs(new_vega) * NDX_MULTIPLIER
        if dollar_vega > MAX_DOLLAR_VEGA:
            return False, (f"Vega limit: |{new_vega:.2f}| × $100 = "
                           f"${dollar_vega:,.0f} > ${MAX_DOLLAR_VEGA:,.0f}")

        return True, "ok"

    def check_ndx_stop(self, ndx_price: float, short_K: float) -> tuple[bool, str]:
        if ndx_price < short_K:
            return True, f"NDX {ndx_price:.0f} broke through short strike {short_K:.0f}"
        return False, ""

    def check_add_block(self, ndx_price: float, short_K: float) -> tuple[bool, str]:
        gap = short_K - ndx_price
        if gap > MAX_100PT_RULE:
            return True, (f"NDX {ndx_price:.0f} is {gap:.0f}pt below short strike "
                          f"{short_K:.0f} — no add, exit instead")
        return False, ""

    # ── Adaptive position sizing ──────────────────────────────────────────────

    def adjusted_contracts(self, base: int) -> int:
        """
        Reduce to MIN_CONTRACTS after consecutive-loss threshold.
        Kelly sizing engages once enough trade history is available.
        """
        if self.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            log.warning(f"Reducing to {MIN_CONTRACTS}c after "
                        f"{self.consecutive_losses} consecutive losses")
            return MIN_CONTRACTS
        return base

    def kelly_contracts(self,
                        base: int = BASE_CONTRACTS,
                        max_loss_per_contract: float = 5_000) -> int:
        """
        Quarter-Kelly position sizing based on observed trade history.
        Falls back to ``base`` if insufficient history.

        Parameters
        ----------
        base                   : default contract count (used when Kelly inactive)
        max_loss_per_contract  : worst-case USD loss per contract (spread width × multiplier)
        """
        if len(self.pnl_history) < KELLY_MIN_TRADES:
            return self.adjusted_contracts(base)

        wins   = [p for p in self.pnl_history if p > 0]
        losses = [p for p in self.pnl_history if p <= 0]
        if not losses or not wins:
            return self.adjusted_contracts(base)

        p = len(wins) / len(self.pnl_history)
        q = 1 - p
        avg_win  = sum(wins)   / len(wins)
        avg_loss = abs(sum(losses) / len(losses))
        b        = avg_win / avg_loss          # payoff ratio

        f_star = (p * b - q) / b              # full Kelly fraction
        f_safe = max(0.0, f_star * KELLY_FRACTION)  # quarter-Kelly

        capital = self.initial_capital + sum(self.pnl_history)
        raw_n   = int(f_safe * capital / max_loss_per_contract)
        n       = max(MIN_CONTRACTS, min(raw_n, BASE_CONTRACTS * 3))

        log.info(f"Kelly sizing: p={p:.0%} b={b:.2f} f*={f_star:.3f} "
                 f"f_safe={f_safe:.3f} → {n}c  (history: {len(self.pnl_history)} trades)")

        if self.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            n = MIN_CONTRACTS
        return n

    def compute_var(self, confidence: float = 0.95) -> float:
        """
        Historical Value-at-Risk (USD) at the given confidence level.
        Uses the full P&L history across sessions.
        Returns 0.0 if insufficient history.
        """
        if len(self.pnl_history) < 10:
            return 0.0
        sorted_pnl = sorted(self.pnl_history)
        idx = max(0, int((1 - confidence) * len(sorted_pnl)) - 1)
        return abs(sorted_pnl[idx])

    def compute_cvar(self, confidence: float = 0.95) -> float:
        """Conditional VaR (expected shortfall) — average loss beyond VaR."""
        if len(self.pnl_history) < 10:
            return 0.0
        sorted_pnl = sorted(self.pnl_history)
        cutoff = int((1 - confidence) * len(sorted_pnl))
        tail   = sorted_pnl[:max(cutoff, 1)]
        return abs(sum(tail) / len(tail))

    # ── State updates ─────────────────────────────────────────────────────────

    def record_entry(self, ndx_price: float, contracts: int, credit_pts: float,
                     greeks: Optional[Greeks] = None):
        self.entry_ndx    = ndx_price
        self.trades_today += 1
        self.scale_in_count = 0
        self._position_greeks = greeks
        log.info(f"Risk: entry — NDX={ndx_price:.0f}  {contracts}c × {credit_pts:.2f}pt"
                 + (f"  Δ={greeks.delta:+.3f}  θ={greeks.theta:+.3f}  "
                    f"ν={greeks.vega:+.3f}" if greeks else ""))

    def record_scale_in(self, additional_greeks: Optional[Greeks] = None):
        self.scale_in_count += 1
        if additional_greeks and self._position_greeks:
            g = self._position_greeks
            self._position_greeks = Greeks(
                delta=g.delta + additional_greeks.delta,
                gamma=g.gamma + additional_greeks.gamma,
                theta=g.theta + additional_greeks.theta,
                vega =g.vega  + additional_greeks.vega,
            )
        log.info(f"Risk: scale-in #{self.scale_in_count}/{MAX_SCALE_INS}")

    def record_exit(self, pnl_usd: float):
        self.daily_pnl_usd    += pnl_usd
        self.pnl_history.append(pnl_usd)
        self.scale_in_count    = 0
        self._position_greeks  = None

        if pnl_usd < 0:
            self.consecutive_losses += 1
            log.warning(f"Risk: loss ${pnl_usd:,.0f} — consecutive: {self.consecutive_losses}")
        else:
            self.consecutive_losses = 0
            log.info(f"Risk: win ${pnl_usd:,.0f} — streak reset")

        log.info(f"Risk: daily P&L ${self.daily_pnl_usd:,.0f}  "
                 f"VaR(95%) ${self.compute_var():,.0f}  "
                 f"CVaR(95%) ${self.compute_cvar():,.0f}")

    def _halt(self, reason: str):
        self.halted      = True
        self.halt_reason = reason
        log.error(f"TRADING HALTED: {reason}")

    # ── Status ────────────────────────────────────────────────────────────────

    def status_dict(self) -> dict:
        greeks = self._position_greeks
        return {
            "date":                 self.session_date,
            "daily_pnl_usd":        round(self.daily_pnl_usd, 2),
            "consecutive_losses":   self.consecutive_losses,
            "trades_today":         self.trades_today,
            "scale_ins_used":       self.scale_in_count,
            "halted":               self.halted,
            "halt_reason":          self.halt_reason,
            "var_95_usd":           round(self.compute_var(), 2),
            "cvar_95_usd":          round(self.compute_cvar(), 2),
            "kelly_trades_history": len(self.pnl_history),
            "position_delta":       round(greeks.delta, 4) if greeks else None,
            "position_vega":        round(greeks.vega, 4)  if greeks else None,
        }
