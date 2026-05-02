@echo off
echo ============================================
echo Interactive Brokers MCP Server
echo ============================================
echo.
echo Starting IBKR MCP Server...
echo Make sure TWS or IB Gateway is running!
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or higher
    pause
    exit /b 1
)

REM Check if required packages are installed
python -c "import mcp" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install required packages
        pause
        exit /b 1
    )
)

echo.
echo Server is running. Press Ctrl+C to stop.
echo ============================================
echo.

python server.py

pause
