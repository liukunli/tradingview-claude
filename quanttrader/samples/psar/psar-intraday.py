#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)


import argparse
import datetime

import quanttrader as trader


class St(trader.Strategy):
    params = (
    )

    def __init__(self):
        self.psar0 = trader.ind.ParabolicSAR(self.data0)
        self.psar1 = trader.ind.ParabolicSAR(self.data1)
        pass

    def next(self):
        txt = []
        txt.append('{:04d}'.format(len(self)))
        txt.append('{:04d}'.format(len(self.data0)))
        txt.append(self.data0.datetime.datetime())
        txt.append('{:.2f}'.format(self.data0.close[0]))
        txt.append('PSAR')
        txt.append('{:04.2f}'.format(self.psar0[0]))
        if len(self.data1):
            txt.append('{:04d}'.format(len(self.data1)))
            txt.append(self.data1.datetime.datetime())
            txt.append('{:.2f}'.format(self.data1.close[0]))
            txt.append('PSAR')
            txt.append('{:04.2f}'.format(self.psar1[0]))

        print(','.join(str(x) for x in txt))


def runstrat(args=None):
    args = parse_args(args)

    engine = trader.Engine()

    # Data feed kwargs
    kwargs = dict(
        timeframe=trader.TimeFrame.Minutes,
        compression=5,
    )

    # Parse from/to-date
    dtfmt, tmfmt = '%Y-%m-%d', 'T%H:%M:%S'
    for a, d in ((getattr(args, x), x) for x in ['fromdate', 'todate']):
        if a:
            strpfmt = dtfmt + tmfmt * ('T' in a)
            kwargs[d] = datetime.datetime.strptime(a, strpfmt)

    # Data feed
    data0 = trader.feeds.QuanttraderCSVData(dataname=args.data0, **kwargs)
    engine.adddata(data0)

    engine.resampledata(data0, timeframe=trader.TimeFrame.Minutes, compression=15)

    # Broker
    engine.broker = trader.brokers.BackBroker(**eval('dict(' + args.broker + ')'))

    # Sizer
    engine.addsizer(trader.sizers.FixedSize, **eval('dict(' + args.sizer + ')'))

    # Strategy
    engine.addstrategy(St, **eval('dict(' + args.strat + ')'))

    # Execute
    engine.run(**eval('dict(' + args.engine + ')'))

    if args.plot:  # Plot if requested to
        engine.plot(**eval('dict(' + args.plot + ')'))


def parse_args(pargs=None):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            'Sample Skeleton'
        )
    )

    parser.add_argument('--data0', default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/2006-min-005.txt',
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
