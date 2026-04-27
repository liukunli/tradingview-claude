"""
signal_engine.py — Gate, Q-Score, BS pricing, strike selection, and bar metrics.
All pure computation (no I/O) — shared by backtest engine and live session.
"""

import math
import numpy as np
import pandas as pd
from datetime import time, datetime
from typing import Optional

from ..config.settings import (
    PRIME_START, PRIME_END, SECONDARY_END, EDT_START,
    MAX_FLAT_MOM, MIN_RANGE_PCT, MAX_TRENDING_MULT, MAX_DAY_RANGE,
    GATE_MIN_PROCEED, GATE_MIN_WATCH,
    QSCORE_HIGH, QSCORE_ACCEPT,
    MIN_OTM_DIST, MAX_OTM_DIST, SPREAD_WIDTH,
    MIN_CREDIT_PTS, MAX_CREDIT_PTS,
    BS_RISK_FREE, BS_DEFAULT_SIGMA, ANNUAL_BARS_5MIN,
)


# ── Bar metrics (pure computation, shared by backtest and live) ───────────────

def compute_bar_metrics(bars: pd.DataFrame, now_et=None) -> dict:
    """
    Compute gate-relevant metrics from an OHLCV bar DataFrame.
    Returns: price, day_range, avg_bar, trending, range_pct, mom_30, vwap, sigma
    """
    closes  = bars["close"].values
    log_ret = np.diff(np.log(np.maximum(closes, 1e-8)))
    sigma   = max(math.sqrt(np.var(log_ret) * ANNUAL_BARS_5MIN), 0.12) \
              if len(log_ret) > 2 else BS_DEFAULT_SIGMA

    day_high  = float(bars["high"].max())
    day_low   = float(bars["low"].min())
    day_range = day_high - day_low
    avg_bar   = float((bars["high"] - bars["low"]).mean())
    trending  = bool(day_range > 2.5 * avg_bar) if avg_bar > 0 else False

    price     = float(bars.iloc[-1]["close"])
    range_pct = (price - day_low) / day_range if day_range > 0 else 0.5

    mom_idx = max(len(bars) - 7, 0)
    mom_30  = price - float(bars.iloc[mom_idx]["close"])

    vol  = float(bars["volume"].sum())
    vwap = float((bars["close"] * bars["volume"]).sum() / vol) if vol > 0 else price

    return dict(
        price=price, day_high=day_high, day_low=day_low,
        day_range=day_range, avg_bar=avg_bar, trending=trending,
        range_pct=range_pct, mom_30=mom_30, vwap=vwap, sigma=sigma,
    )


# ── Black-Scholes ─────────────────────────────────────────────────────────────

def _norm_cdf(x: float) -> float:
    """Abramowitz & Stegun approximation, avoids scipy dependency."""
    a = (1 + 0.2316419 * abs(x))
    t = 1.0 / a
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937
           + t * (-1.821255978 + t * 1.330274429))))
    pdf = math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)
    cdf = 1 - pdf * poly
    return cdf if x >= 0 else 1 - cdf


def bs_put(S: float, K: float, T: float,
           r: float = BS_RISK_FREE, sigma: float = BS_DEFAULT_SIGMA) -> float:
    """Black-Scholes European put price."""
    if T <= 1e-8:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * _norm_cdf(-d1)


def spread_value_pts(S: float, short_K: float, long_K: float,
                     bars_remaining: int, sigma: float) -> float:
    T = bars_remaining / ANNUAL_BARS_5MIN
    val = bs_put(S, short_K, T, sigma=sigma) - bs_put(S, long_K, T, sigma=sigma)
    return max(min(val, SPREAD_WIDTH), 0.0)


# ── Gate evaluation ───────────────────────────────────────────────────────────

def evaluate_gate(m: dict, now_et: time) -> tuple[int, dict]:
    """
    5-criterion Go/No-Go gate from ndx-spread-analysis.md.
    Returns (score, detail_dict).
    """
    details = {
        "prime_window":  PRIME_START <= now_et <= PRIME_END,
        "flat_momentum": abs(m["mom_30"]) <= MAX_FLAT_MOM,
        "top_20_range":  m["range_pct"] >= MIN_RANGE_PCT,
        "calm_regime":   (m["day_range"] < 180) or (not m["trending"]),
        "dte0":          True,   # assume 0DTE available; caller sets to False if not
    }
    return sum(details.values()), details


