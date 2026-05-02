#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,)
#                        unicode_literals)

import argparse
import datetime

import quanttrader as trader
import quanttrader.feeds
feeds = trader.feeds

class St(trader.Strategy):
    def next(self):
        print(','.join(str(x) for x in [
            self.data.datetime.datetime(),
            self.data.open[0], self.data.high[0],
            self.data.high[0], self.data.close[0],
            self.data.volume[0]]))


def runstrat():
    args = parse_args()

    engine = trader.Engine()

    data = feeds.GenericCSVData(
        dataname=args.data,
        dtformat='%d/%m/%y',
        # tmformat='%H%M%S',  # already the default value
        # datetime=0,  # position at default
        time=1,  # position of time
        open=5,  # position of open
        high=5,
        low=5,
        close=5,
        volume=7,
        openinterest=-1,  # -1 for not present
        timeframe=trader.TimeFrame.Ticks)

    engine.resampledata(data,
                         timeframe=trader.TimeFrame.Ticks,
                         compression=args.compression)

    engine.addstrategy(St)

    engine.run()
    if args.plot:
        engine.plot(style='bar')


def parse_args():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='BidAsk to OHLC')

    parser.add_argument('--data', required=False,
                        default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/bidask2.csv',
                        help='Data file to be read in')

    parser.add_argument('--compression', required=False, default=2, type=int,
                        help='How much to compress the bars')

    parser.add_argument('--plot', required=False, action='store_true',
                        help='Plot the vars')

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
