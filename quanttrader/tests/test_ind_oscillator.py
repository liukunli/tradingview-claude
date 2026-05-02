#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import testcommon

import quanttrader as trader
from quanttrader import indicators as indicators

chkdatas = 1
chkvals = [
    ['56.477000', '51.185333', '2.386667']
]

chkmin = 30
chkind = indicators.Oscillator


class TS2(testcommon.TestStrategy):
    def __init__(self):
        ind = indicators.MovAv.SMA(self.data)
        self.p.inddata = [ind]
        super(TS2, self).__init__()


def test_run(main=False):
    datas = [testcommon.getdata(i) for i in range(chkdatas)]
    testcommon.runtest(datas,
                       TS2,
                       main=main,
                       plot=main,
                       chkind=chkind,
                       chkmin=chkmin,
                       chkvals=chkvals)


if __name__ == '__main__':
    test_run(main=True)
