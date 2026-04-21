---
name: ndx-spread-analysis
description: Analyze live NDX chart for vertical spread trade setups. Uses backtest-derived rules from 159 real spread trades (Jan–Apr 2026). Triggers on "analyze NDX", "check NDX for entry", "NDX spread setup", "EDT setup", "check entry/exit", "spread trade", "NDX analysis".
allowed-tools: mcp__tradingview__chart_get_state, mcp__tradingview__quote_get, mcp__tradingview__data_get_ohlcv, mcp__tradingview__chart_set_symbol, mcp__tradingview__chart_set_timeframe, mcp__tradingview__capture_screenshot, mcp__tradingview__chart_scroll_to_date, mcp__tradingview__data_get_study_values
---

# NDX Vertical Spread Analysis

Backtest-driven skill for live NDX spread entry analysis. All rules are derived from 159 real spread trades across two accounts (Jan–Apr 2026). The strategy is NDX 0DTE vertical credit spreads; the only direction with positive expected value is the **Bear Put**. All other directions (Bull Put, Bear Call, Bull Call) have negative EV in the observed regime.

---

## What the Backtest Proved (read this first)

| Finding | Data |
|---------|------|
| Only Bear Put has positive EV | +$1,836/trade vs −$1,915 to −$27,564 for others |
| Prime entry window is 10:00–10:30 ET | 64% WR, +$6,426 avg — only profitable bucket |
| 0DTE far better than 1DTE/EDT | 35% WR / −$358 avg vs 17% / −$6,241 avg |
| Flat 30-min momentum at entry | 38% WR, +$2,954 avg — best condition |
| Short strike 100–150pt OTM optimal | 41% WR — closer strikes get run over |
| NDX in top 20% of intraday range | 37% WR / −$104 avg — best range position |
| 5+ scale-ins = catastrophe | −$7,011 avg; all worst days had 4–7 adds |
| EDT (overnight) = 8% WR | −$8,851 avg; 46% of all losses from 8% of trades |
| Trending regime (range > 2.5× avg bar) | Every catastrophic loss day was TRENDING |

---

## Strategy Mechanics

### The Only Viable Setup: Bear Put Spread

**Structure**: Short higher-strike put + Long lower-strike put, same 0DTE expiry  
**Width**: $50 (standard NDX increment)  
**Thesis**: NDX has moved up intraday into the top portion of its range, sell premium above with a put spread expecting the level to hold through expiry  
**Profit**: NDX stays above the short put at close; spread expires worthless, keep full credit  
**Max loss**: ($50 × 100) − credit received = ~$4,500–$4,800 per contract at typical credits  

**Example at NDX 21,000**:  
`Short 20,850P / Long 20,800P — today's expiry (0DTE)`  
NDX is 150pt above short strike; NDX needs to fall 150pt by close to threaten the position.

### Why Other Directions Fail in This Regime

| Direction | EV/trade | Why it fails |
|-----------|----------|--------------|
| Bull Put  | −$11,106 | "Fade the dip" — every dip in a downtrend is a continuation |
| Bear Call | −$27,564 | "Fade the rally" — sharp rallies in bear markets keep running |
| Bull Call | −$1,915  | Collected premium but NDX reversed through strikes repeatedly |

These are not entirely prohibited — occasionally correct — but have negative expected value. Use only when explicitly indicated (see conditional exceptions below).

### Expiry Selection

**Always prefer 0DTE** over 1DTE. 0DTE (35% WR, −$358 avg) vs 1DTE (17% WR, −$6,241 avg).  

**EDT (Expiration Day Trading) — avoid unless regime is confirmed range-bound**:  
- Definition: enter after 14:45 ET, expiry is the next calendar day  
- Historical result: 1/13 winners, net −$115,066 across 13 trades  
- The Mar 12 EDT alone: −$41,556 (Bull Put entered 15:55, NDX gapped through both strikes)  
- EDT only works when overnight volatility is low and no macro events are pending

### Position Sizing

- Start size: 2–3 contracts  
- Scale-in: maximum 2 adds at $50 lower strikes (hard cap, never 3+)  
- Hard rule: **if NDX has already moved 100pt past short strike, do not add** — exit instead  
- Reduce to 1 contract after 2 consecutive loss days

---

## Pre-Analysis Gate: Go / No-Go

**Compute this before anything else. If AVOID, output AVOID and stop.**

