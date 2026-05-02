#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime
import os.path
import time
import sys


import quanttrader as trader
from quanttrader.utils.py3 import bytes


DATAFORMATS = dict(
    btcsv=trader.feeds.QuanttraderCSVData,
    vchartcsv=trader.feeds.VChartCSVData,
    vchart=trader.feeds.VChartData,
    vcdata=trader.feeds.VCData,
    vcfile=trader.feeds.VChartFile,
    ibdata=trader.feeds.IBData,
    sierracsv=trader.feeds.SierraChartCSVData,
    mt4csv=trader.feeds.MT4CSVData,
    yahoocsv=trader.feeds.YahooFinanceCSVData,
    yahoocsv_unreversed=trader.feeds.YahooFinanceCSVData,
    yahoo=trader.feeds.YahooFinanceData,
)


class RewriteStrategy(trader.Strategy):
    params = (
        ('separator', ','),
        ('outfile', None),
    )

    def start(self):
        if self.p.outfile is None:
            self.f = sys.stdout
        else:
            self.f = open(self.p.outfile, 'wb')

        if self.data._timeframe < trader.TimeFrame.Days:
            headers = 'Date,Time,Open,High,Low,Close,Volume,OpenInterest'
        else:
            headers = 'Date,Open,High,Low,Close,Volume,OpenInterest'

        headers += '\n'
        self.f.write(bytes(headers))

    def next(self):
        fields = list()
        dt = self.data.datetime.date(0).strftime('%Y-%m-%d')
        fields.append(dt)
        if self.data._timeframe < trader.TimeFrame.Days:
            tm = self.data.datetime.time(0).strftime('%H:%M:%S')
            fields.append(tm)

        o = '%.2f' % self.data.open[0]
        fields.append(o)
        h = '%.2f' % self.data.high[0]
        fields.append(h)
        l = '%.2f' % self.data.low[0]
        fields.append(l)
        c = '%.2f' % self.data.close[0]
        fields.append(c)
        v = '%d' % self.data.volume[0]
        fields.append(v)
        oi = '%d' % self.data.openinterest[0]
        fields.append(oi)

        txt = self.p.separator.join(fields)
        txt += '\n'
        self.f.write(bytes(txt))


def runstrat(pargs=None):
    args = parse_args(pargs)

    engine = trader.Engine()

    dfkwargs = dict()
    if args.format == 'yahoo_unreversed':
        dfkwargs['reverse'] = True

    fmtstr = '%Y-%m-%d'
    if args.fromdate:
        dtsplit = args.fromdate.split('T')
        if len(dtsplit) > 1:
            fmtstr += 'T%H:%M:%S'

        fromdate = datetime.datetime.strptime(args.fromdate, fmtstr)
        dfkwargs['fromdate'] = fromdate

    fmtstr = '%Y-%m-%d'
    if args.todate:
        dtsplit = args.todate.split('T')
        if len(dtsplit) > 1:
            fmtstr += 'T%H:%M:%S'
        todate = datetime.datetime.strptime(args.todate, fmtstr)
        dfkwargs['todate'] = todate

    dfcls = DATAFORMATS[args.format]
    data = dfcls(dataname=args.infile, **dfkwargs)
    engine.adddata(data)

    engine.addstrategy(RewriteStrategy,
                        separator=args.separator,
                        outfile=args.outfile)

    engine.run(stdstats=False)

    if args.plot:
        pkwargs = dict(style='bar')
        if args.plot is not True:  # evals to True but is not True
            npkwargs = eval('dict(' + args.plot + ')')  # args were passed
            pkwargs.update(npkwargs)

        engine.plot(**pkwargs)


def parse_args(pargs=None):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Rewrite formats to QuanttraderCSVData format')

    parser.add_argument('--format', '-fmt', required=False,
                        choices=DATAFORMATS.keys(),
                        default=next(iter(DATAFORMATS)),
                        help='File to be read in')

    parser.add_argument('--infile', '-i', required=True,
                        help='File to be read in')

    parser.add_argument('--outfile', '-o', default=None, required=False,
                        help='File to write to')

    parser.add_argument('--fromdate', '-f', required=False,
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--todate', '-t', required=False,
                        help='Ending date in YYYY-MM-DD format')

    parser.add_argument('--separator', '-s', required=False, default=',',
                        help='Plot the read data')

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
