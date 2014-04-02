#!/usr/bin/env python

import ublox, sys

dev = ublox.UBlox(sys.argv[1])

while True:
    msg = dev.receive_message(ignore_eof=False)
    if msg is None:
        break
    if msg.name() in ['NAV_POSECEF', 'NAV_SOL']:
        try:
            msg.unpack()
            print("{},{},{}".format(msg.ecefX * 0.01, msg.ecefY * 0.01, msg.ecefZ * 0.01))
        except ublox.UBloxError as e:
            print e.message
    sys.stdout.flush()