```
1. Is current time between 10:00–10:30 ET?       → YES=+1  NO=0  (outside window: reduce priority)
2. Is 30-min NDX momentum flat (± 10pt)?          → YES=+1  NO=0
3. Is NDX in top 20% of today's running range?    → YES=+1  NO=0
4. Is day_range < 180pt OR not trending?          → YES=+1  NO=0 (trending = range > 2.5×avg_bar)
5. Is DTE = 0 (same-day expiry available)?        → YES=+1  NO=0

Score ≥ 3: PROCEED to setup construction
Score 2:   WATCH — conditions marginal, smaller size
Score ≤ 1: AVOID — do not enter today
```

Hard override to AVOID (regardless of score):
- Day range already >250pt before noon
- NDX moving directionally >50pt in the last 30 min with no reversal
- Known macro event today or overnight (Fed, CPI, tariff announcement, earnings)
- On a 2+ consecutive loss day streak with the same directional bias

---

## Entry Quality Score (Q-Score)

For each proposed setup, compute a Q-score 0–100 to communicate confidence:

| Criterion | +Points | −Points |
|-----------|---------|---------|
| Entry 30–60min after open (10:00–10:30) | +20 | |
| Entry <30min after open | | −10 |
| Entry >5h after open (EDT risk) | | −25 |
| 0DTE expiry | +15 | |
| EDT / overnight (1DTE after 14:45) | | −30 |
| Direction = Bear Put | +15 | |
| Direction = Bull Put | | −30 |
| Direction = Bear Call | | −20 |
| Short strike ≥100pt OTM | +10 | |
| Short strike <50pt OTM | | −15 |
| Trending regime (range > 2.5× avg bar) | | −20 |
| Non-trending / range-bound regime | +10 | |
| ≤2 planned scale-ins | +5 | |

**Score ≥ 65**: High quality — full size  
**Score 45–64**: Acceptable — reduced size (50%)  
**Score < 45**: Poor — do not trade

---

## Trade Rationale Framework

For each proposed setup, explicitly state the WHY using this structure:

```
DIRECTION: [Bear Put / Bull Put / Bear Call / Bull Call]
THESIS:    [1 sentence — what NDX must do for the trade to win]
CONTEXT:   [NDX price position + momentum at entry]
  - vs open: +/-Xpt (X% of range)
  - 30-min momentum: flat / rising Xpt / falling Xpt
  - range position: top/middle/bottom X% of intraday range
  - VWAP: above / below by Xpt
RISK:      [what would invalidate the thesis]
TRIGGER:   [specific price level or condition that triggers entry]
```

**Example — Bear Put at 10:12 ET with NDX at 21,080**:
```
DIRECTION: Bear Put
THESIS:    NDX holds above 20,900 through today's close; put spread expires worthless
CONTEXT:   NDX +180pt from open (top 22% of running range)
           30-min momentum: flat (+8pt) — consolidating after morning rally
           VWAP: +145pt above (strongly extended)
RISK:      Trend reversal if NDX breaks below 20,950 — close immediately
TRIGGER:   Current: NDX 21,080. Sell 20,950P / Buy 20,900P (0DTE) on next 5-min close above 21,050
```

---

## Session Phase Guide

| Phase | ET Window | Action | Backtest Edge |
|-------|-----------|--------|---------------|
| Pre-open | <9:30 | Wait; watch futures | — |
| Opening range | 9:30–10:00 | Observe only; identify direction | 32% WR, −$4,608 avg |
| **★ Prime window** | **10:00–10:30** | **Primary entry zone** | **64% WR, +$6,426 avg** |
| Mid-morning | 10:30–12:00 | Secondary entries; 50% size | 30% WR, −$1,230 avg |
| Lunch | 12:00–14:00 | Avoid new entries | 28% WR, −$2,523 avg |
| Afternoon | 14:00–15:00 | Tertiary only; 1-contract size | 33% WR, −$1,093 avg |
| EDT window | 15:00–16:00 | Avoid unless explicitly range-confirmed | 8% WR, −$7,659 avg |

---

## Setup Construction (Bear Put)

When the Go/No-Go gate says PROCEED:

**Step 1 — Confirm NDX position**
- NDX must be in top 20% of today's running range  
- If not: wait for a test of session high, or look for secondary setup

**Step 2 — Strike selection**
- Short put: round $50 level **100–150pt below current spot**  
  (closer than 100pt = 20% WR historically; farther than 150pt = less credit)
- Long put: exactly $50 below the short put (protection leg)
- Example: NDX at 21,080 → Short 20,950P / Long 20,900P

