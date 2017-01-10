#!/bin/bash
# This script is ment to run on a private network
# There has been absolutly no thought give to security !!!!
# Do not expose this to the outside world without looking at it first!!!!!

xferfile=/var/tmp/observer_data
id=
passwd=
user_agent="Mozilla/4.0"
barometeroffset=2.66
lastfile=
intfile=
seqfile=
host=rtupdate.wunderground.com

echo -en "Content-Type: text/html\r\n"
echo -en "Date:" $(date -u +%a,\ %d\ %b\ %Y\ %H:%M:%S\ GMT) "\r\n"
echo ""

echo success

[ -f $lastfile ] && lastpacket=$(cat $lastfile) || lastpacket=0
[ -f "$seqfile" ] && seqnum=$(cat $seqfile) || seqnum=0
seqnum=$[ $seqnum + 1 ]
[ -n "$seqfile" ] && echo $seqnum > $seqfile


[ -n "$seqfile" ] && echo "seqnum=$seqnum" >$xferfile || echo -n >>$xferfile
data="$QUERY_STRING"

while [ -n "$data" ] ; do
    item=${data%%\&*}
    var=${item%%=*}
    val=${item#*=}
    case $var in
	ID)
	    [ -n "$id" ] && val="$id"
	    [ -n "$req" ] && req="$req&$var=$val" || req="$var=$val"
	    echo "$item" >> $xferfile
	    ;;
	PASSWORD)
	    [ -n "$passwd" ] && val="$passwd"
	    [ -n "$req" ] && req="$req&$var=$val" || req="$var=$val"
	    echo "$item" >> $xferfile
	    ;;
	softwaretype)
	    req="$req&$var=Baked%20logger%20v1.0"
	    echo "$item" >> $xferfile
	    ;;
	UV)
	    tm=$(date +%H%M)
	    if [ $tm -lt 1300 -o $tm -gt 1700 ] ; then
		req="$req&$item" 
	    fi
	    echo "$item" >> $xferfile
	    ;;
	dateutc)
	    realutc=$(date -u +%Y-%m-%d%%20%H:%M:%S)
#	    [ -n "$req" ] && req="$req&$item" || req="$item"
	    [ -n "$req" ] && req="$req&dateutc=$realutc" || req="dateutc=$realutc"
	    obsdate=$(echo $val | sed "s/\%20/ /")
	    obsepoch=$(date -u -d "$obsdate" +%s)
	    echo "realutc=$realutc" >> $xferfile
	    echo "$item" >> $xferfile
	    date +epoch=%s >> $xferfile
	    echo "opoch=$obsepoch" >> $xferfile

	    if [ -n "$lastfile" ] ; then
		packint=$[ $obsepoch - $lastpacket ]
		[ -n "$intfile" ] && echo $packint >> $intfile
		echo $obsepoch > $lastfile
	    fi
	    ;;
	rtfreq)
	    # give the real frequency to wunderground
	    [ -n "$req" ] && req="$req&rtfreq=16" || req="rtfreq=16"
	    echo "$item" >> $xferfile
	    ;;
#barometer is set to station pressure, correct to sea level for wunderground
	baromin)
	    cval=$( echo $val + $barometeroffset | bc )
	    [ -n "$req" ] && req="$req&$var=$cval" || req="$var=$cval"
	    echo "$item" >> $xferfile
	    ;;
#dont send indoor readings to wunderground
	indoortempf)
	    echo "$item" >> $xferfile
	    ;;
	indoorhumidity)
	    echo "$item" >> $xferfile
	    ;;
	*)
	    [ -n "$req" ] && req="$req&$item" || req="$item"
	    echo "$item" >> $xferfile
	    ;;
    esac

    newdata=${data#*\&}
    if [ "$newdata" = "$data" ] ; then
 	data=""
    else
 	data="$newdata"
    fi
done

echo "observerip=$REMOTE_ADDR" >> $xferfile

if [ -n "$id" ] && [ -n "$passwd" ] ; then
    curl -s -m 2 -A ${user_agent} "http://$host/weatherstation/updateweatherstation.php?$req" > /dev/null
fi

# sample iptable command for destination NAT
# iptables -t nat -I PREROUTING -i br-lan -s windy ! -d 192.168.0.0/16 -p tcp --dport 80 --to-destination 192.168.1.1
