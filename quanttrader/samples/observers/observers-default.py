#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import quanttrader as trader
import quanttrader.feeds

if __name__ == '__main__':
    engine = trader.Engine(stdstats=True)
    engine.addstrategy(trader.Strategy)

    data = trader.feeds.QuanttraderCSVData(dataname='/Users/kunliliu/Documents/GitHub/quanttrader/datas/2006-day-001.txt')
    engine.adddata(data)

    engine.run()
    engine.plot()
