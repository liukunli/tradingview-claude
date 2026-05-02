#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

# Reference
# https://estrategiastrading.com/oro-bolsa-estadistica-con-python/

import argparse
import datetime

import scipy.stats

import quanttrader as trader


class PearsonR(trader.ind.PeriodN):
    _mindatas = 2  # hint to the platform

    lines = ('correlation',)
    params = (('period', 20),)

    def next(self):
        c, p = scipy.stats.pearsonr(self.data0.get(size=self.p.period),
                                    self.data1.get(size=self.p.period))

        self.lines.correlation[0] = c


class MACrossOver(trader.Strategy):
    params = (
        ('ma', trader.ind.MovAv.SMA),
        ('pd1', 20),
        ('pd2', 20),
    )

    def __init__(self):
        ma1 = self.p.ma(self.data0, period=self.p.pd1, subplot=True)
        self.p.ma(self.data1, period=self.p.pd2, plotmaster=ma1)
        PearsonR(self.data0, self.data1)


def runstrat(args=None):
    args = parse_args(args)

    engine = trader.Engine()

    # Data feed kwargs
    kwargs = dict()

    # Parse from/to-date
    dtfmt, tmfmt = '%Y-%m-%d', 'T%H:%M:%S'
    for a, d in ((getattr(args, x), x) for x in ['fromdate', 'todate']):
        if a:
            strpfmt = dtfmt + tmfmt * ('T' in a)
            kwargs[d] = datetime.datetime.strptime(a, strpfmt)

    if not args.offline:
        YahooData = trader.feeds.YahooFinanceData
    else:
        YahooData = trader.feeds.YahooFinanceCSVData

    # Data feeds
    data0 = YahooData(dataname=args.data0, **kwargs)
    # engine.adddata(data0)
    engine.resampledata(data0, timeframe=trader.TimeFrame.Weeks)

    data1 = YahooData(dataname=args.data1, **kwargs)
    # engine.adddata(data1)
    engine.resampledata(data1, timeframe=trader.TimeFrame.Weeks)
    data1.plotinfo.plotmaster = data0

    # Broker
    kwargs = eval('dict(' + args.broker + ')')
    engine.broker = trader.brokers.BackBroker(**kwargs)

    # Sizer
    kwargs = eval('dict(' + args.sizer + ')')
    engine.addsizer(trader.sizers.FixedSize, **kwargs)

    # Strategy
    if True:
        kwargs = eval('dict(' + args.strat + ')')
        engine.addstrategy(MACrossOver, **kwargs)

    engine.addobserver(trader.observers.LogReturns2,
                        timeframe=trader.TimeFrame.Weeks,
                        compression=20)

    # Execute
    engine.run(**(eval('dict(' + args.engine + ')')))

    if args.plot:  # Plot if requested to
        engine.plot(**(eval('dict(' + args.plot + ')')))


def parse_args(pargs=None):

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            'Gold vs SP500 from '
            'https://estrategiastrading.com/oro-bolsa-estadistica-con-python/')
    )

    parser.add_argument('--data0', required=False, default='SPY',
                        metavar='TICKER', help='Yahoo ticker to download')

    parser.add_argument('--data1', required=False, default='GLD',
                        metavar='TICKER', help='Yahoo ticker to download')

    parser.add_argument('--offline', required=False, action='store_true',
                        help='Use the offline files')

    # Defaults for dates
    parser.add_argument('--fromdate', required=False, default='2005-01-01',
                        help='Date[time] in YYYY-MM-DD[THH:MM:SS] format')

    parser.add_argument('--todate', required=False, default='2016-01-01',
                        help='Date[time] in YYYY-MM-DD[THH:MM:SS] format')

    parser.add_argument('--engine', required=False, default='',
                        metavar='kwargs', help='kwargs in key=value format')

    parser.add_argument('--broker', required=False, default='',
                        metavar='kwargs', help='kwargs in key=value format')

    parser.add_argument('--sizer', required=False, default='',
                        metavar='kwargs', help='kwargs in key=value format')

    parser.add_argument('--strat', required=False, default='',
                        metavar='kwargs', help='kwargs in key=value format')

    parser.add_argument('--plot', required=False, default='',
                        nargs='?', const='{}',
                        metavar='kwargs', help='kwargs in key=value format')

    return parser.parse_args(pargs)


if __name__ == '__main__':
    runstrat()
