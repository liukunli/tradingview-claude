#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)


import argparse
import datetime

import quanttrader as trader


class St(trader.Strategy):
    params = dict(
        ma=trader.ind.SMA,
        p1=5,
        p2=15,
        limit=0.005,
        limdays=3,
        limdays2=1000,
        hold=10,
        usebracket=False,  # use order_target_size
        switchp1p2=False,  # switch prices of order1 and order2
    )

    def notify_order(self, order):
        print('{}: Order ref: {} / Type {} / Status {}'.format(
            self.data.datetime.date(0),
            order.ref, 'Buy' * order.isbuy() or 'Sell',
            order.getstatusname()))

        if order.status == order.Completed:
            self.holdstart = len(self)

        if not order.alive() and order.ref in self.orefs:
            self.orefs.remove(order.ref)

    def __init__(self):
        ma1, ma2 = self.p.ma(period=self.p.p1), self.p.ma(period=self.p.p2)
        self.cross = trader.ind.CrossOver(ma1, ma2)

        self.orefs = list()

        if self.p.usebracket:
            print('-' * 5, 'Using buy_bracket')

    def next(self):
        if self.orefs:
            return  # pending orders do nothing

        if not self.position:
            if self.cross > 0.0:  # crossing up

                close = self.data.close[0]
                p1 = close * (1.0 - self.p.limit)
                p2 = p1 - 0.02 * close
                p3 = p1 + 0.02 * close

                valid1 = datetime.timedelta(self.p.limdays)
                valid2 = valid3 = datetime.timedelta(self.p.limdays2)

                if self.p.switchp1p2:
                    p1, p2 = p2, p1
                    valid1, valid2 = valid2, valid1

                if not self.p.usebracket:
                    o1 = self.buy(exectype=trader.Order.Limit,
                                  price=p1,
                                  valid=valid1,
                                  transmit=False)

                    print('{}: Oref {} / Buy at {}'.format(
                        self.datetime.date(), o1.ref, p1))

                    o2 = self.sell(exectype=trader.Order.Stop,
                                   price=p2,
                                   valid=valid2,
                                   parent=o1,
                                   transmit=False)

                    print('{}: Oref {} / Sell Stop at {}'.format(
                        self.datetime.date(), o2.ref, p2))

                    o3 = self.sell(exectype=trader.Order.Limit,
                                   price=p3,
                                   valid=valid3,
                                   parent=o1,
                                   transmit=True)

                    print('{}: Oref {} / Sell Limit at {}'.format(
                        self.datetime.date(), o3.ref, p3))

                    self.orefs = [o1.ref, o2.ref, o3.ref]

                else:
                    os = self.buy_bracket(
                        price=p1, valid=valid1,
                        stopprice=p2, stopargs=dict(valid=valid2),
                        limitprice=p3, limitargs=dict(valid=valid3),)

                    self.orefs = [o.ref for o in os]

        else:  # in the market
            if (len(self) - self.holdstart) >= self.p.hold:
                pass  # do nothing in this case


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
    data0 = trader.feeds.QuanttraderCSVData(dataname=args.data0, **kwargs)
    engine.adddata(data0)

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

    return parser.parse_args(pargs)


if __name__ == '__main__':
    runstrat()
