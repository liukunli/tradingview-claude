#!/usr/bin/env python

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import argparse
import datetime

# The above could be sent to an independent module
import quanttrader as trader
import quanttrader.feeds

from relvolbybar import RelativeVolumeByBar


def runstrategy():
    args = parse_args()

    # Create a engine
    engine = trader.Engine()

    # Get the dates from the args
    fromdate = datetime.datetime.strptime(args.fromdate, '%Y-%m-%d')
    todate = datetime.datetime.strptime(args.todate, '%Y-%m-%d')

    # Create the 1st data
    data = trader.feeds.QuanttraderCSVData(
        dataname=args.data,
        fromdate=fromdate,
        todate=todate,
        )

    # Add the 1st data to engine
    engine.adddata(data)

    # Add an empty strategy
    engine.addstrategy(trader.Strategy)

    # Get the session times to pass them to the indicator
    prestart = datetime.datetime.strptime(args.prestart, '%H:%M').time()
    start = datetime.datetime.strptime(args.start, '%H:%M').time()
    end = datetime.datetime.strptime(args.end, '%H:%M').time()

    # Add the Relative volume indicator
    engine.addindicator(RelativeVolumeByBar,
                         prestart=prestart, start=start, end=end)

    # Add a writer with CSV
    if args.writer:
        engine.addwriter(trader.WriterFile, csv=args.wrcsv)

    # And run it
    engine.run(stdstats=False)

    # Plot if requested
    if args.plot:
        engine.plot(numfigs=args.numfigs, volume=True)


def parse_args():
    parser = argparse.ArgumentParser(description='MultiData Strategy')

    parser.add_argument('--data', '-d',
                        default='/Users/kunliliu/Documents/GitHub/quanttrader/datas/2006-01-02-volume-min-001.txt',
                        help='data to add to the system')

    parser.add_argument('--prestart',
                        default='08:00',
                        help='Start time for the Session Filter')

    parser.add_argument('--start',
                        default='09:15',
                        help='Start time for the Session Filter')

    parser.add_argument('--end', '-te',
                        default='17:15',
                        help='End time for the Session Filter')

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
