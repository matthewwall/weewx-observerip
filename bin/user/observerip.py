#!/usr/bin/python
# Copyright 2015 David Malick
"""weewx driver for Ambient ObserverIP

To use this driver:

1) copy this file to the weewx user directory

   cp observerip.py /home/weewx/bin/user

2) configure weewx.conf

[Station]
    ...
    station_type = ObserverIP
[ObserverIP]
    driver = user.observerip
"""


from __future__ import with_statement
import syslog
import time
import io
import socket
import sys
import urllib
import urllib2

import weewx
import weewx.drivers
from weeutil.weeutil import to_int, to_float, to_bool

DRIVER_NAME = 'ObserverIP'
DRIVER_VERSION = "0.1"

if weewx.__version__ < "3":
    raise weewx.UnsupportedFeature("weewx 3 is required, found %s" %
                                   weewx.__version__)

def logmsg(dst, msg):
    syslog.syslog(dst, 'observerip: %s' % msg)
    #sys.stdout.write('observerip: %s\n' % msg)

def logdbg(msg):
    logmsg(syslog.LOG_DEBUG, msg)

def loginf(msg):
    logmsg(syslog.LOG_INFO, msg)

def logcrt(msg):
    logmsg(syslog.LOG_CRIT, msg)

def logerr(msg):
    logmsg(syslog.LOG_ERR, msg)

def loader(config_dict, _):
    return ObserverIPDriver(**config_dict[DRIVER_NAME])

def confeditor_loader():
    return ObserverIPConfEditor()

def configurator_loader(_):
    return ObserverIPConfigurator()

class OpserverIPHardware():
    """
    Interface to communicate directly with ObserverIP
    """

    def __init__(self, ip=None, **stn_dict):
