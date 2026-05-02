# IBKR MCP Server - Troubleshooting Guide

## Common Issues and Solutions

### Installation Issues

#### 1. "Python is not recognized as an internal or external command"

**Cause**: Python is not installed or not in system PATH

**Solutions**:
- Reinstall Python from python.org
- During installation, check "Add Python to PATH"
- Manually add Python to PATH:
  1. Search for "Environment Variables" in Windows
  2. Edit "Path" under System Variables
  3. Add Python installation directory (usually `C:\Users\YourName\AppData\Local\Programs\Python\Python3xx`)
  4. Restart Command Prompt

**Verify Fix**:
```bash
python --version
```

#### 2. "pip is not recognized"

**Cause**: pip not installed or not in PATH

**Solutions**:
```bash
python -m ensurepip --upgrade
python -m pip --version
```

Use `python -m pip` instead of `pip`:
```bash
python -m pip install -r requirements.txt
```

#### 3. "ModuleNotFoundError: No module named 'mcp'"

**Cause**: Required packages not installed

**Solutions**:
```bash
pip install mcp
pip install ib_insync
pip install pydantic
```

Or all at once:
```bash
pip install -r requirements.txt
```

**If still failing**:
```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

#### 4. "Permission denied" during installation

**Cause**: Insufficient permissions

**Solutions**:
- Run Command Prompt as Administrator
- Or use user install:
```bash
pip install --user -r requirements.txt
```

---

### Connection Issues

#### 5. "Connection refused [Errno 10061]"

**Cause**: TWS or IB Gateway not running, or API not enabled

**Solutions**:
1. Start TWS or IB Gateway
2. Log in successfully
3. Verify API settings:
   - File → Global Configuration → API → Settings
   - Enable "ActiveX and Socket Clients"
   - Check socket port (7497 for paper, 7496 for live)
4. Restart TWS/Gateway after changing settings
5. Try connecting again

**Test Connection**:
```python
from ib_insync import IB
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)
print("Connected!")
ib.disconnect()
```

#### 6. "Already connected to IBKR"

**Cause**: Previous connection still active

**Solutions**:
- Ask Claude to disconnect first
- Or restart the MCP server
- Or restart TWS/Gateway

#### 7. "Invalid client id"

**Cause**: Client ID conflict or invalid

**Solutions**:
- Use a different client ID (1-32)
- Check TWS settings for Master API client ID
- Ensure no other programs using same client ID

#### 8. "Connection timeout"

**Cause**: Firewall blocking connection or wrong port

**Solutions**:
1. Check firewall allows TWS/Gateway
2. Verify correct port number:
   - 7497 for paper trading
   - 7496 for live trading
   - 4001 for IB Gateway (sometimes)
3. Try disabling firewall temporarily to test
4. Add exception for Python and TWS in Windows Firewall

---

### API and Market Data Issues

#### 9. "No market data permissions"

**Cause**: Insufficient market data subscriptions

**Solutions**:
- Log into IBKR Account Management
- Navigate to Settings → Market Data Subscriptions
- Subscribe to required data feeds
- For testing, delayed data may be available
- Note: Real-time data requires active subscriptions

#### 10. "No security definition found"

**Cause**: Invalid symbol or exchange

**Solutions**:
- Verify symbol is correct (e.g., "AAPL" not "APPLE")
- Try different exchange:
  - "SMART" for auto-routing
  - "NYSE", "NASDAQ" for specific exchanges
- Check if security exists and trades on IBKR

#### 11. "Historical data request pacing violation"

**Cause**: Too many historical data requests

**Solutions**:
- Wait 10-15 seconds between requests
- Reduce number of historical data calls
- IBKR limits: 60 requests per 10 minutes

---

### Order Placement Issues

#### 12. "Order rejected: Read-only API"

**Cause**: API set to read-only mode

**Solutions**:
1. In TWS: File → Global Configuration → API → Settings
2. Uncheck "Read-Only API"
3. Click OK
4. Restart TWS/Gateway
5. Try order again

#### 13. "Order rejected: Insufficient funds"

**Cause**: Not enough buying power

**Solutions**:
- Check account balance with `get_account_summary`
- Reduce order size
- For paper trading, check paper account balance

#### 14. "Order rejected: Market closed"

**Cause**: Trying to trade outside market hours

**Solutions**:
- Check market hours (9:30 AM - 4:00 PM ET for US stocks)
- For after-hours trading, need to enable extended hours
- Some securities don't trade pre/post market

#### 15. "Invalid limit price"

**Cause**: Limit price outside allowed range

**Solutions**:
- Price must be positive
- Check current market price
- Price can't be too far from market (exchange rules)
- Use realistic limit prices

---

### Claude Desktop Integration Issues

#### 16. "Claude doesn't see IBKR tools"

**Cause**: MCP server not configured in Claude Desktop

**Solutions**:
1. Locate config file:
   - Press `Win + R`
   - Type `%APPDATA%\Claude`
   - Open or create `claude_desktop_config.json`

2. Add configuration:
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

3. Use DOUBLE backslashes in Windows paths
4. Save file
5. Restart Claude Desktop

**Verify**:
- Ask Claude: "What tools do you have access to?"
- Should list IBKR tools

#### 17. "Server not responding"

**Cause**: Server crashed or path incorrect

**Solutions**:
- Check path in config is correct
- Verify `server.py` exists at that location
- Test server manually:
  ```bash
  python server.py
  ```
- Check for Python errors in console
- Restart Claude Desktop

#### 18. "JSON parse error in config"

**Cause**: Invalid JSON syntax

**Solutions**:
- Validate JSON at jsonlint.com
- Common mistakes:
  - Missing commas
  - Extra commas at end
  - Single backslashes (use `\\`)
  - Missing quotes
- Use a JSON validator or editor

---

### Runtime Errors

#### 19. "asyncio errors"

**Cause**: Event loop conflicts

**Solutions**:
- Restart the MCP server
- Ensure only one instance running
- Check Python version (need 3.8+)

#### 20. "Ticker not found"

**Cause**: Contract not qualified or invalid

**Solutions**:
- Verify symbol exists
- Try qualifying contract manually
- Use SMART exchange for auto-routing
- Check security type (Stock vs Option vs Future)

#### 21. "Request timeout"

**Cause**: TWS not responding or slow connection

**Solutions**:
- Check TWS/Gateway is responsive
- Reduce request frequency
- Increase timeout if modifying code
- Restart TWS/Gateway if frozen

---

### Windows-Specific Issues

#### 22. "Cannot find the path specified"

**Cause**: Path with spaces not quoted properly

**Solutions**:
```json
{
  "mcpServers": {
    "ibkr": {
      "command": "python",
      "args": ["C:\\Program Files\\ibkr-mcp-server\\server.py"]
    }
  }
}
```

Or move to path without spaces:
```
C:\Users\YourName\ibkr-mcp-server\
```

#### 23. "Access denied" errors

**Cause**: File permissions or antivirus

**Solutions**:
- Run as Administrator
- Check antivirus isn't blocking
- Add folder to antivirus exclusions
- Verify file isn't marked read-only

#### 24. "Long path issue"

**Cause**: Windows path length limit

**Solutions**:
- Move server to shorter path
- Enable long paths in Windows:
  1. Run as Admin: `gpedit.msc`
  2. Computer Configuration → Administrative Templates → System → Filesystem
  3. Enable "Enable Win32 long paths"

---

## Diagnostic Commands

### Check Python Installation
```bash
python --version
pip --version
```

### Check Dependencies
```bash
pip list | findstr mcp
pip list | findstr ib_insync
pip list | findstr pydantic
```

### Test Server Manually
```bash
cd C:\path\to\ibkr-mcp-server
python test_installation.py
```

### Test IBKR Connection
```python
from ib_insync import IB
ib = IB()
try:
    ib.connect('127.0.0.1', 7497, clientId=1)
    print("✅ Connected successfully!")
    print(f"Server version: {ib.wrapper.serverVersion()}")
    ib.disconnect()
