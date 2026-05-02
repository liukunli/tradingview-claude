#!/usr/bin/env python3
"""
live_trade_ndx.py — NDX Bear Put Spread Live Trader
Uses IBKR paper account (port 7497) for both market data and order execution.

Strategy: Sell a Bear Put vertical credit spread on 0DTE NDX options.
  - Prime window: 10:00–10:30 ET
  - Short put 100–150pt OTM, width 50pt
  - Profit target: 75% credit captured (spread decays to 25% of initial)
  - Loss stop: spread reaches 2× initial credit
  - NDX stop: any bar low crosses the short strike
  - Time exit: 14:30 ET

Usage:
  python3 live_trade_ndx.py                  # paper trading (port 7497)
  python3 live_trade_ndx.py --live           # LIVE trading (port 7496) — REAL MONEY
  python3 live_trade_ndx.py --dry-run        # simulate without placing orders
  python3 live_trade_ndx.py --contracts 2    # override contract count
"""

import asyncio
import logging
import math
import sys
import argparse
from datetime import date, time, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import norm
from ib_insync import IB, Index, Option, Order, util

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"trading_logs/live_{date.today()}.log"),
    ],
)
log = logging.getLogger("ndx-live")
ET = ZoneInfo("America/New_York")

# ─── Strategy constants ────────────────────────────────────────────────────────
N_CONTRACTS    = 3
SPREAD_WIDTH   = 50        # index points
NDX_MULT       = 100       # $100 per index point
ANNUAL_BARS    = 252 * 78  # 5-min bars per trading year

PRIME_START       = time(10, 0)
PRIME_END         = time(10, 30)
PROFIT_TARGET_PCT = 0.25   # close when spread = 25% of credit (75% profit)
LOSS_STOP_MULT    = 2.0    # close when spread = 2× credit
TIME_EXIT_ET      = time(14, 30)
MONITOR_INTERVAL  = 30     # seconds between position checks

# Hard gate limits
MAX_DAY_RANGE  = 250       # skip if intraday range > 250pt
MIN_OTM_DIST   = 100       # minimum OTM distance for short put
MAX_OTM_DIST   = 200       # maximum OTM distance for short put

# ─── Black-Scholes ─────────────────────────────────────────────────────────────
def bs_put(S: float, K: float, T: float, r: float = 0.045, sigma: float = 0.25) -> float:
    if T <= 1e-8:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

def spread_value_pts(S, short_K, long_K, bars_remaining, sigma):
    T = bars_remaining / ANNUAL_BARS
    val = bs_put(S, short_K, T, sigma=sigma) - bs_put(S, long_K, T, sigma=sigma)
    return max(min(val, SPREAD_WIDTH), 0.0)

# ─── Gate logic (mirrors backtest_ndx_spread.py exactly) ──────────────────────
def compute_metrics(bars: pd.DataFrame) -> dict:
    closes    = bars["close"].values
    log_ret   = np.diff(np.log(closes)) if len(closes) > 1 else np.array([0.0])
    sigma     = max(math.sqrt(np.var(log_ret) * ANNUAL_BARS), 0.12) if len(log_ret) > 2 else 0.25

    day_high  = bars["high"].max()
    day_low   = bars["low"].min()
    day_range = day_high - day_low
    avg_bar   = (bars["high"] - bars["low"]).mean()
    trending  = (day_range > 2.5 * avg_bar) if avg_bar > 0 else False

    price     = bars.iloc[-1]["close"]
    range_pct = (price - day_low) / day_range if day_range > 0 else 0.5

    mom_idx = max(len(bars) - 7, 0)
    mom_30  = price - bars.iloc[mom_idx]["close"]

    vol = bars["volume"].sum()
    vwap = (bars["close"] * bars["volume"]).sum() / vol if vol > 0 else price

    return dict(
        day_range=day_range, avg_bar=avg_bar, trending=trending,
        price=price, range_pct=range_pct, mom_30=mom_30, vwap=vwap, sigma=sigma,
    )

