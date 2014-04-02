#!/usr/bin/env python
'''
Two-rover DGPS test code (plus base, uncorrected control)
'''

import ublox, sys, time, struct
import ephemeris, util, positionEstimate, satelliteData
import RTCMv2

from optparse import OptionParser

logprefix = time.strftime('%y%m%d-%H%M')

parser = OptionParser("rel_collection.py [options]")
parser.add_option("--base", help="Base station receiver", default=None)
parser.add_option("--corr1", help="Corrected receiver 1", default=None)
parser.add_option("--corr2", help="Corrected receiver 2", default=None)
parser.add_option("--uncorr1", help="Uncorrected receiver", default=None)

parser.add_option("--baudrate", type='int',
                  help="serial baud rate", default=115200)
parser.add_option("--log-prefix", help="log file1", default=logprefix)
parser.add_option("--reference", help="reference position (lat,lon,alt)", default=None)
parser.add_option("--ecef-reference", help="reference position (X,Y,Z)")

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
    dev.configure_message_rate(ublox.CLASS_RXM, ublox.MSG_RXM_RAW, 1)
    dev.configure_message_rate(ublox.CLASS_RXM, ublox.MSG_RXM_SFRB, 1)
    dev.configure_message_rate(ublox.CLASS_AID, ublox.MSG_AID_EPH, 1)
    dev.configure_message_rate(ublox.CLASS_NAV, ublox.MSG_NAV_SVINFO, 1)
    dev.configure_message_rate(ublox.CLASS_NAV, ublox.MSG_NAV_SOL, 1)
    dev.configure_message_rate(ublox.CLASS_NAV, ublox.MSG_NAV_DGPS, 1)
    dev.configure_solution_rate(rate_ms=200)

    dev.set_preferred_dynamic_model(ublox.DYNAMIC_MODEL_AIRBORNE4G)
    dev.set_preferred_dgps_timeout(60)

    return dev

base = setup_port(opts.base, opts.log_prefix + "-base.ubx")
corr1 = setup_port(opts.corr1, opts.log_prefix + "-corr1.ubx")
corr2 = setup_port(opts.corr2, opts.log_prefix + "-corr2.ubx")
uncorr1 = setup_port(opts.uncorr1, opts.log_prefix + "-uncorr1.ubx")

def position_estimate(messages, satinfo):
    '''process raw messages to calculate position
    '''

    rxm_raw   = messages['RXM_RAW']

    pos = positionEstimate.positionEstimate(satinfo)
    if pos is None:
        # not enough information for a fix
        return

    rtcm = RTCMv2.generateRTCM2_Message1(satinfo)
    if len(rtcm) != 0:
        print("generated type 1")
        corr1.write(rtcm)
        corr2.write(rtcm)

    rtcm = RTCMv2.generateRTCM2_Message3(satinfo)
    if len(rtcm) != 0:
        print("generated type 3")
        corr1.write(rtcm)
        corr2.write(rtcm)
    
    return pos

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

messages = {}
satinfo = satelliteData.SatelliteData()

if opts.reference is not None:
    satinfo.reference_position = util.ParseLLH(opts.reference).ToECEF()
elif opts.ecef_reference is not None:
    satinfo.reference_position = util.PosVector(*opts.ecef_reference.split(','))
else:
    satinfo.reference_position = None


def handle_device1(msg):
    '''handle message from reference GPS'''
    global messages, satinfo
    
    if msg.name() in [ 'RXM_RAW', 'NAV_POSECEF', 'RXM_SFRB', 'RXM_RAW', 'AID_EPH', 'NAV_POSECEF' ]:
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
    msg = base.receive_message_noerror()
    if msg is not None:
        handle_device1(msg)

    msg = corr1.receive_message_noerror()
    if msg.name() == 'NAV_DGPS':
        msg.unpack()
        print("Corr1 DGPS: age=%u numCh=%u pos_count=%u" % (msg.age, msg.numCh, pos_count))

    msg = corr2.receive_message_noerror()
    if msg.name() == 'NAV_DGPS':
        msg.unpack()
        print("Corr2 DGPS: age=%u numCh=%u pos_count=%u" % (msg.age, msg.numCh, pos_count))

    msg = uncorr1.receive_message_noerror()

    sys.stdout.flush()
