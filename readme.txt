observerip - weewx driver for the Ambient ObserverIP

This driver is derived from an implementation by David Malick, who posted the
original version in April 2015.  This fork addresses a few minor issues and
fixes the installation script to work with the wee_extension and wee_config
tools.

===============================================================================
How to install:

1) Run the extension installer:

wee_extension --install weewx-observerip.tar.gz

2) Choose the observerip driver:

wee_config --reconfigure --driver=user.observerip

3) Start weewx

sudo /etc/init.d/weewx start
