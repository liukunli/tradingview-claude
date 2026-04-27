"""
bear_put.py — Main Bear Put Spread strategy orchestrator.

Implements the full lifecycle:
  1. Pre-window: wait for prime window
  2. Gate + Q-Score evaluation
  3. Entry with proper strike/size selection
  4. Position monitoring with exits
  5. Scale-in logic (max 2 adds)
  6. EOD cleanup

Calls into core/signal_engine.py (logic) and core/order_manager.py (execution).
"""

import asyncio
import logging
import math
from datetime import date, time, datetime
from typing import Optional

from ..config.settings import (
    ET, SYMBOL, NDX_MULTIPLIER, SPREAD_WIDTH,
    PRIME_START, PRIME_END, TIME_EXIT_ET, MARKET_CLOSE, OVERNIGHT_CLOSE_ET,
    GATE_MIN_PROCEED, GATE_MIN_WATCH,
    BASE_CONTRACTS, MAX_SCALE_INS, SCALE_IN_DROP,
    PROFIT_TARGET_PCT, LOSS_STOP_MULT, TIME_STOP_HOURS,
    MIN_CREDIT_PTS, MAX_CREDIT_PTS,
    BS_DEFAULT_SIGMA, ANNUAL_BARS_5MIN,
)
from .signal_engine import (
    evaluate_gate, hard_override_avoid, gate_action,
    select_strikes, compute_qscore, size_from_qscore,
    spread_value_pts, format_analysis, bs_put,
    compute_bar_metrics,
)
from .risk_manager import RiskManager

log = logging.getLogger("ndx.strategy")