**Step 3 — Expiry**  
- 0DTE (same-day expiry) always preferred  
- If no 0DTE available (e.g., Monday), use Tuesday expiry but note elevated risk

**Step 4 — Credit check**
- Target credit: $8–15 per spread ($800–1,500 per contract at $50 width)  
- If credit < $5: strikes are too far OTM or IV is crushed — skip  
- If credit > $20: strikes may be dangerously close to current price — widen

**Step 5 — Scale-in plan**
- Initial: 2–3 contracts  
- Add 1: if NDX dips 30pt and holds — add 2 contracts at next $50 lower strike  
- Add 2 (max): if NDX dips another 30pt — add 1 contract  
- Hard stop: if NDX breaks through short strike, close entire position immediately

---

## Conditional Exceptions (Non-Bear-Put setups)

These have negative EV on average but may be warranted in specific conditions:

**Bull Call** (bearish premium collection — NOT Bull Put):  
- Only consider if NDX is strongly extended ABOVE VWAP after a trend day (already ran >200pt)  
- NDX must be in top 5% of multi-day range (near prior week's high)  
- Short call 100–150pt above current spot  
- Hard rule: **never use Bull Put** — 7% win rate, −$11K avg, no redeeming conditions

**Bear Call** (fade rally):  
- Historically 0% win rate in this dataset — do not use

**EDT (any direction)**:  
- Only if: VIX < 15, no macro events overnight, NDX in a clear range-bound regime for 3+ days  
- Default answer is NO; document the specific regime justification if used

---

## Exit Rules (Backtest-Derived)

**Target exit**: 3–6 hour hold is the sweet spot (43% WR vs 26% for <15min trades)  
- Close when spread has decayed to 25–30% of original credit received  
- Or close at 14:30–15:00 ET if entering in prime window — captures full-day theta

**Stop loss** (hard rules, no exceptions):
1. NDX breaks through short put strike — close immediately, no debate
2. Spread value reaches 2× initial credit — close immediately  
3. NDX moves >100pt against position within 30min of entry — close, reassess
4. Do NOT add contracts if any stop trigger is active — this is how −$58K days happen

**Scale-in stops**:
- Never add past 3 total scale-in events  
- If already at max adds and position is losing — close, do not hold to expiry hoping for recovery

**Time stops**:
- Any position open for >4 hours with P&L < −50% of credit: close  
- Any overnight (EDT) position not closed by 9:45 AM: close regardless of P&L

---

## Analysis Output Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NDX SPREAD ANALYSIS — [DATE]  [TIME ET]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MARKET SNAPSHOT
  Price:       [current]     VWAP: [vwap]   vs Open: [+/-pt (+/-]%)]
  Day range:   [low]–[high]  ([range]pt)    Running since open: [X bars]
  30-min mom:  [+/-Xpt]      Position:      [top/mid/bot X% of range]
  Regime:      [TRENDING / RANGE-BOUND]  ([range]pt vs [avg_bar]pt avg bar)

SESSION PHASE: [name]  →  [edge summary from table above]

━━━ GO / NO-GO GATE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [✓/✗] Prime window (10:00–10:30 ET)
  [✓/✗] Flat 30-min momentum (±10pt)
  [✓/✗] NDX top 20% of intraday range
  [✓/✗] Non-trending regime (range < 2.5× avg bar)
  [✓/✗] 0DTE expiry available

  Gate score: [X/5]   →   [PROCEED / WATCH / AVOID]

━━━ SETUP (if PROCEED or WATCH) ━━━━━━━━━━━━━━━━━━━━
  Direction:  Bear Put  [or stated exception + justification]
  Structure:  Short [strike]P / Long [strike]P  —  [expiry DDMMMYY]
  OTM dist:   [Xpt] from current price to short strike
  Entry at:   NDX [trigger level] on [condition]
  Initial:    [X] contracts

  Q-SCORE: [0–100]  ([grade: High/Acceptable/Poor])
  Criteria:
    [+/-] [each scored criterion from Q-Score table]

  TRADE RATIONALE:
    Thesis:   [one sentence]
    Context:  NDX [+/-]pt from open, [position in range], [momentum]
    Risk:     [invalidation condition]

  EXIT PLAN:
    Target:   Close at [X]% profit  (~[time] if held from entry)
    Stop:     Close if NDX breaks [strike level]  OR spread > 2× credit
    Max adds: [X] (hard cap at 2 re-entries)

