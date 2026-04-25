#!/usr/bin/env python3
"""
ndx_options/main.py — Daily trading session entry point.

Modes:
  trade     — live/paper trading session (default)
  backtest  — replay NDX_5min_2026.json through strategy
  report    — generate EOD summary from today's session log

Usage:
  python -m ndx_options.main                         # paper trade
  python -m ndx_options.main --live                  # REAL MONEY — requires YES confirmation
  python -m ndx_options.main --dry-run               # simulate without orders
  python -m ndx_options.main backtest                # run full backtest
  python -m ndx_options.main backtest --improve      # backtest + improvement proposals
  python -m ndx_options.main backtest --start 2026-01-12 --end 2026-04-17
  python -m ndx_options.main report                  # show today's session log
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import date, datetime

# ── Logging setup ─────────────────────────────────────────────────────────────
from .config.settings import ET, LOG_DIR

os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, f"live_{date.today()}.log")),
    ],
)
log = logging.getLogger("ndx.main")


# ── Trade mode ────────────────────────────────────────────────────────────────

async def run_trade(args):
    from .core.market_data import TradingViewClient
    from .core.order_manager import OrderManager
    from .core.risk_manager import RiskManager
    from .strategy.bear_put import BearPutSpread
    from .analysis.daily_report import DailyReport

    live    = args.live
    dry_run = args.dry_run or (not live)  # default safe: dry-run unless --live

    if live and not dry_run:
        log.warning("!!!! LIVE TRADING — REAL MONEY !!!!")
        confirm = input("Type YES to confirm live trading: ").strip()
        if confirm != "YES":
            print("Aborted.")
            return

    log.info(f"Mode: {'LIVE' if live else 'PAPER'}  dry_run={dry_run}")

    data_client  = TradingViewClient()
    risk_manager = RiskManager()
    report       = DailyReport()

    async with OrderManager(live=live, dry_run=dry_run) as om:
        strategy = BearPutSpread(
            order_manager=om,
            risk_manager=risk_manager,
            data_client=data_client,
            dry_run=dry_run,
            macro_event=args.macro_event,
        )
        final_status = await strategy.run_session()

    json_path, txt_path = report.save(final_status)
    log.info(f"Session complete. Log: {json_path}")

    # EOD backtest comparison
    if args.compare_backtest:
        log.info("Running EOD backtest comparison…")
        from .analysis.backtest import run_backtest, propose_improvements
        bt = run_backtest(verbose=False)
        if bt:
            s = bt["summary"]
            log.info(f"Backtest ({s['period']}): {s['trades']} trades, "
                     f"{s['win_rate']:.0%} WR, ${s['total_pnl']:,.0f}")
            proposals = propose_improvements(s, bt["trades"])
            for i, p in enumerate(proposals, 1):
                log.info(f"  Proposal {i}: {p}")


# ── Backtest mode ─────────────────────────────────────────────────────────────

def run_backtest_cli(args):
    from .analysis.backtest import run_backtest, propose_improvements

    results = run_backtest(
        start=args.start,
        end=args.end,
        data_path=args.data,
        verbose=args.verbose,
    )
    if not results:
        sys.exit(1)

    summary = results["summary"]
    trades  = results["trades"]

    print("\n" + "="*55)
    print("NDX BEAR PUT BACKTEST")
    print("="*55)
    for k, v in summary.items():
        if k != "exit_reasons":
            print(f"  {k:<28} {v}")
    print("\n  Exit breakdown:")
    for r, c in summary.get("exit_reasons", {}).items():
        print(f"    {r:<28} {c}")

    if args.improve or True:   # always show proposals
        print("\n" + "="*55)
        print("IMPROVEMENT PROPOSALS")
        print("="*55)
        for i, p in enumerate(propose_improvements(summary, trades), 1):
            print(f"\n{i}. {p}")


# ── Report mode ───────────────────────────────────────────────────────────────

def run_report(args):
    ds = args.date or str(date.today())
    json_path = os.path.join(LOG_DIR, f"session_{ds}.json")
    txt_path  = os.path.join(LOG_DIR, f"session_{ds}.txt")

    if os.path.exists(txt_path):
        with open(txt_path) as f:
            print(f.read())
    elif os.path.exists(json_path):
        with open(json_path) as f:
            data = json.load(f)
        print(json.dumps(data["summary"], indent=2))
    else:
        print(f"No session log found for {ds} at {LOG_DIR}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NDX Options Bot")
    sub = parser.add_subparsers(dest="mode")

    # trade (default)
    tp = sub.add_parser("trade", help="Run live/paper trading session")
    tp.add_argument("--live",             action="store_true")
    tp.add_argument("--dry-run",          action="store_true")
    tp.add_argument("--macro-event",      action="store_true",
                    help="Flag macro event today (Fed/CPI/tariff)")
    tp.add_argument("--compare-backtest", action="store_true",
                    help="Run backtest comparison after session")

    # backtest
    bp = sub.add_parser("backtest", help="Replay strategy against historical data")
    bp.add_argument("--start",   default=None, help="Start date YYYY-MM-DD")
    bp.add_argument("--end",     default=None, help="End date YYYY-MM-DD")
    bp.add_argument("--data",    default=None, help="Path to 5-min OHLCV JSON")
    bp.add_argument("--verbose", action="store_true")
    bp.add_argument("--improve", action="store_true", help="Show improvement proposals")

    # report
    rp = sub.add_parser("report", help="Show session P&L summary")
    rp.add_argument("--date", default=None, help="Date YYYY-MM-DD (default: today)")

    # parse — default to trade if no subcommand
    args = parser.parse_args()
    if args.mode is None:
        # inject trade defaults
        args.mode           = "trade"
        args.live           = False
        args.dry_run        = True
        args.macro_event    = False
        args.compare_backtest = False

    if args.mode == "trade":
        asyncio.run(run_trade(args))
    elif args.mode == "backtest":
        run_backtest_cli(args)
    elif args.mode == "report":
        run_report(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
