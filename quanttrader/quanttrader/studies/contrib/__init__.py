#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import quanttrader as trader

from .import fractal as fractal
for name in fractal.__all__:
    setattr(trader.studies, name, getattr(fractal, name))
