"""
Example usage of IBKR MCP Server tools

This script demonstrates how the MCP tools would be used.
Note: This is for reference only - actual usage is through Claude Desktop.
"""

# Example tool calls and expected responses

example_workflow = """
# Example 1: Connect and check account
User: "Connect to my IBKR paper trading account"
Tool: connect_ibkr
Args: {"host": "127.0.0.1", "port": 7497, "client_id": 1}
Response: "Successfully connected to IBKR at 127.0.0.1:7497"

User: "What's my account balance?"
Tool: get_account_summary
Response: {
  "TotalCashValue": "50000.00 USD",
  "NetLiquidation": "52450.00 USD",
  "BuyingPower": "200000.00 USD",
  "RealizedPnL": "1250.00 USD",
  "UnrealizedPnL": "2450.00 USD"
}

# Example 2: Check positions
User: "What positions do I have?"
Tool: get_positions
Response: [
  {
    "symbol": "AAPL",
    "position": 100,
    "avgCost": 150.25,
    "marketPrice": 175.50,
    "marketValue": 17550.00,
    "unrealizedPNL": 2525.00
  },
  {
    "symbol": "MSFT",
    "position": 50,
    "avgCost": 340.00,
    "marketPrice": 355.75,
    "marketValue": 17787.50,
    "unrealizedPNL": 787.50
  }
]

# Example 3: Get market data
User: "What's the current price of TSLA?"
Tool: get_market_data
Args: {"symbol": "TSLA", "exchange": "SMART", "currency": "USD"}
Response: {
  "symbol": "TSLA",
  "bid": 245.30,
  "ask": 245.35,
  "last": 245.32,
  "close": 244.50,
  "volume": 45678900,
  "high": 248.75,
  "low": 243.10
}

# Example 4: Historical data
User: "Show me Apple's stock price over the last week"
Tool: get_historical_data
Args: {
  "symbol": "AAPL",
  "duration": "1 W",
  "bar_size": "1 day",
  "what_to_show": "TRADES"
}
Response: [
  {
    "date": "2026-01-13",
    "open": 172.50,
    "high": 174.20,
    "low": 171.80,
    "close": 173.45,
    "volume": 52341000
  },
  {
    "date": "2026-01-14",
    "open": 173.50,
    "high": 175.80,
    "low": 173.10,
    "close": 175.20,
    "volume": 58923000
  },
  ...
]

# Example 5: Place an order
User: "Buy 10 shares of Microsoft at market price"
Tool: place_order
Args: {
  "symbol": "MSFT",
  "action": "BUY",
  "quantity": 10,
  "order_type": "MKT"
}
Response: {
  "order_id": 12345,
  "status": "Submitted",
  "symbol": "MSFT",
  "action": "BUY",
  "quantity": 10,
  "order_type": "MKT"
}

# Example 6: Place a limit order
User: "Sell 5 shares of Apple with a limit price of $180"
Tool: place_order
Args: {
  "symbol": "AAPL",
  "action": "SELL",
  "quantity": 5,
  "order_type": "LMT",
  "limit_price": 180.00
}
Response: {
  "order_id": 12346,
  "status": "Submitted",
  "symbol": "AAPL",
  "action": "SELL",
  "quantity": 5,
  "order_type": "LMT",
  "limit_price": 180.00
}

# Example 7: Check open orders
User: "What orders do I have open?"
Tool: get_open_orders
Response: [
  {
    "order_id": 12346,
    "symbol": "AAPL",
    "action": "SELL",
    "quantity": 5,
    "order_type": "LMT",
    "status": "Submitted",
    "filled": 0,
    "remaining": 5
  }
]

# Example 8: Cancel an order
User: "Cancel order 12346"
Tool: cancel_order
Args: {"order_id": 12346}
Response: "Order 12346 cancelled"

# Example 9: Get executions
User: "Show me my trades from today"
Tool: get_executions
Args: {"days": 1}
Response: [
  {
    "symbol": "MSFT",
    "side": "BOT",
    "shares": 10,
    "price": 355.75,
    "time": "20260118  10:30:15",
    "exec_id": "0000e0d1.65a2b3c4.01.01"
  }
]

# Example 10: Get option chain
User: "Show me the option chain for SPY"
Tool: get_option_chain
Args: {"symbol": "SPY", "exchange": "SMART"}
Response: [
  {
    "exchange": "SMART",
    "expirations": [
      "20260220",
      "20260320",
      "20260417",
      ...
    ],
    "strikes": [
      480.0, 482.0, 484.0, 486.0, 488.0,
      490.0, 492.0, 494.0, 496.0, 498.0,
      ...
    ]
  }
]

# Example 11: Disconnect
User: "Disconnect from IBKR"
Tool: disconnect_ibkr
Response: "Disconnected from IBKR"
"""

if __name__ == "__main__":
    print(example_workflow)
    print("\n" + "="*60)
    print("These are example interactions with the IBKR MCP Server")
    print("Actual usage is through Claude Desktop after configuration")
    print("="*60)
