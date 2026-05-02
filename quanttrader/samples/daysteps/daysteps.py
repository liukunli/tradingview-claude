#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse

import quanttrader as trader


class St(trader.Strategy):
    params = ()

    def __init__(self):
        pass

    def start(self):
        self.callcounter = 0
        txtfields = list()
        txtfields.append('Calls')
        txtfields.append('Len Strat')
        txtfields.append('Len Data')
        txtfields.append('Datetime')
        txtfields.append('Open')
        txtfields.append('High')
        txtfields.append('Low')
        txtfields.append('Close')
        txtfields.append('Volume')
        txtfields.append('OpenInterest')
        print(','.join(txtfields))

        self.lcontrol = 0

    def next(self):
        self.callcounter += 1

        txtfields = list()
        txtfields.append('%04d' % self.callcounter)
        txtfields.append('%04d' % len(self))
        txtfields.append('%04d' % len(self.data0))
        txtfields.append(self.data.datetime.datetime(0).isoformat())
        txtfields.append('%.2f' % self.data0.open[0])
        txtfields.append('%.2f' % self.data0.high[0])
        txtfields.append('%.2f' % self.data0.low[0])
        txtfields.append('%.2f' % self.data0.close[0])
        txtfields.append('%.2f' % self.data0.volume[0])
        txtfields.append('%.2f' % self.data0.openinterest[0])
        print(','.join(txtfields))

        if len(self.data) > self.lcontrol:
            print('- I could issue a buy order during the Opening')

        self.lcontrol = len(self.data)


def runstrat():
    args = parse_args()

    engine = trader.Engine()
    data = trader.feeds.QuanttraderCSVData(dataname=args.data)

    data.addfilter(trader.filters.DayStepsFilter)
    engine.adddata(data)

    engine.addstrategy(St)

    engine._doreplay = True
    engine.run(**(eval('dict(' + args.engine + ')')))
    if args.plot:
        engine.plot(**(eval('dict(' + args.plot + ')')))


def parse_args(pargs=None):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Sample for pivot point and cross plotting')

    parser.add_argument('--data', required=False,
                        default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/2005-2006-day-001.txt',
                        help='Data to be read in')

    parser.add_argument('--engine', required=False, action='store',
                        default='', help=('Arguments for engine'))

    parser.add_argument('--plot', '-p', nargs='?', required=False,
                        metavar='kwargs', const='{}',
                        help=('Plot (with additional args if passed'))

    return parser.parse_args(pargs)


if __name__ == '__main__':
    runstrat()
