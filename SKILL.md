---
name: launch-tradingview
description: Launch TradingView Desktop and verify the CDP connection is ready. Use when the user says "launch tradingview", "open tradingview", "start tradingview", "connect to tradingview", or when TradingView tools fail because the app isn't running.
disable-model-invocation: true
allowed-tools: mcp__tradingview__tv_launch, mcp__tradingview__tv_health_check
---

# Launch TradingView

Launch TradingView Desktop with CDP (Chrome DevTools Protocol) enabled so MCP tools can control it.

## Arguments

Optional: `$ARGUMENTS` — accepts `port=<number>` to override the default CDP port (9222), or `keep` to skip killing the existing instance.

## Steps

1. **Parse arguments** (if any):
   - If the user passed `port=<N>`, use that port number.
   - If the user passed `keep`, set `kill_existing` to false.
   - Otherwise use defaults: port 9222, kill_existing true.

2. **Launch TradingView** using `mcp__tradingview__tv_launch` with the resolved parameters.

3. **Verify the connection** by calling `mcp__tradingview__tv_health_check`.
   - If `cdp_connected` is true, report success and show:
     - Symbol currently on chart
     - Timeframe
     - Chart URL
   - If `cdp_connected` is false, report failure and suggest the user:
     - Check that TradingView Desktop is installed
     - Try running `/launch-tradingview` again
     - Manually open TradingView and enable remote debugging on port 9222

## Success output format

```
TradingView is live.
  Symbol:    <chart_symbol>
  Timeframe: <chart_resolution>
  URL:       <target_url>
```
