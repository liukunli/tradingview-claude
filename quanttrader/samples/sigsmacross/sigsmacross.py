#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime

import quanttrader as trader


class SmaCross(trader.SignalStrategy):
    params = dict(sma1=10, sma2=20)

    def notify_order(self, order):
        if not order.alive():
            print('{} {} {}@{}'.format(
                trader.num2date(order.executed.dt),
                'buy' if order.isbuy() else 'sell',
                order.executed.size,
                order.executed.price)
            )

    def notify_trade(self, trade):
        if trade.isclosed:
            print('profit {}'.format(trade.pnlcomm))

    def __init__(self):
        sma1 = trader.ind.SMA(period=self.params.sma1)
        sma2 = trader.ind.SMA(period=self.params.sma2)
        crossover = trader.ind.CrossOver(sma1, sma2)
        self.signal_add(trader.SIGNAL_LONG, crossover)


def runstrat(pargs=None):
    args = parse_args(pargs)

    engine = trader.Engine()
    engine.broker.set_cash(args.cash)

    data0 = trader.feeds.YahooFinanceData(
        dataname=args.data,
        fromdate=datetime.datetime.strptime(args.fromdate, '%Y-%m-%d'),
        todate=datetime.datetime.strptime(args.todate, '%Y-%m-%d'))
    engine.adddata(data0)

    engine.addstrategy(SmaCross, **(eval('dict(' + args.strat + ')')))
    engine.addsizer(trader.sizers.FixedSize, stake=args.stake)

    engine.run()
    if args.plot:
        engine.plot(**(eval('dict(' + args.plot + ')')))


def parse_args(pargs=None):

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='sigsmacross')

    parser.add_argument('--data', required=False, default='YHOO',
                        help='Yahoo Ticker')

    parser.add_argument('--fromdate', required=False, default='2011-01-01',
                        help='Ending date in YYYY-MM-DD format')

    parser.add_argument('--todate', required=False, default='2012-12-31',
                        help='Ending date in YYYY-MM-DD format')

    parser.add_argument('--cash', required=False, action='store', type=float,
                        default=10000, help=('Starting cash'))

    parser.add_argument('--stake', required=False, action='store', type=int,
                        default=1, help=('Stake to apply'))

    parser.add_argument('--strat', required=False, action='store', default='',
                        help=('Arguments for the strategy'))

    parser.add_argument('--plot', '-p', nargs='?', required=False,
                        metavar='kwargs', const='{}',
                        help=('Plot the read data applying any kwargs passed\n'
                              '\n'
                              'For example:\n'
                              '\n'
                              '  --plot style="candle" (to plot candles)\n'))

    return parser.parse_args(pargs)


if __name__ == '__main__':
    runstrat()
