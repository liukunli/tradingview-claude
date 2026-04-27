# NDX Options Bot

Automated NDX 0DTE Bear Put Spread trading system. Derived from 159 real trades (Jan–Apr 2026); validated against 2 years of 1-min OHLCV data (2024–2026).

---

## Table of Contents

1. [Architecture](#architecture)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Usage](#usage)
5. [Strategy Rules](#strategy-rules)
6. [Backtesting](#backtesting)
7. [Backtest Results](#backtest-results)
8. [Risk Controls](#risk-controls)
9. [Daily Workflow](#daily-workflow)
10. [Data Sources](#data-sources)
11. [Security](#security)

---

## Architecture

```
ndx_options/
├── config/
│   └── settings.py          All tunable constants (gate thresholds, sizing, exits)
│
├── strategy/                Pure computation — no I/O; fully unit-testable
│   ├── signal_engine.py     Gate, Q-Score, BS pricer, strike selection, bar metrics
│   ├── risk_manager.py      Circuit breakers, daily loss limit, consecutive loss tracking
│   └── bear_put.py          Live session orchestration: wait → gate → enter → monitor → exit
│
├── backtest/                Historical simulation
│   ├── loader.py            Reads JSON or CSV; auto-resamples 1-min → 5-min
│   ├── engine.py            simulate_day + run_backtest + save_result
│   ├── strategies.py        9-variant comparison framework
│   └── report.py            EOD P&L report (JSON + text)
│
├── live/                    External I/O
│   ├── market_data.py       TradingView MCP + IBKR real-time data clients
│   └── order_manager.py     IBKR ib_insync order placement (paper / live)
│
├── results/                 Backtest output files (auto-created; gitignored)
├── logs/                    Session logs (auto-created; gitignored)
├── .env.example             Credential template
├── main.py                  CLI entry point
└── requirements.txt
```

**Dependency rule:** `strategy/` has zero I/O imports. `backtest/` imports from `strategy/` and `config/` only. `live/` is the only layer that touches the network or IBKR socket.

---

## Installation

**Requirements:** Python 3.11+, IBKR TWS or IB Gateway (paper or live account)

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r ndx_options/requirements.txt

# 3. Copy and fill in credentials
cp ndx_options/.env.example ndx_options/.env
```

---

## Configuration

### Environment Variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `IBKR_HOST` | `127.0.0.1` | TWS / Gateway host |
| `IBKR_PAPER_PORT` | `7497` | Paper trading port |
| `IBKR_LIVE_PORT` | `7496` | Live trading port |
| `IBKR_CLIENT_ID` | `10` | API client ID |
| `IBKR_ACCOUNT` | _(blank)_ | Account number (blank = default managed account) |
| `TV_MCP_PATH` | `mcp/src/server.js` | Path to TradingView MCP server |
| `ALERT_WEBHOOK_URL` | _(blank)_ | Slack / Discord webhook for trade alerts |

### IBKR TWS Setup

1. Open TWS or IB Gateway
2. **File → Global Configuration → API → Settings**
3. Enable: _Allow connections from localhost_
4. Set socket port to `7497` (paper) or `7496` (live)
5. Uncheck: _Read-Only API_

### Strategy Constants (`config/settings.py`)

All tunable parameters are centralized. Key settings:

| Constant | Default | Effect |
|---|---|---|
| `PRIME_START / PRIME_END` | `10:00–10:30 ET` | Entry window |
| `GATE_MIN_PROCEED` | `3` | Minimum gate score to trade |
| `QSCORE_ACCEPT` | `45` | Minimum Q-Score (< this = no trade) |
| `MIN_OTM_DIST` | `100 pt` | Short strike distance from price |
| `PROFIT_TARGET_PCT` | `0.25` | Close when spread = 25% of credit (75% profit) |
| `LOSS_STOP_MULT` | `2.0` | Close when spread = 2× credit |
| `MAX_DAILY_LOSS_USD` | `$15,000` | Hard daily loss halt |
| `BASE_CONTRACTS` | `3` | Standard contract size |

---

## Usage

```bash
# ── Backtest ───────────────────────────────────────────────────────────────────
# Run on default data (trading_logs/NDX_5min_2026.json)
python -m ndx_options.main backtest

# Run on 1-min CSV data (2024–2026, auto-resampled to 5-min)
python -m ndx_options.main backtest --data ndx_spy_historical_data/ndx_1min.csv

# Date range + verbose trade log
python -m ndx_options.main backtest \
  --data ndx_spy_historical_data/ndx_1min.csv \
  --start 2024-01-02 --end 2026-04-24 \
  --verbose

# Remove gate filters (no_gate mode)
python -m ndx_options.main backtest --no-gate

# ── Strategy comparison ────────────────────────────────────────────────────────
# Run all 9 variants side-by-side
python -m ndx_options.main compare --data ndx_spy_historical_data/ndx_1min.csv

# Drill into a single variant
python -m ndx_options.main compare --name no_gate

# ── Live / paper trading ───────────────────────────────────────────────────────
# Dry-run (no orders, prints full gate + Q-Score evaluation)
python -m ndx_options.main --dry-run

# Paper trade (orders sent to TWS port 7497)
python -m ndx_options.main trade

# Live trade — REAL MONEY, requires interactive "YES" confirmation
python -m ndx_options.main trade --live

# Flag macro event day (Fed/CPI/tariff) — skips entry
python -m ndx_options.main trade --macro-event

# ── Session report ─────────────────────────────────────────────────────────────
# Print today's EOD summary
python -m ndx_options.main report

# Print a past session
python -m ndx_options.main report --date 2026-04-17
```

---

## Strategy Rules

### Go/No-Go Gate (score ≥ 3 required)

| # | Criterion | Threshold |
|---|---|---|
| 1 | Prime window | 10:00–10:30 ET |
| 2 | Flat 30-min momentum | \|mom_30\| ≤ 10 pt |
| 3 | NDX in top 20% of intraday range | range_pct ≥ 0.80 |
| 4 | Non-trending regime | day_range < 2.5 × avg_bar |
| 5 | 0DTE expiry available | always true intraday |

**Hard overrides** (block entry regardless of gate score):
- Day range > 250 pt before noon
- 30-min momentum > 50 pt (directional trending move)
- Macro event flagged (Fed/CPI/tariff/earnings)
- 2+ consecutive losses with same directional bias

### Q-Score (0–100 composite)

| Score | Grade | Action |
|---|---|---|
| ≥ 65 | High | Full size (3 contracts) |
| 45–64 | Acceptable | Half size (1–2 contracts) |
| < 45 | Poor | No trade |

**Q-Score components:** entry timing (+20 prime, -10 pre-30min, -25 EDT), expiry (+15 0DTE, -30 1DTE), direction (+15 Bear Put, -30 Bull Put), OTM distance (+10 if ≥100pt), regime (+10 range-bound, -20 trending), scale-in plan (+5)

### Strike Selection

```python
short_K = floor((price - 100) / 50) * 50   # 100–150 pt OTM
long_K  = short_K - 50                      # 50 pt wide spread
```

Target credit: **5–20 pt** ($500–$2,000 per contract). Skip if outside this range.

### Exit Rules (in priority order)

| Trigger | Condition | Action |
|---|---|---|
| Profit target | Spread value ≤ 25% of credit | Close (75% profit captured) |
| Loss stop | Spread value ≥ 2× credit | Close immediately |
| NDX stop | NDX price < short strike | Close immediately |
| Time exit | 14:30 ET | Close regardless of P&L |
| Time-stop loss | Open > 4h AND P&L < -50% credit | Close |

### Scale-in Rules

- Add up to **2 times** (hard cap)
- Only add if NDX drop from entry ≥ 30 pt × add count
- **Never add** if NDX is 100+ pt below short strike → exit instead

---

## Backtesting

The backtest engine replays OHLCV data bar-by-bar through the full strategy logic: gate evaluation → strike selection → entry → forward simulation of exits.

```
loader.py
  ├─ JSON input  (Unix timestamp bars)  ──┐
  └─ CSV input   (PT timezone 1-min)      ├── normalized 5-min DataFrame
       └── auto-resample 1-min → 5-min  ──┘
                    │
              engine.py
           simulate_day()
                    │
          ┌─────────┴─────────┐
          │                   │
    Gate + Q-Score        Forward sim
    (signal_engine)       (exit rules)
          │                   │
          └─────────┬─────────┘
                    │
             trade result dict
                    │
            run_backtest()
                    │
             summary + equity curve
                    │
           PerformanceEvaluator
           (Sharpe, Calmar, MaxDD)
```

Results are saved automatically to `results/backtest_<timestamp>.json`.

---

## Backtest Results

**Dataset:** NDX 1-min bars, 2024-01-02 → 2026-04-24 (resampled to 5-min)  
**Capital:** $100,000 starting equity

| Strategy | Trades | WR | Total P&L | P&L/wk | Sharpe | MaxDD% | WorstWk |
|---|---|---|---|---|---|---|---|
| **no_gate** | 577 | 65.3% | **+327.7%** | +2.71% | 3.47 | 20.9% | -12.88% |
| **high_gate** | 353 | **73.1%** | +133.3% | +1.14% | **3.48** | **8.7%** | -7.24% |
| **gated** | 472 | 67.8% | +155.9% | +1.31% | 3.15 | 10.3% | -7.81% |
| low_credit | 313 | 70.0% | +85.7% | +0.79% | 2.76 | 12.7% | -6.66% |
| mean_reversion | 364 | 34.1% | -23.0% | -0.20% | -0.89 | 25.6% | -5.12% |

**Recommendation:**
- **`high_gate`** (gate score ≥ 4): best risk-adjusted return — Sharpe 3.48, WR 73%, max drawdown only 8.7%
- **`no_gate`**: highest raw return (+327%) but wider drawdown and worst-week (-12.88%)
- **`gated`**: balanced middle ground for daily trading

---

## Risk Controls

| Control | Setting | Rationale |
|---|---|---|
| Daily loss limit | `$15,000` | Hard halt; configurable in `settings.py` |
| Circuit breaker | 3 consecutive losses → stop for day | Prevents revenge trading |
| Size reduction | 1 contract after 2 consecutive losses | Capital preservation |
| Scale-in cap | 2 adds maximum | Prevents −$58K days (observed in real trades) |
| Macro override | Skip Fed/CPI/tariff/earnings days | 8% WR on event days historically |
| EDT block | Skip entries after 14:45 | 8% WR, −$7,659 avg on overnight positions |
| Trending block | Skip if day_range > 250 pt | Directional moves break mean-reversion edge |
| 100-pt rule | Never add if NDX 100+ pt past short strike | Exit instead |

---

## Daily Workflow

```
09:30  Session starts
         └── Check for overnight EDT positions; force-close if present

10:00  Prime window opens
         └── Evaluate gate every 60s
             ├── Gate score < 3 → wait / skip
             ├── Hard override triggered → skip day
             └── Gate ≥ 3 + Q-Score ≥ 45 → ENTER

10:00–14:30  Position monitoring (every 30s)
               ├── Profit target hit (spread ≤ 25% credit) → close
               ├── Loss stop hit (spread ≥ 2× credit) → close
               ├── NDX through short strike → close
               └── Scale-in check (if NDX dips ≥ 30pt from entry)

14:30  Time exit — close any open position

16:00  EOD report written to logs/session_YYYY-MM-DD.{json,txt}
```

---

## Data Sources

| Source | Usage |
|---|---|
| `ndx_spy_historical_data/ndx_1min.csv` | Primary backtest data (NDX, 2024–2026, PT timestamps) |
| `ndx_spy_historical_data/spx_1min.csv` | SPX backtest data (2024–2026) |
| `ndx_spy_historical_data/ndx_1hour.csv` | NDX hourly bars for regime analysis |
| `ndx_spy_historical_data/spx_1hour.csv` | SPX hourly bars |
| TradingView MCP server | Live 1-min / 5-min NDX bars + real-time quote |
| IBKR TWS / Gateway | Option chain quotes, order placement, position management |

Rebuild the CSV files from source zips:
```bash
python3 ndx_spy_historical_data/build_csvs.py
```

---

## Security

**Never commit:**
- `ndx_options/.env` — IBKR credentials and account numbers
- `ndx_options/logs/` — session logs may contain P&L and account info
- `ndx_spy_historical_data/*.csv` — consider gitignoring large CSV files

**`.gitignore` entries to add:**
```
ndx_options/.env
ndx_options/logs/
ndx_options/results/
```

**Before going live:**
1. Run in dry-run mode for ≥ 5 sessions to verify gate + sizing logic
2. Paper trade for ≥ 2 weeks; verify fills match backtest assumptions
3. Set `IBKR_ACCOUNT` explicitly — never rely on default managed account in production
4. Confirm `IBKR_LIVE_PORT=7496` is TWS live (not paper) before typing `YES`