def evaluate_gates(m: dict, now_et: time) -> tuple[int, dict]:
    details = {
        "prime_window":  PRIME_START <= now_et <= PRIME_END,
        "flat_momentum": abs(m["mom_30"]) <= 10,
        "top_20_range":  m["range_pct"] >= 0.80,
        "small_or_calm": (m["day_range"] < 180) or (not m["trending"]),
        "dte0":          True,
    }
    return sum(details.values()), details

# ─── IBKR helpers ─────────────────────────────────────────────────────────────
def expiry_str(d: date) -> str:
    return d.strftime("%Y%m%d")

async def get_ndx_bars(ib: IB, n_bars: int = 40) -> pd.DataFrame:
    """Return up to n_bars of 5-min NDX bars ending now."""
    ndx = Index("NDX", "NASDAQ", "USD")
    await ib.qualifyContractsAsync(ndx)

    bars = await ib.reqHistoricalDataAsync(
        ndx,
        endDateTime="",
        durationStr=f"{n_bars * 5 + 30} S" if n_bars < 10 else "3600 S",
        barSizeSetting="5 mins",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=2,  # return datetime objects
    )
    if not bars:
        raise RuntimeError("No historical bars returned for NDX")

    rows = [{"dt": bar.date, "open": bar.open, "high": bar.high,
              "low": bar.low, "close": bar.close, "volume": bar.volume}
            for bar in bars]
    df = pd.DataFrame(rows)
    df["dt"] = pd.to_datetime(df["dt"], utc=True).dt.tz_convert(ET)
    return df.tail(n_bars).reset_index(drop=True)

async def get_ndx_quote(ib: IB) -> float:
    """Return current NDX last price."""
    ndx = Index("NDX", "NASDAQ", "USD")
    await ib.qualifyContractsAsync(ndx)
    ticker = ib.reqMktData(ndx, "", False, False)
    await asyncio.sleep(2)
    price = ticker.last or ticker.close or 0.0
    ib.cancelMktData(ndx)
    return float(price)

async def qualify_option(ib: IB, strike: float, right: str, exp: str) -> Optional[Option]:
    """Qualify an NDX option contract, return None if not found."""
    opt = Option("NDX", exp, strike, right, "SMART", multiplier="100", currency="USD")
    try:
        await ib.qualifyContractsAsync(opt)
        return opt
    except Exception as e:
        log.warning(f"Could not qualify NDX {exp} {strike} {right}: {e}")
        return None

async def get_option_mid(ib: IB, contract: Option) -> Optional[float]:
    """Return mid-price for an option, waiting up to 5s for a quote."""
    ticker = ib.reqMktData(contract, "", False, False)
    for _ in range(10):
        await asyncio.sleep(0.5)
        if ticker.bid > 0 and ticker.ask > 0:
            mid = (ticker.bid + ticker.ask) / 2.0
            ib.cancelMktData(contract)
            return round(mid, 2)
    ib.cancelMktData(contract)
    return None

async def place_leg(ib: IB, contract: Option, action: str, qty: int,
                    limit_px: float, dry_run: bool) -> Optional[object]:
    """Place a single option leg order."""
    order = Order()
    order.action = action
    order.totalQuantity = qty
    order.orderType = "LMT"
    order.lmtPrice = round(limit_px, 2)
    order.tif = "DAY"
    order.transmit = True
    order.outsideRth = False

    if dry_run:
        log.info(f"[DRY RUN] Would {action} {qty}x {contract.symbol} "
                 f"{contract.lastTradeDateOrContractMonth} {contract.strike} "
                 f"{contract.right} @ ${limit_px:.2f}")
        return None

    trade = ib.placeOrder(contract, order)
    log.info(f"Placed {action} {qty}x NDX {contract.strike}{contract.right} "
             f"@ ${limit_px:.2f}  orderId={trade.order.orderId}")
    return trade

