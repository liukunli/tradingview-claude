#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import time
try:
    time_clock = time.process_time
except:
    time_clock = time.clock

import testcommon

import quanttrader as trader
from quanttrader import indicators as indicators
from quanttrader.utils.py3 import PY2


class TestStrategy(trader.Strategy):
    params = (
        ('period', 15),
        ('printdata', True),
        ('printops', True),
        ('stocklike', True),
    )

    def log(self, txt, dt=None, nodate=False):
        if not nodate:
            dt = dt or self.data.datetime[0]
            dt = trader.num2date(dt)
            print('%s, %s' % (dt.isoformat(), txt))
        else:
            print('---------- %s' % (txt))

    def notify_order(self, order):
        if order.status in [trader.Order.Submitted, trader.Order.Accepted]:
            return  # Await further notifications

        if order.status == order.Completed:
            if isinstance(order, trader.BuyOrder):
                if self.p.printops:
                    txt = 'BUY, %.2f' % order.executed.price
                    self.log(txt, order.executed.dt)
                chkprice = '%.2f' % order.executed.price
                self.buyexec.append(chkprice)
            else:  # elif isinstance(order, SellOrder):
                if self.p.printops:
                    txt = 'SELL, %.2f' % order.executed.price
                    self.log(txt, order.executed.dt)

                chkprice = '%.2f' % order.executed.price
                self.sellexec.append(chkprice)

        elif order.status in [order.Expired, order.Canceled, order.Margin]:
            if self.p.printops:
                self.log('%s ,' % order.Status[order.status])

        # Allow new orders
        self.orderid = None

    def __init__(self):
        # Flag to allow new orders in the system or not
        self.orderid = None

        self.sma = indicators.SMA(self.data, period=self.p.period)
        self.cross = indicators.CrossOver(self.data.close, self.sma, plot=True)

    def start(self):
        if not self.p.stocklike:
            self.broker.setcommission(commission=2.0, mult=10.0, margin=1000.0)

        if self.p.printdata:
            self.log('-------------------------', nodate=True)
            self.log('Starting portfolio value: %.2f' % self.broker.getvalue(),
                     nodate=True)

        self.tstart = time_clock()

        self.buycreate = list()
        self.sellcreate = list()
        self.buyexec = list()
        self.sellexec = list()

    def stop(self):
        tused = time_clock() - self.tstart
        if self.p.printdata:
            self.log('Time used: %s' % str(tused))
            self.log('Final portfolio value: %.2f' % self.broker.getvalue())
            self.log('Final cash value: %.2f' % self.broker.getcash())
            self.log('-------------------------')
        else:
            pass

    def next(self):
        if self.p.printdata:
            self.log(
                'Open, High, Low, Close, %.2f, %.2f, %.2f, %.2f, Sma, %f' %
                (self.data.open[0], self.data.high[0],
                 self.data.low[0], self.data.close[0],
                 self.sma[0]))
            self.log('Close %.2f - Sma %.2f' %
                     (self.data.close[0], self.sma[0]))

        if self.orderid:
            # if an order is active, no new orders are allowed
            return

        if not self.position.size:
            if self.cross > 0.0:
                if self.p.printops:
                    self.log('BUY CREATE , %.2f' % self.data.close[0])

                self.orderid = self.buy()
                chkprice = '%.2f' % self.data.close[0]
                self.buycreate.append(chkprice)

        elif self.cross < 0.0:
            if self.p.printops:
                self.log('SELL CREATE , %.2f' % self.data.close[0])

            self.orderid = self.close()
            chkprice = '%.2f' % self.data.close[0]
            self.sellcreate.append(chkprice)


chkdatas = 1


def test_run(main=False):
    datas = [testcommon.getdata(i) for i in range(chkdatas)]
    engines = testcommon.runtest(datas,
                                  TestStrategy,
                                  printdata=main,
                                  stocklike=False,
                                  printops=main,
                                  plot=main,
                                  analyzer=(trader.analyzers.TimeReturn,
                                            dict(timeframe=trader.TimeFrame.Years))
                                  )

    for engine in engines:
        strat = engine.runstrats[0][0]  # no optimization, only 1
        analyzer = strat.analyzers[0]  # only 1
        analysis = analyzer.get_analysis()
        if main:
            print(analysis)
            print(str(analysis[next(iter(analysis.keys()))]))
        else:
            # Handle different precision
            if PY2:
                sval = '0.2795'
            else:
                sval = '0.2794999999999983'

            assert str(analysis[next(iter(analysis.keys()))]) == sval


if __name__ == '__main__':
    test_run(main=True)
