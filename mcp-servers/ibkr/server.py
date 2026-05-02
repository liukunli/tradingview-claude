#!/usr/bin/env python3
"""
Interactive Brokers MCP Server
Provides tools for interacting with IBKR API through Model Context Protocol
"""

import asyncio
import logging
from typing import Any
from datetime import datetime, timedelta
import json
import os

from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
from pydantic import BaseModel, Field

# IBKR API imports
try:
    from ib_insync import IB, Stock, Option, Future, Forex, Contract, Order, util
except ImportError:
    print("ERROR: ib_insync not installed. Install with: pip install ib_insync")
    exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ibkr-mcp-server")

# Global IB connection
ib = IB()

# Config file path (same directory as server.py)
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

class IBKRConfig(BaseModel):
    """Configuration for IBKR connection"""
    host: str = Field(default="127.0.0.1", description="TWS/Gateway host")
    port: int = Field(default=7497, description="TWS port (7497 paper, 7496 live)")
    client_id: int = Field(default=1, description="Client ID for connection")

def load_config() -> IBKRConfig:
    """Load configuration from config.json file"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config_data = json.load(f)
            logger.info(f"Loaded config from {CONFIG_FILE}")
            return IBKRConfig(**config_data)
        except Exception as e:
            logger.warning(f"Failed to load config file: {e}. Using defaults.")
    else:
        logger.info(f"Config file not found at {CONFIG_FILE}. Using defaults.")
    return IBKRConfig()

config = load_config()

# Initialize MCP server
app = Server("ibkr-mcp-server")

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available IBKR tools"""
    return [
        Tool(
            name="connect_ibkr",
            description=f"Connect to Interactive Brokers TWS or Gateway. Defaults from config.json: host={config.host}, port={config.port}, client_id={config.client_id}",
            inputSchema={
                "type": "object",
                "properties": {
                    "host": {
                        "type": "string",
                        "description": f"Host address (default from config: {config.host})"
                    },
                    "port": {
                        "type": "integer",
                        "description": f"Port number - 7497 for paper, 7496 for live (default from config: {config.port})"
                    },
                    "client_id": {
                        "type": "integer",
                        "description": f"Client ID (default from config: {config.client_id})"
                    }
                }
            }
        ),
        Tool(
            name="disconnect_ibkr",
            description="Disconnect from Interactive Brokers",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_account_summary",
            description="Get account summary including cash, equity, and positions",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_positions",
            description="Get all current positions",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_market_data",
            description="Get real-time market data for a symbol",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol (e.g., AAPL, MSFT)"
                    },
                    "exchange": {
                        "type": "string",
                        "description": "Exchange (default: SMART)",
                        "default": "SMART"
                    },
                    "currency": {
                        "type": "string",
                        "description": "Currency (default: USD)",
                        "default": "USD"
                    }
                },
                "required": ["symbol"]
            }
        ),
        Tool(
            name="get_historical_data",
            description="Get historical market data",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol"
                    },
                    "duration": {
                        "type": "string",
                        "description": "Duration (e.g., '1 D', '1 W', '1 M', '1 Y')",
                        "default": "1 D"
                    },
                    "bar_size": {
                        "type": "string",
                        "description": "Bar size (e.g., '1 min', '5 mins', '1 hour', '1 day')",
                        "default": "1 hour"
                    },
                    "what_to_show": {
                        "type": "string",
                        "description": "Data type (TRADES, MIDPOINT, BID, ASK)",
                        "default": "TRADES"
                    }
                },
                "required": ["symbol"]
            }
        ),
        Tool(
            name="place_order",
            description="Place a trading order (market or limit)",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol"
                    },
                    "action": {
                        "type": "string",
                        "description": "BUY or SELL",
                        "enum": ["BUY", "SELL"]
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Number of shares"
                    },
                    "order_type": {
                        "type": "string",
                        "description": "Order type (MKT or LMT)",
                        "enum": ["MKT", "LMT"],
                        "default": "MKT"
                    },
                    "limit_price": {
                        "type": "number",
                        "description": "Limit price (required for LMT orders)"
                    }
                },
                "required": ["symbol", "action", "quantity", "order_type"]
            }
        ),
        Tool(
            name="cancel_order",
            description="Cancel an existing order",
            inputSchema={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "integer",
                        "description": "Order ID to cancel"
                    }
                },
                "required": ["order_id"]
            }
        ),
        Tool(
            name="get_open_orders",
            description="Get all open orders",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_executions",
            description="Get recent trade executions",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back (default: 1)",
                        "default": 1
                    }
                }
            }
        ),
        Tool(
            name="get_option_chain",
            description="Get option chain for a symbol",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock symbol"
                    },
                    "exchange": {
                        "type": "string",
                        "description": "Exchange (default: SMART)",
                        "default": "SMART"
                    }
                },
                "required": ["symbol"]
            }
        )
    ]

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls"""
    try:
        if name == "connect_ibkr":
            result = await connect_ibkr(
                arguments.get("host", config.host),
                arguments.get("port", config.port),
                arguments.get("client_id", config.client_id)
            )
        elif name == "disconnect_ibkr":
            result = await disconnect_ibkr()
        elif name == "get_account_summary":
            result = await get_account_summary()
        elif name == "get_positions":
            result = await get_positions()
        elif name == "get_market_data":
            result = await get_market_data(
                arguments["symbol"],
                arguments.get("exchange", "SMART"),
                arguments.get("currency", "USD")
            )
        elif name == "get_historical_data":
            result = await get_historical_data(
                arguments["symbol"],
                arguments.get("duration", "1 D"),
                arguments.get("bar_size", "1 hour"),
                arguments.get("what_to_show", "TRADES")
            )
        elif name == "place_order":
            result = await place_order(
                arguments["symbol"],
                arguments["action"],
                arguments["quantity"],
                arguments["order_type"],
                arguments.get("limit_price")
            )
        elif name == "cancel_order":
            result = await cancel_order(arguments["order_id"])
        elif name == "get_open_orders":
            result = await get_open_orders()
        elif name == "get_executions":
            result = await get_executions(arguments.get("days", 1))
        elif name == "get_option_chain":
            result = await get_option_chain(
                arguments["symbol"],
                arguments.get("exchange", "SMART")
            )
        else:
            result = f"Unknown tool: {name}"
        
        return [TextContent(type="text", text=str(result))]
    except Exception as e:
        logger.error(f"Error calling tool {name}: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]

# Tool implementations
async def connect_ibkr(host: str, port: int, client_id: int) -> str:
    """Connect to IBKR TWS or Gateway"""
    try:
        if ib.isConnected():
            return "Already connected to IBKR"
        
        await ib.connectAsync(host, port, clientId=client_id)
        config.host = host
        config.port = port
        config.client_id = client_id
        
        return f"Successfully connected to IBKR at {host}:{port}"
    except Exception as e:
        raise Exception(f"Failed to connect: {str(e)}")

async def disconnect_ibkr() -> str:
    """Disconnect from IBKR"""
    if ib.isConnected():
        ib.disconnect()
        return "Disconnected from IBKR"
    return "Not connected to IBKR"

async def get_account_summary() -> str:
    """Get account summary"""
    if not ib.isConnected():
        raise Exception("Not connected to IBKR. Use connect_ibkr first.")
    
    account_values = ib.accountValues()
    summary = {}
    
    for av in account_values:
        if av.tag in ['TotalCashValue', 'NetLiquidation', 'GrossPositionValue', 
                      'AvailableFunds', 'BuyingPower', 'RealizedPnL', 'UnrealizedPnL']:
            summary[av.tag] = f"{av.value} {av.currency}"
    
    return json.dumps(summary, indent=2)

async def get_positions() -> str:
    """Get all positions"""
    if not ib.isConnected():
        raise Exception("Not connected to IBKR. Use connect_ibkr first.")
    
    positions = ib.positions()
    position_list = []
    
    for pos in positions:
        position_list.append({
            'symbol': pos.contract.symbol,
            'position': pos.position,
            'avgCost': pos.avgCost,
            'marketPrice': pos.marketPrice if hasattr(pos, 'marketPrice') else 'N/A',
            'marketValue': pos.marketValue if hasattr(pos, 'marketValue') else 'N/A',
            'unrealizedPNL': pos.unrealizedPNL if hasattr(pos, 'unrealizedPNL') else 'N/A'
        })
    
    return json.dumps(position_list, indent=2)

async def get_market_data(symbol: str, exchange: str, currency: str) -> str:
    """Get real-time market data"""
    if not ib.isConnected():
        raise Exception("Not connected to IBKR. Use connect_ibkr first.")

    contract = Stock(symbol, exchange, currency)
    await ib.qualifyContractsAsync(contract)
    
    ticker = ib.reqMktData(contract, '', False, False)
    await asyncio.sleep(2)  # Wait for data
    
    data = {
        'symbol': symbol,
        'bid': ticker.bid,
        'ask': ticker.ask,
        'last': ticker.last,
        'close': ticker.close,
        'volume': ticker.volume,
        'high': ticker.high,
        'low': ticker.low
    }
    
    ib.cancelMktData(contract)
    return json.dumps(data, indent=2)

async def get_historical_data(symbol: str, duration: str, bar_size: str, what_to_show: str) -> str:
    """Get historical market data"""
    if not ib.isConnected():
        raise Exception("Not connected to IBKR. Use connect_ibkr first.")

    contract = Stock(symbol, 'SMART', 'USD')
    await ib.qualifyContractsAsync(contract)

    bars = await ib.reqHistoricalDataAsync(
        contract,
        endDateTime='',
        durationStr=duration,
        barSizeSetting=bar_size,
        whatToShow=what_to_show,
        useRTH=True,
        formatDate=1
    )
    
    data = []
    for bar in bars:
        data.append({
            'date': str(bar.date),
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.volume
        })
    
    return json.dumps(data, indent=2)

async def place_order(symbol: str, action: str, quantity: int, order_type: str, limit_price: float = None) -> str:
    """Place a trading order"""
    if not ib.isConnected():
        raise Exception("Not connected to IBKR. Use connect_ibkr first.")

    contract = Stock(symbol, 'SMART', 'USD')
    await ib.qualifyContractsAsync(contract)
    
    if order_type == "MKT":
        order = Order()
        order.action = action
        order.totalQuantity = quantity
        order.orderType = "MKT"
    elif order_type == "LMT":
        if limit_price is None:
            raise Exception("limit_price required for LMT orders")
        order = Order()
        order.action = action
        order.totalQuantity = quantity
        order.orderType = "LMT"
        order.lmtPrice = limit_price
    else:
        raise Exception(f"Unsupported order type: {order_type}")
    
    trade = ib.placeOrder(contract, order)
    await asyncio.sleep(1)
    
    result = {
        'order_id': trade.order.orderId,
        'status': trade.orderStatus.status,
        'symbol': symbol,
        'action': action,
        'quantity': quantity,
        'order_type': order_type
    }
    
    if limit_price:
        result['limit_price'] = limit_price
    
    return json.dumps(result, indent=2)

async def cancel_order(order_id: int) -> str:
    """Cancel an order"""
    if not ib.isConnected():
        raise Exception("Not connected to IBKR. Use connect_ibkr first.")
    
    orders = ib.openOrders()
    for order in orders:
        if order.orderId == order_id:
            ib.cancelOrder(order)
            return f"Order {order_id} cancelled"
    
    return f"Order {order_id} not found"

async def get_open_orders() -> str:
    """Get all open orders"""
    if not ib.isConnected():
        raise Exception("Not connected to IBKR. Use connect_ibkr first.")
    
    orders = ib.openTrades()
    order_list = []
    
    for trade in orders:
        order_list.append({
            'order_id': trade.order.orderId,
            'symbol': trade.contract.symbol,
            'action': trade.order.action,
            'quantity': trade.order.totalQuantity,
            'order_type': trade.order.orderType,
            'status': trade.orderStatus.status,
            'filled': trade.orderStatus.filled,
            'remaining': trade.orderStatus.remaining
        })
    
    return json.dumps(order_list, indent=2)

async def get_executions(days: int) -> str:
    """Get recent executions"""
    if not ib.isConnected():
        raise Exception("Not connected to IBKR. Use connect_ibkr first.")
    
    executions = ib.executions()
    exec_list = []
    
    cutoff = datetime.now() - timedelta(days=days)
    
    for execution in executions:
        exec_time = datetime.strptime(execution.time, '%Y%m%d  %H:%M:%S')
        if exec_time >= cutoff:
            exec_list.append({
                'symbol': execution.contract.symbol,
                'side': execution.side,
                'shares': execution.shares,
                'price': execution.price,
                'time': execution.time,
                'exec_id': execution.execId
            })
    
    return json.dumps(exec_list, indent=2)

async def get_option_chain(symbol: str, exchange: str) -> str:
    """Get option chain"""
    if not ib.isConnected():
        raise Exception("Not connected to IBKR. Use connect_ibkr first.")

    contract = Stock(symbol, exchange, 'USD')
    await ib.qualifyContractsAsync(contract)

    chains = await ib.reqSecDefOptParamsAsync(contract.symbol, '', contract.secType, contract.conId)
    
    chain_data = []
    for chain in chains:
        chain_data.append({
            'exchange': chain.exchange,
            'expirations': sorted(chain.expirations),
            'strikes': sorted(chain.strikes)[:20]  # Limit to 20 strikes
        })
    
    return json.dumps(chain_data, indent=2)

async def main():
    """Run the MCP server"""
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
