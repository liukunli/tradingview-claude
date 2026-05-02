#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)


import argparse
import datetime

import quanttrader as trader


class St(trader.SignalStrategy):
    params = (
    )

    def __init__(self):
        ma1, ma2, = trader.ind.SMA(period=15), trader.ind.SMA(period=50)
        self.signal_add(trader.signal.SIGNAL_LONG, trader.ind.CrossOver(ma1, ma2))

    def next2(self):
        pass


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

    # Data feed
    data0 = trader.feeds.YahooFinanceCSVData(dataname=args.data0, **kwargs)
    engine.adddata(data0)

    # Broker
    engine.broker = trader.brokers.BackBroker(**eval('dict(' + args.broker + ')'))

    engine.addanalyzer(trader.analyzers.Calmar)
    # Sizer
    engine.addsizer(trader.sizers.FixedSize, **eval('dict(' + args.sizer + ')'))

    # Strategy
    engine.addstrategy(St, **eval('dict(' + args.strat + ')'))

    # Execute
    st0 = engine.run(**eval('dict(' + args.engine + ')'))[0]
    i = 1
    for k, v in st0.analyzers.calmar.get_analysis().items():
        print(i, ': '.join((str(k), str(v))))
        i += 1

    if args.plot:  # Plot if requested to
        engine.plot(**eval('dict(' + args.plot + ')'))


def parse_args(pargs=None):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            'Sample Skeleton'
        )
    )

    parser.add_argument('--data0', default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/orcl-1995-2014.txt',
                        required=False, help='Data to read in')

    # Defaults for dates
    parser.add_argument('--fromdate', required=False, default='',
                        help='Date[time] in YYYY-MM-DD[THH:MM:SS] format')

    parser.add_argument('--todate', required=False, default='',
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
