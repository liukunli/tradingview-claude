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