#        self.versionmap = {'wh2600USA_v2.2.0', ('3.0.0')}
        self.max_tries = int(stn_dict.get('max_tries', 5))
        self.retry_wait = int(stn_dict.get('retry_wait', 2))
        self.infopacket = None
        self.infopacket = self.infoprobe(ip)
        if not self.infopacket:
            raise Exception('ObserverIP network probe failed')

    UDP_PORT = 25122
    MESSAGE = "ASIXXISA\x00"

    def infoprobe(self, addr=None):
        if addr is None:
            udp_addr = "255.255.255.255"
        else:
            udp_addr = addr
        sock = socket.socket(socket.AF_INET, # Internet
                             socket.SOCK_DGRAM) # UDP
        if addr is None:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for count in range(self.max_tries):
            try:
                sock.sendto(self.MESSAGE, (udp_addr, self.UDP_PORT))
                sock.settimeout(self.retry_wait)
                recv_data, (addr, port) = sock.recvfrom(1024)
                return recv_data
            except socket.timeout:
                logerr("failed attempt %d: socket timeout" % count)
                time.sleep(self.retry_wait)
            except socket.gaierror:
                logerr("%s: incorrect hostname or address" % addr)
                return None
        else:
            logerr("probe failed after %d tries" % self.max_tries)
        return None

    def packetstr(self, ind):
        es = self.infopacket.find('\x00', ind)
        return self.infopacket[ind:es]

    def packetip(self, ind):
        return "%d.%d.%d.%d" % (ord(self.infopacket[ind]),
                                ord(self.infopacket[ind + 1]),
                                ord(self.infopacket[ind + 2]),
                                ord(self.infopacket[ind + 3]))

    def packetport(self, ind):
        return ord(self.infopacket[ind]) * 256 + ord(self.infopacket[ind + 1])

    def getinfopacket(self):
        return self.infopacket

    def dhcp(self):
        flag = ord(self.infopacket[0x20]) & 0x40
        return False if flag == 0 else True

    def ipaddr(self):
        return self.packetip(0x22)

    def staticipaddr(self):
        return self.packetip(0x26)

    def portuk(self):
        return self.packetport(0x2a)

    def porta(self):
        return self.packetport(0x2c)

    def portb(self):
        return self.packetport(0x2e)

    def port(self):
        return self.packetport(0x34)

    def netmask(self):
        return self.packetip(0x36)

    def staticgateway(self):
        return self.packetip(0x3a)

    def staticdns(self):
        return self.packetip(0x3e)

    def updatehost(self):
        return self.packetstr(0x4b)

    def ipaddruk(self):
        return self.packetip(0x6f)

    def version(self):
        return self.packetstr(0x73)

    def page_to_dict(self, url, value=True):
        dat = dict()

        for count in range(self.max_tries):
            try:
                response = urllib2.urlopen(url)
                break
            except urllib2.URLError:
                logerr('data retrieval failed attempt %d of %d: %s' %
                       (count + 1, self.max_tries, ''))
                time.sleep(self.retry_wait)
        else:
            logerr('data retrieval failed after %d tries' % self.max_tries)
            return dat

        for line in response:
            try:
                line.index('<input')
                es = line.index('name="')
                ee = line.index('"', es + 6)
                name = line[es + 6:ee]
                es = line.index('value="')
                ee = line.index('"', es + 7)
                val = line[es + 7:ee]
                dat[name] = val
            except ValueError:
                try:
                    line.index('<select')
                    es = line.index('name="')
                    ee = line.index('"', es + 6)
                    name = line[es + 6:ee]
                    while True:
                        nextline = response.readline()
                        sl = nextline.find('selected')
                        if sl != -1:
                            if value:
                                es = nextline.index('value="')
                                ee = nextline.index('"', es + 7)
                                val = nextline[es + 7:ee]
                                dat[name] = val
                            else:
                                es = nextline.index('>', sl)
                                ee = nextline.index('<', es)
                                val = nextline[es + 1:ee]
                                dat[name] = val
                            break
                except ValueError:
                    pass
        for i in ('Cancel', 'Apply', 'corr_Default', 'rain_Default', 'reboot', 'restore'):
            if i in dat:
                del dat[i]
        return dat

    @staticmethod
    def dict_to_param(d):
        param = ""
        for i in d:
            if param:
                param += "&"
            param += "%s=%s" % (i, d[i])
        return param

    def getnetworksettings(self, readable=False):
        return self.page_to_dict('http://%s/bscsetting.htm' % self.ipaddr(), not readable)

    def setnetworksettings(self):
        response = urllib2.urlopen("http://%s/bscsetting.htm" % self.ipaddr(),
                                   self.dict_to_param(calibdata) + "&Apply=Apply")
        print response.read()

    def setnetworkdefault(self):
        print 'Not implemented'

    def reboot(self, wait=True):
        if wait:
            self.infopacket = None
            self.infopacket = self.infoprobe()
            if self.infopacket:
                print 'reboot succeded'
            else:
                print 'cannot find station'

    def getidpasswd(self):
        return self.page_to_dict('http://%s/weather.htm' % self.ipaddr())

    def setidpasswd(self, stationid, passwd):
        """set id and passwd"""
        response = urllib2.urlopen("http://%s/weather.htm" % self.ipaddr(),
                                   "stationID=%s&stationPW=%s&Apply=Apply" % (stationid, passwd))
        print response.read()

    def getstationsettings(self, readable=False):
        return self.page_to_dict('http://%s/station.htm' % self.ipaddr(), not readable)

    def setstationsettings(self, settings):
        if 'WRFreq' in settings:
            del settings['WRFreq']
        response = urllib2.urlopen("http://%s/station.htm" % self.ipaddr(),
                                   self.dict_to_param(settings) + "&Apply=Apply")
        print response.read()

    def data(self):
        return self.page_to_dict('http://%s/livedata.htm' % self.ipaddr())

    def getcalibration(self):
        return self.page_to_dict('http://%s/correction.htm' % self.ipaddr())

    def setcalibration(self, calibdata):
        print self.dict_to_param(calibdata)
        response = urllib2.urlopen("http://%s/correction.htm" % self.ipaddr(),
                                   self.dict_to_param(calibdata) + "&Apply=Apply")
        print response.read()

    def setcalibrationdefault(self):
        print "defaults"
        response = urllib2.urlopen('http://%s/msgcoredef.htm' % self.ipaddr())
        print response.read()

# =============================================================================

