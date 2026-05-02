#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime

import quanttrader as trader


class TALibStrategy(trader.Strategy):
    params = (('ind', 'sma'), ('doji', True),)

    INDS = ['sma', 'ema', 'stoc', 'rsi', 'macd', 'bollinger', 'aroon',
            'ultimate', 'trix', 'kama', 'adxr', 'dema', 'ppo', 'tema',
            'roc', 'williamsr']

    def __init__(self):
        if self.p.doji:
            trader.talib.CDLDOJI(self.data.open, self.data.high,
                             self.data.low, self.data.close)

        if self.p.ind == 'sma':
            trader.talib.SMA(self.data.close, timeperiod=25, plotname='TA_SMA')
            trader.indicators.SMA(self.data, period=25)
        elif self.p.ind == 'ema':
            trader.talib.EMA(timeperiod=25, plotname='TA_SMA')
            trader.indicators.EMA(period=25)
        elif self.p.ind == 'stoc':
            trader.talib.STOCH(self.data.high, self.data.low, self.data.close,
                           fastk_period=14, slowk_period=3, slowd_period=3,
                           plotname='TA_STOCH')

            trader.indicators.Stochastic(self.data)

        elif self.p.ind == 'macd':
            trader.talib.MACD(self.data, plotname='TA_MACD')
            trader.indicators.MACD(self.data)
            trader.indicators.MACDHisto(self.data)
        elif self.p.ind == 'bollinger':
            trader.talib.BBANDS(self.data, timeperiod=25,
                            plotname='TA_BBANDS')
            trader.indicators.BollingerBands(self.data, period=25)

        elif self.p.ind == 'rsi':
            trader.talib.RSI(self.data, plotname='TA_RSI')
            trader.indicators.RSI(self.data)

        elif self.p.ind == 'aroon':
            trader.talib.AROON(self.data.high, self.data.low, plotname='TA_AROON')
            trader.indicators.AroonIndicator(self.data)

        elif self.p.ind == 'ultimate':
            trader.talib.ULTOSC(self.data.high, self.data.low, self.data.close,
                            plotname='TA_ULTOSC')
            trader.indicators.UltimateOscillator(self.data)

        elif self.p.ind == 'trix':
            trader.talib.TRIX(self.data, timeperiod=25,  plotname='TA_TRIX')
            trader.indicators.Trix(self.data, period=25)

        elif self.p.ind == 'adxr':
            trader.talib.ADXR(self.data.high, self.data.low, self.data.close,
                          plotname='TA_ADXR')
            trader.indicators.ADXR(self.data)

        elif self.p.ind == 'kama':
            trader.talib.KAMA(self.data, timeperiod=25, plotname='TA_KAMA')
            trader.indicators.KAMA(self.data, period=25)

        elif self.p.ind == 'dema':
            trader.talib.DEMA(self.data, timeperiod=25, plotname='TA_DEMA')
            trader.indicators.DEMA(self.data, period=25)

        elif self.p.ind == 'ppo':
            trader.talib.PPO(self.data, plotname='TA_PPO')
            trader.indicators.PPO(self.data, _movav=trader.indicators.SMA)

        elif self.p.ind == 'tema':
            trader.talib.TEMA(self.data, timeperiod=25, plotname='TA_TEMA')
            trader.indicators.TEMA(self.data, period=25)

        elif self.p.ind == 'roc':
            trader.talib.ROC(self.data, timeperiod=12, plotname='TA_ROC')
            trader.talib.ROCP(self.data, timeperiod=12, plotname='TA_ROCP')
            trader.talib.ROCR(self.data, timeperiod=12, plotname='TA_ROCR')
            trader.talib.ROCR100(self.data, timeperiod=12, plotname='TA_ROCR100')
            trader.indicators.ROC(self.data, period=12)
            trader.indicators.Momentum(self.data, period=12)
            trader.indicators.MomentumOscillator(self.data, period=12)

        elif self.p.ind == 'williamsr':
            trader.talib.WILLR(self.data.high, self.data.low, self.data.close,
                           plotname='TA_WILLR')
            trader.indicators.WilliamsR(self.data)


def runstrat(args=None):
    args = parse_args(args)

    engine = trader.Engine()

    dkwargs = dict()
    if args.fromdate:
        fromdate = datetime.datetime.strptime(args.fromdate, '%Y-%m-%d')
        dkwargs['fromdate'] = fromdate

    if args.todate:
        todate = datetime.datetime.strptime(args.todate, '%Y-%m-%d')
        dkwargs['todate'] = todate

    data0 = trader.feeds.YahooFinanceCSVData(dataname=args.data0, **dkwargs)
    engine.adddata(data0)

    engine.addstrategy(TALibStrategy, ind=args.ind, doji=not args.no_doji)

    engine.run(runcone=not args.use_next, stdstats=False)
    if args.plot:
        pkwargs = dict(style='candle')
        if args.plot is not True:  # evals to True but is not True
            npkwargs = eval('dict(' + args.plot + ')')  # args were passed
            pkwargs.update(npkwargs)

        engine.plot(**pkwargs)


def parse_args(pargs=None):

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Sample for sizer')

    parser.add_argument('--data0', required=False,
                        default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/yhoo-1996-2015.txt',
                        help='Data to be read in')

    parser.add_argument('--fromdate', required=False,
                        default='2005-01-01',
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--todate', required=False,
                        default='2006-12-31',
                        help='Ending date in YYYY-MM-DD format')

    parser.add_argument('--ind', required=False, action='store',
                        default=TALibStrategy.INDS[0],
                        choices=TALibStrategy.INDS,
                        help=('Which indicator pair to show together'))

    parser.add_argument('--no-doji', required=False, action='store_true',
                        help=('Remove Doji CandleStick pattern checker'))

    parser.add_argument('--use-next', required=False, action='store_true',
                        help=('Use next (step by step) '
                              'instead of once (batch)'))

    # Plot options
    parser.add_argument('--plot', '-p', nargs='?', required=False,
                        metavar='kwargs', const=True,
                        help=('Plot the read data applying any kwargs passed\n'
                              '\n'
                              'For example (escape the quotes if needed):\n'
                              '\n'
                              '  --plot style="candle" (to plot candles)\n'))

    if pargs is not None:
        return parser.parse_args(pargs)

    return parser.parse_args()


if __name__ == '__main__':
    runstrat()
