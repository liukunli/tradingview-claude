#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

# The modules below should/must define __all__ with the objects wishes
# or prepend an "_" (underscore) to private classes/variables

try:
    from .ibstore import IBStore
except ImportError:
    pass  # The user may not have ibpy installed

try:
    from .vcstore import VCStore
except ImportError:
    pass  # The user may not have a module installed

try:
    from .oandastore import OandaStore
except ImportError:
    pass  # The user may not have a module installed


from .vchartfile import VChartFile
