#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import testcommon

import quanttrader as trader

chkdatas = 1
chkvals = [
    ['51.991177', '62.334055', '46.707445']
]

chkmin = 29  # 28 from longest SumN/Sum + 1 extra from truelow/truerange
chkind = trader.indicators.UltimateOscillator


def test_run(main=False):
    datas = [testcommon.getdata(i) for i in range(chkdatas)]
    testcommon.runtest(datas,
                       testcommon.TestStrategy,
                       main=main,
                       plot=main,
                       chkind=chkind,
                       chkmin=chkmin,
                       chkvals=chkvals)


if __name__ == '__main__':
    test_run(main=True)
