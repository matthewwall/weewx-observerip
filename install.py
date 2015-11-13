# installer for Ambient ObserverIP driver

from setup import ExtensionInstaller

def loader():
    return ObserverIPInstaller()

class ObserverIPInstaller(ExtensionInstaller):
    def __init__(self):
        super(ObserverIPInstaller, self).__init__(
                version="0.2mw",
                name='observerip',
                description='driver for Ambient ObserverIP',
                author="David Malick",
                config={
#                    'Station': {
#                        'station_type': 'ObserverIP'},
                    'ObserverIP': {
                        'direct': 'true',
                        'poll_interval' : '16',
                        'dup_interval': '2',
                        'xferfile': '/path/to/transfer/file',
                        'check_calibration': 'true',
                        'set_calibration': 'false',
                        'driver': 'user.observerip',
                        'calibration': {
                            'RainGain': '1.0',
                            'windDirOffset': '0',
                            'inHumiOffset': '0',
                            'AbsOffset': '0.00',
                            'UVGain': '1.00',
                            'SolarGain': '1.00',
                            'WindGain': '1.00',
#                            'RelOffset': '0.00',
                            'luxwm2': '126.7',
                            'outHumiOffset': '0',
                            'outTempOffset': '0.0',
                            'inTempOffset': '0.0'
                        }
                    }
                },
                files=[('bin/user', ['bin/user/observerip.py']),
                       ('util/apache/conf.d/weatherstation-intercept.conf',
                        ['util/apache/conf.d/weatherstation-intercept.conf']),
                       ('util/apache/weatherstation/updateweatherstation.php',
                        ['util/apache/weatherstation/updateweatherstation.php'])
                       ]
                )
