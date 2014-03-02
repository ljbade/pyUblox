#!/usr/bin/env python

import ublox, sys, time, struct
import ephemeris, util, positionEstimate, satelliteData

from optparse import OptionParser

parser = OptionParser("dgps_test.py [options]")
parser.add_option("--port1", help="serial port 1", default='/dev/ttyACM0')
parser.add_option("--baudrate", type='int',
                  help="serial baud rate", default=115200)
parser.add_option("--log1", help="log file1", default=None)
parser.add_option("--reference", help="reference position (lat,lon,alt)", default=None)
parser.add_option("--ecef-reference", help="reference position (X,Y,Z)")
parser.add_option("--reopen", action='store_true', default=False, help='re-open on failure')
parser.add_option("--nortcm", action='store_true', default=False, help="don't send RTCM to receiver2")
parser.add_option("--dynmodel1", type='int', default=ublox.DYNAMIC_MODEL_STATIONARY, help="dynamic model for recv1")
parser.add_option("--minelevation", type='float', default=10.0, help="minimum satellite elevation")
parser.add_option("--minquality", type='int', default=6, help="minimum satellite quality")


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
    return dev

dev1 = setup_port(opts.port1, opts.log1)

dev1.configure_message_rate(ublox.CLASS_NAV, ublox.MSG_NAV_POSLLH, 1)
dev1.configure_message_rate(ublox.CLASS_NAV, ublox.MSG_NAV_POSECEF, 1)
dev1.configure_message_rate(ublox.CLASS_RXM, ublox.MSG_RXM_RAW, 1)
dev1.configure_message_rate(ublox.CLASS_RXM, ublox.MSG_RXM_SFRB, 1)
dev1.configure_message_rate(ublox.CLASS_AID, ublox.MSG_AID_EPH, 1)
dev1.configure_message_rate(ublox.CLASS_NAV, ublox.MSG_NAV_SVINFO, 1)
dev1.configure_solution_rate(rate_ms=200)


# we want the ground station to use a stationary model, and the roving
# GPS to use a highly dynamic model
dev1.set_preferred_dynamic_model(opts.dynmodel1)

logfile = time.strftime('residlog-local-adj-%y%m%d-%H%M.txt')
adjlog = open(logfile, 'w')

logfile = time.strftime('residlog-local-raw-%y%m%d-%H%M.txt')
rawlog = open(logfile, 'w')

logfile = time.strftime('residlog-local-cor-%y%m%d-%H%M.txt')
corlog = open(logfile, 'w')

logfile = time.strftime('residlog-local-el-%y%m%d-%H%M.txt')
ellog = open(logfile, 'w')

logfile = time.strftime('residlog-local-az-%y%m%d-%H%M.txt')
azlog = open(logfile, 'w')


def position_estimate(messages, satinfo):
    rxm_raw   = messages['RXM_RAW']

    # If reference position is set, this automatically uses that reference position
    # when solving for the clock error
    pos = positionEstimate.positionEstimate(satinfo)

    #print satinfo.reference_position, satinfo.position_estimate

    adj = {}
    raw = {}
    cor = {}
    for sv in satinfo.prCorrected:
        cor[sv] = satinfo.geometricRange[sv] - satinfo.prCorrected[sv]
        prAdjusted = cor[sv] + satinfo.receiver_clock_error * util.speedOfLight
        adj[sv] = satinfo.geometricRange[sv] - prAdjusted
        raw[sv] = adj[sv] + satinfo.tropospheric_correction[sv] + satinfo.ionospheric_correction[sv]

    for sv in range(32):
        adjlog.write("%f," % adj.get(sv,0))
        rawlog.write("%f," % raw.get(sv,0))
        corlog.write("%f," % cor.get(sv,0))
        ellog.write("%f," % satinfo.elevation.get(sv,0))
        azlog.write("%f," % satinfo.azimuth.get(sv,0))

    adjlog.write('\n')
    rawlog.write('\n')
    corlog.write('\n')
    ellog.write('\n')
    azlog.write('\n')

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
            svid_seen[sv] = tnow

last_msg1_time = time.time()

messages = {}
satinfo = satelliteData.SatelliteData()

if opts.reference is not None:
    satinfo.reference_position = util.ParseLLH(opts.reference).ToECEF()
elif opts.ecef_reference is not None:
    satinfo.reference_position = util.PosVector(*opts.ecef_reference.split(','))
else:
    satinfo.reference_position = None

satinfo.min_elevation = opts.minelevation
satinfo.min_quality = opts.minquality

def handle_device1(msg):
    '''handle message from reference GPS'''
    global messages, satinfo
    
    if msg.name() in [ 'RXM_RAW', 'AID_EPH']:
        try:
            msg.unpack()
            messages[msg.name()] = msg
            satinfo.add_message(msg)
        except ublox.UBloxError as e:
            print(e)
    if msg.name() == 'RXM_RAW':
        handle_rxm_raw(msg)
        position_estimate(messages, satinfo)

while True:
    # get a message from the reference GPS
    msg = dev1.receive_message_noerror()
    if msg is not None:
        handle_device1(msg)
        last_msg1_time = time.time()
    else:
        break

    if opts.reopen and time.time() > last_msg1_time + 5:
        dev1.close()
        dev1 = setup_port(opts.port1, opts.log1, append=True)
        last_msg1_time = time.time()
        sys.stdout.write('R1')

    sys.stdout.flush()
