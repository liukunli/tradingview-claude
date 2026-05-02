#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse

import quanttrader as trader
import quanttrader.feeds
feeds = trader.feeds
from quanttrader import indicators as indicators


class BidAskCSV(feeds.GenericCSVData):
    linesoverride = True  # discard usual OHLC structure
    # datetime must be present and last
    lines = ('bid', 'ask', 'datetime')
    # datetime (always 1st) and then the desired order for
    params = (
        # (datetime, 0), # inherited from parent class
        ('bid', 1),  # default field pos 1
        ('ask', 2),  # default field pos 2
    )


class St(trader.Strategy):
    params = (('sma', False), ('period', 3))

    def __init__(self):
        if self.p.sma:
            self.sma = indicators.SMA(self.data, period=self.p.period)

    def next(self):
        dtstr = self.data.datetime.datetime().isoformat()
        txt = '%4d: %s - Bid %.4f - %.4f Ask' % (
            (len(self), dtstr, self.data.bid[0], self.data.ask[0]))

        if self.p.sma:
            txt += ' - SMA: %.4f' % self.sma[0]
        print(txt)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Bid/Ask Line Hierarchy',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument('--data', '-d', action='store',
                        required=False, default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/bidask.csv',
                        help='data to add to the system')

    parser.add_argument('--dtformat', '-dt',
                        required=False, default='%m/%d/%Y %H:%M:%S',
                        help='Format of datetime in input')

    parser.add_argument('--sma', '-s', action='store_true',
                        required=False,
                        help='Add an SMA to the mix')

    parser.add_argument('--period', '-p', action='store',
                        required=False, default=5, type=int,
                        help='Period for the sma')

    return parser.parse_args()


def runstrategy():
    args = parse_args()

    engine = trader.Engine()  # Create a engine

    data = BidAskCSV(dataname=args.data, dtformat=args.dtformat)
    engine.adddata(data)  # Add the 1st data to engine
    # Add the strategy to engine
    engine.addstrategy(St, sma=args.sma, period=args.period)
    engine.run()


if __name__ == '__main__':
    runstrategy()
