# BLE HID Bridge

A Python application that bridges Bluetooth Low Energy (BLE) HID devices (keyboards, mice, and media controllers) to Linux input events, creating virtual devices that can be used system-wide.

## Features

- **BLE Connection**: Connects to BLE HID devices via MAC address or device name.
- **Virtual Devices**: Creates virtual keyboard and mouse devices using `/dev/uinput`.
- **Key Handling**: Supports standard keyboard keys, modifiers, media keys, and mouse movements/clicks.
- **Key Remapping**: Remap keys from the Bluetooth device to different keys on the virtual device.
- **Device Preparation**: Automatically handles pairing, bonding, and trust management via `bluetoothctl`.
- **Robust Reconnection**: Automatically attempts reconnection on disconnection.
- **Built-in Trigger Support**: Direct command execution on key events without external dependencies.
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
- `os`

### System Dependencies

Ensure the following system packages are available:
- pCP Bluetooth system, installed through the pCP Bluetooth menu on the web interface.

---

## Installation

### On Raspberry Pi with PiCorePlayer

Follow these steps to get the application running on PiCorePlayer:

1. **Install Required Packages**:
   - From the PiCorePlayer interface, go to "Main Page" > "Bluetooth" > "Install."

2. **Enable Bluetooth**:
   - Near the bottom of the Bluetooth page, enable the RPi built-in Bluetooth
   - Or install a supported USB Bluetooth stick.

3. **Install Required package bleak**
   - ```ash
     tce-load -wi python3.11-bleak.tcz
     ```
   - If this was already on your system, make sure it is listed in `/etc/sysconfig/tcedir/onboot.lst`

4. **Reboot**:

5. **Download Scripts from this Repository**:
   - download:
     ```ash
     wget https://github.com/paul-1/pcp-ble-gatt/raw/refs/heads/main/hid_ble_bridge.py
     wget https://github.com/paul-1/pcp-ble-gatt/raw/refs/heads/main/le_auto_pair.py
     chmod 755 hid_ble_bridge.py
     chmod 755 le_auto_pair.py
     pcp bu
     ```

6. **Pair Device**
   - Open a ssh session to the RPi
   - Pair with the auto pairing agent.
     ```ash
     le_auto_pair.py --device-name "<device name prefix>"
     ```
   - Verify Pairing from output
     ```ash
     Device info at cleanup:
       Address: FF:FF:11:5E:88:E2
       Name: HID Remote01
       Paired: 1
       Bonded: 1
       Connected: 0
       Trusted: 0
       LegacyPairing: 0
       ServicesResolved: 0
     Agent unregistered
     Cleanup complete. Exiting.
     ```
   - Backup the changes
     ```ash
     pcp bu
     ```

6.1 **Alternate Manual Pairing**  (Not needed if above works)
   - Scan for Bluetooth
     ```ash
     bluetoothctl
     scan on
     ```
   - Watch for you device to show up, press a button on remote if needed.
     You will need the hardware address for the device in the format XX:XX:XX:XX:XX:XX
   - Stop scanning and pair
     ```ash
     scan off
     pair XX:XX:XX:XX:XX:XX
     ```
   - It is important to see this type of output
     ```ash
     Attempting to pair with XX:XX:XX:XX:XX:XX
     [CHG] Device XX:XX:XX:XX:XX:XX Connected: yes
     [CHG] LE XX:XX:XX:XX:XX:XX Connected: yes
     [CHG] Device XX:XX:XX:XX:XX:XX Bonded: yes
     [CHG] LE XX:XX:XX:XX:XX:XX Bonded: yes
     [CHG] LE XX:XX:XX:XX:XX:XX Paired: yes
     ```
   - Make sure not to set trusted: yes, if you did then "untrust XX:XX:XX:XX:XX:XX"
   - Exit and Backup
     ```ash
     exit
     pcp bu
        [ INFO ] Copying existing backup to /mnt/mmcblk0p2/tce/mydatabk.[tgz|tgz.bfe] .. Done.
        Backing up files to /mnt/mmcblk0p2/tce/mydata.tgz Done.
        [ OK ] Backup successful.
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
- `--triggers <path>`: Path to trigger configuration file for executing commands on key events. If specified and the file exists, the application will directly handle trigger events.
- `--remapkeys <path>`: Path to key remapping configuration file. Allows remapping keys from the Bluetooth device to different keys. **Cannot be used together with --triggers**.

---

### Key Remapping Configuration

The application supports remapping keys from the Bluetooth device to different keys on the virtual input device. This is useful when your Bluetooth device sends keys that you want to map to different keys.

**Note**: The `--remapkeys` option cannot be used together with `--triggers` option. Choose one or the other based on your needs.

#### Enabling Key Remapping

Use the `--remapkeys` option to specify a remapping configuration file:

```ash
sudo -E python3 hid_ble_bridge.py --device-mac AA:BB:CC:DD:EE:FF --remapkeys /path/to/remap.conf
```

#### Key Remapping Configuration Format

The remapping configuration file follows a simple format with one mapping per line:
```
<source key name>:<destination key name>
```

Where:
- `<source key name>`: The key name sent by the Bluetooth device (e.g., `KEY_VOLUMEUP`, `KEY_NEXTSONG`)
- `<destination key name>`: The key name you want to emit instead (e.g., `KEY_UP`, `KEY_RIGHT`)

Example `remap.conf`:
```
# Remap volume keys to arrow keys
KEY_VOLUMEUP:KEY_UP
KEY_VOLUMEDOWN:KEY_DOWN

