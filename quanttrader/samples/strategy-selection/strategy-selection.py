#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse

import quanttrader as trader


class St0(trader.SignalStrategy):
    def __init__(self):
        sma1, sma2 = trader.ind.SMA(period=10), trader.ind.SMA(period=30)
        crossover = trader.ind.CrossOver(sma1, sma2)
        self.signal_add(trader.SIGNAL_LONG, crossover)


class St1(trader.SignalStrategy):
    def __init__(self):
        sma1 = trader.ind.SMA(period=10)
        crossover = trader.ind.CrossOver(self.data.close, sma1)
        self.signal_add(trader.SIGNAL_LONG, crossover)


class StFetcher(object):
    _STRATS = [St0, St1]

    def __new__(cls, *args, **kwargs):
        idx = kwargs.pop('idx')

        obj = cls._STRATS[idx](*args, **kwargs)
        return obj


def runstrat(pargs=None):
    args = parse_args(pargs)

    engine = trader.Engine()
    data = trader.feeds.QuanttraderCSVData(dataname=args.data)
    engine.adddata(data)

    engine.addanalyzer(trader.analyzers.Returns)
    engine.optstrategy(StFetcher, idx=[0, 1])
    results = engine.run(maxcpus=args.maxcpus, optreturn=args.optreturn)

    strats = [x[0] for x in results]  # flatten the result
    for i, strat in enumerate(strats):
        rets = strat.analyzers.returns.get_analysis()
        print('Strat {} Name {}:\n  - analyzer: {}\n'.format(
            i, strat.__class__.__name__, rets))


def parse_args(pargs=None):

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Sample for strategy selection')

    parser.add_argument('--data', required=False,
                        default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/2005-2006-day-001.txt',
                        help='Data to be read in')

    parser.add_argument('--maxcpus', required=False, action='store',
                        default=None, type=int,
                        help='Limit the numer of CPUs to use')

    parser.add_argument('--optreturn', required=False, action='store_true',
                        help='Return reduced/mocked strategy object')

    return parser.parse_args(pargs)


if __name__ == '__main__':
    runstrat()
