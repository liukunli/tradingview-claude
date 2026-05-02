# 🚀 IBKR MCP Server - Quick Start

## What You Get

A complete Model Context Protocol (MCP) server that lets Claude interact with your Interactive Brokers account for:

✅ Account monitoring
✅ Real-time market data
✅ Historical price charts  
✅ Trade execution
✅ Position management
✅ Order tracking

## 📁 Files Included

```
ibkr-mcp-server/
├── server.py                        # Main MCP server
├── requirements.txt                 # Python dependencies
├── start_server.bat                 # Windows startup script
├── test_installation.py             # Installation checker
├── README.md                        # Full documentation
├── WINDOWS_SETUP.md                 # Step-by-step Windows guide
├── TROUBLESHOOTING.md               # Problem solving guide
├── examples.py                      # Usage examples
├── claude_desktop_config.example.json  # Config template
├── LICENSE                          # MIT License
└── .gitignore                       # Git ignore rules
```

## ⚡ 5-Minute Setup

### 1️⃣ Install Python
- Download from: https://python.org
- ✅ Check "Add Python to PATH"

### 2️⃣ Install Dependencies
```bash
cd ibkr-mcp-server
pip install -r requirements.txt
```

### 3️⃣ Setup TWS/Gateway
- Download from: https://www.interactivebrokers.com/en/trading/tws.php
- Enable API: File → Global Configuration → API → Settings
- ✅ Enable ActiveX and Socket Clients
- Port: **7497** (paper trading)

### 4️⃣ Configure Claude Desktop
File location: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ibkr": {
      "command": "python",
      "args": ["C:\\Users\\YourName\\ibkr-mcp-server\\server.py"]
    }
  }
}
```

### 5️⃣ Test It!
1. Start TWS/Gateway
2. Restart Claude Desktop  
3. Ask Claude: "Connect to my IBKR paper trading account"
4. Then: "What's my account balance?"

## 📖 Documentation Guide

- **New to this?** → Read `WINDOWS_SETUP.md`
- **Want all features?** → Read `README.md`
- **Having issues?** → Read `TROUBLESHOOTING.md`
- **See examples?** → Run `python examples.py`

## 🔧 Available Tools

Once connected, ask Claude to:

### 📊 Market Data
- "What's the current price of AAPL?"
- "Show me Tesla's price over the last week"
- "Get the option chain for SPY"

### 💼 Account Info
- "What's my account balance?"
- "Show me all my positions"
- "What are my open orders?"

### 📈 Trading (Use with caution!)
- "Buy 10 shares of Microsoft at market"
- "Sell 5 shares of Apple at $180 limit"
- "Cancel order 12345"

## ⚠️ Important Safety Notes

1. **Always test with paper trading first** (port 7497)
2. Paper trading uses simulated money - it's safe to experiment
3. Live trading uses real money (port 7496) - be very careful
4. Review all orders before confirming
5. Start with small quantities

## 🆘 Need Help?

**Problem**: Python not found
**Fix**: Reinstall Python, check "Add to PATH"

**Problem**: Can't connect to IBKR
**Fix**: 
1. Start TWS/Gateway
2. Enable API in settings
3. Use port 7497 for paper trading

**Problem**: Claude doesn't see tools
**Fix**: 
1. Check config file path is correct
2. Use `\\` (double backslash) in Windows paths
3. Restart Claude Desktop

**For more help**: See `TROUBLESHOOTING.md` (24 common issues solved!)

## 🎯 Next Steps

1. ✅ Test with paper trading extensively
2. ✅ Learn the available commands
3. ✅ Understand market data and orders
4. ✅ Set up risk controls if needed
5. ⚠️ Only move to live trading when confident

## 📞 Support Resources

- **IBKR API**: https://interactivebrokers.github.io/
- **ib_insync**: https://ib-insync.readthedocs.io/
- **MCP**: https://modelcontextprotocol.io/
- **IBKR Support**: https://www.interactivebrokers.com/en/support/

---

**Ready to start?** Open `WINDOWS_SETUP.md` for detailed step-by-step instructions!

**Happy Trading!** 📈 (Remember: Paper trading first!)
