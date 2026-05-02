#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import testcommon

import quanttrader as trader
from quanttrader import indicators as indicators

chkdatas = 1
chkvals = [
    ['4065.884000', '3621.185000', '3582.895500'],
    ['4190.782310', '3712.008864', '3709.453081'],
    ['3940.985690', '3530.361136', '3456.337919'],
]

chkmin = 20
chkind = indicators.BBands


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
