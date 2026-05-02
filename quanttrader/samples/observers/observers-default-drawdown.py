#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime
import os.path
import time
import sys


import quanttrader as trader
import quanttrader.feeds
from quanttrader import indicators as indicators


class MyStrategy(trader.Strategy):
    params = (('smaperiod', 15),)

    def log(self, txt, dt=None):
        ''' Logging function fot this strategy'''
        dt = dt or self.data.datetime[0]
        if isinstance(dt, float):
            dt = trader.num2date(dt)
        print('%s, %s' % (dt.isoformat(), txt))

    def __init__(self):
        # SimpleMovingAverage on main data
        # Equivalent to -> sma = indicators.SMA(self.data, period=self.p.smaperiod)
        sma = indicators.SMA(period=self.p.smaperiod)

        # CrossOver (1: up, -1: down) close / sma
        self.buysell = indicators.CrossOver(self.data.close, sma, plot=True)

        # Sentinel to None: new ordersa allowed
        self.order = None

    def next(self):
        # Access -1, because drawdown[0] will be calculated after "next"
        self.log('DrawDown: %.2f' % self.stats.drawdown.drawdown[-1])
        self.log('MaxDrawDown: %.2f' % self.stats.drawdown.maxdrawdown[-1])

        # Check if we are in the market
        if self.position:
            if self.buysell < 0:
                self.log('SELL CREATE, %.2f' % self.data.close[0])
                self.sell()

        elif self.buysell > 0:
            self.log('BUY CREATE, %.2f' % self.data.close[0])
            self.buy()


def runstrat():
    engine = trader.Engine()

    data = trader.feeds.QuanttraderCSVData(dataname='/Users/kunliliu/Documents/GitHub/quanttrader/datas/2006-day-001.txt')
    engine.adddata(data)

    engine.addobserver(trader.observers.DrawDown)
    engine.addobserver(trader.observers.DrawDown_Old)

    engine.addstrategy(MyStrategy)
    engine.run()

    engine.plot()


if __name__ == '__main__':
    runstrat()
