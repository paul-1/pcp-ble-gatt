#!/usr/bin/env python3
#
# Automate BLE HID pairing by power-cycling the controller, then cleanly exit.
# Flow:
#   1) Discover target device (match by MAC or name prefix)
#   2) Power-cycle adapter (off -> on).
#   3) After adapter is back and device appears again, call Pair()
#   4) Auto-accept RequestAuthorization/RequestConfirmation (KeyboardDisplay agent)
#   5) Optionally set Trusted based on CLI flag
#   6) Disconnect if still connected, print device info, stop discovery, unregister agent, exit
#
# Requirements:
#   tce-load -wi dbus-python3.11.tcz py3.11gobject-mini.tcz
#
import sys
import time
import argparse
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

BUS_NAME = 'org.bluez'
AGENT_PATH = '/auto/agent'

STATE = {
    'adapter': None,          # Adapter1 interface
    'adapter_path': None,     # /org/bluez/hci0
    'device_path': None,      # /org/bluez/hci0/dev_XX_XX_...
    'power_cycled': False,
    'pair_attempted': False,
    'paired': False,
    'loop': None,
    'trust_after_pair': False,
}

# ==============================================================================
# Logging configuration
# ==============================================================================

def setup_logging():
    """
    Configure logging with console and rotating file handler.
    Always outputs to console and to log file.
    """
    logger = logging.getLogger('pcp_hidbridge')
    logger.setLevel(logging.DEBUG)  # Capture all levels
    
    # Remove any existing handlers
    logger.handlers.clear()
    
    # Console handler - always enabled for this utility
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Rotating file handler
    try:
        log_dir = '/var/log'
        # Create log directory if it doesn't exist (for testing in non-system environments)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(log_dir, f'pcp_hidbridge-{timestamp}.log')
        
        # Rotating file handler: max 5MB per file, keep 5 backup files
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5*1024*1024,  # 5MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        logger.info(f'Logging initialized. Log file: {log_file}')
    except (OSError, PermissionError) as e:
        # If we can't write to /var/log, fall back to console only
        logger.warning(f'Could not create log file in /var/log: {e}. Logging to console only.')
    
    return logger

# Initialize logger (will be properly configured in main())
logger = logging.getLogger('pcp_hidbridge')

class Agent(dbus.service.Object):
    def __init__(self, bus, path):
        super().__init__(bus, path)

    @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
    def Release(self):
        logger.info('Agent released')

    # Auto-accept the authorization prompt
    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='')
    def RequestAuthorization(self, device):
        logger.info(f'RequestAuthorization {device} -> accept')
        return

    # Auto-accept numeric comparison / JustWorks
    @dbus.service.method('org.bluez.Agent1', in_signature='ou', out_signature='')
    def RequestConfirmation(self, device, passkey):
        try:
            p = int(passkey)
        except Exception:
            p = passkey
        logger.info(f'RequestConfirmation {device} passkey {p:06d} -> accept' if isinstance(p, int)
              else f'RequestConfirmation {device} passkey {passkey} -> accept')
        return

    # If peripheral asks the central to provide a passkey (unlikely for HID), return if configured
    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='u')
    def RequestPasskey(self, device):
        raise dbus.exceptions.DBusException('org.bluez.Error.Rejected', 'No passkey configured')

    # Typical HID: host displays the code; the remote types it
    @dbus.service.method('org.bluez.Agent1', in_signature='ou', out_signature='')
    def DisplayPasskey(self, device, passkey):
        try:
            p = int(passkey)
            logger.info(f'DisplayPasskey {device} {p:06d}')
        except Exception:
            logger.info(f'DisplayPasskey {device} {passkey}')

    @dbus.service.method('org.bluez.Agent1', in_signature='os', out_signature='')
    def AuthorizeService(self, device, uuid):
        logger.info(f'AuthorizeService {device} uuid={uuid} -> accept')
        return

    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='')
    def Cancel(self, device):
        logger.info(f'Agent request canceled for {device}')

def get_managed_objects(bus):
    obj = bus.get_object(BUS_NAME, '/')
    mgr = dbus.Interface(obj, 'org.freedesktop.DBus.ObjectManager')
    return mgr.GetManagedObjects()

