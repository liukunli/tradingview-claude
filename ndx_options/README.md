# NDX Options Bot

Automated NDX 0DTE Bear Put Spread trading system derived from 159 real trades (Jan–Apr 2026).

## Architecture

```
ndx_options/
├── config/
│   └── settings.py          All constants from ndx-spread-analysis.md
├── core/
│   ├── market_data.py       TradingView MCP + IBKR data clients, bar metrics
│   ├── signal_engine.py     Gate (Go/No-Go), Q-Score, strike selection, BS pricer
│   ├── order_manager.py     IBKR ib_insync order placement (paper/live)
│   └── risk_manager.py      Circuit breakers, daily loss limits, consecutive loss tracking
├── strategy/
│   └── bear_put.py          Full session orchestration: wait → gate → enter → monitor → exit
├── analysis/
│   ├── daily_report.py      EOD P&L summary, event audit trail, JSON + text logs
│   └── backtest.py          Replay NDX_5min_2026.json + PerformanceEvaluator metrics
├── logs/                    Session logs (created at runtime)
├── .env.example             Credential template — copy to .env
├── main.py                  CLI entry point
└── requirements.txt
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r ndx_options/requirements.txt

# 2. Set credentials
cp ndx_options/.env.example ndx_options/.env
# Edit .env: set IBKR_ACCOUNT to your paper account number

# 3. Start IBKR TWS (paper trading, port 7497)
#    Enable API connections: File → Global Configuration → API → Settings

# 4. Dry-run (no orders placed, prints full gate evaluation)
python -m ndx_options.main --dry-run

# 5. Run backtest against historical data
python -m ndx_options.main backtest --verbose

# 6. Paper trade (orders placed to 7497)
python -m ndx_options.main trade

# 7. Live trade (REAL MONEY — requires "YES" confirmation)
python -m ndx_options.main trade --live
```

## Strategy Summary

**Only direction with positive EV: Bear Put Spread**

| Metric | Value |
|--------|-------|
| Expected value | +$1,836 / trade |
| Win rate (prime window) | 64% |
| Win rate (0DTE) | 35% |
| Max loss per contract | ~$4,500–$4,800 |

### Go/No-Go Gate (5 criteria, score ≥ 3 to trade)

1. Prime window 10:00–10:30 ET
2. 30-min momentum flat ±10pt
3. NDX in top 20% of intraday range
4. Non-trending regime (range < 2.5× avg bar)
5. 0DTE expiry available

### Q-Score (0–100)
- ≥ 65: full size (3 contracts)
- 45–64: half size (1–2 contracts)
- < 45: no trade

### Strike Selection
```python
short_K = floor((price - 100) / 50) * 50   # 100–150pt OTM
long_K  = short_K - 50                      # protection leg
```

### Exits (hard rules)
- **Profit**: spread decays to 25% of credit → close
- **Loss stop**: spread reaches 2× credit → close immediately
- **NDX stop**: price breaks through short strike → close immediately
- **Time**: 14:30 ET → close regardless of P&L
- **Scale-ins**: max 2 adds, only if NDX < 100pt below short strike

## Institutional Risk Controls

| Control | Setting |
|---------|---------|
| Daily loss limit | $15,000 (configurable in `settings.py`) |
| Circuit breaker | Halt after 3 consecutive losses |
| Position size reduction | 1 contract after 2 consecutive losses |
| Scale-in hard cap | 2 adds maximum (prevents −$58K days) |
| Hard macro override | Skip if Fed/CPI/tariff/earnings |
| EDT block | Skip if entry after 14:45 (8% WR historically) |
| Trending block | Skip if day_range > 250pt |

## Daily Workflow

1. **9:30 ET** — Bot starts, checks for overnight EDT positions
2. **10:00–10:30 ET** — Evaluates gate every 60s; enters on score ≥ 3
3. **10:30–14:30 ET** — Monitors position every 30s, checks exit conditions
4. **14:30 ET** — Time exit closes any open position
5. **16:00 ET** — EOD summary written to `logs/session_YYYY-MM-DD.{json,txt}`

## Backtest Usage

```bash
# Full historical period
python -m ndx_options.main backtest

# Specific date range + improvement proposals
python -m ndx_options.main backtest --start 2026-01-12 --end 2026-04-17 --improve

# Verbose (print each trade)
python -m ndx_options.main backtest --verbose
```

Sample output:
```
NDX BEAR PUT BACKTEST
======================================================
  period                       2026-01-12 → 2026-04-17
  trading_days                 68
  trades                       21
  win_rate                     0.762
  total_pnl                    $31,424
  sharpe_ratio                 1.842
  max_drawdown_pct             8.3%
```

## Data Sources

- **Live market data**: TradingView MCP (1-min + 5-min NDX bars, real-time quote)
- **Order execution**: IBKR TWS/Gateway via ib_insync
- **Historical backtest**: `trading_logs/NDX_5min_2026.json` (5-min bars Jan–Apr 2026)
- **Strategy rules**: `ndx-spread-analysis.md` (derived from 159 real trades)

## Files NOT to commit

- `ndx_options/.env` — IBKR credentials
- `ndx_options/logs/` — session logs (may contain account info)
