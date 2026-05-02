# IBKR MCP Server - Windows Setup Guide

## Quick Start Guide for Windows Users

### Prerequisites Checklist

- [ ] Windows 10 or later
- [ ] Python 3.8 or higher installed
- [ ] Interactive Brokers account (paper or live)
- [ ] TWS or IB Gateway installed
- [ ] Admin access (for installing packages)

---

## Step-by-Step Installation

### 1. Install Python (if not already installed)

1. Download Python from: https://www.python.org/downloads/
2. Run the installer
3. **IMPORTANT**: Check "Add Python to PATH" during installation
4. Click "Install Now"
5. Verify installation by opening Command Prompt and typing:
   ```
   python --version
   ```

### 2. Download and Extract This Server

1. Download the `ibkr-mcp-server` folder
2. Extract to a location like: `C:\Users\YourName\ibkr-mcp-server`
3. Note this path - you'll need it later

### 3. Install Required Python Packages

**Option A: Use the batch script (Easiest)**
1. Double-click `start_server.bat`
2. It will automatically install dependencies

**Option B: Manual installation**
1. Open Command Prompt
2. Navigate to the server folder:
   ```
   cd C:\Users\YourName\ibkr-mcp-server
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

### 4. Configure TWS or IB Gateway

#### Download and Install TWS/Gateway

1. Go to: https://www.interactivebrokers.com/en/trading/tws.php
2. Download either:
   - **Trader Workstation (TWS)** - Full platform with charts
   - **IB Gateway** - Lightweight, API-only (Recommended for this)
3. Install and create desktop shortcut

#### Enable API Access

1. Start TWS or IB Gateway
2. Log in with your credentials
3. Open settings:
   - **TWS**: File → Global Configuration → API → Settings
   - **Gateway**: Configure → Settings → API → Settings
4. Configure the following:
   - ✅ Enable ActiveX and Socket Clients
   - ✅ Allow connections from localhost
   - ❌ Read-Only API (uncheck if you want to place orders)
   - Socket Port: 
     - **7497** for Paper Trading (Recommended for testing)
     - **7496** for Live Trading
   - Master API client ID: **0**
   - Trusted IPs: Add **127.0.0.1**
5. Click **OK**
6. **Restart TWS/Gateway** for changes to take effect

### 5. Configure Claude Desktop

1. Open File Explorer
2. Press `Win + R`, type `%APPDATA%`, press Enter
3. Navigate to `Claude` folder (create if it doesn't exist)
4. Create or edit `claude_desktop_config.json`
5. Add this configuration:

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

**IMPORTANT**: Replace `C:\\Users\\YourName\\ibkr-mcp-server\\` with your actual path. Use double backslashes (`\\`).

6. Save the file
7. Restart Claude Desktop

---

## Testing Your Setup

### Test 1: Verify TWS/Gateway is Running

1. Start TWS or IB Gateway
2. Log in successfully
3. Keep it running in the background

### Test 2: Test the MCP Server

1. Double-click `start_server.bat`
2. You should see: "Server is running..."
3. Press Ctrl+C to stop
4. If you see errors, check the troubleshooting section below

### Test 3: Test with Claude

1. Open Claude Desktop
2. Start a new conversation
3. Type: "Connect to my IBKR paper trading account"
4. Claude should use the `connect_ibkr` tool
5. You should see a success message
6. Try: "What's my account balance?"

---

## Common Issues and Solutions

### "Python is not recognized"

**Problem**: Python not in system PATH

**Solution**:
1. Reinstall Python
2. Check "Add Python to PATH" during installation
3. Or manually add Python to PATH:
   - Right-click "This PC" → Properties
   - Advanced system settings → Environment Variables
   - Edit "Path" variable
   - Add: `C:\Users\YourName\AppData\Local\Programs\Python\Python3xx`

### "ModuleNotFoundError: No module named 'mcp'"

**Problem**: Dependencies not installed

**Solution**:
```
pip install -r requirements.txt
```

Or individually:
```
pip install mcp ib_insync pydantic
```

### "Connection refused" or "Failed to connect"

**Problem**: TWS/Gateway not running or API not enabled

**Solution**:
1. Verify TWS/Gateway is running
2. Check API settings are enabled
3. Verify port number (7497 for paper, 7496 for live)
4. Restart TWS/Gateway after changing settings

### "Not connected to IBKR"

**Problem**: Need to connect first

**Solution**:
Ask Claude to "Connect to IBKR" before using other tools

### Claude doesn't see the IBKR tools

**Problem**: MCP server not configured correctly

**Solution**:
1. Check `claude_desktop_config.json` path is correct
2. Use double backslashes in Windows paths
3. Restart Claude Desktop
4. Check server.py exists at the specified path

---

## Port Reference

| Port | Trading Mode | Use Case |
|------|--------------|----------|
| 7497 | Paper Trading | Safe testing with simulated money |
| 7496 | Live Trading | Real money trading (USE WITH CAUTION) |

---

## Security Best Practices

1. ✅ **Start with Paper Trading** (port 7497)
2. ✅ Keep TWS/Gateway updated
3. ✅ Use strong passwords
4. ✅ Enable two-factor authentication on your IBKR account
5. ✅ Only enable API when actively using it
6. ✅ Review all orders before confirming
7. ❌ Never share your IBKR credentials
8. ❌ Don't leave API connections open when not in use

---

## Daily Workflow

1. **Morning**:
   - Start TWS or IB Gateway
   - Log in to your account
   - Verify market data is working

2. **Using with Claude**:
   - Open Claude Desktop
   - Ask Claude to connect: "Connect to IBKR"
   - Use Claude to query data or manage positions
   - Example: "What are my positions?" or "Get AAPL price"

3. **Evening**:
   - Disconnect from IBKR (ask Claude or just close)
   - Close TWS/Gateway
   - Review any trades made

---

## Getting Help

### IBKR Support
- Web: https://www.interactivebrokers.com/en/support/
- Phone: Check IBKR website for your region
- API Documentation: https://interactivebrokers.github.io/

### MCP Server Issues
- Check the main README.md
- Review error messages in Command Prompt
- Verify all prerequisites are met

### Claude Desktop
- Check Claude Desktop documentation
- Verify config file syntax
- Restart Claude Desktop after config changes

---

## Next Steps

Once everything is working:

1. Explore available tools (see README.md)
2. Test with paper trading extensively
3. Learn about order types and market data
4. Consider setting up additional risk controls
5. Only move to live trading when comfortable

---

## Useful Commands for Claude

Once connected, try these with Claude:

- "What's my account balance?"
- "Show me all my positions"
- "Get the current price of AAPL"
- "Show me TSLA price over the last week"
- "What are my open orders?"
- "Show me recent executions"
- "Get the option chain for SPY"

**For orders (use with caution):**
- "Place a market order to buy 10 shares of AAPL"
- "Place a limit order to sell 5 shares of MSFT at $350"
- "Cancel order 12345"

---

## Uninstall

To remove the IBKR MCP Server:

1. Remove from Claude config:
   - Delete the "ibkr" section from `claude_desktop_config.json`
   - Restart Claude Desktop

2. Delete the server folder:
   - Delete `C:\Users\YourName\ibkr-mcp-server`

3. Uninstall Python packages (optional):
   ```
   pip uninstall mcp ib_insync pydantic
   ```

---

**Happy Trading! Remember to always start with paper trading!** 📈
