#!/usr/bin/env python

from datetime import datetime
import quanttrader as trader


class SmaCross(trader.SignalStrategy):
    def __init__(self):
        sma1 = trader.ind.SMA(period=10)
        sma2 = trader.ind.SMA(period=30)
        crossover = trader.ind.CrossOver(sma1, sma2)
        self.signal_add(trader.SIGNAL_LONG, crossover)


engine = trader.Engine()
engine.addstrategy(SmaCross)

data0 = trader.feeds.YahooFinanceData(dataname='YHOO',
                                  fromdate=datetime(2011, 1, 1),
                                  todate=datetime(2012, 12, 31))

engine.adddata(data0)

engine.run()
engine.plot()
