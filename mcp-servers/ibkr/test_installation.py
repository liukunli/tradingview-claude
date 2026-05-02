#!/usr/bin/env python3
"""
Test script to verify IBKR MCP Server installation
"""

import sys

def check_python_version():
    """Check if Python version is sufficient"""
    print("Checking Python version...")
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher required")
        print(f"   Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version.split()[0]}")
    return True

def check_dependencies():
    """Check if required packages are installed"""
    print("\nChecking dependencies...")
    required = {
        'mcp': 'mcp',
        'ib_insync': 'ib_insync', 
        'pydantic': 'pydantic'
    }
    
    all_installed = True
    for package, import_name in required.items():
        try:
            __import__(import_name)
            print(f"✅ {package} installed")
        except ImportError:
            print(f"❌ {package} NOT installed")
            all_installed = False
    
    return all_installed

def check_server_file():
    """Check if server.py exists and is valid"""
    print("\nChecking server files...")
    import os
    
    if not os.path.exists('server.py'):
        print("❌ server.py not found")
        return False
    print("✅ server.py found")
    
    if not os.path.exists('requirements.txt'):
        print("❌ requirements.txt not found")
        return False
    print("✅ requirements.txt found")
    
    return True

def main():
    """Run all checks"""
    print("=" * 60)
    print("IBKR MCP Server - Installation Verification")
    print("=" * 60)
    
    checks = [
        check_python_version(),
        check_dependencies(),
        check_server_file()
    ]
    
    print("\n" + "=" * 60)
    if all(checks):
        print("✅ All checks passed! Server is ready to use.")
        print("\nNext steps:")
        print("1. Start TWS or IB Gateway")
        print("2. Enable API access in TWS/Gateway settings")
        print("3. Run: python server.py")
        print("   OR double-click: start_server.bat")
    else:
        print("❌ Some checks failed. Please fix the issues above.")
        print("\nTo install missing dependencies:")
        print("   pip install -r requirements.txt")
    print("=" * 60)

if __name__ == "__main__":
    main()
