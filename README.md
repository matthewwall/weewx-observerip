# weewx-observerip

weewx driver for the Ambient ObserverIP weather station

## Installation

1) Run the extension installer:

    wee_extension --install weewx-observerip.tar.gz

2) Choose the observerip driver:

    wee_config --reconfigure --driver=user.observerip

3) Start weewx

    sudo /etc/init.d/weewx start

## Configuration

This driver has two modes: direct or indirect.  Direct mode reads data directly
from the ObserverIP station.  Indirect mode reads data from a local file that
is updated by a separate process that captures data from the ObserverIP.

To see the configuration options:

    wee_device --default-config

### Direct Mode

This is the default configuration.  WeeWX will read directly from the
ObserverIP.

The ObserverIP must be on the same network segment as WeeWX. UDP
broadcasts must be able to get from one to the other.

### Indirect Mode

Indirect mode uses a PHP script on a local Apache web server to capture the
data from the observer.

- set the mode in weewx.conf

    ```
    [ObserverIP]
        driver = user.observerip
        mode = indirect
        ...
    ```

- install the apache intercept configuration

    ```sudo cp util/apache/conf.d/weatherstation-intercept.conf /etc/apache/conf.d```

- create the weatherstation directory directory

    ```sudo mkdir /var/www/html/weatherstation```

- install the php script

    ```sudo cp util/apache/weatherstation/updateweatherstation.php /var/www/html/weatherstation```

## Notes

Relative Pressure Offset in the calibration tab of the station setup must
be set to 0.

## Credits

This driver is derived from an implementation by David Malick, who posted the
original version in April 2015.  This fork addresses a few minor issues and
fixes the installation script to work with the wee_extension and wee_config
tools.

David's driver is here:
 https://github.com/dkmcode/weewx-observerip
