#!/usr/bin/env python

import base64
import sys, time

f = open(sys.argv[1])

start = time.time()
fstart = -1

for l in f:
    t, data = l.split(":")

    if fstart == -1:
        fstart = float(t)

    tosleep = (float(t) - fstart) - (time.time() - start)

    if tosleep > 0.01:
        time.sleep(tosleep)

    print base64.b64decode(data)

