#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)


from . import GenericCSVData


class MT4CSVData(GenericCSVData):
    '''
    Parses a `Metatrader4 <https://www.metaquotes.net/en/metatrader4>`_ History
    center CSV exported file.

    Specific parameters (or specific meaning):

      - ``dataname``: The filename to parse or a file-like object

      - Uses GenericCSVData and simply modifies the params
    '''

    params = (
        ('dtformat', '%Y.%m.%d'),
        ('tmformat', '%H:%M'),
        ('datetime', 0),
        ('time',  1),
        ('open',  2),
        ('high',  3),
        ('low',   4),
        ('close', 5),
        ('volume', 6),
        ('openinterest', -1),
    )
