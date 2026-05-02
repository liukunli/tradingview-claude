#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse

import quanttrader as trader
import quanttrader.feeds
from quanttrader import indicators as indicators


class SMAStrategy(trader.Strategy):
    params = (
        ('period', 10),
        ('onlydaily', False),
    )

    def __init__(self):
        self.sma = indicators.SMA(self.data, period=self.p.period)

    def start(self):
        self.counter = 0

    def prenext(self):
        self.counter += 1
        print('prenext len %d - counter %d' % (len(self), self.counter))

    def next(self):
        self.counter += 1
        print('---next len %d - counter %d' % (len(self), self.counter))


def runstrat():
    args = parse_args()

    # Create a engine entity
    engine = trader.Engine(stdstats=False)

    engine.addstrategy(
        SMAStrategy,
        # args for the strategy
        period=args.period,
    )

    # Load the Data
    datapath = args.dataname or '/Users/kunliliu/Documents/GitHub/quanttrader/datas/2006-day-001.txt'
    data = trader.feeds.QuanttraderCSVData(
        dataname=datapath)

    tframes = dict(
        daily=trader.TimeFrame.Days,
        weekly=trader.TimeFrame.Weeks,
        monthly=trader.TimeFrame.Months)

    # Handy dictionary for the argument timeframe conversion
    # Resample the data
    if args.oldrp:
        data = trader.DataReplayer(
            dataname=data,
            timeframe=tframes[args.timeframe],
            compression=args.compression)
    else:
        data.replay(
            timeframe=tframes[args.timeframe],
            compression=args.compression)

    # First add the original data - smaller timeframe
    engine.adddata(data)

    # Run over everything
    engine.run(preload=False)

    # Plot the result
    engine.plot(style='bar')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Pandas test script')

    parser.add_argument('--dataname', default='', required=False,
                        help='File Data to Load')

    parser.add_argument('--oldrp', required=False, action='store_true',
                        help='Use deprecated DataReplayer')

    parser.add_argument('--timeframe', default='weekly', required=False,
                        choices=['daily', 'weekly', 'monthly'],
                        help='Timeframe to resample to')

    parser.add_argument('--compression', default=1, required=False, type=int,
                        help='Compress n bars into 1')

    parser.add_argument('--period', default=10, required=False, type=int,
                        help='Period to apply to indicator')

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
