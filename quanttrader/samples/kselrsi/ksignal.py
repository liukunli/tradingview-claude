#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime

import quanttrader as trader


class TheStrategy(trader.SignalStrategy):
    params = dict(rsi_per=14, rsi_upper=65.0, rsi_lower=35.0, rsi_out=50.0,
                  warmup=35)

    def notify_order(self, order):
        super(TheStrategy, self).notify_order(order)
        if order.status == order.Completed:
            print('%s: Size: %d @ Price %f' %
                  ('buy' if order.isbuy() else 'sell',
                   order.executed.size, order.executed.price))

            d = order.data
            print('Close[-1]: %f - Open[0]: %f' % (d.close[-1], d.open[0]))

    def __init__(self):
        # Original code needs artificial warmup phase - hidden sma to replic
        if self.p.warmup:
            trader.indicators.SMA(period=self.p.warmup, plot=False)

        rsi = trader.indicators.RSI(period=self.p.rsi_per,
                                upperband=self.p.rsi_upper,
                                lowerband=self.p.rsi_lower)

        crossup = trader.ind.CrossUp(rsi, self.p.rsi_lower)
        self.signal_add(trader.SIGNAL_LONG, crossup)
        self.signal_add(trader.SIGNAL_LONGEXIT, -(rsi > self.p.rsi_out))

        crossdown = trader.ind.CrossDown(rsi, self.p.rsi_upper)
        self.signal_add(trader.SIGNAL_SHORT, -crossdown)
        self.signal_add(trader.SIGNAL_SHORTEXIT, rsi < self.p.rsi_out)


def runstrat(pargs=None):
    args = parse_args(pargs)

    engine = trader.Engine()
    engine.broker.set_cash(args.cash)
    engine.broker.set_coc(args.coc)
    data0 = trader.feeds.YahooFinanceData(
        dataname=args.data,
        fromdate=datetime.datetime.strptime(args.fromdate, '%Y-%m-%d'),
        todate=datetime.datetime.strptime(args.todate, '%Y-%m-%d'),
        round=False)

    engine.adddata(data0)

    engine.addsizer(trader.sizers.FixedSize, stake=args.stake)
    engine.addstrategy(TheStrategy, **(eval('dict(' + args.strat + ')')))
    engine.addobserver(trader.observers.Value)
    engine.addobserver(trader.observers.Trades)
    engine.addobserver(trader.observers.BuySell, barplot=True)

    engine.run(stdstats=False)
    if args.plot:
        engine.plot(**(eval('dict(' + args.plot + ')')))


def parse_args(pargs=None):

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Sample after post at keithselover.wordpress.com')

    parser.add_argument('--data', required=False, default='XOM',
                        help='Yahoo Ticker')

    parser.add_argument('--fromdate', required=False, default='2012-09-01',
                        help='Ending date in YYYY-MM-DD format')

    parser.add_argument('--todate', required=False, default='2016-01-01',
                        help='Ending date in YYYY-MM-DD format')

    parser.add_argument('--cash', required=False, action='store', type=float,
                        default=100000, help=('Cash to start with'))

    parser.add_argument('--stake', required=False, action='store', type=int,
                        default=100, help=('Cash to start with'))

    parser.add_argument('--coc', required=False, action='store_true',
                        help=('Buy on close of same bar as order is issued'))

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
