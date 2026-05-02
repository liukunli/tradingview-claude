#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import quanttrader as trader

from .import vortex as vortex
for name in vortex.__all__:
    setattr(trader.indicators, name, getattr(vortex, name))