━━━ RISK FLAGS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [✓/✗] Trending session (day range > 180pt) — AVOID or widen
  [✓/✗] Bull Put / Bear Call considered — negative EV, document reason
  [✓/✗] EDT setup — overnight gap risk, low-VIX only
  [✓/✗] 2+ consecutive loss days in same direction
  [✓/✗] Macro event today/overnight (Fed, CPI, tariff, earnings)
  [✓/✗] NDX near prior-week high/low or round-number level
```

---

## Execution Instructions

### Step 1 — Set up chart
```
chart_set_symbol("NDX")
chart_set_timeframe("5")
```

### Step 2 — Collect data (parallel)
```
quote_get()                         → current price, day OHLC
data_get_ohlcv(count=78)            → last 78 bars (full RTH on 5-min)
```

### Step 3 — Compute session metrics from the 78 bars
- `day_open` = bars[0].open
- `day_high` = max(bar.high for all bars)
- `day_low`  = min(bar.low for all bars)
- `day_range` = day_high − day_low
- `avg_bar_range` = mean(bar.high − bar.low for all bars)
- `trending` = day_range > 2.5 × avg_bar_range
- `vwap` = Σ(close × volume) / Σ(volume)
- `range_pos` = (current − day_low) / day_range
- `mom_30m` = current_close − close[6 bars ago]  (6 × 5min = 30min)
- `mins_since_open` = (current ET − 09:30) in minutes

### Step 4 — Run Go/No-Go gate
Score each of the 5 criteria → output gate result. If AVOID, stop here.

### Step 5 — Construct setup (if gate ≥ 2)
- Short strike = round down to nearest $50: `floor((current - 100) / 50) * 50`
- Long strike  = short strike − 50
- Expiry = today's date in DDMMMYY format (0DTE)

### Step 6 — Compute Q-score
Apply each criterion from the Q-Score table → sum to 0–100.

### Step 7 — Generate trade rationale
Using the Trade Rationale Framework above, fill in all five fields.

### Step 8 — Output formatted analysis block
Fill in the Analysis Output Format template exactly as shown.

### Step 9 — Screenshot
```
capture_screenshot(region="chart")
```

**Next-day expiry label format**: `NDX DDMMMYY [strike] [C/P]`  
Example: `NDX 21APR26 20950 P`

---

## Quick Reference Card

```
BEST SETUP:   Bear Put  ·  0DTE  ·  10:00–10:30 ET
              NDX top 20% range  ·  flat momentum  ·  100–150pt OTM

AVOID IF:     Day range >180pt & trending
              Bull Put (always)  ·  Bear Call (always)
              EDT unless VIX<15 & no macro
              5+ scale-ins under any circumstances

STOP RULES:   NDX breaks short strike  →  close immediately
              Spread = 2× credit       →  close immediately
              Max 2 adds               →  hard cap, no exceptions
