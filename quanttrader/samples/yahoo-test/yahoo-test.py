#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime

import quanttrader as trader
from quanttrader import indicators as indicators
import quanttrader.feeds
feeds = trader.feeds
import quanttrader.filters


def runstrat():
    args = parse_args()

    # Create a engine entity
    engine = trader.Engine(stdstats=False)

    # Add a strategy
    engine.addstrategy(trader.Strategy)

    # Get the dates from the args
    fromdate = datetime.datetime.strptime(args.fromdate, '%Y-%m-%d')
    todate = datetime.datetime.strptime(args.todate, '%Y-%m-%d')

    data = feeds.YahooFinanceData(
        dataname=args.data,
        fromdate=fromdate,
        todate=todate)

    # Add the resample data instead of the original
    engine.adddata(data)

    # Add a simple moving average if requirested
    engine.addindicator(indicators.SMA, period=args.period)

    # Add a writer with CSV
    if args.writer:
        engine.addwriter(trader.WriterFile, csv=args.wrcsv)

    # Run over everything
    engine.run()

    # Plot if requested
    if args.plot:
        engine.plot(style='bar', numfigs=args.numfigs, volume=False)


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Calendar Days Filter Sample')

    parser.add_argument('--data', '-d',
                        default='YHOO',
                        help='Ticker to download from Yahoo')

    parser.add_argument('--fromdate', '-f',
                        default='2006-01-01',
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--todate', '-t',
                        default='2006-12-31',
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--period', default=15, type=int,
                        help='Period to apply to the Simple Moving Average')

    parser.add_argument('--writer', '-w', action='store_true',
                        help='Add a writer to engine')

    parser.add_argument('--wrcsv', '-wc', action='store_true',
                        help='Enable CSV Output in the writer')

    parser.add_argument('--plot', '-p', action='store_true',
                        help='Plot the read data')

    parser.add_argument('--numfigs', '-n', default=1, type=int,
                        help='Plot using numfigs figures')

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
