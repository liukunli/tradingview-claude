#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime

# The above could be sent to an independent module
import quanttrader as trader
import quanttrader.feeds
from quanttrader import indicators as indicators


class PlotStrategy(trader.Strategy):
    '''
    The strategy does nothing but create indicators for plotting purposes
    '''
    params = dict(
        smasubplot=False,  # default for Moving averages
        nomacdplot=False,
        rsioverstoc=False,
        rsioversma=False,
        stocrsi=False,
        stocrsilabels=False,
    )

    def __init__(self):
        sma = indicators.SMA(subplot=self.params.smasubplot)

        macd = indicators.MACD()
        # In SMA we passed plot directly as kwarg, here the plotinfo.plot
        # attribute is changed - same effect
        macd.plotinfo.plot = not self.params.nomacdplot

        # Let's put rsi on stochastic/sma or the other way round
        stoc = indicators.Stochastic()
        rsi = indicators.RSI()
        if self.params.stocrsi:
            stoc.plotinfo.plotmaster = rsi
            stoc.plotinfo.plotlinelabels = self.p.stocrsilabels
        elif self.params.rsioverstoc:
            rsi.plotinfo.plotmaster = stoc
        elif self.params.rsioversma:
            rsi.plotinfo.plotmaster = sma


def runstrategy():
    args = parse_args()

    # Create a engine
    engine = trader.Engine()

    # Get the dates from the args
    fromdate = datetime.datetime.strptime(args.fromdate, '%Y-%m-%d')
    todate = datetime.datetime.strptime(args.todate, '%Y-%m-%d')

    # Create the 1st data
    data = trader.feeds.QuanttraderCSVData(
        dataname=args.data,
        fromdate=fromdate,
        todate=todate)

    # Add the 1st data to engine
    engine.adddata(data)

    # Add the strategy
    engine.addstrategy(PlotStrategy,
                        smasubplot=args.smasubplot,
                        nomacdplot=args.nomacdplot,
                        rsioverstoc=args.rsioverstoc,
                        rsioversma=args.rsioversma,
                        stocrsi=args.stocrsi,
                        stocrsilabels=args.stocrsilabels)

    # And run it
    engine.run(stdstats=args.stdstats)

    # Plot
    engine.plot(numfigs=args.numfigs, volume=False)


def parse_args():
    parser = argparse.ArgumentParser(description='Plotting Example')

    parser.add_argument('--data', '-d',
                        default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/2006-day-001.txt',
                        help='data to add to the system')

    parser.add_argument('--fromdate', '-f',
                        default='2006-01-01',
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--todate', '-t',
                        default='2006-12-31',
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--stdstats', '-st', action='store_true',
                        help='Show standard observers')

    parser.add_argument('--smasubplot', '-ss', action='store_true',
                        help='Put SMA on own subplot/axis')

    parser.add_argument('--nomacdplot', '-nm', action='store_true',
                        help='Hide the indicator from the plot')

    group = parser.add_mutually_exclusive_group(required=False)

    group.add_argument('--rsioverstoc', '-ros', action='store_true',
                       help='Plot the RSI indicator on the Stochastic axis')

    group.add_argument('--rsioversma', '-rom', action='store_true',
                       help='Plot the RSI indicator on the SMA axis')

    group.add_argument('--stocrsi', '-strsi', action='store_true',
                       help='Plot the Stochastic indicator on the RSI axis')

    parser.add_argument('--stocrsilabels', action='store_true',
                        help='Plot line names instead of indicator name')

    parser.add_argument('--numfigs', '-n', default=1,
                        help='Plot using numfigs figures')

    return parser.parse_args()


if __name__ == '__main__':
    runstrategy()
