# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an MCP (Model Context Protocol) server that enables Claude AI to interact with Interactive Brokers trading accounts through the TWS API or IB Gateway. It runs on stdio and is designed for Windows with Python.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the MCP server
python server.py

# Windows launcher (auto-installs dependencies)
start_server.bat

# Verify installation
python test_installation.py

# Test IBKR connection directly (requires TWS/Gateway running)
python test_connection.py          # account + positions
python test_connection.py AAPL     # also fetch market data

# View usage examples
python examples.py
```

## Architecture

**Single-file server design** - `server.py` (~545 lines) contains the entire MCP server implementation.

**Data Flow:**
```
Claude Desktop → (stdio) → MCP Server → (ib_insync) → TWS/IB Gateway → IBKR Backend
```

**Tool Categories (11 tools total):**
- Connection: `connect_ibkr`, `disconnect_ibkr`
- Account: `get_account_summary`, `get_positions`
- Market Data: `get_market_data`, `get_historical_data`, `get_option_chain`
- Orders: `place_order`, `cancel_order`, `get_open_orders`, `get_executions`

**Key Patterns:**
- Async-first: All tool implementations use `async def`
- Use async ib_insync methods: `qualifyContractsAsync()`, `reqHistoricalDataAsync()` (not sync versions)
- Global connection: Single `ib` object maintains connection state
- JSON responses: All results returned via `json.dumps()`
- Connection checks: Every tool verifies `ib.isConnected()` before operations
- Pydantic config: Configuration uses `BaseModel` with `Field` annotations

## Configuration

**IBKR Connection Settings:** `config.json` (same directory as server.py)
```json
{
    "host": "127.0.0.1",
    "port": 7497,
    "client_id": 1
}
```

**Claude Desktop config:** `%APPDATA%\Claude\claude_desktop_config.json` (template: `claude_desktop_config.example.json`)

**Port Convention:**
- 7497 = paper trading (safe for testing)
- 7496 = live trading (real money)

## Dependencies

- `mcp>=1.0.0` - Model Context Protocol framework
- `ib_insync>=0.9.86` - Interactive Brokers API wrapper
- `pydantic>=2.0.0` - Data validation
- `tzdata` - Timezone data for historical data parsing