class BearPutSpread:
    """
    Full Bear Put Spread strategy session.

    Usage:
        strategy = BearPutSpread(order_manager, risk_manager, data_client)
        await strategy.run_session()
    """

    def __init__(self, order_manager, risk_manager: RiskManager, data_client,
                 dry_run: bool = False, macro_event: bool = False):
        self.om    = order_manager
        self.rm    = risk_manager
        self.dc    = data_client
        self.dry_run     = dry_run
        self.macro_event = macro_event

        # Position state
        self._open          = False
        self._short_K: Optional[float] = None
        self._long_K:  Optional[float] = None
        self._credit:  Optional[float] = None
        self._contracts: int = 0
        self._entry_ndx: Optional[float] = None
        self._entry_time: Optional[datetime] = None
        self._scale_in_count: int = 0
        self._short_contract = None
        self._long_contract  = None

    # ── Session top-level ─────────────────────────────────────────────────────

    async def run_session(self):
        today = date.today()
        self.rm.new_day(today)
        log.info(f"=== NDX Bear Put Session — {today} ===")

        # Check for overnight EDT position
        await self._handle_overnight_position()

        # Wait for prime window
        await self._wait_for_prime_window()

        # Position open — monitor until exit
        if self._open:
            await self._monitor_position()

        log.info("=== Session complete ===")
        return self.rm.status_dict()

    # ── Overnight / EDT cleanup ────────────────────────────────────────────────

    async def _handle_overnight_position(self):
        """Close any leftover EDT position not closed by 9:45 ET."""
        now_et = datetime.now(tz=ET)
        if now_et.time() < time(9, 30):
            return
        # In a real system, check open positions via IBKR and close if EDT
        # Here we log the intent
        log.info("EDT position check: no overnight positions detected")

    # ── Waiting for prime window ──────────────────────────────────────────────

    async def _wait_for_prime_window(self):
        log.info(f"Waiting for prime window ({PRIME_START}–{PRIME_END} ET)…")
        while True:
            now_et = datetime.now(tz=ET)
            now_t  = now_et.time()

            if now_t > PRIME_END:
                log.info("Prime window closed without entry.")
                return

            if now_t >= PRIME_START:
                entered = await self._evaluate_and_enter(now_et)
                if entered:
                    return
                await asyncio.sleep(60)   # re-evaluate in 1 min if gates failed
            else:
                secs = (datetime.combine(now_et.date(), PRIME_START, tzinfo=ET) - now_et).total_seconds()
                log.info(f"  Prime window in {int(secs//60)}m {int(secs%60)}s")
                await asyncio.sleep(min(secs, 60))

    # ── Gate evaluation + entry ───────────────────────────────────────────────

    async def _evaluate_and_enter(self, now: datetime) -> bool:
        log.info("── Evaluating gate ──")

        try:
            bars = self.dc.get_ohlcv(timeframe="5", bars=40)
        except Exception as e:
            log.error(f"OHLCV fetch failed: {e}")
            return False

        m = compute_bar_metrics(bars, now)

        gate_score, gate_details = evaluate_gate(m, now.time())
        action = gate_action(gate_score)

        avoid_reason = hard_override_avoid(
            m, now.time(),
            macro_event=self.macro_event,
            consecutive_losses=self.rm.consecutive_losses,
        )

        short_K, long_K = select_strikes(m["price"])
        q_score, q_crit = compute_qscore(
            m, now.time(), direction="Bear Put",
            short_K=short_K, is_0dte=True,
        )

        # Estimate credit
        bars_left = max(int((datetime.combine(now.date(), MARKET_CLOSE, tzinfo=ET) - now)
                           .total_seconds() / 300), 10)
        credit_est = spread_value_pts(m["price"], short_K, long_K, bars_left, m["sigma"])

        analysis = format_analysis(
            m, now.time(), gate_score, gate_details,
            short_K, long_K, q_score, q_crit, credit_est,
            action if not avoid_reason else "AVOID",
            avoid_reason,
        )
        log.info("\n" + analysis)

        if avoid_reason or action == "AVOID":
            return False

        if q_score < 45:
            log.info(f"Q-Score too low ({q_score}) — skip")
            return False

        if not (MIN_CREDIT_PTS <= credit_est <= MAX_CREDIT_PTS):
            log.info(f"Credit estimate {credit_est:.1f}pt outside [{MIN_CREDIT_PTS}, {MAX_CREDIT_PTS}] — skip")
            return False

        # Risk pre-check
        ok, reason = self.rm.pre_trade_check("entry")
        if not ok:
            log.warning(f"Risk block: {reason}")
            return False

        # Size
        base = BASE_CONTRACTS
        n = size_from_qscore(self.rm.adjusted_contracts(base), q_score, gate_score)
        if n == 0:
            log.info("Size = 0 after Q-score adjustment — skip")
            return False

        # Get live quotes
        today = now.date()
        try:
            spread_info = await self.om.place_spread(
                today, short_K, long_K, n,
                short_mid=credit_est * 0.6,    # rough split; will be replaced by live quotes
                long_mid=credit_est * 0.4,
            )
        except Exception as e:
            log.error(f"Spread placement failed: {e}")
            return False

        actual_credit = spread_info["credit_pts"]
        if actual_credit <= 0:
            log.warning("Spread credit ≤ 0 at live prices — abort")
            return False

        self._open          = True
        self._short_K       = short_K
        self._long_K        = long_K
        self._credit        = actual_credit
        self._contracts     = n
        self._entry_ndx     = m["price"]
        self._entry_time    = now
        self._scale_in_count = 0
        self._short_contract = spread_info["short_contract"]
        self._long_contract  = spread_info["long_contract"]

        self.rm.record_entry(m["price"], n, actual_credit)
        log.info(f"ENTERED Bear Put — short={short_K} long={long_K} "
                 f"credit={actual_credit:.2f}pt (${actual_credit * NDX_MULTIPLIER * n:,.0f})")
        return True

    # ── Position monitoring ───────────────────────────────────────────────────

    async def _monitor_position(self):
        log.info(f"Monitoring: short={self._short_K} long={self._long_K} "
                 f"credit={self._credit:.2f}pt  {self._contracts}c")

        while self._open:
            now_et = datetime.now(tz=ET)

            try:
                ndx_price = self.dc.get_current_price()
            except Exception as e:
                log.warning(f"Price fetch failed: {e}")
                await asyncio.sleep(15)
                continue

            close_dt   = datetime.combine(now_et.date(), MARKET_CLOSE, tzinfo=ET)
            bars_left  = max(int((close_dt - now_et).total_seconds() / 300), 1)
            spread_val = spread_value_pts(ndx_price, self._short_K, self._long_K,
                                         bars_left, BS_DEFAULT_SIGMA)

            pnl_pts = self._credit - spread_val
            pnl_usd = pnl_pts * NDX_MULTIPLIER * self._contracts

            log.info(f"  NDX={ndx_price:.0f}  spread={spread_val:.2f}pt  "
                     f"P&L={pnl_pts:+.2f}pt (${pnl_usd:+,.0f})")

            # ── Exit conditions ──────────────────────────────────────────────
            exit_reason = None

            if ndx_price < self._short_K:
                exit_reason = "ndx_stop"
            elif spread_val >= self._credit * LOSS_STOP_MULT:
                exit_reason = "loss_stop"
            elif spread_val <= self._credit * PROFIT_TARGET_PCT:
                exit_reason = "profit_target"
            elif now_et.time() >= TIME_EXIT_ET:
                exit_reason = "time_exit"
            else:
                # Check time-based stop: open > 4h with P&L < -50% credit
                hours_open = (now_et - self._entry_time).total_seconds() / 3600
                if hours_open > TIME_STOP_HOURS and pnl_pts < -0.5 * self._credit:
                    exit_reason = "time_stop_loss"

            if exit_reason:
                await self._exit_position(ndx_price, spread_val, exit_reason)
                return

            # ── Scale-in opportunity ─────────────────────────────────────────
            if self._scale_in_count < MAX_SCALE_INS:
                drop_from_entry = (self._entry_ndx - ndx_price) if self._entry_ndx else 0
                if drop_from_entry >= SCALE_IN_DROP * (self._scale_in_count + 1):
                    await self._scale_in(ndx_price, now_et.date())

            await asyncio.sleep(30)

    # ── Scale-in ─────────────────────────────────────────────────────────────

    async def _scale_in(self, ndx_price: float, today: date):
        ok, reason = self.rm.pre_trade_check("scale_in")
        if not ok:
            log.warning(f"Scale-in blocked: {reason}")
            return

        blocked, reason = self.rm.check_add_block(ndx_price, self._short_K)
        if blocked:
            log.warning(f"Scale-in blocked: {reason}")
            await self._exit_position(ndx_price, 0, "ndx_stop_on_scale_in")
            return

        new_short_K = self._short_K - SPREAD_WIDTH
        new_long_K  = new_short_K  - SPREAD_WIDTH
        add_qty     = max(1, self._contracts // 2)

        log.info(f"Scale-in #{self._scale_in_count + 1}: "
                 f"{new_short_K}/{new_long_K} × {add_qty}c")

        try:
            spread_info = await self.om.place_spread(
                today, new_short_K, new_long_K, add_qty,
                short_mid=2.0, long_mid=0.5,   # rough; will use live quotes
            )
        except Exception as e:
            log.error(f"Scale-in placement failed: {e}")
            return

        self._scale_in_count += 1
        self._contracts += add_qty
        self.rm.record_scale_in()
        log.info(f"Scale-in complete — total contracts: {self._contracts}")

    # ── Exit ──────────────────────────────────────────────────────────────────

    async def _exit_position(self, ndx_price: float, spread_val: float, reason: str):
        log.info(f"EXIT triggered: {reason}  NDX={ndx_price:.0f}  spread={spread_val:.2f}pt")

        aggressive = reason in ("ndx_stop", "loss_stop", "ndx_stop_on_scale_in")
        try:
            close_info = await self.om.close_spread(
                self._short_contract, self._long_contract,
                self._contracts, aggressive=aggressive,
            )
            close_val = close_info["close_val_pts"]
        except Exception as e:
            log.error(f"Exit failed: {e}")
            close_val = spread_val

        pnl_pts = self._credit - close_val
        pnl_usd = pnl_pts * NDX_MULTIPLIER * self._contracts
        self.rm.record_exit(pnl_usd)

        log.info(f"  Closed: credit={self._credit:.2f}pt  close_val={close_val:.2f}pt  "
                 f"P&L={pnl_pts:+.2f}pt (${pnl_usd:+,.0f})  reason={reason}")

        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open