class ObserverIPDriver(weewx.drivers.AbstractDevice):
    """
    weewx driver to download data from ObserverIP
    """

    DIRECTMAP = {
        'wh2600USA_v2.2.0': {
            'dateTime': ('epoch', to_int),
            'inTemp': ('inTemp', to_float),
            'inHumidity': ('inHumi', to_float),
            'pressure': ('AbsPress', to_float),
            'outTemp': ('outTemp', to_float),
            'outHumidity': ('outHumi', to_float),
            'windDir': ('windir', to_float),
            'windSpeed': ('avgwind', to_float),
            'windGust': ('gustspeed', to_float),
            'radiation': ('solarrad', to_float),
            'UV': ('uvi', to_float),
            'rain': ('rainofyearly', to_float),
            'inTempBatteryStatus': ('inBattSta', ObserverIPDriver.norm),
            'outTempBatteryStatus': ('outBattSta1', ObserverIPDriver.norm)
        },
        'default': {
            'dateTime': ('epoch', to_int),
            'inTemp': ('inTemp', to_float),
            'inHumidity': ('inHumi', to_float),
            'pressure': ('AbsPress', to_float),
            'outTemp': ('outTemp', to_float),
            'outHumidity': ('outHumi', to_float),
            'windDir': ('windir', to_float),
            'windSpeed': ('avgwind', to_float),
            'windGust': ('gustspeed', to_float),
            'radiation': ('solarrad', to_float),
            'UV': ('uvi', to_float),
            'rain': ('rainofyearly', to_float),
        },
        'wu': {
            'dateTime': ('epoch', to_int),
            'outTemp': ('tempf', to_float),
            'outHumidity': ('humidity', to_float),
            'dewpoint': ('dewptf', to_float),
            'windchill': ('windchillf', to_float),
            'windDir': ('winddir', to_float),
            'windSpeed': ('windspeedmph', to_float),
            'windGust': ('windgustmph', to_float),
            'rain': ('yearlyrainin', to_float),
            'radiation': ('solarradiation', to_float),
            'UV': ('UV', to_float),
            'inTemp': ('indoortempf', to_float),
            'inHumidity': ('indoorhumidity', to_float),
            'pressure': ('baromin', to_float),
            'txBatteryStatus': ('lowbatt', to_float),
        }
    }

    def __init__(self, **stn_dict):
        loginf("version is %s" % DRIVER_VERSION)

        self.xferfile = stn_dict['xferfile']
        self.poll_interval = float(stn_dict.get('poll_interval', 10))
        self.dup_interval = float(stn_dict.get('dup_interval', 5))
        self.max_tries = int(stn_dict.get('max_tries', 5))
        self.retry_wait = int(stn_dict.get('retry_wait', 2))
        self.mode = stn_dict.get('mode', 'direct')
        self.check_calibration = to_bool(stn_dict.get('check_calibration', False))
        self.lastrain = None
        self.lastpacket = 0
                
        if self.mode == 'direct':
            self.obshardware = OpserverIPHardware()
            if self.obshardware.version() in self.DIRECTMAP:
                self.map = self.DIRECTMAP[self.obshardware.version()]
            else:
                loginf("Unknown firmware version: %s" % self.obshardware.version())
                self.map = self.DIRECTMAP['default']
        else:
            self.map = self.DIRECTMAP['wu']
            if self.check_calibration:
                self.obshardware = OpserverIPHardware()

        if 'calibration' in stn_dict and self.check_calibration:
            self.chkcalib(stn_dict['calibration'])

        loginf("polling interval is %s" % self.poll_interval)

    @property
    def hardware_name(self):
        return "ObserverIP"

    def genLoopPackets(self):
        while True:    
            if self.mode == 'direct':
                data = self.get_data_direct()
            else:
                data = self.get_data()
            packet = dict()
            packet.update(self.parse_page(data))
            if packet:
                yield packet
                        
                if self.mode == 'direct':
                    sleeptime = self.poll_interval
                else:
                    sleeptime = self.poll_interval - time.time() + int(packet['dateTime'])
                if sleeptime < 0:
                    sleeptime = self.dup_interval
                time.sleep(sleeptime)
            else:
                logdbg('No data or duplicate packet')
                time.sleep(self.dup_interval)

    def get_data(self):
        data = dict()
        for count in range(self.max_tries):
            try:
                with open(self.xferfile, 'r') as f:
                    for line in f:
                        eq_index = line.index('=')
                        name = line[:eq_index].strip()
                        data[name] = line[eq_index + 1:].strip()
                return data
            except (IOError, ValueError), e:
                logerr('data retrieval failed attempt %d of %d: %s' %
                       (count + 1, self.max_tries, e))
                time.sleep(self.retry_wait)
        else:
            logerr('data retrieval failed after %d tries' % self.max_tries)
        return None

    def get_data_direct(self):
        data = self.obshardware.data()
        data['epoch'] = int(time.time() + 0.5)
        return data

    def parse_page(self, data):
        packet = dict()
        if data is not None:
            packet['usUnits'] = weewx.US
            for obs in self.map:
                try:
                    packet[obs] = self.map[obs][1](data[self.map[obs][0]])
                except KeyError:
                    loginf("packet missing %s" % obs)
                    packet = dict()
                    break

            if packet:
                currrain = packet['rain']
                if self.lastrain is not None:
                    if currrain >= self.lastrain:
                        packet['rain'] = currrain - self.lastrain
                else:
                    del packet['rain']
                self.lastrain = currrain

                if self.lastpacket >= packet['dateTime']:
                    loginf("duplicate packet or out of order packet")
                    packet = dict()
                else:
                    logdbg("packet interval %s" % (int(packet['dateTime']) - self.lastpacket))
                    self.lastpacket = packet['dateTime']
        
        return packet

    @staticmethod
    def norm(val):
        return 0 if val == 'Normal' else 1

    def chkcalib(self, calibdata):
        stcalib = self.obshardware.getcalibration()
        for i in calibdata:
            if to_float(calibdata[i]) != to_float(stcalib[i]):
                raise Exception("calibration error %s: %s != %s" %
                                (i, calibdata[i], stcalib[i]))