```

---

## Backtesting Results (Jan–Apr 2026, 645 legs, 159 spreads, 2 accounts)

**Data**: `trading_logs/trades.json` + `trading_logs/NDX_5min_2026.json`  
**Charts**: `trading_logs/viz/YYYY-MM-DD.png` (1920×1080, one per trading day)  
**Accounts**: U23445314 (85 spreads, −$114K) and U24514532 (74 spreads, −$138K)

---

### 1. Overall Performance

| Period   | Spreads | Wins | Win Rate | Net P&L      |
|----------|---------|------|----------|--------------|
| Jan 2026 | 73      | 23   | 32%      | −$115,871    |
| Feb 2026 | 25      | 7    | 28%      | −$17,890     |
| Mar 2026 | 51      | 16   | 31%      | −$105,011    |
| Apr 2026 | 10      | 3    | 30%      | −$13,593     |
| **Total**| **159** | **49**| **31%** | **−$252,365**|

Both accounts stopped trading after mid-March 2026 (accounts blown). Win rate is consistent at ~31% across all months — this is a structural characteristic of the strategy, not a drawdown period artifact.

**Payoff asymmetry**: Winners average +$11,063; losers average −$7,356. Win/loss ratio = 1.50×. Despite a favorable payoff ratio, the 31% win rate yields negative expected value: `EV = 0.31 × $11,063 − 0.69 × $7,356 = −$1,637/trade`.

---

### 2. Direction Breakdown

| Spread Type | Trades | Win Rate | Avg Win | Avg Loss | EV/trade |
|-------------|--------|----------|---------|----------|----------|
| Bear Put    | 78     | 42%      | +$12,807| −$6,209  | **+$1,836** |
| Bull Call   | 62     | 24%      | +$5,608 | −$4,316  | −$1,915 |
| Bull Put    | 15     | 7%       | +$35,325| −$14,422 | −$11,106|
| Bear Call   | 4      | 0%       | —       | −$27,564 | −$27,564|

**Bear Put is the only direction with positive EV** (+$1,836/trade). It was the dominant strategy in Jan: short high-strike put, long protective put $50 lower — collects premium when NDX stays above the short put.

**Bull Put and Bear Call are account-killers**: Bull Put (15 trades, 7% WR) was used to "buy the dip" with spread protection. In a downtrending market, those dips kept going. Bear Call (4 trades, 0% WR) was used to fade sharp rallies — every rally continued.

---

### 3. DTE at Entry

The expiry is encoded as `DDMMMYY` (e.g., `03FEB26`). DTE = calendar days from trade date to expiry.

| DTE at Entry | Trades | Win Rate | Avg P&L   |
|--------------|--------|----------|-----------|
| 0DTE         | 119    | **35%**  | **−$358** |
| 1DTE         | 30     | 17%      | −$6,241   |
| 2DTE         | 2      | 0%       | −$15,250  |
| 3–4DTE       | 6      | 17%      | +$1,543   |

**0DTE is dramatically better than 1DTE** (35% vs 17% win rate, −$358 vs −$6,241 per trade). The 1DTE category is dominated by EDT setups — positions entered the afternoon before expiry — which carried overnight gap risk through the tariff-shock macro environment. Every 1DTE loss was significantly larger than 0DTE losses.

---

### 4. EDT (Expiration Day Trading) Deep Dive

EDT = entry after 14:45 ET, expiry the following calendar day (hold overnight, close at next morning's open).

**13 confirmed EDT trades — 1 winner — net P&L: −$115,066**

| Date       | Entry  | Direction  | Expiry   | P&L        | What Happened                            |
|------------|--------|------------|----------|------------|------------------------------------------|
| 2026-01-06 | 15:20  | Bear Put   | 07JAN26  | −$290      | Small, worked partially                  |
| 2026-01-15 | 15:54  | Bull Put   | 16JAN26  | −$2,500    | Overnight gap down                       |
| 2026-01-19 | 21:59  | Bull Put   | 20JAN26  | −$8,000    | After-hours, gapped below strikes        |
| 2026-01-20 | 15:46  | Bear Put   | 21JAN26  | −$3,250    | Continued drift                          |
| 2026-01-22 | 15:58  | Bull Put   | 23JAN26  | −$10,000   | Gap down at open wiped spread            |
| 2026-02-03 | 16:11  | Bull Put   | 04FEB26  | −$22,500   | **Largest single EDT loss**              |
| 2026-03-01 | 20:31  | Bear Put   | 02MAR26  | **+$600**  | Only EDT winner                          |
| 2026-03-04 | 14:56  | Bull Call  | 05MAR26  | −$1,000    | Overnight reversal                       |
| 2026-03-08 | 22:41  | Bull Put   | 09MAR26  | −$14,045   | Pre-market tariff news gapped below      |
| 2026-03-09 | 15:40  | Bear Call  | 10MAR26  | −$12,000   | Continued rally through short call       |
| 2026-03-12 | 15:55  | Bull Put   | 13MAR26  | −$41,556   | **Catastrophic — max loss hit**          |
| 2026-04-01 | 21:19  | Bull Call  | 02APR26  | −$525      | Small                                    |

The Mar 12 EDT trade alone (Bull Put, entered 15:55 for next-day expiry) lost −$41,556. The strategy was: sell a put spread near the close, collect overnight theta, exit at open. In a volatile macro environment, NDX gapped through both strikes repeatedly.

**EDT is viable only in low-VIX, range-bound regimes**. In Jan–Mar 2026, it was run as if volatility was stable. It was not.

---

### 5. Session Timing

**Minutes after 9:30 ET open:**

| Entry Window     | Trades | Win Rate | Avg P&L   |
|------------------|--------|----------|-----------|
| 0–30 min (open)  | 22     | 32%      | −$4,608   |
| **30–60 min**    | **11** | **64%**  | **+$6,426** |
| 60–120 min       | 23     | 30%      | −$1,230   |
| 120–180 min      | 17     | 29%      | +$1,748   |
| 180–300 min (lunch+)| 53  | 28%      | −$2,523   |
| 300+ min (late)  | 13     | 8%       | −$7,659   |

**The 30–60 minute window (10:00–10:30 ET) is the only clearly profitable entry window**: 64% win rate, +$6,426 average. The market has had time to establish direction and volume, opening extremes have been tested, and the position still has the rest of the day to decay.

Entries in the first 30 minutes catch volatile opens and often get swept. Lunch-hour and afternoon entries face thin liquidity and mean-reversion that has already played out.

**Session phases for analysis:**

| Phase          | Hours ET    | Trades | Win Rate | Notes                            |
|----------------|-------------|--------|----------|----------------------------------|
| Opening Range  | 9:30–10:00  | ~15    | ~27%     | Too volatile, wide spreads       |
| Prime Window   | 10:00–10:30 | 11     | 64%      | Best entry window                |
| Mid-Morning    | 10:30–12:00 | 24     | 28%      | Diminishing edge                 |
| Lunch Chop     | 12:00–14:00 | 53     | 28%      | Poor; no directional follow-through |
| Afternoon      | 14:00–15:00 | 12     | 33%      | Secondary window; smaller size   |
| EDT Window     | 15:00–16:00 | 13     | 8%       | Avoid in high-VIX environment    |

---

### 6. Intraday Momentum at Entry

Where was NDX trending in the 30 minutes before entry?

| 30-Min Momentum  | Trades | Win Rate | Avg P&L   |
|------------------|--------|----------|-----------|
| Falling hard >50pt | 31   | 26%      | −$3,187   |
| Falling 10–50pt  | 28     | 25%      | −$3,402   |
| **Flat ±10pt**   | **13** | **38%**  | **+$2,954** |
| Rising 10–50pt   | 28     | 25%      | −$2,949   |
| Rising hard >50pt| 20     | 40%      | +$3,295   |

**Flat momentum (±10pt in the prior 30 min) produces the best risk-adjusted entries**: 38% WR, +$2,954 average. This is the consolidation condition the strategy was designed for — NDX is digesting a move, not extending it.

Rising hard >50pt also produces good outcomes (40% WR) but the average is dragged by outlier wins. The directional entries during sharp rises are Bear Put setups that benefit when the rise reverses.

---

### 7. Strike OTM Distance at Entry

Distance from NDX spot to the short strike at time of entry:

| OTM Distance        | Trades | Win Rate | Avg P&L   |
|---------------------|--------|----------|-----------|
| 0–50pt OTM          | 33     | 30%      | −$3,581   |
| 50–100pt OTM        | 30     | 20%      | −$4,250   |
| **100–150pt OTM**   | **17** | **41%**  | **−$843** |
| 150–200pt OTM       | 4      | 25%      | −$3,337   |
| >200pt OTM          | 2      | 50%      | +$4,510   |

**100–150pt OTM is the optimal placement**: 41% win rate, minimal average loss. Going closer than 100pt provides higher credit but dramatically worse outcomes — the short strike gets tested in nearly every trending session.

Positioning 50–100pt OTM (the most common placement) is the worst bucket at 20% win rate. The traders systematically under-compensated for realized volatility.

---

### 8. Intraday Range Position at Entry

Where was NDX in the day's running range at the moment of entry?

| Position in Day Range | Trades | Win Rate | Avg P&L   | Dominant Bias        |
|-----------------------|--------|----------|-----------|----------------------|
| Bottom 20%            | 48     | 29%      | −$2,894   | Bear 29, Bull 19     |
| 20–40%                | 23     | 22%      | −$3,958   | Mixed                |
| Middle (40–60%)       | 11     | 27%      | −$1,959   | Bear 7, Bull 4       |
| 60–80%                | 16     | 31%      | −$425     | Bull 10, Bear 6      |
| **Top 20%**           | **41** | **37%**  | **−$104** | Bull 24, Bear 17     |

**Entering when NDX is near the top of its intraday range yields the best outcomes** (37% WR, near-zero avg loss). This is the Bear Put setup: sell a put spread after NDX has run up, expecting it to hold or drift higher.

Entering near the bottom (29% WR, −$2,894 avg) when trying to fade a dip with Bull Puts is the worst placement. The dip typically continued.

---

### 9. Scale-In (Averaging Down) Behavior

Number of distinct trade times per spread (add-ins during adverse moves):

| Add-ins | Trades | Win Rate | Avg P&L   | Interpretation                       |
|---------|--------|----------|-----------|--------------------------------------|
| 0       | 22     | 36%      | −$3,142   | Single entry, no adds                |
| 1       | 53     | **19%**  | −$894     | One add: worst win rate              |
| 2       | 14     | 50%      | +$2,285   | Two adds: works when mean-reversion occurs |
| 3       | 36     | 42%      | −$69      | Three adds: break-even territory     |
| 4       | 9      | 33%      | +$1,103   | Four adds: smaller sample            |
| 5+      | 25     | 24%      | −$7,011   | Deep averaging: catastrophic         |

**One add-in has the worst win rate (19%)**: this is the pattern of adding once into an adverse move and then either cutting or letting it expire. The single add increases cost basis without enough recovery.

**5+ add-ins produce the worst absolute losses** (−$7,011 avg): these are the "doubling down" trades on the worst days. Every catastrophic day (Jan 28–30, Mar 10–12) had 4–7 scale-ins.

**2–3 add-ins at ~$50 intervals can work** — but only when the market is genuinely mean-reverting. In a trending market, each add-in is an additional losing trade.

---

### 10. Consecutive Loss Streaks

Three major losing streaks accounted for −$365K (~144% of total loss, partially offset by winners):

**Streak 1: Jan 9–20 (8 days, −$68,021)**
- Starting with post-holiday NDX weakness, progressively larger losses
- Jan 20 single day: −$28,800 (NDX DOWN 326pt trending)
- Pattern: faded each dip with Bull Put, each dip continued

**Streak 2: Jan 26 – Feb 4 (7 days, −$148,334)**
- The worst streak — accounts near maximum drawdown
- Jan 30: −$58,079 (NDX DOWN 367pt, 6 scale-ins on bull calls and bear puts)
- Feb 3: −$6,806 on a −728pt NDX day (smaller because accounts were partly de-risked)
- Pattern: continued Bull Call and Bear Put sizing into a sustained downtrend; scale-in amplified every loss

**Streak 3: Mar 5–12 (7 days, −$148,480)**
- Tariff-announcement selloff — NDX DOWN 500+ pts over the period
- Mar 10: −$56,451 (Bear Call entered next-day + Bull Call fades)
- Mar 12: −$41,736 (EDT Bull Put entered prior afternoon gapped through strikes)
- Pattern: switched from pure Bear Put to also buying Bear Calls (betting on further decline while also fading dips — contradictory book)

**After Mar 13 (+$39,600)**: account sizes were effectively too small for normal position sizing. Trading continued in April at 1-contract sizes with minimal P&L impact.

---

### 11. Hold Time vs Outcome

| Hold Duration     | Trades | Win Rate | Avg P&L   |
|-------------------|--------|----------|-----------|
| <15 min           | 39     | 26%      | −$2,071   |
| 15–60 min         | 33     | 33%      | −$1,325   |
| 1–3 hours         | 48     | 25%      | −$1,545   |
| **3–6 hours**     | **35** | **43%**  | **−$209** |
| 6+ hours          | 4      | 25%      | −$11,601  |

**3–6 hour holds produce the best outcomes** (43% WR). This aligns with the 0DTE strategy: enter in the morning, let theta decay do its work through the RTH session, exit before close. The very quick trades (<15 min, 26% WR) are panic stops or fills on EDT setups that immediately went wrong.

---

### 12. Expiry Day of Week

| Expiry Weekday | Trades | Win Rate | Avg P&L   |
|----------------|--------|----------|-----------|
| **Monday**     | **27** | **33%**  | **+$131** |
| Tuesday        | 40     | 38%      | −$1,907   |
| Wednesday      | 31     | 23%      | −$3,251   |
| Thursday       | 31     | 32%      | −$1,035   |
| Friday         | 30     | 27%      | −$1,560   |

**Monday-expiry trades are roughly break-even** (avg +$131), the only near-neutral bucket. Monday expiries are typically opened on Friday or the previous Thursday — they benefit from weekend theta decay if the position survives over the weekend (rare in this dataset; most are same-day).

**Wednesday-expiry trades are the worst** (23% WR, −$3,251). This is partially driven by Mar 10–12 catastrophic losses on Wednesday-expiry spreads during the tariff selloff.

---

### 13. Size Escalation on Worst Days

Every catastrophic loss day had 4–7 scale-in add-ins:

| Date       | Net P&L     | Max Add-ins | NDX Regime            |
|------------|-------------|-------------|------------------------|
| 2026-01-30 | −$58,079    | 6           | DOWN 367pt TRENDING   |
| 2026-03-10 | −$56,451    | 7           | DOWN 318pt TRENDING   |
| 2026-03-12 | −$41,736    | 6           | DOWN 287pt TRENDING   |
| 2026-01-28 | −$32,860    | 5           | DOWN 190pt TRENDING   |
| 2026-03-11 | −$30,143    | 4           | DOWN 296pt TRENDING   |

**Without scale-ins, maximum single-trade loss on $50-wide spread (9 contracts) = ~$45,000**. With 5–7 scale-ins, actual losses reached 1.3–3× that maximum. Scale-in is the primary mechanism that converts a bad trade into a catastrophic one.

---

### 14. Market Regime Analysis

**Trending day identification**: `day_range > 2.5 × avg_5min_bar_range`

The NDX was in a persistent trending/high-volatility macro regime throughout Jan–Mar 2026 driven by tariff policy uncertainty. There were effectively zero quiet range-bound sessions during the study period. **The strategy was deployed in exactly the wrong environment**.

| Regime      | Days | Total P&L   | Avg P&L/day |
|-------------|------|-------------|-------------|
| Trending    | 53   | −$246,397   | −$4,649     |
| Range-bound | 0    | —           | —           |

A simple regime filter (skip if `day_range > 200pt at 11:00 ET`) would have prevented the three catastrophic loss streaks.

---

### 15. Strategy Rationale — Why Trades Were Made

Reconstructed from entry timing, strike placement, and market context:

**Bear Put entries** (78 trades, best EV): Entered after NDX moved up intraday. Thesis: NDX will stay above the short put at expiry. Intended as premium collection on a day expected to consolidate. Works when NDX is in the top 20% of its range and momentum is flat.

**Bull Call entries** (62 trades, second-most common): Entered when NDX was fading from highs, or when sellers were active. Thesis: NDX rally is overextended, will stay below short call. Repeatedly failed in trending-up sessions (Jan 23, Mar 13 reversed correctly; most others did not).

**Bull Put entries** (15 trades, worst EV at −$11K): Entered after sharp NDX drops, treating every selloff as a buying opportunity. Thesis: mean-reversion, NDX will recover above the short put. In Jan 2026 trending selloff, each "dip" was a continuation. Four of the five worst trades are Bull Puts.

**Bear Call entries** (4 trades, 0% WR): Entered after sharp NDX rallies. Thesis: overbought, will fade. All four failed — the rallies continued. Used exclusively in late Feb / early Mar (pattern change after Bull Put failures became evident).

**EDT rationale**: Observed that NDX often consolidated overnight, so premium from afternoon entry would decay by morning open. Works in stable regimes. Failed spectacularly in Jan–Mar 2026 due to overnight macro news gaps.

---

### 16. What a Refined Strategy Would Look Like

Based on the backtest, the following rules would have dramatically improved outcomes:

**Entry Rules (Hard Filters)**
1. Skip if current day range at entry time > 180pt AND trending (day_range > 2.5 × avg_bar_range)
2. Only enter Bear Put — no Bull Put, Bear Call, or Bull Call (positive EV direction only)
3. Entry window: 10:00–10:30 ET only (30–60 min after open)
4. 30-min momentum before entry must be flat (±10pt) — no directional momentum
5. NDX must be in top 20% of intraday range at entry (confirms Bear Put is appropriate)
6. Short strike ≥100pt OTM from current price
7. Never enter EDT in macro-uncertain environment (no 1DTE after 14:45)

**Position Management**
- Maximum 2 add-ins (never 3+) — stops scale-in spiral
- Hard stop: close if spread value doubles
- Hard stop: close if NDX breaks 100pt past short strike
- Target: close at 60–70% max profit

**Expected Improvement (theoretical)**  
Applying filters 1–3 alone would have eliminated most catastrophic days (Jan 28–30, Mar 10–12). Bear Put only with 10:00–10:30 ET entry and flat-momentum condition produces ~45–50% estimated win rate with similar average win size and smaller losses (no deep-averaging into losers).

---

### Backtesting — Usage in Live Analysis

When running `/ndx-spread-analysis`, apply these rules:

| Signal | Action |
|--------|--------|
| Day range >180pt AND trending at time of analysis | Skip all entries; flag as AVOID day |
| NDX in bottom 40% of intraday range | Avoid Bull Put; only Bull Call if bias warranted |
| NDX in top 20% of intraday range | Prefer Bear Put, 100–150pt OTM short strike |
| Time before 10:00 ET or after 11:00 ET | Reduce sizing; lower confidence window |
| 30-min momentum flat (±10pt) | Green light for entry |
| 30-min momentum directional (>30pt) | Wait for consolidation before entry |
| EDT setup (after 14:45 for next-day expiry) | Only in low-VIX, pre-confirmed range-bound regime |
| Current streak of 2+ loss days | Reduce size by 50%; skip marginally qualifying setups |
