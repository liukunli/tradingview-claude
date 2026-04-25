"""
risk_manager.py — Pre-trade risk checks and circuit breakers.
All checks return (ok: bool, reason: str).
"""

import logging
from datetime import date, time, datetime
from typing import Optional

from ..config.settings import (
    MAX_DAILY_LOSS_USD, MAX_CONSECUTIVE_LOSSES, CIRCUIT_BREAKER_LOSSES,
    MAX_SCALE_INS, MAX_100PT_RULE, SPREAD_WIDTH, NDX_MULTIPLIER,
    MIN_CONTRACTS, BASE_CONTRACTS,
)

log = logging.getLogger("ndx.risk")


class RiskManager:
    """
    Tracks intraday risk state and enforces hard limits.
    Instantiate once per trading session; state resets on new day.
    """

    def __init__(self):
        self._reset()

    def _reset(self):
        self.session_date: Optional[date] = None
        self.daily_pnl_usd: float = 0.0
        self.consecutive_losses: int = 0
        self.trades_today: int = 0
        self.scale_in_count: int = 0
        self.halted: bool = False
        self.halt_reason: str = ""
        self.entry_ndx: Optional[float] = None

    def new_day(self, today: date):
        """Call at start of each trading session to reset intraday state."""
        if self.session_date != today:
            self._reset()
            self.session_date = today
            log.info(f"Risk manager reset for {today}")

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

        if action == "scale_in":
            if self.scale_in_count >= MAX_SCALE_INS:
                return False, f"Max scale-ins reached ({MAX_SCALE_INS})"

        return True, "ok"

    def check_ndx_stop(self, ndx_price: float, short_K: float) -> tuple[bool, str]:
        """Hard stop: NDX has broken through short strike."""
        if ndx_price < short_K:
            return True, f"NDX {ndx_price:.0f} broke through short strike {short_K:.0f}"
        return False, ""

    def check_add_block(self, ndx_price: float, short_K: float) -> tuple[bool, str]:
        """Never add if NDX is 100pt+ past short strike."""
        gap = short_K - ndx_price
        if gap > MAX_100PT_RULE:
            return True, (f"NDX {ndx_price:.0f} is {gap:.0f}pt below short strike "
                          f"{short_K:.0f} — no add, exit instead")
        return False, ""

    def adjusted_contracts(self, base: int) -> int:
        """Reduce to 1 contract after 2 consecutive losses."""
        if self.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            log.warning(f"Reducing to {MIN_CONTRACTS} contract(s) after "
                        f"{self.consecutive_losses} consecutive losses")
            return MIN_CONTRACTS
        return base

    # ── State updates ─────────────────────────────────────────────────────────

    def record_entry(self, ndx_price: float, contracts: int, credit_pts: float):
        self.entry_ndx   = ndx_price
        self.trades_today += 1
        self.scale_in_count = 0
        log.info(f"Risk: entry recorded — NDX={ndx_price:.0f}, "
                 f"{contracts}c × {credit_pts:.2f}pt credit")

    def record_scale_in(self):
        self.scale_in_count += 1
        log.info(f"Risk: scale-in #{self.scale_in_count}/{MAX_SCALE_INS}")

    def record_exit(self, pnl_usd: float):
        self.daily_pnl_usd += pnl_usd
        self.scale_in_count = 0
        if pnl_usd < 0:
            self.consecutive_losses += 1
            log.warning(f"Risk: loss recorded ${pnl_usd:,.0f} — "
                        f"consecutive losses: {self.consecutive_losses}")
        else:
            self.consecutive_losses = 0
            log.info(f"Risk: win recorded ${pnl_usd:,.0f} — streak reset")
        log.info(f"Risk: daily P&L: ${self.daily_pnl_usd:,.0f}")

    def _halt(self, reason: str):
        self.halted = True
        self.halt_reason = reason
        log.error(f"TRADING HALTED: {reason}")

    # ── Status report ─────────────────────────────────────────────────────────

    def status_dict(self) -> dict:
        return {
            "date":                self.session_date,
            "daily_pnl_usd":       round(self.daily_pnl_usd, 2),
            "consecutive_losses":  self.consecutive_losses,
            "trades_today":        self.trades_today,
            "scale_ins_used":      self.scale_in_count,
            "halted":              self.halted,
            "halt_reason":         self.halt_reason,
        }
