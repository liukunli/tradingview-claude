#!/usr/bin/env python

import testcommon

class TestFrompackages(testcommon.SampleParamsHolder):
    """
    This class is used for testing that inheriting from base class that
    uses `frompackages` import mechanism, doesnt brake the functionality
    of the base class.
    """
    def __init__(self):
        super(TestFrompackages, self).__init__()
        # Prepare the lags array

def test_run(main=False):
    """
    Instantiate the TestFrompackages and see that no exception is raised
    Bug Discussion:
    https://community.trader.com/topic/2661/frompackages-directive-functionality-seems-to-be-broken-when-using-inheritance
    """
    test = TestFrompackages()

if __name__ == '__main__':
    test_run(main=True)