# ─── Main trading session ──────────────────────────────────────────────────────
class NDXSpreadTrader:
    def __init__(self, ib: IB, n_contracts: int, dry_run: bool):
        self.ib = ib
        self.n_contracts = n_contracts
        self.dry_run = dry_run
        self.position_open = False
        self.short_strike: Optional[float] = None
        self.long_strike: Optional[float] = None
        self.credit_pts: Optional[float] = None
        self.short_contract: Optional[Option] = None
        self.long_contract: Optional[Option] = None
        self.entry_time: Optional[datetime] = None
        self.entry_ndx: Optional[float] = None

    async def run(self):
        today = date.today()
        log.info(f"=== NDX Bear Put Spread — {today} ===")
        log.info(f"Contracts: {self.n_contracts}  Width: {SPREAD_WIDTH}pt  "
                 f"Dry-run: {self.dry_run}")

        await self._wait_for_prime_window()

        if self.position_open:
            await self._monitor_position()

        log.info("=== Session complete ===")

    async def _now_et(self) -> datetime:
        return datetime.now(tz=ET)

    async def _wait_for_prime_window(self):
        """Poll until 10:00 ET, evaluate gates, enter if all checks pass."""
        log.info("Waiting for prime window (10:00–10:30 ET)…")
        while True:
            now = await self._now_et()
            now_t = now.time()

            if now_t > PRIME_END:
                log.info("Prime window passed without entry. Done for today.")
                return

            if now_t >= PRIME_START:
                entered = await self._evaluate_and_enter(now)
                if entered:
                    return
                # Gates failed — check again in 1 min in case momentum changes
                await asyncio.sleep(60)
            else:
                secs_until = (
                    datetime.combine(now.date(), PRIME_START, tzinfo=ET) - now
                ).total_seconds()
                log.info(f"  Prime window opens in {int(secs_until/60)}m {int(secs_until%60)}s")
                await asyncio.sleep(min(secs_until, 60))

    async def _evaluate_and_enter(self, now: datetime) -> bool:
        log.info("── Gate evaluation ──")

        try:
            bars = await get_ndx_bars(self.ib, n_bars=40)
        except Exception as e:
            log.error(f"Failed to fetch NDX bars: {e}")
            return False

        m = compute_metrics(bars)
        score, details = evaluate_gates(m, now.time())

        log.info(f"  NDX: {m['price']:.1f}  range: {m['day_range']:.0f}pt  "
                 f"mom30: {m['mom_30']:+.0f}pt  range_pct: {m['range_pct']:.0%}")
        log.info(f"  Gates: {details}  score={score}/5")

        # Hard skips
        if score < 3:
            log.info(f"  SKIP: gate score {score} < 3")
            return False
        if m["day_range"] > MAX_DAY_RANGE:
            log.info(f"  SKIP: day range {m['day_range']:.0f}pt > {MAX_DAY_RANGE}pt limit")
            return False
        if not details["top_20_range"]:
            log.info("  SKIP: NDX not in top 20% of intraday range (Bear Put prerequisite)")
            return False

        # Strike selection: short put 100–150pt OTM, round to nearest 50
        price = m["price"]
        short_K = math.floor((price - 100) / 50) * 50
        long_K  = short_K - SPREAD_WIDTH
        otm_dist = price - short_K

        if not (MIN_OTM_DIST <= otm_dist <= MAX_OTM_DIST):
            log.info(f"  SKIP: OTM distance {otm_dist:.0f}pt out of [{MIN_OTM_DIST}, {MAX_OTM_DIST}] range")
            return False

        log.info(f"  Strikes: short={short_K}  long={long_K}  OTM={otm_dist:.0f}pt")

        # Estimate credit with Black-Scholes
        today = now.date()
        bars_left = len(bars[bars["dt"].dt.time >= now.time()])  # rough
        bars_left = max(bars_left, 20)
        credit_bs = spread_value_pts(price, short_K, long_K, bars_left, m["sigma"])
        log.info(f"  BS credit est: {credit_bs:.2f}pt = ${credit_bs * NDX_MULT * self.n_contracts:.0f}")

        # Qualify option contracts
        exp = expiry_str(today)
        short_opt = await qualify_option(self.ib, short_K, "P", exp)
        long_opt  = await qualify_option(self.ib, long_K,  "P", exp)

        if short_opt is None or long_opt is None:
            log.error("  Could not qualify option contracts — aborting entry")
            return False

        # Get live market quotes
        short_mid = await get_option_mid(self.ib, short_opt)
        long_mid  = await get_option_mid(self.ib, long_opt)

        if short_mid is None or long_mid is None:
            log.warning("  No live quote yet — using BS estimate for limit prices")
            short_mid = bs_put(price, short_K, bars_left / ANNUAL_BARS, sigma=m["sigma"])
            long_mid  = bs_put(price, long_K,  bars_left / ANNUAL_BARS, sigma=m["sigma"])

        actual_credit = short_mid - long_mid
        log.info(f"  Market mid: short={short_mid:.2f}  long={long_mid:.2f}  "
                 f"spread credit={actual_credit:.2f}pt = ${actual_credit * NDX_MULT * self.n_contracts:.0f}")

        if actual_credit <= 0:
            log.info("  SKIP: spread credit is zero or negative at current quotes")
            return False

        # Place legs: SELL short put (higher strike), BUY long put (lower strike)
        # Use midpoint limit, lean slightly aggressive to get filled quickly
        short_limit = round(short_mid - 0.05, 2)   # sell slightly below mid
        long_limit  = round(long_mid  + 0.05, 2)   # buy slightly above mid

        sell_trade = await place_leg(self.ib, short_opt, "SELL", self.n_contracts,
                                     short_limit, self.dry_run)
        buy_trade  = await place_leg(self.ib, long_opt,  "BUY",  self.n_contracts,
                                     long_limit,  self.dry_run)

        if not self.dry_run:
            # Wait a few seconds and confirm fills
            await asyncio.sleep(5)
            open_orders = self.ib.openOrders()
            open_ids = {o.orderId for o in open_orders}

            if sell_trade and sell_trade.order.orderId in open_ids:
                log.warning("  Short put leg not yet filled — widening limit by 0.50")
                sell_trade.order.lmtPrice = round(short_limit - 0.50, 2)
                self.ib.placeOrder(short_opt, sell_trade.order)

            if buy_trade and buy_trade.order.orderId in open_ids:
                log.warning("  Long put leg not yet filled — widening limit by 0.50")
                buy_trade.order.lmtPrice = round(long_limit + 0.50, 2)
                self.ib.placeOrder(long_opt, buy_trade.order)

            await asyncio.sleep(5)

        self.position_open = True
        self.short_strike  = short_K
        self.long_strike   = long_K
        self.credit_pts    = actual_credit
        self.short_contract = short_opt
        self.long_contract  = long_opt
        self.entry_time     = now
        self.entry_ndx      = price

        credit_dollar = actual_credit * NDX_MULT * self.n_contracts
        log.info(f"  ✓ ENTERED Bear Put Spread — credit: {actual_credit:.2f}pt "
                 f"(${credit_dollar:.0f})  short={short_K}  long={long_K}")
        return True

    async def _monitor_position(self):
        log.info(f"Monitoring position: short={self.short_strike}  long={self.long_strike}  "
                 f"credit={self.credit_pts:.2f}pt")

        while True:
            now = await self._now_et()
            now_t = now.time()

            # Get current NDX price
            try:
                ndx_price = await get_ndx_quote(self.ib)
            except Exception as e:
                log.warning(f"Quote fetch failed: {e} — retrying in 15s")
                await asyncio.sleep(15)
                continue

            # Estimate bars remaining until 16:00 ET
            close_dt = datetime.combine(now.date(), time(16, 0), tzinfo=ET)
            mins_left = max((close_dt - now).total_seconds() / 60, 1)
            bars_left = max(int(mins_left / 5), 1)

            current_sv = spread_value_pts(
                ndx_price, self.short_strike, self.long_strike, bars_left, 0.25
            )

            pnl_pts    = self.credit_pts - current_sv
            pnl_dollar = pnl_pts * NDX_MULT * self.n_contracts

            log.info(f"  NDX={ndx_price:.1f}  spread={current_sv:.2f}pt  "
                     f"P&L={pnl_pts:+.2f}pt (${pnl_dollar:+.0f})  "
                     f"target≤{self.credit_pts * PROFIT_TARGET_PCT:.2f}  "
                     f"stop≥{self.credit_pts * LOSS_STOP_MULT:.2f}")

            exit_reason = None

            # 1. NDX stop: price touched short strike
            if ndx_price < self.short_strike:
                exit_reason = "NDX_stop"

            # 2. Loss stop: spread >= 2× credit
            elif current_sv >= self.credit_pts * LOSS_STOP_MULT:
                exit_reason = "loss_stop"

            # 3. Profit target: spread <= 25% of credit
            elif current_sv <= self.credit_pts * PROFIT_TARGET_PCT:
                exit_reason = "profit_target"

            # 4. Time exit: 14:30 ET
            elif now_t >= TIME_EXIT_ET:
                exit_reason = "time_exit"

            if exit_reason:
                log.info(f"  *** EXIT triggered: {exit_reason} ***")
                await self._close_position(ndx_price, current_sv, exit_reason)
                return

            await asyncio.sleep(MONITOR_INTERVAL)

    async def _close_position(self, ndx_price: float, spread_val: float, reason: str):
        log.info(f"Closing position (reason={reason}) — NDX={ndx_price:.1f}  "
                 f"spread_val={spread_val:.2f}pt")

        # Buy back the short put (close the sold leg)
        short_mid = await get_option_mid(self.ib, self.short_contract)
        long_mid  = await get_option_mid(self.ib, self.long_contract)

        if short_mid is None:
            short_mid = spread_val * 0.65  # fallback: rough allocation
        if long_mid is None:
            long_mid = spread_val * 0.35

        # For urgency on stop-loss exits, use aggressive limits
        if reason in ("NDX_stop", "loss_stop"):
            short_limit = round(short_mid + 1.00, 2)  # pay up to buy back
            long_limit  = round(long_mid  - 1.00, 2)  # accept less selling
        else:
            short_limit = round(short_mid + 0.10, 2)
            long_limit  = round(long_mid  - 0.10, 2)

        # BUY back the short put, SELL out the long put
        await place_leg(self.ib, self.short_contract, "BUY",  self.n_contracts,
                        short_limit, self.dry_run)
        await place_leg(self.ib, self.long_contract,  "SELL", self.n_contracts,
                        long_limit,  self.dry_run)

        if not self.dry_run:
            await asyncio.sleep(5)

        pnl_pts    = self.credit_pts - spread_val
        pnl_dollar = pnl_pts * NDX_MULT * self.n_contracts

        log.info(f"  ✓ Position closed — P&L: {pnl_pts:+.2f}pt (${pnl_dollar:+.0f})")
        log.info(f"  Summary: entry={self.entry_ndx:.1f}  exit={ndx_price:.1f}  "
                 f"credit={self.credit_pts:.2f}  close_val={spread_val:.2f}  "
                 f"reason={reason}")

        self.position_open = False