def find_adapter_path(objects, name):
    # Prefer adapter path ending with the given name (e.g., hci0)
    for path, ifaces in objects.items():
        if ifaces.get('org.bluez.Adapter1') and path.endswith(name):
            return path
    # Fallback: first adapter found
    for path, ifaces in objects.items():
        if 'org.bluez.Adapter1' in ifaces:
            return path
    raise RuntimeError('No Bluetooth adapter found')

def device_matches(props, target_address, target_prefix):
    addr = props.get('Address')
    name = props.get('Name') or props.get('Alias')
    if target_address:
        return addr == target_address
    if target_prefix:
        return name and name.startswith(target_prefix)
    # If neither provided, never match
    return False

def stop_discovery():
    if STATE['adapter']:
        try:
            STATE['adapter'].StopDiscovery()
        except dbus.DBusException:
            pass

def start_discovery():
    if STATE['adapter']:
        try:
            STATE['adapter'].StartDiscovery()
        except dbus.DBusException as e:
            logger.error(f'StartDiscovery failed: {e}')

def power_cycle_adapter(bus):
    if not STATE['adapter_path']:
        return
    adapter_obj = bus.get_object(BUS_NAME, STATE['adapter_path'])
    adapter_props = dbus.Interface(adapter_obj, 'org.freedesktop.DBus.Properties')

    try:
        logger.info('Power cycling adapter: off...')
        adapter_props.Set('org.bluez.Adapter1', 'Powered', dbus.Boolean(False))
    except dbus.DBusException as e:
        logger.error(f'Power off failed: {e}')
    time.sleep(1.0)
    try:
        logger.info('Power cycling adapter: on...')
        adapter_props.Set('org.bluez.Adapter1', 'Powered', dbus.Boolean(True))
    except dbus.DBusException as e:
        logger.error(f'Power on failed: {e}')
    STATE['power_cycled'] = True
    # Restart discovery shortly after power returns
    GLib.timeout_add(500, lambda: (start_discovery(), False)[1])

def pair_now(bus):
    if not STATE['device_path'] or STATE['pair_attempted'] or STATE['paired']:
        return
    STATE['pair_attempted'] = True
    path = STATE['device_path']
    logger.info(f'Calling Pair() on {path}...')
    dev_iface = dbus.Interface(bus.get_object(BUS_NAME, path), 'org.bluez.Device1')
    props_iface = dbus.Interface(bus.get_object(BUS_NAME, path), 'org.freedesktop.DBus.Properties')

    def ok():
        logger.info('Pair() completed')
        STATE['paired'] = True
        # Optionally set Trusted based on CLI flag
        if STATE['trust_after_pair']:
            try:
                props_iface.Set('org.bluez.Device1', 'Trusted', dbus.Boolean(True))
                logger.info('Trusted set to True')
            except dbus.DBusException as e:
                logger.error(f'Setting Trusted failed: {e}')
        GLib.idle_add(lambda: cleanup_and_exit(bus))

    def err(e):
        logger.error(f'Pair() error: {e}')
        # If the object disappeared or transient error, retry once after short delay
        STATE['pair_attempted'] = False
        GLib.timeout_add(1500, lambda: (pair_now(bus), False)[1])

    try:
        dev_iface.Pair(reply_handler=ok, error_handler=err, timeout=120)
    except dbus.DBusException as e:
        logger.info(f'Pair() immediate failure: {e}')
        STATE['pair_attempted'] = False
        GLib.timeout_add(1500, lambda: (pair_now(bus), False)[1])

