#!/usr/bin/env python

import sys
from pylab import *

from optparse import OptionParser

parser = OptionParser("resid_elscatter.py <resfile> <elfile>")

(opts, args) = parser.parse_args()

def safe_float(s):
    try:
        return float(s)
    except ValueError:
        return 0.0

rfile = open(args[0])
efile = open(args[1])

xdat, ydat = [], []

while True:
    rline = rfile.readline().split(',')
    eline = efile.readline().split(',')

    rline = [safe_float(x) for x in rline]
    eline = [safe_float(x) for x in eline]

    if len(rline) != 33 or len(eline) != 33:
        break

    for i in range(32):
        if rline[i] != 0: #and abs(rline[i]) < 1000.0 and eline[i] != 0:
            xdat.append(eline[i])
            ydat.append(rline[i])

figure()
title("Correction vs Elevation")
scatter(xdat,ydat)
show()

