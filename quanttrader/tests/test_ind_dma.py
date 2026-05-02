#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import testcommon

import quanttrader as trader
from quanttrader import indicators as indicators

chkdatas = 1
chkvals = [
    ['4121.903804', '3677.634675', '3579.962958']
]


chkmin = 30
chkind = indicators.DMA


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
