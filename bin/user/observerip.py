#!/usr/bin/python
# Copyright 2015 David Malick
"""weewx driver for Ambient ObserverIP

To use this driver, see readme.txt
"""

from __future__ import with_statement
import time
import io
import socket
import sys
import syslog
import urllib
import urllib2

import weewx
import weewx.drivers
from weeutil.weeutil import to_int, to_float, to_bool

DRIVER_NAME = 'ObserverIP'
DRIVER_VERSION = '0.4mw'

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

    UDP_PORT = 25122
    MESSAGE = "ASIXXISA\x00"

    CALIBRATIONBOUND = {'RainGain': (to_float, 0.1, 5.0),
                        'AbsOffset': (to_float, -23.62, 23.62),
                        'outTempOffset': (to_float, -18.0, 18.0),
                        'windDirOffset': (to_float, -180.0, 180.0),
                        'luxwm2': (to_float, 1.0, 1000.0),
                        'SolarGain': (to_float, 0.1, 5.0),
                        'WindGain': (to_float, 0.1, 5.0),
                        'inTempOffset': (to_float, -18.0, 18.0),
                        'UVGain': (to_float, 0.1, 5.0),
                        'outHumiOffset': (to_float, -10.0, 10.0),
                        'inHumiOffset': (to_float, -10.0, 10.0),
                        'RelOffset': (to_float, -23.62, 23.62)
    }

    def __init__(self, **stn_dict):
        self.versionmap = {'wh2600USA_v2.2.0':'3.0.0'}
        self.hostname = stn_dict.get('hostname',None)
        self.max_tries = int(stn_dict.get('max_tries', 5))
        self.retry_wait = int(stn_dict.get('retry_wait', 2))
        self.infopacket = None
        #FIXME modify to allow using hostname to traverse routers
        self.infopacket = self.infoprobe()
        if not self.infopacket:
            raise Exception('ObserverIP network probe failed')

    def infoprobe(self):
        if self.hostname is None:
            udp_addr = "255.255.255.255"
        else:
            udp_addr = self.hostname
        sock = socket.socket(socket.AF_INET, # Internet
                             socket.SOCK_DGRAM) # UDP
        if self.hostname is None:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for count in range(self.max_tries):
            try:
                sock.sendto(self.MESSAGE, (udp_addr, self.UDP_PORT))
                sock.settimeout(self.retry_wait)
                recv_data, (addr, port) = sock.recvfrom(1024)
                return recv_data
            except socket.timeout:
                logerr("socket timeout %d of %d" % (count+1, self.max_tries))
                time.sleep(self.retry_wait)
            except socket.gaierror:
                logerr("%s: incorrect hostname or IP" % self.hostname)
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
                                dat[name]=val
                            else:
                                es = nextline.index('>', sl)
                                ee = nextline.index('<', es)
                                val = nextline[es+1:ee]
                                dat[name]=val
                            break
                except ValueError:
                    pass
        for i in ('Cancel', 'Apply', 'corr_Default', 'rain_Default', 'reboot', 'restore'):
            if i in dat:
                del dat[i]
        return dat

    @staticmethod
    def dict_to_param(d):
        param=""
        for i in d:
            if param:
                param += "&"
            param += "%s=%s" % (i,d[i])
        return param

    def boundcheck(self, bound, data):
        for i in data:
            if i in bound:
                if ( bound[i][0](data[i]) < bound[i][0](bound[i][1]) or bound[i][0](data[i]) > bound[i][0](bound[i][2])):
                    logerr("%s bound error: range: %s-%s value: %s" % (i, bound[i][1], bound[i][2], data[i] ))
                    exit(1)
            else:
                logerr("%s not bound" % i)
                exit(1)

    def getnetworksettings(self, Readable=False):
        return self.page_to_dict('http://%s/bscsetting.htm' % self.ipaddr(), not Readable)

    def setnetworksettings(self):
        response = urllib2.urlopen("http://%s/bscsetting.htm" % self.ipaddr(),
                                   self.dict_to_param(calibdata) + "&Apply=Apply")
    def setnetworkdefault(self):
        #print 'Not implemented'
        pass

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

    def setidpasswd(self, wuid, passwd):
        """set wunderground id and passwd"""
        response = urllib2.urlopen("http://%s/weather.htm" % self.ipaddr(),
                                   "stationID=%s&stationPW=%s&Apply=Apply" % (wuid, passwd))

    def getstationsettings(self, readable=False):
        return self.page_to_dict('http://%s/station.htm' % self.ipaddr(),not readable)

    def setstationsettings(self, settings):
        if 'WRFreq' in settings:
            del settings['WRFreq']
        response = urllib2.urlopen("http://%s/station.htm" % self.ipaddr(),
                                   self.dict_to_param(settings) + "&Apply=Apply")

    def data(self):
        return self.page_to_dict('http://%s/livedata.htm' % self.ipaddr())

    def getcalibration(self):
        return self.page_to_dict('http://%s/correction.htm' % self.ipaddr())

    def setcalibration(self, calibdata):
        self.boundcheck(self.CALIBRATIONBOUND ,calibdata)
        try:
            response = urllib2.urlopen("http://%s/correction.htm" % self.ipaddr(),
                                       self.dict_to_param(calibdata) + "&Apply=Apply")
            pass
        except urllib2.URLError:
            pass

    def setcalibrationdefault(self):
        response = urllib2.urlopen('http://%s/msgcoredef.htm' % self.ipaddr())

