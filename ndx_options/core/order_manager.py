"""
order_manager.py — IBKR order execution via ib_insync.
Credentials are loaded from the .env file (never hardcoded).
"""

import asyncio
import logging
import os
from datetime import date
from typing import Optional

from dotenv import load_dotenv
from ib_insync import IB, Index, Option, Order, util

from ..config.settings import (
    IBKR_HOST, IBKR_PAPER_PORT, IBKR_LIVE_PORT, IBKR_CLIENT_ID,
    NDX_MULTIPLIER, SPREAD_WIDTH,
)

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

log = logging.getLogger("ndx.orders")

# Override from env if set
_HOST      = os.getenv("IBKR_HOST",      IBKR_HOST)
_PAPER_PORT = int(os.getenv("IBKR_PAPER_PORT", str(IBKR_PAPER_PORT)))
_LIVE_PORT  = int(os.getenv("IBKR_LIVE_PORT",  str(IBKR_LIVE_PORT)))
_CLIENT_ID  = int(os.getenv("IBKR_CLIENT_ID",  str(IBKR_CLIENT_ID)))
_ACCOUNT    = os.getenv("IBKR_ACCOUNT", "")   # leave blank = use default managed account


class OrderManager:
    """
    Manages IBKR connection and NDX option order placement.
    Use as async context manager:
        async with OrderManager(live=False) as om:
            await om.place_spread(...)
    """

    def __init__(self, live: bool = False, dry_run: bool = False):
        self.live    = live
        self.dry_run = dry_run
        self.port    = _LIVE_PORT if live else _PAPER_PORT
        self.ib      = IB()

    async def __aenter__(self):
        util.patchAsyncio()
        if not self.dry_run:
            log.info(f"Connecting IBKR at {_HOST}:{self.port} (clientId={_CLIENT_ID})")
            await self.ib.connectAsync(_HOST, self.port, clientId=_CLIENT_ID)
            accounts = self.ib.managedAccounts()
            log.info(f"Connected. Accounts: {accounts}")
            if _ACCOUNT and _ACCOUNT not in accounts:
                log.warning(f"Configured account {_ACCOUNT} not in {accounts}")
        return self

    async def __aexit__(self, *_):
        if self.ib.isConnected():
            self.ib.disconnect()
            log.info("IBKR disconnected")

    # ── Option contract helpers ───────────────────────────────────────────────

    @staticmethod
    def expiry_str(d: date) -> str:
        return d.strftime("%Y%m%d")

    async def qualify_option(self, strike: float, right: str, exp: str) -> Optional[Option]:
        opt = Option("NDX", exp, strike, right, "SMART",
                     multiplier=str(NDX_MULTIPLIER), currency="USD")
        try:
            await self.ib.qualifyContractsAsync(opt)
            return opt
        except Exception as e:
            log.warning(f"Could not qualify NDX {exp} {strike}{right}: {e}")
            return None

    async def get_mid_price(self, contract: Option, timeout_s: float = 5.0) -> Optional[float]:
        ticker = self.ib.reqMktData(contract, "", False, False)
        elapsed = 0.0
        while elapsed < timeout_s:
            await asyncio.sleep(0.5)
            elapsed += 0.5
            if ticker.bid > 0 and ticker.ask > 0:
                self.ib.cancelMktData(contract)
                return round((ticker.bid + ticker.ask) / 2.0, 2)
        self.ib.cancelMktData(contract)
        return None

    # ── Order placement ───────────────────────────────────────────────────────

    async def place_leg(self, contract: Option, action: str,
                        qty: int, limit_px: float) -> Optional[object]:
        log.info(f"{'[DRY RUN] ' if self.dry_run else ''}Order: "
                 f"{action} {qty}× NDX {contract.lastTradeDateOrContractMonth} "
                 f"{contract.strike}{contract.right} @ ${limit_px:.2f}")
        if self.dry_run:
            return None

        order = Order()
        order.action       = action
        order.totalQuantity = qty
        order.orderType    = "LMT"
        order.lmtPrice     = round(limit_px, 2)
        order.tif          = "DAY"
        order.transmit     = True
        order.outsideRth   = False
        if _ACCOUNT:
            order.account  = _ACCOUNT

        trade = self.ib.placeOrder(contract, order)
        log.info(f"  orderId={trade.order.orderId}")
        return trade

    async def place_spread(self, expiry_date: date,
                           short_K: float, long_K: float, qty: int,
                           short_mid: float, long_mid: float,
                           aggressive: bool = False) -> dict:
        """
        Open Bear Put spread: SELL short put, BUY long put.
        Returns dict with trade objects and actual credit.
        """
        exp = self.expiry_str(expiry_date)
        short_opt = await self.qualify_option(short_K, "P", exp)
        long_opt  = await self.qualify_option(long_K,  "P", exp)

        if short_opt is None or long_opt is None:
            raise RuntimeError("Option contract qualification failed")

        # Lean slightly aggressive for fills
        slippage = 0.50 if aggressive else 0.05
        short_limit = round(short_mid - slippage, 2)  # sell at slight discount
        long_limit  = round(long_mid  + slippage, 2)  # buy at slight premium

        sell_trade = await self.place_leg(short_opt, "SELL", qty, short_limit)
        buy_trade  = await self.place_leg(long_opt,  "BUY",  qty, long_limit)

        if not self.dry_run:
            await asyncio.sleep(5)
            await self._widen_unfilled(short_opt, sell_trade, "SELL", qty, short_limit)
            await self._widen_unfilled(long_opt,  buy_trade,  "BUY",  qty, long_limit)

        actual_credit = short_mid - long_mid
        return {
            "short_contract": short_opt,
            "long_contract":  long_opt,
            "short_trade":    sell_trade,
            "long_trade":     buy_trade,
            "credit_pts":     actual_credit,
            "short_limit":    short_limit,
            "long_limit":     long_limit,
        }

    async def close_spread(self, short_contract: Option, long_contract: Option,
                           qty: int, aggressive: bool = False) -> dict:
        """Close Bear Put spread: BUY back short, SELL long."""
        short_mid = await self.get_mid_price(short_contract) or 0.0
        long_mid  = await self.get_mid_price(long_contract)  or 0.0

        slippage = 1.00 if aggressive else 0.10
        buy_limit  = round(short_mid + slippage, 2)
        sell_limit = round(long_mid  - slippage, 2)

        buy_trade  = await self.place_leg(short_contract, "BUY",  qty, buy_limit)
        sell_trade = await self.place_leg(long_contract,  "SELL", qty, sell_limit)

        if not self.dry_run:
            await asyncio.sleep(5)

        return {
            "close_val_pts": short_mid - long_mid,
            "buy_trade":     buy_trade,
            "sell_trade":    sell_trade,
        }

    async def _widen_unfilled(self, contract: Option, trade, action: str,
                               qty: int, original_limit: float):
        if trade is None:
            return
        open_ids = {o.orderId for o in self.ib.openOrders()}
        if trade.order.orderId in open_ids:
            adj = -0.50 if action == "SELL" else 0.50
            new_limit = round(original_limit + adj, 2)
            log.warning(f"  Leg unfilled — adjusting limit to {new_limit:.2f}")
            trade.order.lmtPrice = new_limit
            self.ib.placeOrder(contract, trade.order)
            await asyncio.sleep(3)
