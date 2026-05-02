#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse

import quanttrader as trader
import quanttrader.feeds

import pandas


def runstrat():
    args = parse_args()

    # Create a engine entity
    engine = trader.Engine(stdstats=False)

    # Add a strategy
    engine.addstrategy(trader.Strategy)

    # Get a pandas dataframe
    datapath = ('/Users/kunliliu/Documents/GitHub/quanttrader/datas/2006-day-001.txt')

    # Simulate the header row isn't there if noheaders requested
    skiprows = 1 if args.noheaders else 0
    header = None if args.noheaders else 0

    dataframe = pandas.read_csv(
        datapath,
        skiprows=skiprows,
        header=header,
        # parse_dates=[0],
        parse_dates=True,
        index_col=0,
    )

    if not args.noprint:
        print('--------------------------------------------------')
        print(dataframe)
        print('--------------------------------------------------')

    # Pass it to the quanttrader datafeed and add it to the engine
    data = trader.feeds.PandasData(dataname=dataframe,
                               # datetime='Date',
                               nocase=True,
                               )

    engine.adddata(data)

    # Run over everything
    engine.run()

    # Plot the result
    engine.plot(style='bar')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Pandas test script')

    parser.add_argument('--noheaders', action='store_true', default=False,
                        required=False,
                        help='Do not use header rows')

    parser.add_argument('--noprint', action='store_true', default=False,
                        help='Print the dataframe')

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
