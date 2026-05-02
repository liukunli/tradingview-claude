#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime

import quanttrader as trader


class St(trader.Strategy):
    params = (
        ('ondata', False),
    )

    def __init__(self):
        if not self.p.ondata:
            a = self.data.high - self.data.low
        else:
            a = 1.05 * (self.data.high + self.data.low) / 2.0

        b = trader.LinePlotterIndicator(a, name='hilo')
        b.plotinfo.subplot = not self.p.ondata


def runstrat(pargs=None):
    args = parse_args(pargs)

    engine = trader.Engine()

    dkwargs = dict()
    # Get the dates from the args
    if args.fromdate is not None:
        fromdate = datetime.datetime.strptime(args.fromdate, '%Y-%m-%d')
        dkwargs['fromdate'] = fromdate
    if args.todate is not None:
        todate = datetime.datetime.strptime(args.todate, '%Y-%m-%d')
        dkwargs['todate'] = todate

    data = trader.feeds.QuanttraderCSVData(dataname=args.data, **dkwargs)
    engine.adddata(data)

    engine.addstrategy(St, ondata=args.ondata)
    engine.run(stdstats=False)

    # Plot if requested
    if args.plot:
        pkwargs = dict(style='bar')
        if args.plot is not True:  # evals to True but is not True
            npkwargs = eval('dict(' + args.plot + ')')  # args were passed
            pkwargs.update(npkwargs)

        engine.plot(**pkwargs)


def parse_args(pargs=None):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Fake Indicator')

    parser.add_argument('--data', '-d',
                        default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/2005-2006-day-001.txt',
                        help='data to add to the system')

    parser.add_argument('--fromdate', '-f',
                        default=None,
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--todate', '-t',
                        default=None,
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--ondata', '-o', action='store_true',
                        help='Plot fake indicator on the data')

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