def hard_override_avoid(m: dict, now_et: time,
                        macro_event: bool = False,
                        consecutive_losses: int = 0,
                        same_direction_bias: bool = False) -> Optional[str]:
    """
    Returns a string reason if a hard AVOID override applies, else None.
    These block trading regardless of gate score.
    """
    if m["day_range"] > MAX_DAY_RANGE:
        return f"day_range={m['day_range']:.0f}pt > {MAX_DAY_RANGE}pt hard limit"
    if abs(m["mom_30"]) > 50:
        return f"directional momentum {m['mom_30']:+.0f}pt > 50pt (trending move)"
    if macro_event:
        return "macro event flagged (Fed/CPI/tariff/earnings)"
    if consecutive_losses >= 2 and same_direction_bias:
        return f"{consecutive_losses} consecutive losses with same directional bias"
    return None


def gate_action(score: int) -> str:
    if score >= GATE_MIN_PROCEED:
        return "PROCEED"
    if score == GATE_MIN_WATCH:
        return "WATCH"
    return "AVOID"


# ── Strike selection ──────────────────────────────────────────────────────────

def select_strikes(price: float) -> tuple[float, float]:
    """
    Formula from ndx-spread-analysis.md:
      short_K = floor((price - 100) / 50) * 50
      long_K  = short_K - 50
    """
    short_K = math.floor((price - 100) / 50) * 50
    long_K  = short_K - SPREAD_WIDTH
    return short_K, long_K


def otm_distance(price: float, short_K: float) -> float:
    return price - short_K


# ── Q-Score computation ───────────────────────────────────────────────────────

def compute_qscore(m: dict, now_et: time,
                   direction: str = "Bear Put",
                   short_K: Optional[float] = None,
                   is_0dte: bool = True,
                   planned_scale_ins: int = 0) -> tuple[int, list[str]]:
    """
    Compute Q-Score 0–100 per ndx-spread-analysis.md table.
    Returns (score, list_of_criterion_lines).
    """
    score = 0
    criteria = []

    # Timing
    mins_after_open = (datetime.combine(datetime.today(), now_et)
                       - datetime.combine(datetime.today(), time(9, 30))).seconds // 60

    if PRIME_START <= now_et <= PRIME_END:
        score += 20
        criteria.append("+20  Prime window (10:00–10:30 ET)")
    elif mins_after_open < 30:
        score -= 10
        criteria.append("-10  Entry <30min after open")
    elif now_et >= EDT_START:
        score -= 25
        criteria.append("-25  Entry >5h after open (EDT risk)")

    # Expiry
    if is_0dte:
        score += 15
        criteria.append("+15  0DTE expiry")
    else:
        score -= 30
        criteria.append("-30  EDT / overnight (1DTE after 14:45)")

    # Direction
    if direction == "Bear Put":
        score += 15
        criteria.append("+15  Direction = Bear Put")
    elif direction == "Bull Put":
        score -= 30
        criteria.append("-30  Direction = Bull Put (historically −$11K avg)")
    elif direction == "Bear Call":
        score -= 20
        criteria.append("-20  Direction = Bear Call (0% WR historically)")

    # OTM distance
    if short_K is not None:
        otm = otm_distance(m["price"], short_K)
        if otm >= 100:
            score += 10
            criteria.append(f"+10  Short strike ≥100pt OTM ({otm:.0f}pt)")
        elif otm < 50:
            score -= 15
            criteria.append(f"-15  Short strike <50pt OTM ({otm:.0f}pt — dangerous)")

    # Regime
    if m["trending"]:
        score -= 20
        criteria.append(f"-20  Trending regime (range={m['day_range']:.0f}pt > 2.5×avg_bar)")
    else:
        score += 10
        criteria.append("+10  Non-trending / range-bound regime")

    # Scale-in plan
    if planned_scale_ins <= 2:
        score += 5
        criteria.append(f"+5   ≤2 planned scale-ins ({planned_scale_ins})")

    return max(0, min(score, 100)), criteria


def qscore_grade(score: int) -> str:
    if score >= QSCORE_HIGH:
        return "High"
    if score >= QSCORE_ACCEPT:
        return "Acceptable"
    return "Poor"


