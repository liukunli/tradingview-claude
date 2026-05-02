#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)


import quanttrader as trader
import quanttrader.indicators


class RelativeVolume(trader.Indicator):
    csv = True  # show up in csv output (default for indicators is False)

    lines = ('relvol',)
    params = (
        ('period', 20),
        ('volisnan', True),
    )

    def __init__(self):
        if self.p.volisnan:
            # if missing volume will be NaN, do a simple division
            # the end result for missing volumes will also be NaN
            relvol = self.data.volume(-self.p.period) / self.data.volume
        else:
            # Else do a controlled Div with a built-in function
            relvol = trader.DivByZero(
                self.data.volume(-self.p.period),
                self.data.volume,
                zero=0.0)

        self.lines.relvol = relvol
