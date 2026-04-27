"""
daily_report.py — EOD P&L summary + audit trail.

Writes a structured JSON log and a human-readable summary to trading_logs/.
Mirrors institutional post-trade reporting: every exit reason, every scale-in,
every gate evaluation logged with timestamps.
"""

import json
import logging
import os
from datetime import date, datetime
from typing import Optional

from ..config.settings import ET, LOG_DIR, NDX_MULTIPLIER

log = logging.getLogger("ndx.report")


class DailyReport:
    """Collects intraday events and writes EOD summary."""

    def __init__(self, trade_date: Optional[date] = None):
        self.trade_date = trade_date or date.today()
        self.events: list[dict] = []
        self.gate_evaluations: list[dict] = []
        self.trades: list[dict] = []
        self._start_time = datetime.now(tz=ET)

    # ── Event recording ───────────────────────────────────────────────────────

    def log_gate(self, gate_score: int, action: str, q_score: int,
                 m: dict, avoid_reason: Optional[str] = None):
        self.gate_evaluations.append({
            "time":         datetime.now(tz=ET).isoformat(),
            "gate_score":   gate_score,
            "q_score":      q_score,
            "action":       action,
            "avoid_reason": avoid_reason,
            "ndx_price":    round(m.get("price", 0), 1),
            "day_range":    round(m.get("day_range", 0), 1),
            "mom_30":       round(m.get("mom_30", 0), 1),
            "trending":     m.get("trending", False),
            "range_pct":    round(m.get("range_pct", 0), 4),
        })

    def log_entry(self, short_K: float, long_K: float, contracts: int,
                  credit_pts: float, ndx_price: float, scale_in: int = 0):
        event = {
            "type":       "entry" if scale_in == 0 else "scale_in",
            "time":       datetime.now(tz=ET).isoformat(),
            "short_K":    short_K,
            "long_K":     long_K,
            "contracts":  contracts,
            "credit_pts": round(credit_pts, 2),
            "ndx_price":  round(ndx_price, 1),
            "scale_in_n": scale_in,
        }
        self.events.append(event)
        if scale_in == 0:
            self.trades.append({**event, "exits": []})

    def log_exit(self, close_val_pts: float, ndx_price: float,
                 reason: str, credit_pts: float, contracts: int):
        pnl_pts = credit_pts - close_val_pts
        pnl_usd = pnl_pts * NDX_MULTIPLIER * contracts
        event = {
            "type":          "exit",
            "time":          datetime.now(tz=ET).isoformat(),
            "close_val_pts": round(close_val_pts, 2),
            "pnl_pts":       round(pnl_pts, 2),
            "pnl_usd":       round(pnl_usd, 2),
            "ndx_price":     round(ndx_price, 1),
            "reason":        reason,
        }
        self.events.append(event)
        if self.trades:
            self.trades[-1]["exits"].append(event)

    # ── Summary generation ────────────────────────────────────────────────────

    def generate_summary(self, risk_status: dict) -> dict:
        entries = [e for e in self.events if e["type"] == "entry"]
        exits   = [e for e in self.events if e["type"] == "exit"]
        scale_ins = [e for e in self.events if e["type"] == "scale_in"]

        total_pnl   = sum(e["pnl_usd"] for e in exits)
        wins        = [e for e in exits if e["pnl_usd"] > 0]
        losses      = [e for e in exits if e["pnl_usd"] <= 0]
        win_rate    = len(wins) / len(exits) if exits else 0

        exit_reasons = {}
        for e in exits:
            exit_reasons[e["reason"]] = exit_reasons.get(e["reason"], 0) + 1

        summary = {
            "date":              str(self.trade_date),
            "session_start":     self._start_time.isoformat(),
            "session_end":       datetime.now(tz=ET).isoformat(),
            "gate_evaluations":  len(self.gate_evaluations),
            "gates_proceeded":   sum(1 for g in self.gate_evaluations if g["action"] != "AVOID"),
            "entries":           len(entries),
            "scale_ins":         len(scale_ins),
            "exits":             len(exits),
            "wins":              len(wins),
            "losses":            len(losses),
            "win_rate":          round(win_rate, 4),
            "total_pnl_usd":     round(total_pnl, 2),
            "avg_pnl_usd":       round(total_pnl / max(len(exits), 1), 2),
            "exit_reasons":      exit_reasons,
            "risk_status":       risk_status,
        }
        return summary

    def format_summary_text(self, summary: dict) -> str:
        lines = [
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"NDX TRADING SUMMARY — {summary['date']}",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"  Gate evaluations: {summary['gate_evaluations']}   "
            f"Proceeded: {summary['gates_proceeded']}",
            f"  Trades entered:   {summary['entries']}",
            f"  Scale-ins:        {summary['scale_ins']}",
            f"  Exits:            {summary['exits']}",
            f"  Wins / Losses:    {summary['wins']} / {summary['losses']}   "
            f"({summary['win_rate']:.0%} WR)",
            f"  Total P&L:        ${summary['total_pnl_usd']:>10,.2f}",
            f"  Avg P&L / trade:  ${summary['avg_pnl_usd']:>10,.2f}",
            "",
            "  Exit reasons:",
        ]
        for reason, count in summary["exit_reasons"].items():
            lines.append(f"    {reason:<25} {count}")

        risk = summary["risk_status"]
        lines += [
            "",
            f"  Consecutive losses: {risk['consecutive_losses']}",
            f"  Daily P&L:          ${risk['daily_pnl_usd']:,.2f}",
            f"  Halted:             {risk['halted']}",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        return "\n".join(lines)

    # ── File I/O ──────────────────────────────────────────────────────────────

    def save(self, risk_status: dict) -> tuple[str, str]:
        """Save JSON log and text summary. Returns (json_path, txt_path)."""
        os.makedirs(LOG_DIR, exist_ok=True)
        ds = str(self.trade_date)

        summary = self.generate_summary(risk_status)
        full_log = {
            "summary":         summary,
            "gate_evaluations": self.gate_evaluations,
            "events":          self.events,
        }

        json_path = os.path.join(LOG_DIR, f"session_{ds}.json")
        txt_path  = os.path.join(LOG_DIR, f"session_{ds}.txt")

        with open(json_path, "w") as f:
            json.dump(full_log, f, indent=2, default=str)

        text = self.format_summary_text(summary)
        with open(txt_path, "w") as f:
            f.write(text)

        log.info(f"Session log saved: {json_path}")
        log.info(text)
        return json_path, txt_path
