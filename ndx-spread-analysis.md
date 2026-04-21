---
name: ndx-spread-analysis
description: Analyze live NDX chart for vertical spread trade setups using the observed trading strategy from Animus LLC accounts. Use when asked to analyze NDX for entries, exits, EDT setups, or spread trade ideas. Triggers on: "analyze NDX", "check NDX for entry", "NDX spread setup", "EDT setup", "check entry/exit", "spread trade".
allowed-tools: mcp__tradingview__chart_get_state, mcp__tradingview__quote_get, mcp__tradingview__data_get_ohlcv, mcp__tradingview__chart_set_symbol, mcp__tradingview__chart_set_timeframe, mcp__tradingview__capture_screenshot, mcp__tradingview__chart_scroll_to_date, mcp__tradingview__data_get_study_values
---

# NDX Vertical Spread Analysis

This skill analyzes live NDX price action and suggests spread trade setups based on the observed strategy from Animus LLC trading logs (Jan–Mar 2026, ~645 trades across two accounts).

---

## Strategy Mechanics (Observed from Trade Logs)

### Core Structure: NDX Vertical Credit Spreads (0–3 DTE)

**Bull Put Spread** (bullish bias):
- Long lower-strike put + Short higher-strike put, same expiry
- Standard spread width: $50 on NDX
- Entry: After bearish intraday move, expecting price to hold / recover
- Profit: NDX stays above short strike at expiry or closes spread for less than received
- Max loss: Spread width ($50 × 100) minus credit received

**Bear Call Spread** (bearish bias):
- Short lower-strike call + Long higher-strike call, same expiry
- Standard spread width: $50 on NDX
- Entry: After bullish intraday move, expecting price to reject / consolidate
- Profit: NDX stays below short strike at expiry or closes spread for less than received
- Max loss: Spread width ($50 × 100) minus credit received

### Expiration Selection
- **0DTE / 1DTE**: Most common — same-day or next-calendar-day expiry
- **EDT (Expiration Day Trading)**: Enter 3:00–4:00 PM the afternoon before expiry; close at or shortly after next day's 9:30 AM open. Captures overnight theta decay without holding through full RTH

### Position Sizing (observed)
- 1–9 contracts per leg
- Scale in: add contracts during adverse moves (averaging down on spread cost)
- Exit: close 50–80% of max profit, or cut at 100–150% of credit received

### Strike Placement
- Short strike: ~50–150 pts OTM from current spot
- Long strike: $50 further OTM (protection)
- On high-volatility days: strikes placed further OTM to avoid getting run over

### Risk Observations from Logs
- **Feb 3, 2026**: -$102K in one session — gap/trend move through both strikes
- **Mar 10–12, 2026**: -$113K over 3 days — sustained directional selloff (tariff-driven)
- **Key lesson**: The strategy bleeds on trending, high-VIX days; performs well on mean-reverting, range-bound sessions
- Both accounts effectively stopped trading after mid-March 2026 (accounts blown)

---

## Analysis Steps

### 1. Set Chart
- Symbol: NDX, Timeframe: 5 min
- Scroll to current date if needed

### 2. Read Current State

Collect from live chart:
- Current price and quote
- Day's OHLC and range (last 78 bars = full RTH session on 5-min)
- Intraday structure: direction, key levels, range size

### 3. Market Context Assessment

**Range calculation**:
- Day range = Day High − Day Low
- Tight range (<150 pts): low-volatility, credit spreads favorable
- Normal range (150–300 pts): standard setup
- Wide range (>300 pts): elevated risk, widen strikes or skip

**Session phase** (ET):
- 9:30–10:30: Opening range — observe, identify direction bias
- 10:30–12:00: Mid-morning — primary entry window for scalp spreads
- 12:00–14:00: Lunch chop — lower priority, smaller size
- 14:00–15:30: Afternoon trend / reversal — second entry window
- 15:00–16:00: EDT entry window — open next-day expiry spreads

**Intraday bias determination**:
- Compare current price vs. open: above = bullish, below = bearish
- Look at last 6 bars (30 min): is price making HH/HL or LH/LL?
- Day range position: price in top 30% = resistance bias, bottom 30% = support bias

