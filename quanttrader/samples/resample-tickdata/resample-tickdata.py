#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse

import quanttrader as trader
import quanttrader.feeds
feeds = trader.feeds

def runstrat():
    args = parse_args()

    # Create a engine entity
    engine = trader.Engine(stdstats=False)

    # Add a strategy
    engine.addstrategy(trader.Strategy)

    # Load the Data
    datapath = args.dataname or '/Users/kunliliu/Documents/GitHub/quanttrader/datas/ticksample.csv'

    data = feeds.GenericCSVData(
        dataname=datapath,
        dtformat='%Y-%m-%dT%H:%M:%S.%f',
        timeframe=trader.TimeFrame.Ticks,
    )

    # Handy dictionary for the argument timeframe conversion
    tframes = dict(
        ticks=trader.TimeFrame.Ticks,
        microseconds=trader.TimeFrame.MicroSeconds,
        seconds=trader.TimeFrame.Seconds,
        minutes=trader.TimeFrame.Minutes,
        daily=trader.TimeFrame.Days,
        weekly=trader.TimeFrame.Weeks,
        monthly=trader.TimeFrame.Months)

    # Resample the data
    engine.resampledata(
        data,
        timeframe=tframes[args.timeframe],
        compression=args.compression,
        bar2edge=not args.nobar2edge,
        adjbartime=not args.noadjbartime,
        rightedge=args.rightedge)

    if args.writer:
        # add a writer
        engine.addwriter(trader.WriterFile, csv=args.wrcsv)

    # Run over everything
    engine.run()

    # Plot the result
    engine.plot(style='bar')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Resampling script down to tick data')

    parser.add_argument('--dataname', default='', required=False,
                        help='File Data to Load')

    parser.add_argument('--timeframe', default='ticks', required=False,
                        choices=['ticks', 'microseconds', 'seconds',
                                 'minutes', 'daily', 'weekly', 'monthly'],
                        help='Timeframe to resample to')

    parser.add_argument('--compression', default=1, required=False, type=int,
                        help=('Compress n bars into 1'))

    parser.add_argument('--nobar2edge', required=False, action='store_true',
                        help=('Do not Resample IntraDay Timed Bars to edges'))

    parser.add_argument('--noadjbartime', required=False,
                        action='store_true',
                        help=('Do not adjust the time bar to meet the edges'))

    parser.add_argument('--rightedge', required=False, action='store_true',
                        help=('Resample to right edge of boundary'))

    parser.add_argument('--writer', required=False, action='store_true',
                        help=('Add a Writer'))

    parser.add_argument('--wrcsv', required=False, action='store_true',
                        help=('Add CSV to the Writer'))

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
