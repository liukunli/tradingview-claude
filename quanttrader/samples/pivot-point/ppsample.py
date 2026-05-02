#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse

import quanttrader as trader
import quanttrader.feeds
import quanttrader.utils.flushfile


class St(trader.Strategy):
    params = (('usepp1', False),
              ('plot_on_daily', False))

    def __init__(self):
        autoplot = self.p.plot_on_daily
        self.pp = pp = trader.ind.PivotPoint(self.data1, _autoplot=autoplot)

    def next(self):
        txt = ','.join(
            ['%04d' % len(self),
             '%04d' % len(self.data0),
             '%04d' % len(self.data1),
             self.data.datetime.date(0).isoformat(),
             '%04d' % len(self.pp),
             '%.2f' % self.pp[0]])

        print(txt)


def runstrat():
    args = parse_args()

    engine = trader.Engine()
    data = trader.feeds.QuanttraderCSVData(dataname=args.data)
    engine.adddata(data)
    engine.resampledata(data, timeframe=trader.TimeFrame.Months)

    engine.addstrategy(St,
                        usepp1=args.usepp1,
                        plot_on_daily=args.plot_on_daily)
    engine.run(runonce=False)
    if args.plot:
        engine.plot(style='bar')


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Sample for pivot point and cross plotting')

    parser.add_argument('--data', required=False,
                        default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/2005-2006-day-001.txt',
                        help='Data to be read in')

    parser.add_argument('--plot', required=False, action='store_true',
                        help=('Plot the result'))

    parser.add_argument('--plot-on-daily', required=False, action='store_true',
                        help=('Plot the indicator on the daily data'))

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
