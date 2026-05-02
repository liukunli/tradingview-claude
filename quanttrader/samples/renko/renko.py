#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime

import quanttrader as trader


class St(trader.Strategy):
    params = dict(
    )

    def __init__(self):
        for d in self.datas:
            trader.ind.RSI(d)

    def next(self):
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

    data0 = trader.feeds.QuanttraderCSVData(dataname=args.data0, **kwargs)

    fkwargs = dict()
    fkwargs.update(**eval('dict(' + args.renko + ')'))

    if not args.dual:
        data0.addfilter(trader.filters.Renko, **fkwargs)
        engine.adddata(data0)
    else:
        engine.adddata(data0)
        data1 = data0.clone()
        data1.addfilter(trader.filters.Renko, **fkwargs)
        engine.adddata(data1)

    # Broker
    engine.broker = trader.brokers.BackBroker(**eval('dict(' + args.broker + ')'))

    # Sizer
    engine.addsizer(trader.sizers.FixedSize, **eval('dict(' + args.sizer + ')'))

    # Strategy
    engine.addstrategy(St, **eval('dict(' + args.strat + ')'))

    # Execute
    kwargs = dict(stdstats=False)
    kwargs.update(**eval('dict(' + args.engine + ')'))
    engine.run(**kwargs)

    if args.plot:  # Plot if requested to
        kwargs = dict(style='candle')
        kwargs.update(**eval('dict(' + args.plot + ')'))
        engine.plot(**kwargs)


def parse_args(pargs=None):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            'Renko bricks sample'
        )
    )

    parser.add_argument('--data0', default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/2005-2006-day-001.txt',
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

    parser.add_argument('--renko', required=False, default='',
                        metavar='kwargs', help='kwargs in key=value format')

    parser.add_argument('--dual', required=False, action='store_true',
                        help='put the filter on a second version of the data')

    return parser.parse_args(pargs)


if __name__ == '__main__':
    runstrat()
