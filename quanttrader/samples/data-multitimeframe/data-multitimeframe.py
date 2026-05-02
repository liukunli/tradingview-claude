#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse

import quanttrader as trader
import quanttrader.feeds
from quanttrader import indicators as indicators
from trader import ResamplerDaily, ResamplerWeekly, ResamplerMonthly
from trader import ReplayerDaily, ReplayerWeekly, ReplayerMonthly
from quanttrader.utils import flushfile


class SMAStrategy(trader.Strategy):
    params = (
        ('period', 10),
        ('onlydaily', False),
    )

    def __init__(self):
        self.sma_small_tf = indicators.SMA(self.data, period=self.p.period)
        trader.indicators.MACD(self.data0)

        if not self.p.onlydaily:
            self.sma_large_tf = indicators.SMA(self.data1, period=self.p.period)
            trader.indicators.MACD(self.data1)

    def prenext(self):
        self.next()

    def nextstart(self):
        print('--------------------------------------------------')
        print('nextstart called with len', len(self))
        print('--------------------------------------------------')

        super(SMAStrategy, self).nextstart()

    def next(self):
        print('Strategy:', len(self))

        txt = list()
        txt.append('Data0')
        txt.append('%04d' % len(self.data0))
        dtfmt = '%Y-%m-%dT%H:%M:%S.%f'
        txt.append('{:f}'.format(self.data.datetime[0]))
        txt.append('%s' % self.data.datetime.datetime(0).strftime(dtfmt))
        # txt.append('{:f}'.format(self.data.open[0]))
        # txt.append('{:f}'.format(self.data.high[0]))
        # txt.append('{:f}'.format(self.data.low[0]))
        txt.append('{:f}'.format(self.data.close[0]))
        # txt.append('{:6d}'.format(int(self.data.volume[0])))
        # txt.append('{:d}'.format(int(self.data.openinterest[0])))
        # txt.append('{:f}'.format(self.sma_small[0]))
        print(', '.join(txt))

        if len(self.datas) > 1 and len(self.data1):
            txt = list()
            txt.append('Data1')
            txt.append('%04d' % len(self.data1))
            dtfmt = '%Y-%m-%dT%H:%M:%S.%f'
            txt.append('{:f}'.format(self.data1.datetime[0]))
            txt.append('%s' % self.data1.datetime.datetime(0).strftime(dtfmt))
            # txt.append('{}'.format(self.data1.open[0]))
            # txt.append('{}'.format(self.data1.high[0]))
            # txt.append('{}'.format(self.data1.low[0]))
            txt.append('{}'.format(self.data1.close[0]))
            # txt.append('{}'.format(self.data1.volume[0]))
            # txt.append('{}'.format(self.data1.openinterest[0]))
            # txt.append('{}'.format(float('NaN')))
            print(', '.join(txt))


def runstrat():
    args = parse_args()

    # Create a engine entity
    engine = trader.Engine()

    # Add a strategy
    if not args.indicators:
        engine.addstrategy(trader.Strategy)
    else:
        engine.addstrategy(
            SMAStrategy,

            # args for the strategy
            period=args.period,
            onlydaily=args.onlydaily,
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
    if args.noresample:
        datapath = args.dataname2 or '/Users/kunliliu/Documents/GitHub/quanttrader/datas/2006-week-001.txt'
        data2 = trader.feeds.QuanttraderCSVData(
            dataname=datapath)
    else:
        if args.oldrs:
            if args.replay:
                data2 = trader.DataReplayer(
                    dataname=data,
                    timeframe=tframes[args.timeframe],
                    compression=args.compression)
            else:
                data2 = trader.DataResampler(
                    dataname=data,
                    timeframe=tframes[args.timeframe],
                    compression=args.compression)

        else:
            data2 = trader.DataClone(dataname=data)
            if args.replay:
                if args.timeframe == 'daily':
                    data2.addfilter(ReplayerDaily)
                elif args.timeframe == 'weekly':
                    data2.addfilter(ReplayerWeekly)
                elif args.timeframe == 'monthly':
                    data2.addfilter(ReplayerMonthly)
            else:
                if args.timeframe == 'daily':
                    data2.addfilter(ResamplerDaily)
                elif args.timeframe == 'weekly':
                    data2.addfilter(ResamplerWeekly)
                elif args.timeframe == 'monthly':
                    data2.addfilter(ResamplerMonthly)

    # First add the original data - smaller timeframe
    engine.adddata(data)

    # And then the large timeframe
    engine.adddata(data2)

    # Run over everything
    engine.run(runonce=not args.runnext,
                preload=not args.nopreload,
                oldsync=args.oldsync,
                stdstats=False)

    # Plot the result
    if args.plot:
        engine.plot(style='bar')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Pandas test script')

    parser.add_argument('--dataname', default='', required=False,
                        help='File Data to Load')

    parser.add_argument('--dataname2', default='', required=False,
                        help='Larger timeframe file to load')

    parser.add_argument('--runnext', action='store_true',
                        help='Use next by next instead of runonce')

    parser.add_argument('--nopreload', action='store_true',
                        help='Do not preload the data')

    parser.add_argument('--oldsync', action='store_true',
                        help='Use old data synchronization method')

    parser.add_argument('--oldrs', action='store_true',
                        help='Use old resampler')

    parser.add_argument('--replay', action='store_true',
                        help='Replay instead of resample')

    parser.add_argument('--noresample', action='store_true',
                        help='Do not resample, rather load larger timeframe')

    parser.add_argument('--timeframe', default='weekly', required=False,
                        choices=['daily', 'weekly', 'monthly'],
                        help='Timeframe to resample to')

    parser.add_argument('--compression', default=1, required=False, type=int,
                        help='Compress n bars into 1')

    parser.add_argument('--indicators', action='store_true',
                        help='Wether to apply Strategy with indicators')

    parser.add_argument('--onlydaily', action='store_true',
                        help='Indicator only to be applied to daily timeframe')

    parser.add_argument('--period', default=10, required=False, type=int,
                        help='Period to apply to indicator')

    parser.add_argument('--plot', required=False, action='store_true',
                        help='Plot the chart')

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
