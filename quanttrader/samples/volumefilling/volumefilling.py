#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime
import os.path
import time
import sys


import quanttrader as trader


class St(trader.Strategy):
    params = (
        ('stakeperc', 10.0),
        ('opbreak', 10),
    )

    def notify_order(self, order):
        print('-- NOTIFY ORDER BEGIN')
        print(order)
        print('-- NOTIFY ORDER END')
        print('-- ORDER REMSIZE:', order.executed.remsize)

        if order.status == order.Completed:
            print('++ ORDER COMPLETED at data.len:', len(order.data))
            self.doop = -self.p.opbreak

    def __init__(self):
        pass

    def start(self):
        self.callcounter = 0
        txtfields = list()
        txtfields.append('Len')
        txtfields.append('Datetime')
        txtfields.append('Open')
        txtfields.append('High')
        txtfields.append('Low')
        txtfields.append('Close')
        txtfields.append('Volume')
        txtfields.append('OpenInterest')
        print(','.join(txtfields))

        self.doop = 0

    def next(self):
        txtfields = list()
        txtfields.append('%04d' % len(self))
        txtfields.append(self.data0.datetime.date(0).isoformat())
        txtfields.append('%.2f' % self.data0.open[0])
        txtfields.append('%.2f' % self.data0.high[0])
        txtfields.append('%.2f' % self.data0.low[0])
        txtfields.append('%.2f' % self.data0.close[0])
        txtfields.append('%.2f' % self.data0.volume[0])
        txtfields.append('%.2f' % self.data0.openinterest[0])
        print(','.join(txtfields))

        # Single order
        if self.doop == 0:
            if not self.position.size:
                stakevol = (self.data0.volume[0] * self.p.stakeperc) // 100
                print('++ STAKE VOLUME:', stakevol)
                self.buy(size=stakevol)

            else:
                self.close()

        self.doop += 1


FILLERS = {
    'FixedSize': trader.broker.fillers.FixedSize,
    'FixedBarPerc': trader.broker.fillers.FixedBarPerc,
    'BarPointPerc': trader.broker.fillers.BarPointPerc,
}


def runstrat():
    args = parse_args()

    datakwargs = dict()
    if args.fromdate:
        fromdate = datetime.datetime.strptime(args.fromdate, '%Y-%m-%d')
        datakwargs['fromdate'] = fromdate

    if args.todate:
        todate = datetime.datetime.strptime(args.todate, '%Y-%m-%d')
        datakwargs['todate'] = todate

    data = trader.feeds.QuanttraderCSVData(dataname=args.data, **datakwargs)

    engine = trader.Engine()
    engine.adddata(data)

    engine.broker.set_cash(args.cash)
    if args.filler is not None:
        fillerkwargs = dict()
        if args.filler_args is not None:
            fillerkwargs = eval('dict(' + args.filler_args + ')')

        filler = FILLERS[args.filler](**fillerkwargs)
        engine.broker.set_filler(filler)

    engine.addstrategy(St, stakeperc=args.stakeperc, opbreak=args.opbreak)

    engine.run()
    if args.plot:
        engine.plot(style='bar')


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Volume Filling Sample')

    parser.add_argument('--data', required=False,
                        default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/2006-volume-day-001.txt',
                        help='Data to be read in')

    parser.add_argument('--cash', required=False, action='store',
                        default=500e6, type=float,
                        help=('Starting cash'))

    parser.add_argument('--filler', required=False, action='store',
                        default=None, choices=FILLERS.keys(),
                        help=('Apply a volume filler for the execution'))

    parser.add_argument('--filler-args', required=False, action='store',
                        default=None,
                        help=('kwargs for the filler with format:\n'
                              '\n'
                              'arg1=val1,arg2=val2...'))

    parser.add_argument('--stakeperc', required=False, action='store',
                        type=float, default=10.0,
                        help=('Percentage of 1st bar to use for stake'))

    parser.add_argument('--opbreak', required=False, action='store',
                        type=int, default=10,
                        help=('Bars to wait for new op after completing '
                              'another'))

    parser.add_argument('--fromdate', '-f', required=False, default=None,
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--todate', '-t', required=False, default=None,
                        help='Ending date in YYYY-MM-DD format')

    parser.add_argument('--plot', required=False, action='store_true',
                        help=('Plot the result'))

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
