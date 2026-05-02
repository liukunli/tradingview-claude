#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import random
import quanttrader as trader


# The filter which changes the close price
def close_changer(data, *args, **kwargs):
    data.close[0] += 50.0 * random.randint(-1, 1)
    return False  # length of stream is unchanged


# override the standard markers
class BuySellArrows(trader.observers.BuySell):
    plotlines = dict(buy=dict(marker='$\u21E7$', markersize=12.0),
                     sell=dict(marker='$\u21E9$', markersize=12.0))


class St(trader.Strategy):
    def __init__(self):
        trader.obs.BuySell(self.data0, barplot=True)  # done here for
        BuySellArrows(self.data1, barplot=True)  # different markers per data

    def next(self):
        if not self.position:
            if random.randint(0, 1):
                self.buy(data=self.data0)
                self.entered = len(self)

        else:  # in the market
            if (len(self) - self.entered) >= 10:
                self.sell(data=self.data1)


def runstrat(args=None):
    args = parse_args(args)
    engine = trader.Engine()

    dataname = '/Users/kunliliu/Documents/GitHub/quanttrader/datas/2006-day-001.txt'  # data feed

    data0 = trader.feeds.QuanttraderCSVData(dataname=dataname, name='data0')
    engine.adddata(data0)

    data1 = trader.feeds.QuanttraderCSVData(dataname=dataname, name='data1')
    data1.addfilter(close_changer)
    if not args.no_comp:
        data1.compensate(data0)
    data1.plotinfo.plotmaster = data0
    if args.sameaxis:
        data1.plotinfo.sameaxis = True
    engine.adddata(data1)

    engine.addstrategy(St)  # sample strategy

    engine.addobserver(trader.obs.Broker)  # removed below with stdstats=False
    engine.addobserver(trader.obs.Trades)  # removed below with stdstats=False

    engine.broker.set_coc(True)
    engine.run(stdstats=False)  # execute
    engine.plot(volume=False)  # and plot


def parse_args(pargs=None):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=('Compensation example'))

    parser.add_argument('--no-comp', required=False, action='store_true')
    parser.add_argument('--sameaxis', required=False, action='store_true')
    return parser.parse_args(pargs)


if __name__ == '__main__':
    runstrat()
