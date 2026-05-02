#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse

import quanttrader as trader
import quanttrader.feeds


def runstrat():
    args = parse_args()

    # Create a engine entity
    engine = trader.Engine(stdstats=False)

    # Add a strategy
    engine.addstrategy(trader.Strategy)

    # Load the Data
    datapath = args.dataname or '/Users/kunliliu/Documents/GitHub/quanttrader/datas/2006-day-001.txt'
    data = trader.feeds.QuanttraderCSVData(
        dataname=datapath)

    # Handy dictionary for the argument timeframe conversion
    tframes = dict(
        daily=trader.TimeFrame.Days,
        weekly=trader.TimeFrame.Weeks,
        monthly=trader.TimeFrame.Months)

    # Resample the data
    if args.oldrs:
        # Old resampler, fully deprecated
        data = trader.DataResampler(
            dataname=data,
            timeframe=tframes[args.timeframe],
            compression=args.compression)

        # Add the resample data instead of the original
        engine.adddata(data)
    else:
        # New resampler
        engine.resampledata(
            data,
            timeframe=tframes[args.timeframe],
            compression=args.compression)

    # Run over everything
    engine.run()

    # Plot the result
    engine.plot(style='bar')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Resample down to minutes')

    parser.add_argument('--dataname', default='', required=False,
                        help='File Data to Load')

    parser.add_argument('--oldrs', required=False, action='store_true',
                        help='Use deprecated DataResampler')

    parser.add_argument('--timeframe', default='weekly', required=False,
                        choices=['daily', 'weekly', 'monthly'],
                        help='Timeframe to resample to')

    parser.add_argument('--compression', default=1, required=False, type=int,
                        help='Compress n bars into 1')

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
