#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse

import quanttrader as trader
import quanttrader.feeds
feeds = trader.feeds
import pandas


class PandasDataOptix(feeds.PandasData):

    lines = ('optix_close', 'optix_pess', 'optix_opt',)
    params = (('optix_close', -1),
              ('optix_pess', -1),
              ('optix_opt', -1))

    if False:
        # No longer needed with version 1.9.62.122
        datafields = feeds.PandasData.datafields + (
            ['optix_close', 'optix_pess', 'optix_opt'])


class StrategyOptix(trader.Strategy):

    def next(self):
        print('%03d %f %f, %f' % (
            len(self),
            self.data.optix_close[0],
            self.data.lines.optix_pess[0],
            self.data.optix_opt[0],))


def runstrat():
    args = parse_args()

    # Create a engine entity
    engine = trader.Engine(stdstats=False)

    # Add a strategy
    engine.addstrategy(StrategyOptix)

    # Get a pandas dataframe
    datapath = ('/Users/kunliliu/Documents/GitHub/quanttrader/datas/2006-day-001-optix.txt')

    # Simulate the header row isn't there if noheaders requested
    skiprows = 1 if args.noheaders else 0
    header = None if args.noheaders else 0

    dataframe = pandas.read_csv(datapath,
                                skiprows=skiprows,
                                header=header,
                                parse_dates=True,
                                index_col=0)

    if not args.noprint:
        print('--------------------------------------------------')
        print(dataframe)
        print('--------------------------------------------------')

    # Pass it to the quanttrader datafeed and add it to the engine
    data = PandasDataOptix(dataname=dataframe)

    engine.adddata(data)

    # Run over everything
    engine.run()

    # Plot the result
    if not args.noplot:
        engine.plot(style='bar')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Pandas test script')

    parser.add_argument('--noheaders', action='store_true', default=False,
                        required=False,
                        help='Do not use header rows')

    parser.add_argument('--noprint', action='store_true', default=False,
                        help='Print the dataframe')

    parser.add_argument('--noplot', action='store_true', default=False,
                        help='Do not plot the chart')

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