# =============================================================================

class ObserverIPDriver(weewx.drivers.AbstractDevice):
    """
    weewx driver to download data from ObserverIP
    """
    expected_units = {'unit_Wind': 'mph',
                      'u_Rainfall': 'in',
                      'unit_Pressure': 'inhg',
                      'u_Temperature': 'degF',
                      'unit_Solar': 'w/m2'}

# Does not work using function norm
    XXXdirectmap = {
        'wh2600USA_v2.2.0' : {
            'dateTime' : ('epoch', to_int),
            'inTemp' : ('inTemp', to_float),
            'inHumidity' : ('inHumi', to_float),
            'pressure' : ('AbsPress', to_float),
            'outTemp' : ('outTemp',to_float),
            'outHumidity' : ('outHumi', to_float),
            'windDir' : ('windir', to_float),
            'windSpeed' : ('avgwind', to_float),
            'windGust' : ('gustspeed', to_float),
            'radiation' : ('solarrad', to_float),
            'UV' : ('uvi', to_float),
            'rain' : ('rainofyearly', to_float),
            'inTempBatteryStatus' : ('inBattSta', ),
            'outTempBatteryStatus' : ('outBattSta1', )
        },
        'default' : {
            'dateTime' : ('epoch', to_int),
            'inTemp' : ('inTemp', to_float),
            'inHumidity' : ('inHumi', to_float),
            'pressure' : ('AbsPress', to_float),
            'outTemp' : ('outTemp',to_float),
            'outHumidity' : ('outHumi', to_float),
            'windDir' : ('windir', to_float),
            'windSpeed' : ('avgwind', to_float),
            'windGust' : ('gustspeed', to_float),
            'radiation' : ('solarrad', to_float),
            'UV' : ('uvi', to_float),
            'rain' : ('rainofyearly', to_float),
        },
        'wu' : {
            'dateTime' : ('epoch', to_int),
            'outTemp' : ('tempf',to_float),
            'outHumidity' : ('humidity', to_float),
            'dewpoint' : ('dewptf', to_float),
            'windchill' : ('windchillf', to_float),
            'windDir' : ('winddir', to_float),
            'windSpeed' : ('windspeedmph', to_float),
            'windGust' : ('windgustmph', to_float),
            'rain' : ('yearlyrainin', to_float),
            'radiation' : ('solarradiation', to_float),
            'UV' : ('UV', to_float),
            'inTemp' : ('indoortempf', to_float),
            'inHumidity' : ('indoorhumidity', to_float),
            'pressure' : ('baromin', to_float),
            'txBatteryStatus' : ('lowbatt', to_float),
        }
    }

    def __init__(self, **stn_dict):
        loginf("version is %s" % DRIVER_VERSION)

        self.directmap = {
            'wh2600USA_v2.2.0' : {
                'dateTime' : ('epoch', to_int),
                'inTemp' : ('inTemp', to_float),
                'inHumidity' : ('inHumi', to_float),
                'pressure' : ('AbsPress', to_float),
                'outTemp' : ('outTemp',to_float),
                'outHumidity' : ('outHumi', to_float),
                'windDir' : ('windir', to_float),
                'windSpeed' : ('avgwind', to_float),
                'windGust' : ('gustspeed', to_float),
                'radiation' : ('solarrad', to_float),
                'UV' : ('uvi', to_float),
                'rain' : ('rainofyearly', to_float),
                'inTempBatteryStatus' : ('inBattSta', self.norm),
                'outTempBatteryStatus' : ('outBattSta1', self.norm)
            },
            'default' : {
                'dateTime' : ('epoch', to_int),
                'inTemp' : ('inTemp', to_float),
                'inHumidity' : ('inHumi', to_float),
                'pressure' : ('AbsPress', to_float),
                'outTemp' : ('outTemp',to_float),
                'outHumidity' : ('outHumi', to_float),
                'windDir' : ('windir', to_float),
                'windSpeed' : ('avgwind', to_float),
                'windGust' : ('gustspeed', to_float),
                'radiation' : ('solarrad', to_float),
                'UV' : ('uvi', to_float),
                'rain' : ('rainofyearly', to_float),
            },
            'wu' : {
                'dateTime' : ('epoch', to_int),
                'outTemp' : ('tempf',to_float),
                'outHumidity' : ('humidity', to_float),
                'dewpoint' : ('dewptf', to_float),
                'windchill' : ('windchillf', to_float),
                'windDir' : ('winddir', to_float),
                'windSpeed' : ('windspeedmph', to_float),
                'windGust' : ('windgustmph', to_float),
                'rain' : ('yearlyrainin', to_float),
                'radiation' : ('solarradiation', to_float),
                'UV' : ('UV', to_float),
                'inTemp' : ('indoortempf', to_float),
                'inHumidity' : ('indoorhumidity', to_float),
                'pressure' : ('baromin', to_float),
                'txBatteryStatus' : ('lowbatt', to_float),
            }
        }

        self.xferfile = stn_dict['xferfile']
        self.poll_interval = float(stn_dict.get('poll_interval', 10))
        self.dup_interval = float(stn_dict.get('dup_interval', 5))
        self.max_tries = int(stn_dict.get('max_tries', 5))
        self.retry_wait = int(stn_dict.get('retry_wait', 2))
        self.mode = stn_dict.get('mode', 'direct')
        self.check_calibration = to_bool(stn_dict.get('check_calibration',False))
        self.set_calibration = to_bool(stn_dict.get('set_calibration', False))
        self.lastrain = None
        self.lastpacket = 0

        if self.mode == 'direct':
            self.obshardware = OpserverIPHardware(**stn_dict)
            if self.chkunits(self.expected_units):
                logerr("calibration error: %s is expexted to be %f but is %f" % 
                          (i, to_float(calibdata[i]), to_float(stcalib[i])))
                raise Exception("Station units not set correctly")
            if self.obshardware.version() in self.directmap:
                self.map = self.directmap[self.obshardware.version()]
            else:
                loginf("Unknown firmware version: %s" % self.obshardware.version())
                self.map = self.directmap['default']
        else:
            self.map = self.directmap['wu']
            if self.check_calibration:
                self.obshardware = OpserverIPHardware(**stn_dict)
                if self.chkunits(self.expected_units):
                    raise Exception("Station units not set correctly")

        if 'calibration' in stn_dict and self.check_calibration:
            if self.chkcalib(stn_dict['calibration']):
                if(self.set_calibration):
                    self.obshardware.setcalibration(stn_dict['calibration'])
                    if self.chkcalib(stn_dict['calibration']):
                        raise Exception("Setting calibration unsuccessful")
                else:
                    raise Exception("calibration error")
                
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
                    #print time.time()
                    #print to_int(packet['dateTime'])
                    sleeptime = self.poll_interval - time.time() + int(packet['dateTime'])
                    #print sleeptime
                if ( sleeptime < 0 ):
                    sleeptime = self.dup_interval
                time.sleep(sleeptime)
            else:
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
        data = dict()
        for count in range(self.max_tries):
            try:
                data = self.obshardware.data()
                # added rounding, the epoch is already to large but this
                # will make it more consistent
                data['epoch'] = int(time.time() + 0.5 )
                return data
            except socket.error, e:
                logerr('direct retrieval failed attempt %d of %d: %s' %
                       (count + 1, self.max_tries, e))
                time.sleep(self.retry_wait)
        else:
            logerr('direct retrieval failed after %d tries' % self.max_tries)
        return None

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
                logerr("calibration error: %s is expexted to be %f but is %f" % 
                       (i, to_float(calibdata[i]), to_float(stcalib[i])))
                return True
        return False

    def chkunits(self, bound):
        data = self.obshardware.getstationsettings(True);
        for i in bound:
            if i in data:
                if ( bound[i] != data[i]):
                    logerr("%s expexted in unit %s but is in %s" % (i, bound[i], data[i]))
                    return True
        return False


