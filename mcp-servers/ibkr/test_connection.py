#!/usr/bin/env python3
"""Test script for IBKR connection and tools"""

import asyncio
import json
import sys
from ib_insync import IB, Stock

# Load config
with open("config.json", "r") as f:
    config = json.load(f)

ib = IB()

async def connect():
    """Connect to IBKR"""
    print(f"Connecting to {config['host']}:{config['port']} (client_id={config['client_id']})...")
    await ib.connectAsync(config['host'], config['port'], clientId=config['client_id'])
    print("Connected successfully!")
    return True

async def get_account_summary():
    """Get account summary"""
    account_values = ib.accountValues()
    summary = {}
    for av in account_values:
        if av.tag in ['TotalCashValue', 'NetLiquidation', 'GrossPositionValue',
                      'AvailableFunds', 'BuyingPower', 'RealizedPnL', 'UnrealizedPnL']:
            summary[av.tag] = f"{av.value} {av.currency}"
    return summary

async def get_positions():
    """Get all positions"""
    positions = ib.positions()
    position_list = []
    for pos in positions:
        position_list.append({
            'symbol': pos.contract.symbol,
            'position': pos.position,
            'avgCost': pos.avgCost
        })
    return position_list

async def get_market_data(symbol: str, exchange: str = "SMART", currency: str = "USD"):
    """Get market data for a symbol"""
    contract = Stock(symbol, exchange, currency)
    await ib.qualifyContractsAsync(contract)

    ticker = ib.reqMktData(contract, '', False, False)
    await asyncio.sleep(2)

    data = {
        'symbol': symbol,
        'bid': ticker.bid,
        'ask': ticker.ask,
        'last': ticker.last,
        'close': ticker.close,
        'volume': ticker.volume
    }
    ib.cancelMktData(contract)
    return data

async def main():
    """Main test function"""
    try:
        await connect()

        print("\n--- Account Summary ---")
        summary = await get_account_summary()
        print(json.dumps(summary, indent=2))

        print("\n--- Positions ---")
        positions = await get_positions()
        print(json.dumps(positions, indent=2))

        if len(sys.argv) > 1:
            symbol = sys.argv[1]
            print(f"\n--- Market Data: {symbol} ---")
            data = await get_market_data(symbol)
            print(json.dumps(data, indent=2))

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("\nDisconnected.")

if __name__ == "__main__":
    asyncio.run(main())
