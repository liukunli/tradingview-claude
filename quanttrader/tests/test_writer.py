#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import time

import testcommon

import quanttrader as trader
from quanttrader import indicators as indicators


chkdatas = 1


class TestStrategy(trader.Strategy):
    params = dict(main=False)

    def __init__(self):
        indicators.SMA()


def test_run(main=False):
    datas = [testcommon.getdata(i) for i in range(chkdatas)]
    engines = testcommon.runtest(datas,
                                  TestStrategy,
                                  main=main,
                                  plot=main,
                                  writer=(trader.WriterStringIO, dict(csv=True)))

    for engine in engines:
        writer = engine.runwriters[0]
        if main:
            # writer.out.seek(0)
            for l in writer.out:
                print(l.rstrip('\r\n'))

        else:
            lines = iter(writer.out)
            l = next(lines).rstrip('\r\n')
            assert l == '=' * 79

            count = 0
            while True:
                l = next(lines).rstrip('\r\n')
                if l[0] == '=':
                    break
                count += 1

            assert count == 256  # header + 256 lines data


if __name__ == '__main__':
    test_run(main=True)
