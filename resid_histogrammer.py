#!/usr/bin/env python

import sys
from pylab import *

from optparse import OptionParser

parser = OptionParser("resid_historgrammer.py [options] <file1> [<file2> ...]")
parser.add_option("--bins", type=int, help="Number of histogram bins to use", default=1000)
parser.add_option("--min", type=int, help="Minimum value to plot", default=-1000)
parser.add_option("--max", type=int, help="Maximum value to plot", default=1000)
parser.add_option("--neg", action='store_true', help="Residuals stored with opposite sign")
parser.add_option("--drop-first", action='store_true', help="First column contains other data (e.g. timestamp)")

(opts, args) = parser.parse_args()

def safe_float(s):
    try:
        return float(s)
    except ValueError:
        return 0.0

for f in args:
    with open(f) as dfile:

        cols = len(dfile.readline().split(',')) - 1
        if opts.drop_first:
            cols = cols - 1

        print cols

        d = [[] for i in range(cols)]
        for l in dfile:
            row = [safe_float(x) for x in l.split(',')]
            if opts.drop_first:
                row = row[1:]

            if opts.neg:
                row = [-x for x in row]

            for i in range(cols):
                try:
                    if row[i] != 0 and row[i] < opts.max and row[i] > opts.min:
                        d[i].append(row[i])
                except IndexError:
                    continue

        t = []
        for i in range(cols):
            t.extend(d[i])

        print(max(t), min(t))

        figure()
        #title(f)
        hist(t, bins=opts.bins)

show()