def size_from_qscore(base_contracts: int, score: int, gate_score: int) -> int:
    """
    Adjust contract count based on Q-Score and gate score.
    - Watch (gate=2): halve size
    - Poor Q-Score: don't trade (return 0)
    - Acceptable Q-Score: 50% size
    - High Q-Score: full size
    """
    if score < QSCORE_ACCEPT:
        return 0
    n = base_contracts
    if score < QSCORE_HIGH:
        n = max(1, n // 2)
    if gate_score == GATE_MIN_WATCH:
        n = max(1, n // 2)
    return n


# ── Session phase ─────────────────────────────────────────────────────────────

def session_phase(now_et: time) -> tuple[str, str]:
    """Returns (phase_name, edge_summary)."""
    if now_et < time(9, 30):
        return "Pre-open", "Wait; watch futures"
    if now_et < PRIME_START:
        return "Opening range", "32% WR, −$4,608 avg — OBSERVE ONLY"
    if now_et <= PRIME_END:
        return "Prime window ★", "64% WR, +$6,426 avg — PRIMARY ENTRY"
    if now_et < time(12, 0):
        return "Mid-morning", "30% WR, −$1,230 avg — 50% size only"
    if now_et < time(14, 0):
        return "Lunch", "28% WR, −$2,523 avg — AVOID new entries"
    if now_et < time(15, 0):
        return "Afternoon", "33% WR, −$1,093 avg — 1-contract only"
    return "EDT window", "8% WR, −$7,659 avg — AVOID unless range-confirmed"


# ── Full analysis output ──────────────────────────────────────────────────────

def format_analysis(m: dict, now_et: time, gate_score: int, gate_details: dict,
                    short_K: float, long_K: float, q_score: int,
                    q_criteria: list[str], credit_est: float,
                    action: str, avoid_reason: Optional[str] = None) -> str:
    """Render the full Analysis Output Format from ndx-spread-analysis.md."""
    phase, phase_edge = session_phase(now_et)
    otm = otm_distance(m["price"], short_K)
    expiry_label = "0DTE (today)"
    vs_open_pct  = (m["price"] - m["day_low"]) / m["day_range"] * 100 if m["day_range"] > 0 else 50

    def tick(v): return "✓" if v else "✗"

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"NDX SPREAD ANALYSIS — {now_et.strftime('%H:%M ET')}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "MARKET SNAPSHOT",
        f"  Price:      {m['price']:.1f}     VWAP: {m['vwap']:.1f}   "
        f"vs Low: +{m['price'] - m['day_low']:.0f}pt ({vs_open_pct:.0f}% of range)",
        f"  Day range:  {m['day_low']:.0f}–{m['day_high']:.0f}  "
        f"({m['day_range']:.0f}pt)",
        f"  30-min mom: {m['mom_30']:+.0f}pt    "
        f"Regime: {'TRENDING' if m['trending'] else 'RANGE-BOUND'}  "
        f"({m['day_range']:.0f}pt vs {m['avg_bar']:.0f}pt avg bar × 2.5 = "
        f"{m['avg_bar'] * 2.5:.0f}pt)",
        "",
        f"SESSION PHASE: {phase}  →  {phase_edge}",
        "",
        "━━━ GO / NO-GO GATE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  [{tick(gate_details['prime_window'])}] Prime window (10:00–10:30 ET)",
        f"  [{tick(gate_details['flat_momentum'])}] Flat 30-min momentum (±10pt)  "
        f"[actual: {m['mom_30']:+.0f}pt]",
        f"  [{tick(gate_details['top_20_range'])}] NDX top 20% of intraday range  "
        f"[actual: {m['range_pct']:.0%}]",
        f"  [{tick(gate_details['calm_regime'])}] Non-trending regime",
        f"  [{tick(gate_details['dte0'])}] 0DTE expiry available",
        f"",
        f"  Gate score: {gate_score}/5   →   {action}",
    ]

    if avoid_reason:
        lines += ["", f"  HARD OVERRIDE: {avoid_reason}"]
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    if action == "AVOID":
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

    q_grade = qscore_grade(q_score)
    lines += [
        "",
        "━━━ SETUP ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  Direction:  Bear Put",
        f"  Structure:  Short {short_K:.0f}P / Long {long_K:.0f}P  —  {expiry_label}",
        f"  OTM dist:   {otm:.0f}pt from current price to short strike",
        f"  Credit est: {credit_est:.1f}pt  (${credit_est * 100:.0f}/contract)",
        "",
        f"  Q-SCORE: {q_score}  ({q_grade})",
        "  Criteria:",
    ]
    for c in q_criteria:
        lines.append(f"    {c}")

    lines += [
        "",
        "  TRADE RATIONALE:",
        f"    Thesis:  NDX holds above {short_K:.0f} through today's close; spread expires worthless",
        f"    Context: NDX {m['price']:.0f}, {m['range_pct']:.0%} of intraday range, "
        f"mom={m['mom_30']:+.0f}pt",
        f"    Risk:    Trend reversal if NDX breaks below {short_K + 50:.0f} — close immediately",
        "",
        "  EXIT PLAN:",
        f"    Target:  Close at 75% profit (spread ≤ {credit_est * 0.25:.1f}pt)",
        f"    Stop:    NDX breaks {short_K:.0f}  OR spread ≥ {credit_est * 2:.1f}pt",
        f"    Time:    Close at 14:30 ET if still open",
        "    Max adds: 2 (hard cap)",
        "",
        "━━━ RISK FLAGS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"  [{tick(m['day_range'] > 180)}] Trending session (day range > 180pt)",
        f"  [✗] Bull Put / Bear Call considered",
        f"  [✗] EDT setup",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(lines)
