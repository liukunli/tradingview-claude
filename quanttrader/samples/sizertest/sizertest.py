#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime
import random

import quanttrader as trader


class CloseSMA(trader.Strategy):
    params = (('period', 15),)

    def __init__(self):
        sma = trader.indicators.SMA(self.data, period=self.p.period)
        self.crossover = trader.indicators.CrossOver(self.data, sma)

    def next(self):
        if self.crossover > 0:
            self.buy()

        elif self.crossover < 0:
            self.sell()


class LongOnly(trader.Sizer):
    params = (('stake', 1),)

    def _getsizing(self, comminfo, cash, data, isbuy):
        if isbuy:
            return self.p.stake

        # Sell situation
        position = self.broker.getposition(data)
        if not position.size:
            return 0  # do not sell if nothing is open

        return self.p.stake


class FixedReverser(trader.Sizer):
    params = (('stake', 1),)

    def _getsizing(self, comminfo, cash, data, isbuy):
        position = self.strategy.getposition(data)
        size = self.p.stake * (1 + (position.size != 0))
        return size


def runstrat(args=None):
    args = parse_args(args)

    engine = trader.Engine()
    engine.broker.set_cash(args.cash)

    dkwargs = dict()
    if args.fromdate:
        fromdate = datetime.datetime.strptime(args.fromdate, '%Y-%m-%d')
        dkwargs['fromdate'] = fromdate

    if args.todate:
        todate = datetime.datetime.strptime(args.todate, '%Y-%m-%d')
        dkwargs['todate'] = todate

    data0 = trader.feeds.YahooFinanceCSVData(dataname=args.data0, **dkwargs)
    engine.adddata(data0, name='Data0')

    engine.addstrategy(CloseSMA, period=args.period)

    if args.longonly:
        engine.addsizer(LongOnly, stake=args.stake)
    else:
        engine.addsizer(trader.sizers.FixedReverser, stake=args.stake)

    engine.run()
    if args.plot:
        pkwargs = dict()
        if args.plot is not True:  # evals to True but is not True
            pkwargs = eval('dict(' + args.plot + ')')  # args were passed

        engine.plot(**pkwargs)


def parse_args(pargs=None):

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Sample for sizer')

    parser.add_argument('--data0', required=False,
                        default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/yhoo-1996-2015.txt',
                        help='Data to be read in')

    parser.add_argument('--fromdate', required=False,
                        default='2005-01-01',
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--todate', required=False,
                        default='2006-12-31',
                        help='Ending date in YYYY-MM-DD format')

    parser.add_argument('--cash', required=False, action='store',
                        type=float, default=50000,
                        help=('Cash to start with'))

    parser.add_argument('--longonly', required=False, action='store_true',
                        help=('Use the LongOnly sizer'))

    parser.add_argument('--stake', required=False, action='store',
                        type=int, default=1,
                        help=('Stake to pass to the sizers'))

    parser.add_argument('--period', required=False, action='store',
                        type=int, default=15,
                        help=('Period for the Simple Moving Average'))

    # Plot options
    parser.add_argument('--plot', '-p', nargs='?', required=False,
                        metavar='kwargs', const=True,
                        help=('Plot the read data applying any kwargs passed\n'
                              '\n'
                              'For example:\n'
                              '\n'
                              '  --plot style="candle" (to plot candles)\n'))

    if pargs is not None:
        return parser.parse_args(pargs)

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
