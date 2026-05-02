#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import testcommon

import quanttrader as trader


chkdatas = 1
chkvals = [
    ['nan', 'nan', 'nan'],
    ['nan', 'nan', '3553.692850']
]

chkmin = 5
chkind = trader.studies.Fractal


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
