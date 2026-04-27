"""
live/market_data.py — TradingView MCP and IBKR real-time data clients.

Backends:
  TradingViewClient  — calls TradingView MCP server via subprocess
  IBKRDataClient     — direct ib_insync fallback when TV is unavailable

Bar metrics computation lives in strategy/signal_engine.py (compute_bar_metrics).
"""

import json
import subprocess
import asyncio
import logging
import pandas as pd
from datetime import datetime
from typing import Optional

from ..config.settings import ET, SYMBOL, TV_BARS_LOOKBACK, TV_TIMEFRAME

log = logging.getLogger("ndx.market_data")


def _tv_call(tool: str, params: dict) -> dict:
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
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"TV MCP call failed: {result.stderr.strip()}")
    return json.loads(result.stdout.strip())


class TradingViewClient:
    """Real-time NDX data via TradingView MCP tools."""

    def get_quote(self) -> dict:
        result  = _tv_call("quote_get", {"symbol": SYMBOL})
        content = result.get("content", [{}])
        if isinstance(content, list) and content:
            raw = content[0].get("text", "{}")
            return json.loads(raw) if isinstance(raw, str) else raw
        return {}

    def get_ohlcv(self, timeframe: str = "5", bars: int = 40) -> pd.DataFrame:
        result  = _tv_call("data_get_ohlcv", {"symbol": SYMBOL, "timeframe": timeframe,
                                               "bars": bars, "summary": False})
        content = result.get("content", [{}])
        raw     = content[0].get("text", "{}") if isinstance(content, list) and content else "{}"
        data    = json.loads(raw) if isinstance(raw, str) else raw

        rows = data.get("bars", data.get("data", []))
        if not rows:
            raise RuntimeError(f"No OHLCV data for {SYMBOL}")

        df = pd.DataFrame(rows)
        df.columns = [c.lower() for c in df.columns]
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df.columns:
                df[col] = 0.0

        ts_col = next((c for c in ("time", "timestamp", "t", "dt") if c in df.columns), None)
        if ts_col:
            df["dt"] = pd.to_datetime(df[ts_col], unit="s", utc=True).dt.tz_convert(ET)
        else:
            df["dt"] = pd.date_range(end=pd.Timestamp.now(tz=ET), periods=len(df), freq="5min")

        return df.sort_values("dt").reset_index(drop=True)

    def get_current_price(self) -> float:
        q = self.get_quote()
        return float(q.get("last") or q.get("close") or q.get("price") or 0.0)


class IBKRDataClient:
    """Fetch NDX bars directly from IBKR TWS (fallback)."""

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
        df = pd.DataFrame([{"dt": b.date, "open": b.open, "high": b.high,
                             "low": b.low, "close": b.close, "volume": b.volume}
                            for b in bars])
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
