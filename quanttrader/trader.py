"""
Compatibility shim: re-export the `quanttrader` package as `trader`.

Some tests and older code import `trader` directly. This module
makes `import trader` work by exposing the `quanttrader` package
symbols at top level.
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import quanttrader as _qt

# Re-export common names from quanttrader for compatibility
from quanttrader import *  # noqa: F401,F403

# Also make the package object available as the module
__all__ = getattr(_qt, '__all__', [])
