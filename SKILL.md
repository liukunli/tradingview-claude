---
name: launch-tradingview
description: Launch TradingView Desktop and verify the CDP connection is ready. Use when the user says "launch tradingview", "open tradingview", "start tradingview", "connect to tradingview", or when TradingView tools fail because the app isn't running. Also use when the user asks to "set up tradingview", "install tradingview mcp", or "configure tradingview with claude".
disable-model-invocation: true
allowed-tools: mcp__tradingview__tv_launch, mcp__tradingview__tv_health_check, Bash, Read, Write
---

# TradingView + Claude — Launch & Setup

This skill handles two scenarios:
1. **Launch** — TradingView MCP is already installed, just start the app and verify connection.
2. **Full setup from scratch** — Install the MCP server, configure Claude Code, and launch TradingView.

---

## Scenario 1: Launch (MCP already installed)

Use this when the user just wants to start TradingView.

### Arguments

Optional: `$ARGUMENTS` — accepts `port=<number>` to override the default CDP port (9222), or `keep` to skip killing the existing instance.

### Steps

1. **Parse arguments** (if any):
   - `port=<N>` → use that port number
   - `keep` → set `kill_existing` to false
   - Otherwise: port 9222, kill_existing true

2. **Launch TradingView** using `mcp__tradingview__tv_launch` with the resolved parameters.

3. **Verify the connection** with `mcp__tradingview__tv_health_check`.
   - If `cdp_connected: true`, report success:
     ```
     TradingView is live.
       Symbol:    <chart_symbol>
       Timeframe: <chart_resolution>
       URL:       <target_url>
     ```
   - If `cdp_connected: false`, follow the troubleshooting steps below.

### Troubleshooting

- Confirm TradingView Desktop is installed (not the web version)
- Try running `/launch-tradingview` again
- If it still fails, manually launch with CDP enabled (see platform commands in Setup below)
- Confirm port 9222 is not blocked by another process: `lsof -i :9222`

---

## Scenario 2: Full Setup from Scratch

Use this when the MCP server is not yet installed or the user asks for a fresh setup.

### Prerequisites

- **Node.js** v18+ — check with `node --version`
- **TradingView Desktop** installed (download from tradingview.com)
- **Claude Code** CLI installed

### Step 1 — Install MCP dependencies

The MCP server ships inside this skill at `~/.claude/skills/tradingview-claude/mcp-servers/tradingview/`. Just install its dependencies:

```bash
cd ~/.claude/skills/tradingview-claude/mcp-servers/tradingview
npm install
```

### Step 2 — Add to Claude Code MCP config

Edit `~/.claude/.mcp.json` (global) or `.mcp.json` in the project root. Merge this entry — do **not** overwrite other servers:

```json
{
  "mcpServers": {
    "tradingview": {
      "command": "node",
      "args": ["/Users/<username>/.claude/skills/tradingview-claude/mcp-servers/tradingview/src/server.js"]
    }
  }
}
```

Replace `/Users/<username>` with the actual home directory path (run `echo $HOME` to get it).

### Step 3 — Launch TradingView Desktop with CDP enabled

**Recommended:** after MCP is connected, use `tv_launch` — it auto-detects the install location.

**Manual launch by platform:**

macOS:
```bash
/Applications/TradingView.app/Contents/MacOS/TradingView --remote-debugging-port=9222
```

Windows:
```bash
%LOCALAPPDATA%\TradingView\TradingView.exe --remote-debugging-port=9222
```

Linux:
```bash
tradingview --remote-debugging-port=9222
```

### Step 4 — Restart Claude Code

The MCP server loads at startup. After updating `.mcp.json`:

1. Exit Claude Code (`Ctrl+C`)
2. Relaunch Claude Code
3. The `tradingview` MCP server connects automatically on startup

### Step 5 — Verify

Run `tv_health_check`. Expected:

```json
{
  "success": true,
  "cdp_connected": true,
  "chart_symbol": "...",
  "api_available": true
}
```

If `cdp_connected: false` — TradingView is not running with `--remote-debugging-port=9222`. Relaunch it manually using the platform command above.

---

## Quick reference — useful tools after connecting

| Goal | Tool |
|------|------|
| Check connection | `tv_health_check` |
| Change symbol | `chart_set_symbol` |
| Change timeframe | `chart_set_timeframe` (use minutes: 5, 15, 60, 240, D, W) |
| Get price | `quote_get` |
| Take screenshot | `capture_screenshot` |
| Clear drawings | `draw_clear` |
| Add indicator | `chart_manage_indicator` |
