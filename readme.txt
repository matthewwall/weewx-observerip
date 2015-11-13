observerip - weewx driver for the Ambient ObserverIP

How to install:

1) Run the extension installer:

wee_extension --install weewx-observerip.tar.gz

2) Choose the observerip driver:

wee_config --reconfigure --driver=user.observerip

3) Start weewx

sudo /etc/init.d/weewx start
