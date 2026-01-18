# BLE HID Bridge

A Python application that bridges Bluetooth Low Energy (BLE) HID devices (keyboards, mice, and media controllers) to Linux input events, creating virtual devices that can be used system-wide.

## Features

- **BLE Connection**: Connects to BLE HID devices via MAC address or device name.
- **Virtual Devices**: Creates virtual keyboard and mouse devices using `/dev/uinput`.
- **Key Handling**: Supports standard keyboard keys, modifiers, media keys, and mouse movements/clicks.
- **Device Preparation**: Automatically handles pairing, bonding, and trust management via `bluetoothctl`.
- **Robust Reconnection**: Automatically attempts reconnection on disconnection.
- **Debug Mode**: Optional verbose logging for troubleshooting.

---

## Requirements

- **Python 3.11+**
- **Linux** (with BlueZ Bluetooth stack and `/dev/uinput` support)
- **Root privileges** (required for BLE operations and virtual device creation)
- **Bluetooth adapter** supporting BLE

---

## Python Dependencies

- **bleak**: For BLE communication.

Dependencies of bleak (Installed automatically with bleak):

- `dbus-fast`
- `evdev`

Standard library modules used (no additional installation needed):
- `asyncio`
- `signal`
- `argparse`
- `subprocess`

### System Dependencies

Ensure the following system packages are available:
- Bluetooth system:
- triggerhappy or some other handling for input events.

---

## Installation

### On Raspberry Pi with PiCorePlayer

Follow these steps to get the application running on PiCorePlayer:

1. **Install Required Packages**:
   - From the PiCorePlayer interface, go to "Main Page" > "Bluetooth" > "Install."

2. **Enable Bluetooth**:
   - Near the bottom of the Bluetooth page, enable the RPi built-in Bluetooth
   - Or install a supported USB Bluetooth stick.

3. **Reboot**:

4. **Pair Device**
   - Open a ssh session to the RPi
   - Scan for Bluetooth
     ```bluetoothctl
     scan on
     ```
   - Watch for you device to show up, press a button on remote if needed.
     You will need the hardware address for the device in the format XX:XX:XX:XX:XX:XX
   - Stop scanning and pair
     ```scan off
     pair XX:XX:XX:XX:XX:XX
     ```
   - It is important to see this type of output
     ```Attempting to pair with XX:XX:XX:XX:XX:XX
     [CHG] Device XX:XX:XX:XX:XX:XX Connected: yes
     [CHG] LE XX:XX:XX:XX:XX:XX Connected: yes
     [CHG] Device XX:XX:XX:XX:XX:XX Bonded: yes
     [CHG] LE XX:XX:XX:XX:XX:XX Bonded: yes
     [CHG] LE XX:XX:XX:XX:XX:XX Paired: yes
     ```
   - Make sure not to set trusted: yes, if you did then "untrust XX:XX:XX:XX:XX:XX"
   - Exit and Backup
     ```exit
     pcp bu
        [ INFO ] Copying existing backup to /mnt/mmcblk0p2/tce/mydatabk.[tgz|tgz.bfe] .. Done.
        Backing up files to /mnt/mmcblk0p2/tce/mydata.tgz Done.
        [ OK ] Backup successful.
     ```

5. **Download Scripts from this Repository**:
   - download:
     ```ash
     wget https://github.com/paul-1/pcp-ble-gatt/raw/refs/heads/main/hid_ble_bridge.py
     wget https://github.com/paul-1/pcp-ble-gatt/raw/refs/heads/main/start_ble_events.sh
     pcp bu
     ```

---

## Usage

Run the script with root privileges (required for BLE and `/dev/uinput` access):

### Connect by MAC Address
```ash
sudo -E python3 hid_ble_bridge.py --device-mac AA:BB:CC:DD:EE:FF
```

### Connect by Device Name
```ash
sudo -E python3 hid_ble_bridge.py --device-name "HID Remote01"
```

---

### Enable Debug Logging (No output is produced by default)
```ash
sudo -E python3 hid_ble_bridge.py --device-mac AA:BB:CC:DD:EE:FF --debug
```

---

### Additional Options
- `--scan-timeout <seconds>`: Timeout for device scanning by name (default: 10.0)

- Press `Ctrl+C` to stop the application.

-  `start_ble_events.sh`  This script will
    - Automatically find the required device events
    - Start triggerhappy in dump mode, printing device inputs to console.
    - You will need to create your triggerhappy configuration and edit this script to use it. A sample is found: https://github.com/paul-1/pcp-ble-gatt/blob/main/triggerhappy.conf

### Finally Set Automatic Start
   
- To Be Detmined.

---

## How It Works

1. **Device Discovery**: Scans for or uses the specified BLE HID device.
2. **Preparation**: Ensures the device is properly paired/bonded and trusted.
3. **Connection**: Establishes a BLE connection and subscribes to HID report notifications.
4. **Event Translation**: Decodes incoming HID reports and injects corresponding Linux input events.
5. **Virtual Devices**: Keyboard and mouse events are routed through virtual `/dev/uinput` devices.

---

### Troubleshooting for PiCorePlayer

- **Bluetooth Not Available**: Check the bluetooth logs from the pCP web interface: -or-
  ```ash
  cat /var/log/pcp_bt.log
  ```

---

## Troubleshooting General Issues

- **Connection Issues**: Ensure the device is in paired.  If you do not pair manually, bleak will attempt to pair, but will require you to be running bluetoothctl to acknowledge pairing request.
- **Permission Denied**: Always run with `sudo -E` to preserve environment variables.
- **No Input Events**: Check that `/dev/uinput` is accessible. Ensure no other applications are interfering.
- **Debug Mode**: Use `--debug` for detailed logs to diagnose issues.

---

## License

This project is licensed under the MIT License. See [LICENSE](./LICENSE) for details.

---

## Contributing

Contributions are welcome! Please open issues or pull requests for bugs, features, or improvements.

---