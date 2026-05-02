#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import collections
import datetime
import itertools

import quanttrader as trader


class SMACrossOver(trader.Indicator):
    lines = ('signal',)
    params = (('p1', 10), ('p2', 30),)

    def __init__(self):
        sma1 = trader.indicators.SMA(period=self.p.p1)
        sma2 = trader.indicators.SMA(period=self.p.p2)
        self.lines.signal = trader.indicators.CrossOver(sma1, sma2)


class SlipSt(trader.SignalStrategy):
    opcounter = itertools.count(1)

    def notify_order(self, order):
        if order.status == trader.Order.Completed:
            t = ''
            t += '{:02d}'.format(next(self.opcounter))
            t += ' {}'.format(order.data.datetime.datetime())
            t += ' BUY ' * order.isbuy() or ' SELL'
            t += ' Size: {:+d} / Price: {:.2f}'
            print(t.format(order.executed.size, order.executed.price))


def runstrat(args=None):
    args = parse_args(args)

    engine = trader.Engine()
    engine.broker.set_cash(args.cash)

    dkwargs = dict()
    if args.fromdate is not None:
        fromdate = datetime.datetime.strptime(args.fromdate, '%Y-%m-%d')
        dkwargs['fromdate'] = fromdate

    if args.todate is not None:
        todate = datetime.datetime.strptime(args.todate, '%Y-%m-%d')
        dkwargs['todate'] = todate

    # if dataset is None, args.data has been given
    data = trader.feeds.QuanttraderCSVData(dataname=args.data, **dkwargs)
    engine.adddata(data)

    engine.signal_strategy(SlipSt)
    if not args.longonly:
        stype = trader.signal.SIGNAL_LONGSHORT
    else:
        stype = trader.signal.SIGNAL_LONG

    engine.add_signal(stype, SMACrossOver, p1=args.period1, p2=args.period2)

    if args.slip_perc is not None:
        engine.broker.set_slippage_perc(args.slip_perc,
                                         slip_open=args.slip_open,
                                         slip_match=not args.no_slip_match,
                                         slip_out=args.slip_out)

    elif args.slip_fixed is not None:
        engine.broker.set_slippage_fixed(args.slip_fixed,
                                          slip_open=args.slip_open,
                                          slip_match=not args.no_slip_match,
                                          slip_out=args.slip_out)

    engine.run()
    if args.plot:
        pkwargs = dict(style='bar')
        if args.plot is not True:  # evals to True but is not True
            npkwargs = eval('dict(' + args.plot + ')')  # args were passed
            pkwargs.update(npkwargs)

        engine.plot(**pkwargs)


def parse_args(pargs=None):

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Sample for Slippage')

    parser.add_argument('--data', required=False,
                        default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/2005-2006-day-001.txt',
                        help='Specific data to be read in')

    parser.add_argument('--fromdate', required=False, default=None,
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--todate', required=False, default=None,
                        help='Ending date in YYYY-MM-DD format')

    parser.add_argument('--cash', required=False, action='store',
                        type=float, default=50000,
                        help=('Cash to start with'))

    parser.add_argument('--period1', required=False, action='store',
                        type=int, default=10,
                        help=('Fast moving average period'))

    parser.add_argument('--period2', required=False, action='store',
                        type=int, default=30,
                        help=('Slow moving average period'))

    parser.add_argument('--longonly', required=False, action='store_true',
                        help=('Long only strategy'))

    pgroup = parser.add_mutually_exclusive_group(required=False)
    pgroup.add_argument('--slip_perc', required=False, default=None,
                        type=float,
                        help='Set the value for commission percentage')

    pgroup.add_argument('--slip_fixed', required=False, default=None,
                        type=float,
                        help='Set the value for commission percentage')

    parser.add_argument('--no-slip_match', required=False, action='store_true',
                        help=('Match by capping slippage at bar ends'))

    parser.add_argument('--slip_out', required=False, action='store_true',
                        help=('Disable capping and return non-real prices'))

    parser.add_argument('--slip_open', required=False, action='store_true',
                        help=('Slip even if match price is next open'))

    # Plot options
    parser.add_argument('--plot', '-p', nargs='?', required=False,
                        metavar='kwargs', const=True,
                        help=('Plot the read data applying any kwargs passed\n'
                              '\n'
                              'For example:\n'
                              '\n'
                              '  --plot style="candle" (to plot candles)\n'))

    if pargs is not None:
        return parser.parse_args(pargs)

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
