#!/bin/sh

while [ 1 ]; do
	while ! ps | grep -v grep | grep -q hid_ble_bridge; do
		sleep 5
	done
	sleep 5

	TMPFILE=$(mktemp)
	KEYBOARD=""
	MOUSE=""

	udevadm info --export-db | grep "P: " | grep "/event"  | sed 's/P: //' > $TMPFILE

	for LINE in $(cat $TMPFILE); do
		sys_path="/sys/class/input/${LINE%/*}"
		sys_path="${sys_path/\/devices\/virtual\/input\//}"
		if [ "$(cat $sys_path/name)" == "pCP BLE HID Keyboard" ]; then
			KEYBOARD="/dev/input/${LINE##*/}"
			echo "Keyboard Event: $KEYBOARD"
		elif [ "$(cat $sys_path/name)" == "pCP BLE HID Mouse" ]; then
			MOUSE="/dev/input/${LINE##*/}"
			echo "Mouse Event: $MOUSE"
		fi
	done
	rm -f $TMPFILE

	if [ "$KEYBOARD" = "" ]; then
		sleep 5
		continue
	fi

	echo "Starting Triggerhappy"
	##### This is just a dump line, once working remove this and use the trigger file
	sudo thd --dump $KEYBOARD $MOUSE
	#sudo thd --triggers /home/tc/triggers.conf $KEYBOARD $MOUSE

	sleep 5
done
