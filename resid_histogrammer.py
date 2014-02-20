#!/usr/bin/env python

import sys
from pylab import *

from optparse import OptionParser

parser = OptionParser("resid_historgrammer.py [options] <file1> [<file2> ...]")
parser.add_option("--bins", type=int, help="Number of histogram bins to use", default=1000)

(opts, args) = parser.parse_args()

def safe_float(s):
    try:
        return float(s)
    except ValueError:
        return 0.0

for f in args:
    with open(f) as dfile:
        d = [[] for i in range(32)]
        for l in dfile:
            row = [safe_float(x) for x in l.split(',')]

            for i in range(32):
                if row[i] != 0 and abs(row[i]) < 1000.0:
                    d[i].append(row[i]) 

        t = []
        for i in range(32):
            t.extend(d[i])

        print(max(t), min(t))

        figure()
        title(f)
        hist(t, bins=opts.bins)

show()