# Remap media keys to arrow keys
KEY_NEXTSONG:KEY_RIGHT
KEY_PREVIOUSSONG:KEY_LEFT

# Remap play/pause to Enter
KEY_PLAYPAUSE:KEY_ENTER
```

Lines starting with `#` are treated as comments and are ignored. Empty lines are also ignored.

**Key names**: Use standard Linux input event key names (e.g., `KEY_A`, `KEY_ENTER`, `KEY_VOLUMEUP`, `KEY_PLAYPAUSE`). You can find a list of available key names in the evdev documentation or by examining the `ecodes` module in Python's evdev library.

---

### Trigger Configuration

The application now supports direct trigger handling. This allows key events to directly execute commands.

**Security Note**: Commands in the trigger configuration file are executed via shell. Only use trigger configuration files from trusted sources, and never allow untrusted users to modify your trigger configuration file.

#### Enabling Trigger Support

Use the `--triggers` option to specify a configuration file:

```ash
sudo -E python3 hid_ble_bridge.py --device-mac AA:BB:CC:DD:EE:FF --triggers /path/to/triggers.conf
```

#### Trigger Configuration Format

The trigger configuration file follows the format:
```
<event name>	<event value>	<command line>
```

Where:
- `<event name>`: Key name (e.g., `KEY_PLAYPAUSE`, `KEY_VOLUMEUP`)
- `<event value>`: Event type based on how long the key was held before release
  - `0` = key release (always available after any key release)
  - `1` = short press (key was held for less than 0.5 seconds)
  - `2` = long press/hold (key was held for 0.5 seconds or more)
- `<command line>`: Command to execute when the trigger matches

**Note on press duration detection**: The system waits for a complete press-and-release cycle before determining which trigger to execute. When you press a key, it records the press time. When you release the key, it calculates how long the key was held and executes either the value 1 trigger (< 0.5s) or value 2 trigger (>= 0.5s). This means:
- Value 1 triggers execute on release after a short press
- Value 2 triggers execute on release after a long press
- Value 0 triggers execute on any release (optional, for cleanup actions)

**Important**: Unlike some systems where value 2 means "repeat", in this implementation value 2 means "long press". You get ONE trigger execution per key release, not continuous repeats.

Example `triggers.conf`:
```
# Short press actions (key held < 0.5s)
KEY_PLAYPAUSE   1   /usr/local/bin/pcp pause

# Long press actions (key held >= 0.5s)
KEY_PLAYPAUSE   2   /usr/local/bin/pcp stop

# Can have both short and long press for same key
KEY_NEXTSONG    1   /usr/local/bin/pcp next
KEY_NEXTSONG    2   /usr/local/bin/pcp random

# Simple single action (short press only)
KEY_VOLUMEUP    1   /usr/local/bin/pcp up
KEY_VOLUMEDOWN  1   /usr/local/bin/pcp down
```

#### Modifier Keys

You can also specify modifier keys by appending them with `+`:
```
KEY_VOLUMEUP+KEY_LEFTSHIFT  1  /usr/local/bin/pcp up_big
KEY_A+KEY_LEFTCTRL          1  /usr/bin/echo "Ctrl+A pressed"
```

The application will only trigger the command when all specified modifier keys are pressed together with the main key.

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