### 4. Entry Setup Evaluation

**Bull Put Spread Entry Criteria**:
- Price is near session low or a prior support level
- Last 3–4 bars show slowing bearish momentum (smaller ranges, wicks below)
- NDX has sold off ≥100 pts from intraday high
- Entry: short strike ~50–75 pts below current price, long strike $50 below that
- Example at NDX 26,500: Short 26,450P / Long 26,400P (next-day expiry)

**Bear Call Spread Entry Criteria**:
- Price is near session high or a prior resistance level
- Last 3–4 bars show slowing bullish momentum (upper wicks, decreasing volume)
- NDX has rallied ≥100 pts from intraday low
- Entry: short strike ~50–75 pts above current price, long strike $50 above that
- Example at NDX 26,500: Short 26,550C / Long 26,600C (next-day expiry)

**EDT Entry Criteria** (3:00–4:00 PM):
- Price is consolidating or trending away from a key level
- Use next calendar day's expiry (0DTE at tomorrow's open)
- Short strike: 100–150 pts from current price in the direction of trend
- Close position between 9:30–10:00 AM next day before the market establishes direction

### 5. Exit Criteria

**Take profit**: 
- Spread has decayed to 20–30% of original credit → buy back for ~70–80% profit
- Or: NDX has moved 50+ pts in favorable direction within 30 min

**Stop loss**:
- Spread value doubles (cost basis 2× initial credit) → close immediately
- NDX breaks through short strike level → close immediately
- Do NOT average down if NDX is trending — the Feb/Mar blowups came from holding/adding into a trend

**Time stop**:
- Any position open for >3 hours with no profit → evaluate for exit
- Any overnight position not closed by 10:00 AM → close regardless of P&L

---

## Analysis Output Format

When running this skill, output the following:

```
NDX SPREAD ANALYSIS — [DATE] [TIME ET]

CURRENT PRICE: [price]
DAY RANGE: [low] – [high] ([range] pts)
VS OPEN: [+/- pts] ([+/- %])
SESSION PHASE: [Opening/Mid-Morning/Afternoon/EDT Window]

INTRADAY BIAS: [Bullish / Bearish / Neutral]
REASONING: [2–3 sentences on price structure, key levels, momentum]

RANGE REGIME: [Tight / Normal / Wide] — [implication for sizing]

--- SETUPS ---

BULL PUT SPREAD (if applicable):
  Trigger: [price level or condition to watch for]
  Structure: Short [strike]P / Long [strike]P — [expiry]
  Rationale: [why this level is support]
  Max risk: $[X] per contract | Ideal credit target: $[X]

BEAR CALL SPREAD (if applicable):
  Trigger: [price level or condition to watch for]
  Structure: Short [strike]C / Long [strike]C — [expiry]
  Rationale: [why this level is resistance]
  Max risk: $[X] per contract | Ideal credit target: $[X]

EDT SETUP (if 2:30 PM or later):
  Direction: [Bullish / Bearish]
  Structure: [strikes + tomorrow's expiry]
  Entry window: [time range]
  Close target: 9:30–10:00 AM tomorrow

RISK FLAGS:
  [ ] Wide range day (>300 pts) — reduce size
  [ ] Trending session — avoid fading
  [ ] News/macro event today or overnight — elevated gap risk
  [ ] Near major level (round number, prior week H/L)
```

---

## Execution Instructions

1. Call `chart_set_symbol` (NDX) and `chart_set_timeframe` (5) if not already set
2. Call `quote_get` and `data_get_ohlcv` (count=78, summary=false) in parallel
3. Compute day OHLC from bars (first bar open = day open, scan all bars for H/L)
4. Determine session phase from current timestamp (ET)
5. Assess intraday bias from last 12 bars (1 hour)
6. Calculate proposed strikes using round $50 increments from current price
7. Output the formatted analysis block above
8. Take screenshot for visual confirmation

**Next-day expiry label format**: `NDX DDMMMYY [strike] [C/P]`
(e.g., `NDX 21APR26 26550 C`)
