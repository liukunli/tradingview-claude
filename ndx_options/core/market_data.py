"""
market_data.py — TradingView MCP client for real-time NDX data.

Two backends selectable at runtime:
  - "tradingview"  : uses subprocess JSON-RPC calls to the tradingview-claude MCP server
  - "ibkr"         : uses ib_insync (fallback when TV is unavailable)
"""

import json
import math
import subprocess
import asyncio
import logging
import numpy as np
import pandas as pd
from datetime import datetime, date
from typing import Optional

from ..config.settings import (
    ET, SYMBOL, TV_MCP_BASE_URL, TV_BARS_LOOKBACK, TV_TIMEFRAME,
    ANNUAL_BARS_5MIN, BS_DEFAULT_SIGMA,
)

log = logging.getLogger("ndx.market_data")


# ── TradingView MCP thin wrapper ─────────────────────────────────────────────

def _tv_call(tool: str, params: dict) -> dict:
    """
    Call a TradingView MCP tool via the CLI bridge.
    Requires `mcp-tradingview` server running locally (see SKILL.md).
    """
    payload = json.dumps({"tool": tool, "params": params})
    result = subprocess.run(
        ["node", "-e", f"""
const {{Client}} = require('@modelcontextprotocol/sdk/client/index.js');
const {{StdioClientTransport}} = require('@modelcontextprotocol/sdk/client/stdio.js');
const t = new StdioClientTransport({{command:'node', args:[process.env.TV_MCP_PATH||'mcp/src/server.js']}});
const c = new Client({{name:'ndx-bot',version:'1.0'}},{{}});
(async()=>{{
  await c.connect(t);
  const r = await c.callTool({{name:{json.dumps(tool)},arguments:{json.dumps(params)}}});
  console.log(JSON.stringify(r));
  await c.close();
}})().catch(e=>{{console.error(e.message);process.exit(1)}});
"""],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"TV MCP call failed: {result.stderr.strip()}")
    return json.loads(result.stdout.strip())


class TradingViewClient:
    """High-level TradingView data client using MCP tools."""

    def get_quote(self) -> dict:
        """Return real-time NDX quote: last, bid, ask, volume."""
        result = _tv_call("quote_get", {"symbol": SYMBOL})
        content = result.get("content", [{}])
        if isinstance(content, list) and content:
            raw = content[0].get("text", "{}")
            return json.loads(raw) if isinstance(raw, str) else raw
        return {}

    def get_ohlcv(self, timeframe: str = "5", bars: int = 40) -> pd.DataFrame:
        """Return recent OHLCV bars as DataFrame with ET-localized DatetimeIndex."""
        result = _tv_call("data_get_ohlcv", {
            "symbol": SYMBOL,
            "timeframe": timeframe,
            "bars": bars,
            "summary": False,
        })
        content = result.get("content", [{}])
        raw = content[0].get("text", "{}") if isinstance(content, list) and content else "{}"
        data = json.loads(raw) if isinstance(raw, str) else raw

        rows = data.get("bars", data.get("data", []))
        if not rows:
            raise RuntimeError(f"No OHLCV data returned for {SYMBOL}")

        df = pd.DataFrame(rows)
        # Normalize column names
        df.columns = [c.lower() for c in df.columns]
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                df[col] = 0.0

        # Parse timestamps
        ts_col = next((c for c in ("time", "timestamp", "t", "dt") if c in df.columns), None)
        if ts_col:
            df["dt"] = pd.to_datetime(df[ts_col], unit="s", utc=True).dt.tz_convert(ET)
        else:
            df["dt"] = pd.date_range(end=pd.Timestamp.now(tz=ET), periods=len(df), freq="5min")

        return df.sort_values("dt").reset_index(drop=True)

    def get_current_price(self) -> float:
        q = self.get_quote()
        return float(q.get("last") or q.get("close") or q.get("price") or 0.0)


# ── IBKR fallback client ─────────────────────────────────────────────────────

class IBKRDataClient:
    """Fetch NDX bars directly from IBKR TWS (fallback if TV is unavailable)."""

    def __init__(self, ib):
        self.ib = ib

    async def get_ohlcv_async(self, n_bars: int = 40) -> pd.DataFrame:
        from ib_insync import Index
        ndx = Index("NDX", "NASDAQ", "USD")
        await self.ib.qualifyContractsAsync(ndx)
        bars = await self.ib.reqHistoricalDataAsync(
            ndx, endDateTime="", durationStr="3600 S",
            barSizeSetting="5 mins", whatToShow="TRADES",
            useRTH=True, formatDate=2,
        )
        if not bars:
            raise RuntimeError("No IBKR bars for NDX")
        rows = [{"dt": b.date, "open": b.open, "high": b.high,
                 "low": b.low, "close": b.close, "volume": b.volume}
                for b in bars]
        df = pd.DataFrame(rows)
        df["dt"] = pd.to_datetime(df["dt"], utc=True).dt.tz_convert(ET)
        return df.tail(n_bars).reset_index(drop=True)

    async def get_current_price_async(self) -> float:
        from ib_insync import Index
        ndx = Index("NDX", "NASDAQ", "USD")
        await self.ib.qualifyContractsAsync(ndx)
        ticker = self.ib.reqMktData(ndx, "", False, False)
        await asyncio.sleep(2)
        price = ticker.last or ticker.close or 0.0
        self.ib.cancelMktData(ndx)
        return float(price)


# ── Market metrics computation ───────────────────────────────────────────────

def compute_bar_metrics(bars: pd.DataFrame, now_et: Optional[datetime] = None) -> dict:
    """
    Compute all gate-relevant metrics from a bar DataFrame.
    Returns: price, day_range, avg_bar, trending, range_pct, mom_30, vwap, sigma
    """
    closes  = bars["close"].values
    log_ret = np.diff(np.log(np.maximum(closes, 1e-8)))
    sigma   = max(math.sqrt(np.var(log_ret) * ANNUAL_BARS_5MIN), 0.12) \
              if len(log_ret) > 2 else BS_DEFAULT_SIGMA

    day_high  = bars["high"].max()
    day_low   = bars["low"].min()
    day_range = day_high - day_low
    avg_bar   = (bars["high"] - bars["low"]).mean()
    trending  = bool(day_range > 2.5 * avg_bar) if avg_bar > 0 else False

    price     = float(bars.iloc[-1]["close"])
    range_pct = (price - day_low) / day_range if day_range > 0 else 0.5

    mom_idx = max(len(bars) - 7, 0)  # ~30-min lookback at 5-min bars
    mom_30  = price - float(bars.iloc[mom_idx]["close"])

    vol  = bars["volume"].sum()
    vwap = (bars["close"] * bars["volume"]).sum() / vol if vol > 0 else price

    return dict(
        price=price, day_high=day_high, day_low=day_low,
        day_range=day_range, avg_bar=avg_bar, trending=trending,
        range_pct=range_pct, mom_30=mom_30, vwap=vwap, sigma=sigma,
    )