# =============================================================================

class ObserverIPConfEditor(weewx.drivers.AbstractConfEditor):
    @property
    def default_stanza(self):
        return """
[ObserverIP]
    # This section is for the weewx ObserverIP driver

    # hostname - hostname or IP address of the ObserverIP, not required

    # mode determines the method for obtaining data from the station
    # 	   direct   - communicate directly with the station
    #	   indirect - get station data from the CGI intermediary
    mode = direct

    # poll_interval
    #	mode = direct   - The time (in seconds) between LOOP packets (should be 16)
    #	mode = indirect - Time to wait for new packet ( 17 is a good value)
    poll_interval = 16

    # dup_interval
    #	mode = direct   - time to wait if there is an error getting a packet
    #	mode = indirect - subsequent time to wait if new packet has not arived after poll_interval
    dup_interval = 2

    # xferfile
    #	mode = direct   - unused
    #	mode = indirect - file where the CGI script puts the data from the observerip
    xferfile = /path/to/transfer/file

    # retry_wait - time to wait after failed network attempt

    # check_calibration - make sure the station calibration is as expected
    check_calibration = true

    # set_calibration - set calibration in station if it is not as expected
    #                   only meaningful if check_calibration is true
    set_calibration = false

    # The driver to use:
    driver = user.observerip

    # The calibration the driver expects from the station, only useful
    # if check_calibration is set. Items that are not set, are not checked.
    [[calibration]]
	 RainGain=1.00
	 windDirOffset=0
	 inHumiOffset=0
	 AbsOffset=0.00
	 UVGain=1.00
	 SolarGain=1.00
	 WindGain=1.00
         # RelOffset should be set to 0 in indirect mode
	 #RelOffset=0.00
	 luxwm2=126.7
	 outHumiOffset=0
	 outTempOffset=0.0
	 inTempOffset=0.0
"""