# =============================================================================

class ObserverIPConfEditor(weewx.drivers.AbstractConfEditor):
    @property
    def default_stanza(self):
        return """
[ObserverIP]
    # This section is for the weewx ObserverIP driver

    # the mode determines how to obtain data from the station
    #   direct - communicate directly with the station
    #	indirect - get station data from the CGI intermediary
    mode = direct

    # poll_interval
    #	direct - time (in seconds) between LOOP packets (should be 16)
    #	indirect - time to wait for new packet (17 is a good value)
    poll_interval = 16

    # dup_interval
    #	direct - time to wait if there is an error getting a packet
    #	indirect - subsequent time to wait if new packet has not arived after poll_interval
    dup_interval = 2

    # xferfile
    #	direct - unused
    #	indirect - file where the CGI script puts the data from the observerip
    xferfile = /net/athene/tmp/hacktest

    # retry_wait - time to wait after failed network attempt

    # check_calibration - make sure the station calibration is as expected
    check_calibration = true

    # set_calibration - set calibration in station if it is not as expected,
    # only meaningful if check_calibration is true
    # not implemented
    set_calibration = false

    # The driver to use:
    driver = user.observerip

    # The calibration the driver expects from the station, only useful
    # if check_calibration is set
    [[calibration]]
        RainGain=1.00
        windDirOffset=0
        inHumiOffset=0
        AbsOffset=0.00
        UVGain=1.00
        SolarGain=1.00
        WindGain=1.00
        RelOffset=0.00
        luxwm2=126.7
        outHumiOffset=0
        outTempOffset=0.0
        inTempOffset=0.0
"""


# =============================================================================
# FIXME: This class needs some features added and alot of cleanup
# FIXME: but does not effect the operation of the driver

