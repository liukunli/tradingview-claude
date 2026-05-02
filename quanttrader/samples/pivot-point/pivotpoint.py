#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,)
#                        unicode_literals)

import quanttrader as trader


class PivotPoint1(trader.Indicator):
    lines = ('p', 's1', 's2', 'r1', 'r2',)

    def __init__(self):
        h = self.data.high(-1)  # previous high
        l = self.data.low(-1)  # previous low
        c = self.data.close(-1)  # previous close

        self.lines.p = p = (h + l + c) / 3.0

        p2 = p * 2.0
        self.lines.s1 = p2 - h  # (p x 2) - high
        self.lines.r1 = p2 - l  # (p x 2) - low

        hilo = h - l
        self.lines.s2 = p - hilo  # p - (high - low)
        self.lines.r2 = p + hilo  # p + (high - low)


class PivotPoint(trader.Indicator):
    lines = ('p', 's1', 's2', 'r1', 'r2',)
    plotinfo = dict(subplot=False)

    def __init__(self):
        h = self.data.high  # current high
        l = self.data.low  # current high
        c = self.data.close  # current high

        self.lines.p = p = (h + l + c) / 3.0

        p2 = p * 2.0
        self.lines.s1 = p2 - h  # (p x 2) - high
        self.lines.r1 = p2 - l  # (p x 2) - low

        hilo = h - l
        self.lines.s2 = p - hilo  # p - (high - low)
        self.lines.r2 = p + hilo  # p + (high - low)