def print_device_info(bus):
    if not STATE['device_path']:
        logger.info('No device path available for info.')
        return
    dev_obj = bus.get_object(BUS_NAME, STATE['device_path'])
    props = dbus.Interface(dev_obj, 'org.freedesktop.DBus.Properties')
    info = {'Address': None, 'Name': None, 'Paired': None, 'Connected': None,
            'Trusted': None, 'LegacyPairing': None, 'ServicesResolved': None,
            'Bonded': None}

    # Safe getters
    def get_prop(pname):
        try:
            return props.Get('org.bluez.Device1', pname)
        except dbus.DBusException:
            return None

    info['Address'] = get_prop('Address')
    info['Name'] = get_prop('Name') or get_prop('Alias')
    info['Paired'] = get_prop('Paired')
    info['Connected'] = get_prop('Connected')
    info['Trusted'] = get_prop('Trusted')
    info['LegacyPairing'] = get_prop('LegacyPairing')
    info['ServicesResolved'] = get_prop('ServicesResolved')

    # Bonded: not always exposed as a Device1 property. Try, else infer from Paired.
    bonded = get_prop('Bonded')
    if bonded is None:
        # Some UIs show "Bonded" when Paired==True; reflect that here
        bonded = bool(info['Paired']) if info['Paired'] is not None else None
    info['Bonded'] = bonded

    logger.info('Device info at cleanup:')
    logger.info(f'  Address: {info["Address"]}')
    logger.info(f'  Name: {info["Name"]}')
    logger.info(f'  Paired: {info["Paired"]}')
    logger.info(f'  Bonded: {info["Bonded"]}')
    logger.info(f'  Connected: {info["Connected"]}')
    logger.info(f'  Trusted: {info["Trusted"]}')
    logger.info(f'  LegacyPairing: {info["LegacyPairing"]}')
    logger.info(f'  ServicesResolved: {info["ServicesResolved"]}')

def cleanup_and_exit(bus):
    # Disconnect if still connected (we dont want to keep a link up)
    if STATE['device_path']:
        try:
            dev_obj = bus.get_object(BUS_NAME, STATE['device_path'])
            dev_props = dbus.Interface(dev_obj, 'org.freedesktop.DBus.Properties')
            dev_iface = dbus.Interface(dev_obj, 'org.bluez.Device1')
            if dev_props.Get('org.bluez.Device1', 'Connected'):
                logger.info('Disconnecting after pairing to keep manual connect workflow...')
                dev_iface.Disconnect()
        except dbus.DBusException:
            pass

    # Print device info
    print_device_info(bus)

    # Stop discovery
    stop_discovery()

    # Unregister agent
    try:
        agent_mgr = dbus.Interface(bus.get_object(BUS_NAME, '/org/bluez'), 'org.bluez.AgentManager1')
        agent_mgr.UnregisterAgent(AGENT_PATH)
        logger.info('Agent unregistered')
    except dbus.DBusException as e:
        logger.error(f'UnregisterAgent failed: {e}')

    logger.info('Cleanup complete. Exiting.')
    if STATE['loop']:
        STATE['loop'].quit()
    return False

def on_properties_changed(bus, interface_name, changed, invalidated, path):
    # Adapter powered back on -> (re)start discovery
    if path == STATE['adapter_path'] and interface_name == 'org.bluez.Adapter1':
        if 'Powered' in changed and bool(changed['Powered']):
            logger.info('Adapter Powered=True')
            start_discovery()
        return
    # Device properties
    if path == STATE['device_path'] and interface_name == 'org.bluez.Device1':
        if 'Paired' in changed:
            logger.info(f'[CHG] {path} Paired -> {changed["Paired"]}')
            if bool(changed['Paired']):
                STATE['paired'] = True
                # Optionally set Trusted when paired flips to True
                if STATE['trust_after_pair']:
                    try:
                        props_iface = dbus.Interface(bus.get_object(BUS_NAME, path), 'org.freedesktop.DBus.Properties')
                        props_iface.Set('org.bluez.Device1', 'Trusted', dbus.Boolean(True))
                        logger.info('Trusted set to True')
                    except dbus.DBusException as e:
                        logger.error(f'Setting Trusted failed: {e}')
                GLib.idle_add(lambda: cleanup_and_exit(bus))
        if 'Connected' in changed:
            logger.info(f'[CHG] {path} Connected -> {changed["Connected"]}')
        return

