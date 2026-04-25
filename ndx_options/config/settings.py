"""
All constants derived from ndx-spread-analysis.md (backtest of 159 real trades, Jan–Apr 2026).
Never hardcode these inline — import from here so changes propagate everywhere.
"""

from datetime import time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# ── Underlying ──────────────────────────────────────────────────────────────
SYMBOL          = "NDX"
NDX_MULTIPLIER  = 100          # $100 per index point (CBOE spec)
SPREAD_WIDTH    = 50           # standard NDX strike increment

# ── Session windows ─────────────────────────────────────────────────────────
PRIME_START     = time(10, 0)
PRIME_END       = time(10, 30)
SECONDARY_END   = time(12, 0)  # 50% size
TERTIARY_END    = time(15, 0)  # 1-contract only
EDT_START       = time(14, 45) # after here + next-day expiry = EDT
MARKET_OPEN     = time(9, 30)
MARKET_CLOSE    = time(16, 0)
TIME_EXIT_ET    = time(14, 30) # mandatory position close

# ── Gate thresholds (from backtest) ─────────────────────────────────────────
MAX_FLAT_MOM    = 10.0         # ±10pt 30-min momentum for "flat"
MIN_RANGE_PCT   = 0.80         # top 20% = range_pct ≥ 0.80
MAX_TRENDING_MULT = 2.5        # day_range > 2.5 × avg_bar → trending
MAX_DAY_RANGE   = 250.0        # hard skip if range > 250pt before noon
GATE_MIN_PROCEED = 3           # gate score ≥ 3 to trade
GATE_MIN_WATCH  = 2            # gate score = 2: trade at 50% size

# ── Q-Score thresholds ───────────────────────────────────────────────────────
QSCORE_HIGH     = 65           # full size
QSCORE_ACCEPT   = 45           # 50% size
# < 45 → do not trade

# ── Strike selection ─────────────────────────────────────────────────────────
MIN_OTM_DIST    = 100          # min 100pt OTM for short strike (41% WR sweet spot)
MAX_OTM_DIST    = 150          # max 150pt OTM

# ── Credit range ─────────────────────────────────────────────────────────────
MIN_CREDIT_PTS  = 5.0          # < 5pt credit → skip (IV crushed / too far OTM)
MAX_CREDIT_PTS  = 20.0         # > 20pt credit → strikes too close, widen

# ── Position sizing ──────────────────────────────────────────────────────────
BASE_CONTRACTS  = 3
MIN_CONTRACTS   = 1            # after 2 consecutive losses
MAX_SCALE_INS   = 2            # hard cap: 2 adds max
SCALE_IN_DROP   = 30           # add if NDX dips Xpt from entry
MAX_100PT_RULE  = 100          # if NDX already 100pt past short strike → do not add, exit

# ── Exit rules ───────────────────────────────────────────────────────────────
PROFIT_TARGET_PCT  = 0.25      # close when spread = 25% of credit (75% profit)
LOSS_STOP_MULT     = 2.0       # close when spread = 2× initial credit
TIME_STOP_HOURS    = 4.0       # if open > 4h and P&L < -50% credit → close
OVERNIGHT_CLOSE_ET = time(9, 45)  # EDT positions not closed by 9:45 → force close

# ── Regime / risk circuit breakers ──────────────────────────────────────────
MAX_DAILY_LOSS_USD = 15_000    # hard daily loss limit — halt trading
MAX_CONSECUTIVE_LOSSES = 2     # after N losses → reduce to MIN_CONTRACTS
CIRCUIT_BREAKER_LOSSES = 3     # after N losses → stop trading for the day

# ── Black-Scholes defaults ───────────────────────────────────────────────────
BS_RISK_FREE       = 0.045     # 4.5% risk-free rate
BS_DEFAULT_SIGMA   = 0.25      # fallback IV if unable to compute
ANNUAL_BARS_5MIN   = 252 * 78  # 5-min bars per trading year

# ── IBKR connectivity ────────────────────────────────────────────────────────
IBKR_HOST         = "127.0.0.1"
IBKR_PAPER_PORT   = 7497
IBKR_LIVE_PORT    = 7496
IBKR_CLIENT_ID    = 10

# ── TradingView MCP ──────────────────────────────────────────────────────────
TV_MCP_BASE_URL   = "http://localhost:3100"  # default tradingview-claude MCP server
TV_BARS_LOOKBACK  = 40                       # bars to fetch for gate evaluation
TV_TIMEFRAME      = "1"                      # 1-min bars for live monitoring

# ── Paths ────────────────────────────────────────────────────────────────────
import os
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOG_DIR           = os.path.join(_HERE, "logs")
BACKTEST_DATA     = os.path.join(_HERE, "..", "trading_logs", "NDX_5min_2026.json")
TRADES_JSON       = os.path.join(_HERE, "..", "trading_logs", "trades.json")