# =============================================================================

class ObserverIPConfigurator(weewx.drivers.AbstractConfigurator):
    @property
    def description(self):
        return """Configures the Ambient ObserverIP"""

    #@property
    #def usage(self):
    #    return """Usage: """

    def add_options(self, parser):
        super(ObserverIPConfigurator, self).add_options(parser)

        parser.add_option("--findobserver", dest="findobserver",
                          action="store_true",
                          help="Find the observerIP on the network")
        parser.add_option("--getdata", dest="getdata",
                          action="store_true",
                          help="print weather data from the station")
        parser.add_option("--defaultconfig", dest="defconf",
                          action="store_true",
                          help="show the default configuration for weewx.conf")

    def do_options(self, options, parser, config_dict, prompt):
        driver_dict = config_dict['ObserverIP']
        obshardware = OpserverIPHardware(**driver_dict)

        if options.findobserver:
            sys.stdout.write("http://%s\n" % obshardware.ipaddr())
            try:
                hostname = socket.gethostbyaddr(obshardware.ipaddr())[0]
                print "or"
                sys.stdout.write("http://%s\n" % hostname)
            except:
                pass

        if options.getdata:
            data = obshardware.data()
            for obs in data:
                sys.stdout.write("%s=%s\n" % (obs, data[obs]))

        if options.defconf:
            stconf = ObserverIPConfEditor()
            print stconf.default_stanza

    @staticmethod
    def areyousure(prompt=True, msg=''):
        if prompt:
            print msg
            ans = ''
            while ans not in ['y', 'n']:
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
    (options, args) = parser.parse_args()

    import weeutil.weeutil
    if options.xferfile is None:
        mode='direct'
    else:
        mode='indirect'
    station = ObserverIPDriver(mode=mode, xferfile=options.xferfile)
    for p in station.genLoopPackets():
        print weeutil.weeutil.timestamp_to_string(p['dateTime']), p

