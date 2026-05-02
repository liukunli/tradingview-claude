#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime

import quanttrader as trader
import quanttrader.feeds
feeds = trader.feeds
from quanttrader import indicators as indicators
import quanttrader.utils.flushfile

# from wkdaysfiller import WeekDaysFiller
from weekdaysfiller import WeekDaysFiller


class St(trader.Strategy):
    params = (('sma', 0),)

    def __init__(self):
        if self.p.sma:
            indicators.SMA(self.data0, period=self.p.sma)
            indicators.SMA(self.data1, period=self.p.sma)

    def next(self):
        dtequal = (self.data0.datetime.datetime() ==
                   self.data1.datetime.datetime())

        txt = ''
        txt += '%04d, %5s' % (len(self), str(dtequal))
        txt += ', data0, %s' % self.data0.datetime.datetime().isoformat()
        txt += ', %s, data1' % self.data1.datetime.datetime().isoformat()
        print(txt)


def runstrat():
    args = parse_args()

    fromdate = datetime.datetime.strptime(args.fromdate, '%Y-%m-%d')
    todate = datetime.datetime.strptime(args.todate, '%Y-%m-%d')

    engine = trader.Engine(stdstats=False)

    DataFeed = feeds.YahooFinanceCSVData
    if args.online:
        DataFeed = feeds.YahooFinanceData

    data0 = DataFeed(dataname=args.data0, fromdate=fromdate, todate=todate)

    if args.data1:
        data1 = DataFeed(dataname=args.data1, fromdate=fromdate, todate=todate)
    else:
        data1 = data0.clone()

    if args.filler or args.filler0:
        data0.addfilter(WeekDaysFiller, fillclose=args.fillclose)

    if args.filler or args.filler1:
        data1.addfilter(WeekDaysFiller, fillclose=args.fillclose)

    engine.adddata(data0)
    engine.adddata(data1)

    engine.addstrategy(St, sma=args.sma)
    engine.run(runonce=True, preload=True)

    if args.plot:
        engine.plot(style='bar')


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Sample for aligning with trade ')

    parser.add_argument('--online', required=False, action='store_true',
                        help='Fetch data online from Yahoo')

    parser.add_argument('--data0', required=True, help='Data 0 to be read in')
    parser.add_argument('--data1', required=False, help='Data 1 to be read in')

    parser.add_argument('--sma', required=False, default=0, type=int,
                        help='Add a sma to the datas')

    parser.add_argument('--fillclose', required=False, action='store_true',
                        help='Fill with Close price instead of NaN')

    parser.add_argument('--filler', required=False, action='store_true',
                        help='Add Filler to Datas 0 and 1')

    parser.add_argument('--filler0', required=False, action='store_true',
                        help='Add Filler to Data 0')

    parser.add_argument('--filler1', required=False, action='store_true',
                        help='Add Filler to Data 1')

    parser.add_argument('--fromdate', '-f', default='2012-01-01',
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--todate', '-t', default='2012-12-31',
                        help='Ending date in YYYY-MM-DD format')

    parser.add_argument('--plot', required=False, action='store_true',
                        help='Do plot')

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
