#!/usr/bin/env python3
"""
A-Share Quantitative Backtesting & Analysis System
====================================================
Entry point.  Run from inside the quant_backtest/ directory:

    python run_backtest.py [--mode backtest|analyze|multifactor] [options]

────────────────────────────────────────────────────────────────────────
MODE: backtest   (default)
  Run a single-factor strategy backtest.

  python run_backtest.py --strategy momentum --start 2020-01-02 --end 2021-12-31
  python run_backtest.py --strategy cpv --top-n 50 --rebalance month_start
  python run_backtest.py --strategy reversal --period 5 --rebalance 5 --no-cost

────────────────────────────────────────────────────────────────────────
MODE: analyze
  Run IC analysis + factor scoring + turnover diagnostics on pre-computed
  factor files saved in --factor-dir.

  python run_backtest.py --mode analyze \\
        --data-dir ./data --factor-dir ./factors/preprocessed \\
        --start 2020-01-02 --end 2021-12-31 --output-dir ./outputs

────────────────────────────────────────────────────────────────────────
MODE: multifactor
  Combine Barra factors (from data/data_barra/) into composite signals
  and score them across 4 weighting schemes.

  python run_backtest.py --mode multifactor \\
        --data-dir ./data --start 2020-01-02 --end 2021-12-31

────────────────────────────────────────────────────────────────────────
Data layout expected under --data-dir (default: ./data):
    data/
    ├── date.pkl               trading-day list
    ├── data_daily/<date>.csv  OHLCV + optional market-cap columns
    ├── data_ret/<date>.csv    forward returns (1vwap_pct, 5vwap_pct, 10vwap_pct)
    ├── data_ud_new/<date>.csv trade status  (paused, zt, dt, st)
    ├── data_barra/<date>.csv  Barra risk exposures   [multifactor / exposure]
    └── data_industry/<date>.csv  industry labels    [cpv / neutralization]
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config
from core.backtest_engine import BacktestEngine
from strategies.momentum import MomentumStrategy, ReversalStrategy
from strategies.cpv import CPVStrategy


# ─────────────────────────────── CLI ────────────────────────────────────────

def _parse():
    p = argparse.ArgumentParser(
        description="A-Share Quant Backtest & Analysis",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # ── shared ──────────────────────────────────────────────────────────────
    p.add_argument("--mode",
                   choices=["backtest", "analyze", "multifactor",
                            "validate", "stability", "constraints",
                            "linear", "nonlinear"],
                   default="backtest", help="Operation mode")
    p.add_argument("--data-dir",    default=config.DATA_DIR)
    p.add_argument("--start",       default="2020-01-02", metavar="YYYY-MM-DD")
    p.add_argument("--end",         default="2021-12-31", metavar="YYYY-MM-DD")
    p.add_argument("--output-dir",  default="./outputs",
                   help="Where analysis results are written")

    # ── backtest ─────────────────────────────────────────────────────────────
    p.add_argument("--strategy", choices=["momentum", "reversal", "cpv"],
                   default="momentum")
    p.add_argument("--top-n",    type=int, default=50)
    p.add_argument("--rebalance", default="month_start",
                   help="month_start | month_end | N (integer days)")
    p.add_argument("--capital",  type=float, default=config.INITIAL_CAPITAL)
    p.add_argument("--n-groups", type=int,   default=5,
                   help="Quantile groups for L/S analysis (0 = skip)")
    p.add_argument("--no-cost",  action="store_true")
    p.add_argument("--period",   type=int,   default=20,
                   help="Look-back window for momentum/reversal")
    p.add_argument("--cpv-no-industry-neutral", action="store_true")
    p.add_argument("--cpv-weights", default="1,1,1,1,1",
                   help="CPV sub-factor weights: U,B,L,WR,TREND")

    # ── analyze ──────────────────────────────────────────────────────────────
    p.add_argument("--factor-dir", default="./factors/preprocessed",
                   help="[analyze] Directory of per-date factor CSVs")
    p.add_argument("--factor-col", default=None,
                   help="[analyze] Specific factor column name (None = first col)")
    p.add_argument("--ret-col",    default="1vwap_pct",
                   help="[analyze] Return column in data_ret files")
    p.add_argument("--horizons",   default="1vwap_pct,5vwap_pct,10vwap_pct",
                   help="[analyze] Comma-separated return columns for IC-decay")
    p.add_argument("--max-dates",  type=int, default=120,
                   help="[analyze/multifactor/validate/stability] Max days to process")

    # ── validate ─────────────────────────────────────────────────────────────
    p.add_argument("--lookback",      type=int, default=60,
                   help="[validate] Rolling weight lookback window")
    p.add_argument("--min-history",   type=int, default=40,
                   help="[validate] Min history for rolling weights")
    p.add_argument("--rebalance-freq",type=int, default=5,
                   help="[validate] Rebalance frequency in days")

    # ── stability ────────────────────────────────────────────────────────────
    p.add_argument("--train-size",    type=int, default=80,
                   help="[stability] Walk-forward train window")
    p.add_argument("--test-size",     type=int, default=20,
                   help="[stability] Walk-forward test window")
    p.add_argument("--step",          type=int, default=20,
                   help="[stability] Walk-forward step size")

    # ── constraints ──────────────────────────────────────────────────────────
    p.add_argument("--cap",           type=float, default=0.3,
                   help="[constraints] Max weight per factor")
    p.add_argument("--turnover-penalty", type=float, default=0.2,
                   help="[constraints] EWMA smoothing coefficient")

    # ── linear / nonlinear ───────────────────────────────────────────────────
    p.add_argument("--alpha",         type=float, default=1e-4,
                   help="[linear] Ridge/Lasso regularization strength")
    p.add_argument("--model-type",    default="auto",
                   choices=["auto", "xgboost", "lightgbm", "random_forest"],
                   help="[nonlinear] Model type")
    p.add_argument("--no-rolling",    action="store_true",
                   help="[nonlinear] Disable walk-forward rolling evaluation")
    p.add_argument("--no-shap",       action="store_true",
                   help="[nonlinear] Disable SHAP value computation")

    return p.parse_args()


def _parse_rebalance(v):
    try:
        return int(v)
    except ValueError:
        return v


# ─────────────────────────────── modes ──────────────────────────────────────

def run_backtest(args):
    # Build strategy
    if args.strategy == "momentum":
        strategy = MomentumStrategy(period=args.period)
    elif args.strategy == "reversal":
        strategy = ReversalStrategy(period=args.period)
    else:
        w   = [float(x) for x in args.cpv_weights.split(",")]
        if len(w) != 5:
            raise ValueError("--cpv-weights must be 5 comma-separated numbers")
        strategy = CPVStrategy(
            data_dir=args.data_dir,
            neutralize_industry=not args.cpv_no_industry_neutral,
            weights=dict(zip(["U", "B", "L", "WR", "TREND"], w)),
        )

    engine = BacktestEngine(
        data_dir=args.data_dir,
        initial_capital=args.capital,
        commission_rate=config.COMMISSION_RATE,
        slippage_rate=config.SLIPPAGE_RATE,
        stamp_duty=config.STAMP_DUTY,
        risk_free_rate=config.RISK_FREE_RATE,
    )
    report = engine.run(
        start_date=args.start,
        end_date=args.end,
        strategy=strategy,
        top_n=args.top_n,
        rebalance_freq=_parse_rebalance(args.rebalance),
        enable_cost=not args.no_cost,
        calculate_ic=True,
        n_groups=args.n_groups,
    )
    engine.print_report(report)


def run_analyze(args):
    from analysis.ic_analysis      import ICAnalyzer
    from analysis.factor_turnover  import FactorTurnoverAnalyzer
    from analysis.factor_scoring   import score_factors

    date_pkl  = str(Path(args.data_dir) / "date.pkl")
    ret_dir   = str(Path(args.data_dir) / "data_ret")
    horizons  = args.horizons.split(",")
    out       = args.output_dir

    print("\n" + "="*60)
    print("📊 IC Series")
    print("="*60)
    analyzer = ICAnalyzer(factor_col=args.factor_col, horizons=horizons)
    ic_df = analyzer.compute_ic_series(
        date_pkl, args.factor_dir, args.data_dir,
        ret_col=args.ret_col,
        start_date=args.start, end_date=args.end,
        output_dir=out,
    )
    if not ic_df.empty:
        stats = ICAnalyzer.summarize_ic_stats(ic_df, output_dir=out)
        print(stats.to_string(index=False))

    print("\n" + "="*60)
    print("📉 IC Decay")
    print("="*60)
    decay_df = analyzer.compute_ic_decay(
        date_pkl, args.factor_dir, ret_dir,
        horizons=horizons,
        start_date=args.start, end_date=args.end,
        output_dir=out,
    )
    if not decay_df.empty:
        summary = decay_df.groupby("horizon")["ic"].agg(["mean","std"])
        summary["ir"] = summary["mean"] / summary["std"]
        print(summary.to_string())

    print("\n" + "="*60)
    print("🔄 Factor Turnover")
    print("="*60)
    turn_df = FactorTurnoverAnalyzer(factor_col=args.factor_col).factor_turnover(
        date_pkl, args.factor_dir,
        start_date=args.start, end_date=args.end,
        output_dir=out,
    )
    if not turn_df.empty:
        print(f"  Mean Rank-IC:  {turn_df['rank_ic'].mean():.4f}")
        print(f"  Mean Turnover: {turn_df['turnover'].mean():.4f}")

    print("\n" + "="*60)
    print("🏆 Factor Scoring")
    print("="*60)
    scored = score_factors(
        date_pkl, args.factor_dir, args.data_dir,
        ret_col=args.ret_col,
        start_date=args.start, end_date=args.end,
        max_dates=args.max_dates,
        output_dir=out,
    )
    if not scored.empty:
        print(scored[["factor","ic_mean","ic_ir","score"]].to_string(index=False))

    print(f"\n✅ Analysis output written to: {out}")


def run_multifactor(args):
    from analysis.multifactor import MultifactorWeighter, ObjectiveScorer

    out = args.output_dir

    print("\n" + "="*60)
    print("🧮 Multi-Factor Weighting")
    print("="*60)
    mfw = MultifactorWeighter()
    result = mfw.run(
        data_dir=args.data_dir,
        ret_horizon=args.ret_col if hasattr(args, "ret_col") else "1vwap_pct",
        start_date=args.start, end_date=args.end,
        max_dates=args.max_dates,
        output_dir=out,
    )
    print(result["metrics"].to_string(index=False))
    print("\nWeights by method:")
    print(result["weights"].to_string())

    print("\n" + "="*60)
    print("🎯 Objective Scores")
    print("="*60)
    scores = ObjectiveScorer().run(
        data_dir=args.data_dir,
        start_date=args.start, end_date=args.end,
        max_dates=args.max_dates,
        output_dir=out,
    )
    if not scores.empty:
        print(scores.to_string(index=False))

    print(f"\n✅ Multi-factor output written to: {out}")


def run_validate(args):
    from analysis.backtest_validation import run
    run(
        data_dir=args.data_dir,
        output_multifactor=str(Path(args.output_dir) / "multifactor"),
        output_report=str(Path(args.output_dir) / "report"),
        ret_col=args.ret_col if hasattr(args, "ret_col") else "1vwap_pct",
        start_date=args.start,
        end_date=args.end,
        max_dates=args.max_dates,
        lookback=args.lookback,
        min_history=args.min_history,
        top_n=args.top_n,
        rebalance_freq=args.rebalance_freq,
    )


def run_stability(args):
    from analysis.stability_checks import run
    run(
        output_dir=args.output_dir,
        data_dir=args.data_dir,
        start_date=args.start,
        end_date=args.end,
        max_dates=args.max_dates,
        train_size=args.train_size,
        test_size=args.test_size,
        step=args.step,
    )


def run_constraints(args):
    from analysis.constraints import run
    run(
        output_dir=args.output_dir,
        data_dir=args.data_dir,
        start_date=args.start,
        end_date=args.end,
        max_dates=args.max_dates,
        cap=args.cap,
        turnover_penalty=args.turnover_penalty,
    )


def run_linear(args):
    from analysis.linear_models import run
    run(
        output_dir=args.output_dir,
        data_dir=args.data_dir,
        start_date=args.start,
        end_date=args.end,
        max_dates=args.max_dates,
        alpha=args.alpha,
    )


def run_nonlinear(args):
    from analysis.nonlinear_models import run
    run(
        output_dir=args.output_dir,
        data_dir=args.data_dir,
        start_date=args.start,
        end_date=args.end,
        max_dates=args.max_dates,
        model_type=args.model_type,
        enable_rolling=not args.no_rolling,
        enable_shap=not args.no_shap,
    )


# ─────────────────────────────── main ───────────────────────────────────────

def main():
    args = _parse()
    if args.mode == "backtest":
        run_backtest(args)
    elif args.mode == "analyze":
        run_analyze(args)
    elif args.mode == "multifactor":
        run_multifactor(args)
    elif args.mode == "validate":
        run_validate(args)
    elif args.mode == "stability":
        run_stability(args)
    elif args.mode == "constraints":
        run_constraints(args)
    elif args.mode == "linear":
        run_linear(args)
    elif args.mode == "nonlinear":
        run_nonlinear(args)


if __name__ == "__main__":
    main()