# ─── Entry point ──────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="NDX Bear Put Spread Live Trader")
    parser.add_argument("--live",      action="store_true", help="Use live account (port 7496)")
    parser.add_argument("--dry-run",   action="store_true", help="Simulate without placing orders")
    parser.add_argument("--contracts", type=int, default=N_CONTRACTS, help="Number of contracts")
    parser.add_argument("--host",      default="127.0.0.1", help="TWS/Gateway host")
    parser.add_argument("--client-id", type=int, default=10, help="IBKR client ID")
    args = parser.parse_args()

    port = 7496 if args.live else 7497
    if args.live and not args.dry_run:
        log.warning("!!!! LIVE TRADING MODE — REAL MONEY !!!!")
        confirm = input("Type YES to confirm live trading: ").strip()
        if confirm != "YES":
            print("Aborted.")
            return

    log.info(f"Connecting to IBKR at {args.host}:{port} (clientId={args.client_id})")
    ib = IB()
    util.patchAsyncio()

    try:
        await ib.connectAsync(args.host, port, clientId=args.client_id)
        log.info(f"Connected. Accounts: {ib.managedAccounts()}")

        trader = NDXSpreadTrader(ib, args.contracts, args.dry_run)
        await trader.run()

    except ConnectionRefusedError:
        log.error(
            f"Could not connect to TWS/IB Gateway at {args.host}:{port}.\n"
            "Make sure TWS is running, API connections are enabled, and\n"
            "the port matches (7497 paper / 7496 live)."
        )
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
    finally:
        if ib.isConnected():
            ib.disconnect()
            log.info("Disconnected from IBKR.")

if __name__ == "__main__":
    asyncio.run(main())
