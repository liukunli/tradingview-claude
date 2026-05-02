from pathlib import Path

BASE_DIR = Path(__file__).parent

# Point this at your data folder.  Can be overridden via CLI --data-dir.
DATA_DIR = str(BASE_DIR / 'data')

# Backtest defaults
INITIAL_CAPITAL  = 1_000_000.0
COMMISSION_RATE  = 0.0003   # 万三佣金
SLIPPAGE_RATE    = 0.001    # 千一滑点
STAMP_DUTY       = 0.001    # 千一印花税 (sell only)
RISK_FREE_RATE   = 0.03     # 3% annualised risk-free rate