except Exception as e:
    print(f"❌ Connection failed: {e}")
```

### Check TWS/Gateway Status
- Look for TWS/Gateway in Task Manager
- Check system tray for TWS icon
- Verify login successful (no error messages)

---

## Getting Additional Help

### Log Files Location

**TWS Logs**:
- Windows: `C:\Users\YourName\Jts\<username>\`

**IB Gateway Logs**:
- Windows: `C:\Users\YourName\ibgateway\<username>\`

**MCP Server Logs**:
- Console output when running server

### Useful Resources

1. **IBKR API Documentation**:
   - https://interactivebrokers.github.io/

2. **ib_insync Documentation**:
   - https://ib-insync.readthedocs.io/

3. **IBKR Support**:
   - https://www.interactivebrokers.com/en/support/
   - Phone support (check website for number)

4. **MCP Documentation**:
   - https://modelcontextprotocol.io/

### Reporting Issues

When reporting issues, include:
1. Python version: `python --version`
2. Package versions: `pip list`
3. Windows version
4. Error message (full traceback)
5. TWS or Gateway version
6. What you were trying to do
7. Steps to reproduce

---

## Prevention Tips

1. **Always test with paper trading first** (port 7497)
2. Keep TWS/Gateway updated
3. Keep Python packages updated: `pip install --upgrade -r requirements.txt`
4. Restart TWS daily to prevent memory issues
5. Don't run multiple MCP servers simultaneously
6. Close Claude Desktop properly (don't force kill)
7. Back up your `claude_desktop_config.json`

---

## Emergency Procedures

### If Everything Fails

1. **Clean Reinstall**:
   ```bash
   pip uninstall mcp ib_insync pydantic
   pip install -r requirements.txt
   ```

2. **Reset TWS/Gateway Settings**:
   - Close TWS/Gateway
   - Delete settings folder
   - Restart and reconfigure

3. **Start Fresh**:
   - Delete `ibkr-mcp-server` folder
   - Download fresh copy
   - Follow setup guide from beginning

4. **Contact Support**:
   - IBKR support for TWS/API issues
   - Python community for Python issues
   - Claude support for Claude Desktop issues

---

**Remember**: Most issues are configuration-related and can be fixed by carefully following the setup guide. Always start with paper trading! 📈