class ObserverIPConfigurator(weewx.drivers.AbstractConfigurator):
    @property
    def description(self):
        return """Configures the Ambient ObserverIP"""

    #@property
    #def usage(self):
    #    return """Usage: """

    def add_options(self, parser):
        super(ObserverIPConfigurator, self).add_options(parser)

        parser.add_option("--scan", dest="scan",
                          action="store_true",
                          help="Print probe information from ObserverIP")

        parser.add_option("--getdata", dest="getdata",
                          action="store_true",
                          help="print weather data from the station")

        parser.add_option("--readable", dest="readable",
                          action="store_true",
                          help="Return readable values")

        parser.add_option("--getnetwork", dest="getnetwork",
                          action="store_true",
                          help="print network settings from the station")
        parser.add_option("--setnetwork", dest="setnetwork",
                          action="store_true",
                          help="set network settings for the station")

        parser.add_option("--getidpassword", dest="getidpassword",
                          action="store_true",
                          help="print the Weather Underground ID and password from the station")
        parser.add_option("--setpasswd", dest="setpasswd",
                          action="store_true",
                          help="set Weather Underground ID and/or password on ObserverIP")
        parser.add_option("--wuid", dest="wuid",
                          help="    Weather Underground ID")
        parser.add_option("--wupasswd", dest="wupasswd",
                          help="    Weather Underground password")

        parser.add_option("--getstationsettings", dest="getstationsettings",
                          action="store_true",
                          help="get station settings for ObserverIP")
        parser.add_option("--setstationsettings", dest="setstationsettings",
                          action="store_true",
                          help="set station settings for ObserverIP")
        parser.add_option("--dst", dest="dst",
                          help="    set daylight saving time")
        parser.add_option("--timezone", dest="timezone",
                          help="    set timezone")

        parser.add_option("--getcalibration", dest="getcalib",
                          action="store_true",
                          help="list corrections")
        parser.add_option("--setcalibrationdefaults", dest="setcalibdef",
                          action="store_true",
                          help="set calibration defaults for ObserverIP")
        parser.add_option("--setcalibration", dest="setcalib",
                          action="store_true",
                          help="set station corrections")
        parser.add_option("--raingain", dest="raingain",
                          help="    set station corrections")
        parser.add_option("--winddiroffset", dest="winddiroffset",
                          help="    set station corrections")
        parser.add_option("--inhumioffset", dest="inhumioffset",
                          help="    set station corrections")
        parser.add_option("--absoffset", dest="absoffset",
                          help="    set station corrections")
        parser.add_option("--uvgain", dest="uvgain",
                          help="    set station corrections")
        parser.add_option("--solargain", dest="solargain",
                          help="    set station corrections")
        parser.add_option("--windgain", dest="windgain",
                          help="    set station corrections")
        parser.add_option("--reloffset", dest="reloffset",
                          help="    set station corrections")
        parser.add_option("--luxwm2", dest="luxwm2",
                          help="    set station corrections")
        parser.add_option("--outhumioffset", dest="outhumioffset",
                          help="    set station corrections")
        parser.add_option("--outtempoffset", dest="outtempoffset",
                          help="    set station corrections")
        parser.add_option("--intempoffset", dest="intempoffset",
                          help="    set station corrections")
        parser.add_option("--reboot", dest="reboot",
                          action="store_true",
                          help="reboot the ObserverIP")
        parser.add_option("--defaultconfig", dest="defconf",
                          action="store_true",
                          help="show the default configuration for weewx.conf")

    def do_options(self, options, parser, config_dict, prompt):
        obshardware = OpserverIPHardware()
        driver_dict = config_dict['ObserverIP']
        self.xferfile = driver_dict['xferfile']
        with open(self.xferfile, 'r') as f:
            for line in f:
                try:
                    line.index('observerip=')
                    eq_index = line.index('=')
                    self.observerloc = line[eq_index + 1:].strip()
                    break
                except:
                    pass

        if options.getnetwork:
            data = obshardware.getnetworksettings(options.readable)
            for obs in data:
                sys.stdout.write("%s=%s\n" % (obs, data[obs]))

        if options.getidpassword:
            data = obshardware.getidpasswd()
            for obs in data:
                sys.stdout.write("%s=%s\n" % (obs, data[obs]))

        if options.setpasswd:
            if not options.wuid and not options.wupasswd:
                print 'nothing to set'
            else:
                if not options.wuid or not options.wupasswd:
                    data = obshardware.getidpasswd()
                    if not options.wuid:
                        options.wuid = data['stationID']
                    if not options.wupasswd:
                        options.wupasswd = data['stationPW']
                if self.areyousure(prompt, 'This will set the Weather Undergroung password on the ObserverIP'):
                    obshardware.setidpasswd(options.wuid, options.wupasswd)

        if options.getstationsettings:
            data = obshardware.getstationsettings(options.readable)
            for obs in data:
                sys.stdout.write("%s=%s\n" % (obs, data[obs]))

        if options.setstationsettings:
            data = obshardware.getstationsettings(options.readable)
            if options.dst:
                data['dst'] = options.dst
            if options.timezone:
                data['timezone'] = options.timezone
            if self.areyousure(prompt, 'This will change the station settings'):
                obshardware.setstationsettings(data)

        if options.getdata:
            data = obshardware.data()
            for obs in data:
                sys.stdout.write("%s=%s\n" % (obs, data[obs]))

        if options.getcalib:
            data = obshardware.getcalibration()
            for obs in data:
                sys.stdout.write("%s=%s\n" % (obs, data[obs]))
            cf = driver_dict['calibration']
            for i in cf:
                if to_float(cf[i]) != to_float(data[i]):
                    print i

        if options.setcalibdef:
            if self.areyousure(prompt, 'This will set the default calibration values on the ObserverIP'):
                obshardware.setcalibrationdefault()

        if options.setcalib:
            data = obshardware.getcalibration()
            if options.raingain:
                data['RainGain'] = options.raingain
            if options.winddiroffset:
                data['windDirOffset'] = options.winddiroffset
            if options.inhumioffset:
                data['inHumiOffset'] = options.inhumioffset
            if options.absoffset:
                data['AbsOffset'] = options.absoffset
            if options.uvgain:
                data['UVGain'] = options.uvgain
            if options.solargain:
                data['SolarGain'] = options.solargain
            if options.windgain:
                data['WindGain'] = options.windgain
            if options.reloffset:
                data['RelOffset'] = options.reloffset
            if options.luxwm2:
                data['luxwm2'] = options.luxwm2
            if options.outhumioffset:
                data['outHumiOffset'] = options.outhumioffset
            if options.outtempoffset:
                data['outTempOffset'] = options.outtempoffset
            if options.intempoffset:
                data['inTempOffset'] = options.intempoffset
            if self.areyousure(prompt, 'This will set calibration values on the ObserverIP'):
                obshardware.setcalibration(data)

        if options.defconf:
            stconf = ObserverIPConfEditor()
            if hasattr(stconf, 'default_stanza'):
                print stconf.default_stanza
            else:
                print "cant"
        if options.scan:
            print

            sys.stdout.write("Network Initialization:  ")
            if obshardware.dhcp():
                print 'DHCP'
            else:
                print 'STATIC'

            try:
                print "Hostname:                %s" % socket.gethostbyaddr(obshardware.ipaddr())[0]
            except:
                print 'Unknown Hostname'

            sys.stdout.write("Current IP:              %s\n" % obshardware.ipaddr())
            sys.stdout.write("Static IP:               %s\n" % obshardware.staticipaddr())
            sys.stdout.write("Unknown Port:            %s\n" % obshardware.portuk())
            sys.stdout.write("Unknown Port:            %s\n" % obshardware.porta())
            sys.stdout.write("Probe Port:              %s\n" % obshardware.portb())
            sys.stdout.write("Server Listening Port:   %s\n" % obshardware.port())
            sys.stdout.write("Netmask:                 %s\n" % obshardware.netmask())
            sys.stdout.write("Gateway:                 %s\n" % obshardware.staticgateway())
            sys.stdout.write("DNS Server:              %s\n" % obshardware.staticdns())
            sys.stdout.write("Update Host:             %s\n" % obshardware.updatehost())
            sys.stdout.write("Unknown IP:              %s\n" % obshardware.ipaddruk())
            sys.stdout.write("Firmware Version String: %s\n" % obshardware.version())

        if options.reboot:
            if self.areyousure(prompt, 'This will reboot the ObserverIP'):
                obshardware.reboot()

    @staticmethod
    def areyousure(prompt=True, msg=''):
        if prompt:
            print msg
            ans = ''
            while ans not in ['y', 'n']:
                print"This program does not check validity of values."
                print"Please know exactly what you are doing"
                print"Otherwise please use the web interface to change the configuration"
                print"The consequences of not knowing could brick you weatherstation"
                ans = raw_input("Are you sure you wish to proceed (y/n)? ")
                if ans == 'y':
                    return True
                elif ans == 'n':
                    print 'Aborting'
                    return False
        else:
            return True


# =============================================================================
# To test this driver, do the following:
#   PYTHONPATH=/home/weewx/bin python /home/weewx/bin/user/observerip.py

if __name__ == "__main__":
    usage = """%prog [options]"""
    import optparse
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--xferfile', dest='xferfile',
                      help='Transfer file')
    parser.add_option('--test-driver', dest='test_driver', action='store_true',
                      help='test the driver')
    parser.add_option('--test-parser', dest='test_parser', action='store_true',
                      help='test the parser')
    (options, args) = parser.parse_args()
    if options.test_parser:
        data = []
        with open('testfile.xml') as f:
            for line in f:
                data.append(line)
        parser = WLParser()
        parser.feed(''.join(data))
        print parser.get_data()
    else:
        import weeutil.weeutil
        station = ObserverIP(xferfile=options.xferfile)
        for p in station.genLoopPackets():
            print weeutil.weeutil.timestamp_to_string(p['dateTime']), p

