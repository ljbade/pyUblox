#!/usr/bin/env python
'''
Locally-generated DGPS corrections, publish as UDP datagrams
'''

import ublox, sys, time, struct, select, subprocess
import ephemeris
import RTCMv2

from optparse import OptionParser

parser = OptionParser("local_to_udp.py [options]")
parser.add_option("--port1", help="serial port", default=None)
parser.add_option("--port2", help="serial port", default=None)
parser.add_option("--port3", help="serial port", default=None)

parser.add_option("--baudrate", type='int',
                  help="serial baud rate", default=115200)
parser.add_option("--prefix", help="log file", default='')
parser.add_option("--usePPP", type='int', default=0, help="usePPP on recv1")
parser.add_option("--dynmodel1", type='int', default=ublox.DYNAMIC_MODEL_STATIONARY, help="dynamic model for recv1")
parser.add_option("--append", action='store_true', default=False, help='append to log file')
parser.add_option("--module-reset", action='store_true', help="cold start all the modules")

parser.add_option("--ntrip-server", default='192.104.43.25')
parser.add_option("--ntrip-port", type='int', default=2101)
parser.add_option("--ntrip-user")
parser.add_option("--ntrip-password")
parser.add_option("--ntrip-mount", default='TID10')

(opts, args) = parser.parse_args()

def setup_port(port, log, append=False):
    dev = ublox.UBlox(port, baudrate=opts.baudrate, timeout=0.01)
    dev.set_logfile(log, append=append)
    dev.set_binary()
    dev.configure_poll_port()
    dev.configure_poll(ublox.CLASS_CFG, ublox.MSG_CFG_USB)
    dev.configure_poll(ublox.CLASS_CFG, ublox.MSG_CFG_NAVX5)
    dev.configure_poll(ublox.CLASS_MON, ublox.MSG_MON_HW)
    dev.configure_poll(ublox.CLASS_NAV, ublox.MSG_NAV_DGPS)
    dev.configure_poll(ublox.CLASS_MON, ublox.MSG_MON_VER)
    dev.configure_port(port=ublox.PORT_SERIAL1, inMask=0x7, outMask=1)
    dev.configure_port(port=ublox.PORT_USB, inMask=0x7, outMask=1)
    dev.configure_port(port=ublox.PORT_SERIAL2, inMask=0x7, outMask=1)
    dev.configure_poll_port()
    dev.configure_poll_port(ublox.PORT_SERIAL1)
    dev.configure_poll_port(ublox.PORT_SERIAL2)
    dev.configure_poll_port(ublox.PORT_USB)

    dev.configure_message_rate(ublox.CLASS_NAV, ublox.MSG_NAV_POSLLH, 1)
    dev.configure_message_rate(ublox.CLASS_NAV, ublox.MSG_NAV_POSECEF, 1)
    dev.configure_message_rate(ublox.CLASS_NAV, ublox.MSG_NAV_SOL, 1)
    dev.configure_message_rate(ublox.CLASS_RXM, ublox.MSG_RXM_RAW, 1)
    dev.configure_message_rate(ublox.CLASS_RXM, ublox.MSG_RXM_SFRB, 1)
    dev.configure_message_rate(ublox.CLASS_AID, ublox.MSG_AID_EPH, 1)
    dev.configure_message_rate(ublox.CLASS_NAV, ublox.MSG_NAV_SVINFO, 1)
    dev.configure_solution_rate(rate_ms=200)


    # we want the ground station to use a stationary model, and the roving
    # GPS to use a highly dynamic model
    dev.set_preferred_dynamic_model(opts.dynmodel1)

    # enable PPP on the ground side if we can
    dev.set_preferred_usePPP(opts.usePPP)

    return dev

if opts.port1 is not None:
    logfile = time.strftime(opts.prefix + 'port1-%y%m%d-%H%M.ubx')
    dev1 = setup_port(opts.port1, logfile, append=opts.append)

if opts.port2 is not None:
    logfile = time.strftime(opts.prefix + 'port2-%y%m%d-%H%M.ubx')
    dev2 = setup_port(opts.port2, logfile, append=opts.append)
else:
    dev2 = None

if opts.port3 is not None:
    logfile = time.strftime(opts.prefix + 'port3-%y%m%d-%H%M.ubx')
    dev3 = setup_port(opts.port3, logfile, append=opts.append)
else:
    dev3 = None

if opts.ntrip_user is not None:
    nt = subprocess.Popen(["./ntrip.py",
            opts.ntrip_server,
            str(opts.ntrip_port),
            opts.ntrip_user,
            opts.ntrip_password,
            opts.ntrip_mount],
        stdout=subprocess.PIPE)
    ntrip_pipe = nt.stdout

    nfile = open(time.strftime(opts.prefix + 'ntrip-%y%m%d-%H%M.rtcm3'), 'wb')
else:
    ntrip_pipe = None


# which SV IDs we have seen
svid_seen = {}
svid_ephemeris = {}

def handle_rxm_raw(msg):
    '''handle a RXM_RAW message'''
    global svid_seen, svid_ephemeris

    for i in range(msg.numSV):
        sv = msg.recs[i].sv
        tnow = time.time()
        if not sv in svid_seen or tnow > svid_seen[sv]+30:
            if sv in svid_ephemeris and svid_ephemeris[sv].timereceived+1800 < tnow:
                continue
            dev1.configure_poll(ublox.CLASS_AID, ublox.MSG_AID_EPH, struct.pack('<B', sv))

            if dev2 is not None:
                dev2.configure_poll(ublox.CLASS_AID, ublox.MSG_AID_EPH, struct.pack('<B', sv))

            if dev3 is not None:
                dev3.configure_poll(ublox.CLASS_AID, ublox.MSG_AID_EPH, struct.pack('<B', sv))

            svid_seen[sv] = tnow

last_msg1_time = time.time()

messages = {}

def handle_device1(msg):
    '''handle message from reference GPS'''
    global messages, satinfo
    
    if msg.name() == 'RXM_RAW':
        try:
            msg.unpack()
        except ublox.UBloxError as e:
            print(e)

        handle_rxm_raw(msg)

pos_count = 0

while True:

    if opts.port1 is not None:
        # get a message from the reference GPS
        msg = dev1.receive_message_noerror()

        if msg is not None:
            handle_device1(msg)
            last_msg1_time = time.time()

            print '1: {}'.format(msg.name())

    if dev2 is not None:
        msg = dev2.receive_message_noerror()
        if msg is not None:
            print '2: {}'.format(msg.name())

    if dev3 is not None:
        msg = dev3.receive_message_noerror()
        if msg is not None:
            print '3: {}'.format(msg.name())

    if opts.ntrip_user is not None:
        # There's got to be a better way (without threading)
        r, w, x = select.select([ntrip_pipe], [nfile], [], 0)
        up = False
        while ntrip_pipe in r and nfile in w:
            up = True
            nfile.write(ntrip_pipe.read(1))
            r, w, x = select.select([ntrip_pipe], [nfile], [], 0)

        if up:
            print 'N'
            nfile.flush()

    sys.stdout.flush()