def on_interfaces_added(bus, adapter, path, ifaces, target_address, target_prefix):
    dev_props = ifaces.get('org.bluez.Device1')
    if not dev_props:
        return
    if not device_matches(dev_props, target_address, target_prefix):
        return

    addr = dev_props.get('Address')
    name = dev_props.get('Name') or dev_props.get('Alias')
    logger.info(f'Matched {addr} name={name} at {path}')
    STATE['device_path'] = path

    # Before power cycle: stop discovery and cycle power first (only once)
    if not STATE['power_cycled']:
        stop_discovery()
        GLib.idle_add(lambda: (power_cycle_adapter(bus), False)[1])
        return

    # After power cycle: call Pair once the device appears
    if STATE['power_cycled'] and not STATE['pair_attempted'] and not STATE['paired']:
        pair_now(bus)

def main():
    parser = argparse.ArgumentParser(description='Auto-pair BLE HID by power cycling the adapter, then exit.')
    parser.add_argument('--adapter', default='hci0', help='Adapter name (default: hci0)')
    parser.add_argument('--device-mac', help='Exact MAC address of target device (disables name matching)')
    parser.add_argument('--device-name', default='HID Remote', help='Device name prefix to match (default "HID Remote")')
    parser.add_argument('--trust', action='store_true', help='Set Trusted=true after pairing (default: false)')
    args = parser.parse_args()

    # Setup logging
    global logger
    logger = setup_logging()

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    # Register agent
    agent = Agent(bus, AGENT_PATH)
    agent_mgr = dbus.Interface(bus.get_object(BUS_NAME, '/org/bluez'), 'org.bluez.AgentManager1')
    capability = 'KeyboardDisplay'
    agent_mgr.RegisterAgent(AGENT_PATH, capability)
    agent_mgr.RequestDefaultAgent(AGENT_PATH)
    logger.info(f'Agent registered with capability {capability}')

    # Adapter
    objs = get_managed_objects(bus)
    adapter_path = find_adapter_path(objs, args.adapter)
    STATE['adapter_path'] = adapter_path
    adapter_obj = bus.get_object(BUS_NAME, adapter_path)
    adapter = dbus.Interface(adapter_obj, 'org.bluez.Adapter1')
    adapter_props = dbus.Interface(adapter_obj, 'org.freedesktop.DBus.Properties')
    STATE['adapter'] = adapter
    STATE['trust_after_pair'] = bool(args.trust)

    # Ensure adapter is powered and pairable
    adapter_props.Set('org.bluez.Adapter1', 'Powered', dbus.Boolean(True))
    adapter_props.Set('org.bluez.Adapter1', 'Pairable', dbus.Boolean(True))

    # Optional discovery filter
    try:
        adapter.SetDiscoveryFilter({'Transport': dbus.String('le'), 'DuplicateData': dbus.Boolean(True)})
    except dbus.DBusException as e:
        logger.error(f'Filter error (OK on some BlueZ versions): {e}')

    # Signals: PropertiesChanged (adapter + device)
    bus.add_signal_receiver(
        lambda iface, changed, invalidated, path: on_properties_changed(bus, iface, changed, invalidated, path),
        dbus_interface='org.freedesktop.DBus.Properties',
        signal_name='PropertiesChanged',
        path_keyword='path'
    )

    # Signal: InterfacesAdded (for devices)
    obj_mgr = dbus.Interface(bus.get_object(BUS_NAME, '/'), 'org.freedesktop.DBus.ObjectManager')
    obj_mgr.connect_to_signal('InterfacesAdded',
                              lambda path, ifaces: on_interfaces_added(bus, adapter, path, ifaces,
                                                                       args.device_mac, None if args.device_mac else args.device_name))

    # If the device is already known, treat it as added
    for path, ifaces in objs.items():
        dev_props = ifaces.get('org.bluez.Device1')
        if dev_props and device_matches(dev_props, args.device_mac, None if args.device_mac else args.device_name):
            on_interfaces_added(bus, adapter, path, ifaces, args.device_mac, None if args.device_mac else args.device_name)

    logger.info('Starting LE discovery...')
    start_discovery()

    loop = GLib.MainLoop()
    STATE['loop'] = loop

    # Safety: bail out if not paired within 1 minutes
    GLib.timeout_add_seconds(60, lambda: (logger.warning('Timeout waiting for pairing'),
                                           cleanup_and_exit(bus), False)[2])

    loop.run()
    # Non-zero exit if pairing didnt complete
    if not STATE['paired']:
        sys.exit(1)

if __name__ == '__main__':
    main()
