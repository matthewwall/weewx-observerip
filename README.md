# weewx-observerip
weewx driver for the Ambient ObserverIP weather station

mwall modifications to David Malick's ObserverIP driver for weewx.

David's driver is here:
 https://github.com/dkmcode/weewx-observerip/archive/master.tar.gz


NOTES

Relative Pressure Offset in the calibration tab of the station setup must
be set to 0.

This driver has two modes: direct or indirect.  Direct mode reads data directly
from the ObserverIP station.  Indirect mode reads data from a local file that
is updated by a separate process that sniffs the network for ObserverIP data.

The ObserverIP must be on the same network segment as the weewx server. UDP
broadcasts must be able to get from one to the other.

In order to run in indirect mode:
- change direct in the [ObserverIP] section of weewx.conf to false
- copy util/apache/conf.d/weatherstation-intercept.conf to the apache
  configuration directory, /etc/httpd/conf.d on most systems
- make sure the path in that file is reasonable
- create directory /var/www/weatherstation
- copy util/apache/weatherstation/updateweatherstation.php
  to /var/www/weatherstation
- edit both the updateweatherstation.php and weewx.conf
- set xferfile in each to point to the same file

The file must be writable by the web server and readable by weewx.

To see the configuration options:
  wee_device --defaultconfig
