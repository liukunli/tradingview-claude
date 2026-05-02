#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime
import math

# The above could be sent to an independent module
import quanttrader as trader
import quanttrader.feeds
import quanttrader.utils.flushfile
import quanttrader.filters

from relativevolume import RelativeVolume


def runstrategy():
    args = parse_args()

    # Create a engine
    engine = trader.Engine()

    # Get the dates from the args
    fromdate = datetime.datetime.strptime(args.fromdate, '%Y-%m-%d')
    todate = datetime.datetime.strptime(args.todate, '%Y-%m-%d')

    # Get the session times to pass them to the indicator
    # datetime.time has no strptime ...
    dtstart = datetime.datetime.strptime(args.tstart, '%H:%M')
    dtend = datetime.datetime.strptime(args.tend, '%H:%M')

    # Create the 1st data
    data = trader.feeds.QuanttraderCSVData(
        dataname=args.data,
        fromdate=fromdate,
        todate=todate,
        timeframe=trader.TimeFrame.Minutes,
        compression=1,
        sessionstart=dtstart,  # internally just the "time" part will be used
        sessionend=dtend,  # internally just the "time" part will be used
    )

    if args.filter:
        data.addfilter(btfilters.SessionFilter)

    if args.filler:
        data.addfilter(btfilters.SessionFiller, fill_vol=args.fvol)

    # Add the data to engine
    engine.adddata(data)

    if args.relvol:
        # Calculate backward period - tend tstart are in same day
        # + 1 to include last moment of the interval dstart <-> dtend
        td = ((dtend - dtstart).seconds // 60) + 1
        engine.addindicator(RelativeVolume,
                             period=td,
                             volisnan=math.isnan(args.fvol))

    # Add an empty strategy
    engine.addstrategy(trader.Strategy)

    # Add a writer with CSV
    if args.writer:
        engine.addwriter(trader.WriterFile, csv=args.wrcsv)

    # And run it - no trading - disable stdstats
    engine.run(stdstats=False)

    # Plot if requested
    if args.plot:
        engine.plot(numfigs=args.numfigs, volume=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description='DataFilter/DataFiller Sample')

    parser.add_argument('--data', '-d',
                        default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/2006-01-02-volume-min-001.txt',
                        help='data to add to the system')

    parser.add_argument('--filter', '-ft', action='store_true',
                        help='Filter using session start/end times')

    parser.add_argument('--filler', '-fl', action='store_true',
                        help='Fill missing bars inside start/end times')

    parser.add_argument('--fvol', required=False, default=0.0,
                        type=float,
                        help='Use as fill volume for missing bar (def: 0.0)')

    parser.add_argument('--tstart', '-ts',
                        # default='09:14:59',
                        # help='Start time for the Session Filter (%H:%M:%S)')
                        default='09:15',
                        help='Start time for the Session Filter (HH:MM)')

    parser.add_argument('--tend', '-te',
                        # default='17:15:59',
                        # help='End time for the Session Filter (%H:%M:%S)')
                        default='17:15',
                        help='End time for the Session Filter (HH:MM)')

    parser.add_argument('--relvol', '-rv', action='store_true',
                        help='Add relative volume indicator')

    parser.add_argument('--fromdate', '-f',
                        default='2006-01-01',
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--todate', '-t',
                        default='2006-12-31',
                        help='Starting date in YYYY-MM-DD format')

    parser.add_argument('--writer', '-w', action='store_true',
                        help='Add a writer to engine')

    parser.add_argument('--wrcsv', '-wc', action='store_true',
                        help='Enable CSV Output in the writer')

    parser.add_argument('--plot', '-p', action='store_true',
                        help='Plot the read data')

    parser.add_argument('--numfigs', '-n', default=1,
                        help='Plot using numfigs figures')

    return parser.parse_args()


if __name__ == '__main__':
    runstrategy()
