# Interactive Brokers MCP Server for Windows

A Model Context Protocol (MCP) server that provides tools for interacting with Interactive Brokers (IBKR) through the TWS API or IB Gateway.

## Features

- **Account Management**: Get account summary, positions, and portfolio information
- **Market Data**: Real-time and historical market data for stocks
- **Order Management**: Place market and limit orders, cancel orders, view open orders
- **Trade Execution**: View recent trade executions
- **Options Trading**: Get option chains for stocks

## Prerequisites

1. **Interactive Brokers Account**: You need an active IBKR account
2. **TWS or IB Gateway**: Install either:
   - Trader Workstation (TWS) - Full trading platform
   - IB Gateway - Lightweight API gateway
   
   Download from: https://www.interactivebrokers.com/en/trading/tws.php

3. **Python 3.8+**: Required for running the MCP server
4. **Enable API Access**: In TWS/Gateway settings:
   - File → Global Configuration → API → Settings
   - Enable "Enable ActiveX and Socket Clients"
   - Note the Socket port (7497 for paper trading, 7496 for live)
   - Add 127.0.0.1 to trusted IPs

## Installation

### Step 1: Install Python Dependencies

Open Command Prompt or PowerShell and run:

```bash
pip install -r requirements.txt
```

Or install packages individually:

```bash
pip install mcp ib_insync pydantic
```

### Step 2: Configure TWS/IB Gateway

1. Start TWS or IB Gateway
2. Log in with your credentials
3. Go to: **File → Global Configuration → API → Settings**
4. Check "Enable ActiveX and Socket Clients"
5. Uncheck "Read-Only API" if you want to place orders
6. Note the Socket Port:
   - **7497** for Paper Trading
   - **7496** for Live Trading
7. Add **127.0.0.1** to Trusted IPs
8. Click **OK** and restart TWS/Gateway

## Usage

### Starting the MCP Server

```bash
python server.py
```

The server will run and wait for MCP client connections via stdio.

### Integrating with Claude Desktop

Add this configuration to your Claude Desktop config file:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ibkr": {
      "command": "python",
      "args": ["C:\\path\\to\\ibkr-mcp-server\\server.py"]
    }
  }
}
```

Replace `C:\\path\\to\\ibkr-mcp-server\\` with the actual path where you saved this project.

### Available Tools

#### 1. **connect_ibkr**
Connect to Interactive Brokers TWS or Gateway.

```json
{
  "host": "127.0.0.1",
  "port": 7497,
  "client_id": 1
}
```

- `port`: 7497 (paper trading) or 7496 (live trading)
- Must be called before using other tools

#### 2. **disconnect_ibkr**
Disconnect from IBKR.

#### 3. **get_account_summary**
Get account summary including cash, equity, and P&L.

Returns:
```json
{
  "TotalCashValue": "50000.00 USD",
  "NetLiquidation": "52000.00 USD",
  "BuyingPower": "200000.00 USD",
  "RealizedPnL": "500.00 USD",
  "UnrealizedPnL": "2000.00 USD"
}
```

#### 4. **get_positions**
Get all current positions.

Returns array of positions with symbol, quantity, avg cost, market value, and P&L.

#### 5. **get_market_data**
Get real-time market data for a symbol.

```json
{
  "symbol": "AAPL",
  "exchange": "SMART",
  "currency": "USD"
}
```

Returns bid, ask, last, volume, high, low prices.

#### 6. **get_historical_data**
Get historical market data.

```json
{
  "symbol": "AAPL",
  "duration": "1 D",
  "bar_size": "1 hour",
  "what_to_show": "TRADES"
}
```

Duration options: "1 D", "1 W", "1 M", "1 Y"
Bar size options: "1 min", "5 mins", "1 hour", "1 day"

#### 7. **place_order**
Place a trading order.

Market Order:
```json
{
  "symbol": "AAPL",
  "action": "BUY",
  "quantity": 100,
  "order_type": "MKT"
}
```

Limit Order:
```json
{
  "symbol": "AAPL",
  "action": "SELL",
  "quantity": 100,
  "order_type": "LMT",
  "limit_price": 150.50
}
```

#### 8. **cancel_order**
Cancel an existing order.

```json
{
  "order_id": 123
}
```

#### 9. **get_open_orders**
Get all open orders.

#### 10. **get_executions**
Get recent trade executions.

```json
{
  "days": 1
}
```

#### 11. **get_option_chain**
Get option chain for a symbol.

```json
{
  "symbol": "AAPL",
  "exchange": "SMART"
}
```

## Example Conversations with Claude

Once configured, you can ask Claude:

- "Connect to my IBKR paper trading account"
- "What's my current account balance?"
- "Show me all my positions"
- "Get the current price of AAPL"
- "Show me historical data for TSLA over the last week"
- "Place a market order to buy 10 shares of MSFT"
- "What are my open orders?"
- "Get the option chain for SPY"

## Security Notes

⚠️ **Important Security Considerations:**

1. **Paper Trading First**: Always test with paper trading (port 7497) before using live account
2. **Order Confirmation**: The server allows order placement - use with caution
3. **API Access**: Only enable API access when actively using it
4. **Firewall**: Ensure your firewall allows connections to TWS/Gateway
5. **Credentials**: Never share your IBKR credentials or API keys

## Troubleshooting

### Connection Failed
- Ensure TWS or IB Gateway is running
- Verify API settings are enabled
- Check port number (7497 for paper, 7496 for live)
- Confirm 127.0.0.1 is in trusted IPs

### No Market Data
- Your IBKR account needs market data subscriptions
- Real-time data requires active subscriptions
- Delayed/snapshot data may be available without subscription

### Order Placement Fails
- Ensure "Read-Only API" is unchecked in TWS settings
- Verify you have sufficient buying power
- Check that the market is open for the security

### Module Not Found
```bash
pip install --upgrade mcp ib_insync pydantic
```

## Development

### Running Tests
```bash
python -m pytest tests/
```

### Logging
Logs are written to console. Adjust logging level in `server.py`:

```python
logging.basicConfig(level=logging.DEBUG)
```

## License

MIT License - See LICENSE file for details

## Disclaimer

This software is for educational purposes. Trading involves risk. Use at your own discretion. The authors are not responsible for any financial losses.

## Resources

- [Interactive Brokers API](https://interactivebrokers.github.io/)
- [ib_insync Documentation](https://ib-insync.readthedocs.io/)
- [MCP Documentation](https://modelcontextprotocol.io/)
- [IBKR API Reference](https://interactivebrokers.github.io/tws-api/)

## Support

For issues related to:
- **IBKR API**: Contact Interactive Brokers support
- **MCP Server**: Open an issue on GitHub
- **ib_insync**: Check the ib_insync documentation

## Changelog

### Version 1.0.0
- Initial release
- Support for basic account operations
- Market data retrieval
- Order management
- Historical data queries
- Option chain retrieval
