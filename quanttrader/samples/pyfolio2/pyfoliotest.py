#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)


import argparse
import collections
import datetime


import quanttrader as trader


class St(trader.SignalStrategy):
    params = (
        ('pfast', 13),
        ('pslow', 50),
        ('printdata', False),
        ('stake', 1000),
        ('short', False),
    )

    def __init__(self):
        self.sfast = trader.indicators.SMA(period=self.p.pfast)
        self.sslow = trader.indicators.SMA(period=self.p.pslow)
        self.cover = trader.indicators.CrossOver(self.sfast, self.sslow)
        if self.p.short:
            self.signal_add(trader.SIGNAL_LONGSHORT, self.cover)
        else:
            self.signal_add(trader.SIGNAL_LONG, self.cover)

    def start(self):
        super(self.__class__, self).start()
        if self.p.printdata:
            txtfields = list()
            txtfields.append('Len')
            txtfields.append('Datetime')
            txtfields.append('Open')
            txtfields.append('High')
            txtfields.append('Low')
            txtfields.append('Close')
            txtfields.append('Volume')
            txtfields.append('OpenInterest')
            print(','.join(txtfields))

    def next(self):
        super(self.__class__, self).next()
        if self.p.printdata:
            # Print only 1st data ... is just a check that things are running
            txtfields = list()
            txtfields.append('%04d' % len(self))
            txtfields.append(self.data.datetime.datetime(0).isoformat())
            txtfields.append('%.2f' % self.data0.open[0])
            txtfields.append('%.2f' % self.data0.high[0])
            txtfields.append('%.2f' % self.data0.low[0])
            txtfields.append('%.2f' % self.data0.close[0])
            txtfields.append('%.2f' % self.data0.volume[0])
            txtfields.append('%.2f' % self.data0.openinterest[0])
            print(','.join(txtfields))


_TFRAMES = collections.OrderedDict(
    (
        ('minutes', trader.TimeFrame.Minutes),
        ('days', trader.TimeFrame.Days),
        ('weeks', trader.TimeFrame.Weeks),
        ('months', trader.TimeFrame.Months),
        ('years', trader.TimeFrame.Years),
    )
)

_TFS = _TFRAMES.keys()


def runstrat(args=None):
    args = parse_args(args)

    engine = trader.Engine()
    engine.broker.set_cash(args.cash)

    dkwargs = dict()
    if args.fromdate:
        fromdate = datetime.datetime.strptime(args.fromdate, '%Y-%m-%d')
        dkwargs['fromdate'] = fromdate

    if args.todate:
        todate = datetime.datetime.strptime(args.todate, '%Y-%m-%d')
        dkwargs['todate'] = todate

    if args.timeframe:
        dkwargs['timeframe'] = _TFRAMES[args.timeframe]

    if args.compression:
        dkwargs['compression'] = args.compression

    # data0 = trader.feeds.QuanttraderCSVData(dataname=args.data0, **dkwargs)
    data0 = trader.feeds.VCData(dataname=args.data0, historical=True, **dkwargs)
    engine.adddata(data0, name='Data0')

    engine.addstrategy(St, short=args.short, printdata=args.printdata)
    engine.addsizer(trader.sizers.FixedSize, stake=args.stake)

    # Own analyzerset
    engine.addanalyzer(trader.analyzers.TimeReturn, timeframe=trader.TimeFrame.Years)
    engine.addanalyzer(trader.analyzers.SharpeRatio, timeframe=trader.TimeFrame.Years)
    engine.addanalyzer(trader.analyzers.SQN,)

    if args.pyfolio:
        engine.addanalyzer(trader.analyzers.PyFolio, _name='pyfolio',
                            timeframe=_TFRAMES[args.pftimeframe])

    if args.printout:
        print('Start run')
    results = engine.run()
    if args.printout:
        print('End Run')
    strat = results[0]

    # Results of own analyzers
    al = strat.analyzers.timereturn
    print('-- Time Return:')
    for k, v in al.get_analysis().items():
        print('{}: {}'.format(k, v))

    al = strat.analyzers.sharperatio
    print('-- Sharpe Ratio:')
    for k, v in al.get_analysis().items():
        print('{}: {}'.format(k, v))

    al = strat.analyzers.sqn
    print('-- SQN:')
    for k, v in al.get_analysis().items():
        print('{}: {}'.format(k, v))

    if args.pyfolio:
        pyfoliozer = strat.analyzers.getbyname('pyfolio',)

        returns, positions, transactions, gross_lev = pyfoliozer.get_pf_items()
        if args.printout:
            print('-- RETURNS')
            print(returns)
            print('-- POSITIONS')
            print(positions)
            print('-- TRANSACTIONS')
            print(transactions)
            print('-- GROSS LEVERAGE')
            print(gross_lev)

        if True:
            import pyfolio as pf
            pf.create_full_tear_sheet(
                returns,
                positions=positions,
                transactions=transactions,
                gross_lev=gross_lev,
                round_trips=True)

    if args.plot:
        pkwargs = dict(style='bar')
        if args.plot is not True:  # evals to True but is not True
            pkwargs = eval('dict(' + args.plot + ')')  # args were passed

        engine.plot(**pkwargs)


def parse_args(pargs=None):

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Sample for pivot point and cross plotting')

    parser.add_argument('--data0', required=True,
                        help='Data to be read in')

    parser.add_argument('--timeframe', required=False,
                        default=_TFS[0], choices=_TFS,
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--compression', required=False,
                        default=1, type=int,
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--fromdate', required=False,
                        default='2013-01-01',
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--todate', required=False,
                        default='2015-12-31',
                        help='Ending date in YYYY-MM-DD format')

    parser.add_argument('--stake', required=False, action='store',
                        default=10, type=int,
                        help=('Stake size'))

    parser.add_argument('--short', required=False, action='store_true',
                        help=('Go short too'))

    parser.add_argument('--cash', required=False, action='store',
                        type=float, default=50000,
                        help=('Cash to start with'))

    parser.add_argument('--pyfolio', required=False, action='store_true',
                        help=('Do pyfolio things'))

    parser.add_argument('--pftimeframe', required=False,
                        default='days', choices=_TFS,
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--printout', required=False, action='store_true',
                        help=('Print infos'))

    parser.add_argument('--printdata', required=False, action='store_true',
                        help=('Print data lines'))

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
