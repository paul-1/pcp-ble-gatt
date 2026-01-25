#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BLE HID Bridge with verified keyboard and mouse state handling.
Run:  sudo -E python3 hid_ble_bridge.py --device-mac <MAC_ADDRESS>
 or:  sudo -E python3 hid_ble_bridge.py --device-name "HID Remote01"
"""

import asyncio
import signal
import argparse
import subprocess
import time
import os
from bleak import BleakClient, BleakScanner
from evdev import UInput, ecodes as e
from bleak.exc import BleakDeviceNotFoundError, BleakDBusError

# BLE UUIDs for HID Service and Characteristics
UUID_HID_SERVICE = "00001812-0000-1000-8000-00805f9b34fb"  # HID Service
UUID_HID_REPORT = "00002a4d-0000-1000-8000-00805f9b34fb"   # HID Report

# Key Mappings for HID Usages
USAGE_TO_EVKEY = {
    **{i: getattr(e, f"KEY_{chr(ord('A') + (i - 0x04))}") for i in range(0x04, 0x1e)},  # A-Z
    0x1e: e.KEY_1, 0x1f: e.KEY_2, 0x20: e.KEY_3, 0x21: e.KEY_4, 0x22: e.KEY_5,
    0x23: e.KEY_6, 0x24: e.KEY_7, 0x25: e.KEY_8, 0x26: e.KEY_9, 0x27: e.KEY_0,
    0x28: e.KEY_ENTER, 0x29: e.KEY_ESC, 0x2a: e.KEY_BACKSPACE, 0x2b: e.KEY_TAB,
    0x2c: e.KEY_SPACE, 0x2d: e.KEY_MINUS, 0x2e: e.KEY_EQUAL, 0x2f: e.KEY_LEFTBRACE,
    0x30: e.KEY_RIGHTBRACE, 0x31: e.KEY_BACKSLASH, 0x33: e.KEY_SEMICOLON,
    0x34: e.KEY_APOSTROPHE, 0x35: e.KEY_GRAVE, 0x36: e.KEY_COMMA,
    0x37: e.KEY_DOT, 0x38: e.KEY_SLASH, 0x39: e.KEY_CAPSLOCK,
    0x3a: e.KEY_F1, 0x3b: e.KEY_F2, 0x3c: e.KEY_F3, 0x3d: e.KEY_F4,
    0x3e: e.KEY_F5, 0x3f: e.KEY_F6, 0x40: e.KEY_F7, 0x41: e.KEY_F8,
    0x42: e.KEY_F9, 0x43: e.KEY_F10, 0x44: e.KEY_F11, 0x45: e.KEY_F12,
    0x4f: e.KEY_RIGHT, 0x50: e.KEY_LEFT, 0x51: e.KEY_DOWN, 0x52: e.KEY_UP,  # Arrow keys
}

# Expanded media/consumer usage mappings (common HID Consumer Page codes)
MEDIA_USAGE_TO_EVKEY = {
    0x00B0: e.KEY_PLAY,           # Play
    0x00B1: e.KEY_PAUSE,          # Pause
    0x00B2: e.KEY_RECORD,         # Record
    0x00B3: e.KEY_FASTFORWARD,    # Fast Forward
    0x00B4: e.KEY_REWIND,         # Rewind
    0x00B5: e.KEY_NEXTSONG,       # Scan Next Track
    0x00B6: e.KEY_PREVIOUSSONG,   # Scan Previous Track
    0x00B7: e.KEY_STOP,           # Stop
    0x00B8: e.KEY_EJECTCD,        # Eject
    0x00CD: e.KEY_PLAYPAUSE,      # Play/Pause toggle
    0x00E2: e.KEY_MUTE,           # Mute
    0x00E9: e.KEY_VOLUMEUP,       # Volume Up
    0x00EA: e.KEY_VOLUMEDOWN,     # Volume Down
    0x0183: e.KEY_CONFIG,         # Consumer Control Configuration
    0x018A: e.KEY_MAIL,           # AL Email Reader
    0x0192: e.KEY_CALC,           # AL Calculator
    0x0194: e.KEY_FILE,           # AL Local Machine Browser
    0x0223: e.KEY_HOMEPAGE,       # AC Home
    0x0224: e.KEY_BACK,           # AC Back
    0x0225: e.KEY_FORWARD,        # AC Forward
    0x0226: e.KEY_STOP,           # AC Stop
    0x0227: e.KEY_REFRESH,        # AC Refresh
    0x022A: e.KEY_BOOKMARKS,      # AC Bookmarks
}

# System control (HID Usage Page 0x01, Usage 0x80, bits 0..2)
SYSTEM_BITS_TO_EVKEY = {
    0: e.KEY_POWER,    # System Power Down
    1: e.KEY_SLEEP,    # System Sleep
    2: e.KEY_WAKEUP,   # System Wake Up
}

MOD_BITS_TO_EVKEY = {
    0: e.KEY_LEFTCTRL, 1: e.KEY_LEFTSHIFT, 2: e.KEY_LEFTALT, 3: e.KEY_LEFTMETA,
    4: e.KEY_RIGHTCTRL, 5: e.KEY_RIGHTSHIFT, 6: e.KEY_RIGHTALT, 7: e.KEY_RIGHTMETA,
}

# Reverse lookup for readable key names (handles aliases safely)
KEYCODE_TO_NAME = {}
NAME_TO_KEYCODE = {}  # Reverse lookup for efficiency
for name, code in e.ecodes.items():
    if not name.startswith("KEY_"):
        continue
    if isinstance(code, int):
        KEYCODE_TO_NAME[code] = name
        NAME_TO_KEYCODE[name] = code
    elif isinstance(code, list):
        # For aliases, use the first code and store all names
        for c in code:
            KEYCODE_TO_NAME[c] = name
        # Store only first code for reverse lookup to avoid overwriting
        if name not in NAME_TO_KEYCODE:
            NAME_TO_KEYCODE[name] = code[0]

# Task management and key tracking
notification_tasks = []
key_states = set()
key_press_times = {}  # track when keys were pressed for hold duration
media_pressed_by_source = {}  # track currently pressed media keys per source
media_press_times = {}  # track when media keys were pressed for hold duration
system_pressed_by_source = {}  # track system control presses per source
system_press_times = {}  # track when system control keys were pressed for hold duration
current_modifiers = set()  # track currently active modifiers for trigger matching
stop_loop = False

# Report definitions parsed from HID Report Map
report_definitions = {}  # report_id -> {"type": str, "size_bytes": int, "usage_pairs": set}

# Minimum hold duration in seconds before value 2 (hold/repeat) events are triggered
MIN_HOLD_DURATION = 0.5  # 500ms - typical hold threshold

debug = False
def printlog(data):
    global debug
    if debug:
        print(data)

# ==============================================================================
# Trigger configuration handling
# ==============================================================================

triggers = []  # List of (event_keys, event_value, command) tuples
MAX_LOG_COMMAND_LENGTH = 50  # Maximum length of command to log (for security)

def parse_triggers_file(filepath: str) -> list:
    """
    Parse triggerhappy-style configuration file.
    Format: <event name>	<event value>	<command line>
    
    Returns list of tuples: (event_keys, event_value, command)
    where event_keys is a list of key names (first is main key, rest are modifiers)
    
    Note: Caller should verify file exists before calling this function.
    """
    parsed_triggers = []
    
    try:
        with open(filepath, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Split on whitespace, limiting to 3 parts
                parts = line.split(None, 2)
                if len(parts) < 3:
                    printlog(f"Warning: Invalid trigger line {line_num}: {line}")
                    continue
                
                event_name, event_value_str, command = parts
                
                # Parse event value
                try:
                    event_value = int(event_value_str)
                except ValueError:
                    printlog(f"Warning: Invalid event value on line {line_num}: {event_value_str}")
                    continue
                
                # Parse event name (may include modifiers with +)
                event_keys = event_name.split('+')
                
                parsed_triggers.append((event_keys, event_value, command))
                # Log only first MAX_LOG_COMMAND_LENGTH chars to avoid exposing sensitive data
                safe_command = command[:MAX_LOG_COMMAND_LENGTH] + "..." if len(command) > MAX_LOG_COMMAND_LENGTH else command
                printlog(f"Loaded trigger: {event_keys} = {event_value} -> {safe_command}")
    
    except Exception as e:
        printlog(f"Error reading trigger file {filepath}: {e}")
    
    return parsed_triggers

def match_trigger(keycode: int, value: int, active_modifiers: set) -> str:
    """
    Check if a key event matches any configured trigger.
    
    Args:
        keycode: The evdev keycode that was pressed/released
        value: Event value (0=release, 1=press, 2=hold/repeat)
        active_modifiers: Set of currently active modifier keycodes
    
    Returns:
        Command string to execute, or None if no match
    """
    global triggers
    
    # Get the key name for the keycode
    key_name = KEYCODE_TO_NAME.get(keycode)
    if not key_name:
        return None
    
    # Find all matching triggers and select the most specific one
    matches = []
    
    for trigger_keys, trigger_value, command in triggers:
        # Check if event value matches
        if trigger_value != value:
            continue
        
        # First key in trigger_keys is the main key
        main_key = trigger_keys[0]
        modifier_keys = set(trigger_keys[1:])
        
        # Check if main key matches
        if main_key != key_name:
            continue
        
        # Check if all required modifiers are active (use NAME_TO_KEYCODE for efficiency)
        required_modifier_codes = set()
        for mod_name in modifier_keys:
            mod_code = NAME_TO_KEYCODE.get(mod_name)
            if mod_code is not None:
                required_modifier_codes.add(mod_code)
            else:
                # Log warning for unknown modifier names
                printlog(f"Warning: Unknown modifier key name '{mod_name}' in trigger configuration")
        
        # Check if required modifiers are a subset of active modifiers
        # This allows additional modifiers to be pressed (standard triggerhappy behavior)
        if required_modifier_codes.issubset(active_modifiers):
            matches.append((len(required_modifier_codes), command))
    
    # Return the most specific match (most modifiers)
    if matches:
        matches.sort(reverse=True)  # Sort by number of modifiers, descending
        return matches[0][1]
    
    return None

async def execute_trigger_command(command: str):
    """
    Execute a trigger command asynchronously in the background.
    Uses shell execution for compatibility with triggerhappy behavior.
    WARNING: Commands are executed via shell - only use trusted configuration files.
    """
    try:
        # Run command in background without waiting for completion
        # Note: Using shell=True for compatibility with triggerhappy format
        # Users should only use trusted trigger configuration files
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        # Log only first MAX_LOG_COMMAND_LENGTH chars to avoid exposing sensitive data
        safe_command = command[:MAX_LOG_COMMAND_LENGTH] + "..." if len(command) > MAX_LOG_COMMAND_LENGTH else command
        printlog(f"Executed trigger: {safe_command}")
        # Note: We don't wait for the process to complete to avoid blocking
    except Exception as e:
        printlog(f"Error executing trigger command: {e}")

async def handle_key_release_triggers(keycode: int, press_times: dict, active_modifiers: set, actions: list):
    """
    Handle trigger execution on key release based on hold duration.
    
    Args:
        keycode: The key that was released
        press_times: Dictionary tracking press times (either key_press_times or media_press_times)
        active_modifiers: Set of currently active modifier keycodes
        actions: List to append action descriptions to
    
    Returns:
        List of commands to execute (returned to allow logging after main HID report log)
    """
    commands_to_execute = []
    
    if keycode in press_times:
        press_time = press_times[keycode]
        current_time = time.time()
        hold_duration = current_time - press_time
        del press_times[keycode]
        
        # Check which trigger to execute based on hold duration
        if hold_duration >= MIN_HOLD_DURATION:
            # Key was held >= 0.5s, execute value 2 trigger
            actions.append(f"{key_name(keycode)} held for {hold_duration:.2f}s (value 2)")
            if command := match_trigger(keycode, 2, active_modifiers):
                commands_to_execute.append(command)
        else:
            # Key was held < 0.5s, execute value 1 trigger
            actions.append(f"{key_name(keycode)} held for {hold_duration:.2f}s (value 1)")
            if command := match_trigger(keycode, 1, active_modifiers):
                commands_to_execute.append(command)
        
        # Also check for release trigger (value 0)
        if command := match_trigger(keycode, 0, active_modifiers):
            commands_to_execute.append(command)
    
    return commands_to_execute

# ==============================================================================
# UInput device creation with retry logic
# ==============================================================================

def create_uinput_with_retry(capabilities, name, max_retries=5, initial_delay=0.5, max_delay=5.0):
    """
    Create a UInput device with retry logic to handle transient device errors.
    
    Args:
        capabilities: Device capabilities dict
        name: Device name string
        max_retries: Maximum number of retry attempts (default: 5)
        initial_delay: Initial delay between retries in seconds (default: 0.5)
        max_delay: Maximum delay between retries in seconds (default: 5.0)
    
    Returns:
        UInput device instance
    
    Raises:
        OSError: If all retry attempts fail
    """
    delay = initial_delay
    last_error = None
    
    for attempt in range(max_retries):
        try:
            ui = UInput(capabilities, name=name)
            if attempt > 0:
                printlog(f"Successfully created {name} after {attempt + 1} attempts")
            return ui
        except OSError as e:
            last_error = e
            if attempt < max_retries - 1:
                printlog(f"Failed to create {name} (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay:g}s...")
                time.sleep(delay)
                delay = min(delay * 2, max_delay)  # Exponential backoff with cap
            else:
                printlog(f"Failed to create {name} after {max_retries} attempts")
    
    # If we get here, all retries failed
    raise last_error

# ==============================================================================
# bluetoothctl helper functions for device preparation
# ==============================================================================

def run_bluetoothctl(*args: str) -> subprocess.CompletedProcess:
    cmd = ["bluetoothctl"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10)


def get_controller_power():
    result = run_bluetoothctl("show")
    info = {"powered": False}
    if result.returncode != 0:
        return info
    for line in result.stdout.splitlines():
        line_lower = line.strip().lower()
        if line_lower.startswith("powered:"):
            info["powered"] = "yes" in line_lower
    return info

def get_device_info(mac_address: str) -> dict:
    result = run_bluetoothctl("info", mac_address)
    info = {"paired": False, "bonded": False, "trusted": False, "connected": False}
    if result.returncode != 0:
        return info

    for line in result.stdout.splitlines():
        line_lower = line.strip().lower()
        if line_lower.startswith("paired:"):
            info["paired"] = "yes" in line_lower
        elif line_lower.startswith("bonded:"):
            info["bonded"] = "yes" in line_lower
        elif line_lower.startswith("trusted:"):
            info["trusted"] = "yes" in line_lower
        elif line_lower.startswith("connected:"):
            info["connected"] = "yes" in line_lower
    return info


def get_paired_devices() -> dict:
    result = run_bluetoothctl("devices", "Paired")
    devices = {}
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if line.startswith("Device "):
                parts = line.split(" ", 2)
                if len(parts) == 3:
                    mac = parts[1]
                    name = parts[2]
                    devices[name] = mac
    return devices


async def find_device_by_name(device_name: str, scan_timeout: float = 10.0) -> str:
    paired_devices = get_paired_devices()
    for name, mac in paired_devices.items():
        if device_name.lower() in name.lower():
            printlog(f"Found paired device '{name}' with MAC address {mac}.")
            return mac

    printlog(f"Device not paired. Scanning for '{device_name}'...")
    found_device = None

    def detection_callback(device, advertisement_data):
        nonlocal found_device
        if device.name and device_name.lower() in device.name.lower():
            found_device = device

    scanner = BleakScanner(detection_callback=detection_callback)
    try:
        await scanner.start()
        start_time = asyncio.get_event_loop().time()
        while found_device is None:
            if asyncio.get_event_loop().time() - start_time > scan_timeout:
                break
            await asyncio.sleep(0.1)
    except Exception as ex:
        printlog(f"Error during scan: {ex}")
    finally:
        await scanner.stop()

    if found_device:
        printlog(f"Found device '{found_device.name}' at {found_device.address}.")
        return found_device.address

    printlog(f"Could not find device named '{device_name}'.")
    return None


async def prepare_device_for_connection(mac_address: str) -> bool:
    info = get_device_info(mac_address)
    printlog(f"Device state: Paired={info['paired']}, Bonded={info['bonded']}, "
          f"Trusted={info['trusted']}, Connected={info['connected']}")

    if info["connected"]:
        printlog("Device is connected. Disconnecting...")
        run_bluetoothctl("disconnect", mac_address)
        await asyncio.sleep(1)
        info = get_device_info(mac_address)
        if info["connected"]:
            printlog("Error: Failed to disconnect device.")
            return False
        printlog("Device disconnected.")

    if info["paired"] and not info["bonded"]:
        printlog("Error: Device is paired but not bonded. Please remove and re-pair the device.")
        return False

    if info["trusted"]:
        printlog("Device is trusted. Removing trust to prevent auto-connect...")
        run_bluetoothctl("untrust", mac_address)
        await asyncio.sleep(0.5)
        printlog("Device untrusted.")

    if not info["paired"]:
        printlog("Device is not paired. Bleak will handle pairing automatically.")

    printlog("Device is ready for connection.")
    return True


# ==============================================================================
# HID Report Map parsing
# ==============================================================================

def determine_report_type(usage_pairs: set) -> str:
    for usage_page, usage in usage_pairs:
        if usage_page == 0x01 and usage == 0x02:
            return "mouse"
        if usage_page == 0x01 and usage == 0x06:
            return "keyboard"
        if usage_page == 0x0C and usage == 0x01:
            return "consumer"
        if usage_page == 0x01 and usage == 0x80:
            return "system"
    return "unknown"

def parse_hid_report_map(report_map: bytes) -> dict:
    """
    Parse HID Report Map to build report definitions by report ID.
    Returns dict: report_id -> { "type": str, "size_bytes": int, "usage_pairs": set }
    """
    report_bits = {}
    report_types = {}
    usage_page = None
    usage = None
    report_size = 0
    report_count = 0
    report_id = 0
    collection_stack = []

    i = 0
    while i < len(report_map):
        prefix = report_map[i]

        # Long item
        if prefix == 0xFE and i + 2 < len(report_map):
            data_len = report_map[i + 1]
            i += 2 + data_len
            continue

        size_code = prefix & 0x03
        size = 4 if size_code == 3 else size_code
        item_type = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        data = report_map[i + 1:i + 1 + size] if size else b""
        value = int.from_bytes(data, "little") if size else 0

        if item_type == 1:  # Global
            if tag == 0x0:  # Usage Page
                usage_page = value
            elif tag == 0x7:  # Report Size
                report_size = value
            elif tag == 0x9:  # Report Count
                report_count = value
            elif tag == 0x8:  # Report ID
                report_id = value
        elif item_type == 2:  # Local
            if tag == 0x0:  # Usage
                usage = value
        elif item_type == 0:  # Main
            if tag == 0xA:  # Collection
                collection_stack.append((usage_page, usage))
            elif tag == 0xC:  # End Collection
                if collection_stack:
                    collection_stack.pop()
            elif tag == 0x8:  # Input
                bits = report_size * report_count
                report_bits[report_id] = report_bits.get(report_id, 0) + bits
                if collection_stack:
                    report_types.setdefault(report_id, set()).add(collection_stack[-1])

        i += 1 + size

    definitions = {}
    for rid, bits in report_bits.items():
        size_bytes = (bits + 7) // 8
        usage_pairs = report_types.get(rid, set())
        report_type = determine_report_type(usage_pairs)
        definitions[rid] = {
            "type": report_type,
            "size_bytes": size_bytes,
            "usage_pairs": usage_pairs,
        }
    return definitions

def resolve_report_definition(data: bytes):
    """
    Resolve report ID + payload based on report definitions.
    Handles devices that omit report IDs by matching payload length.
    """
    if not report_definitions:
        return None

    if data and data[0] in report_definitions:
        definition = report_definitions[data[0]]
        size_bytes = definition["size_bytes"]
        if len(data) - 1 >= size_bytes:
            return data[0], definition, data[1:1 + size_bytes]

    matches = []
    for rid, definition in report_definitions.items():
        if len(data) == definition["size_bytes"]:
            matches.append((rid, definition))

    if len(matches) == 1:
        rid, definition = matches[0]
        return rid, definition, data

    return None

# ==============================================================================
# HID handling functions with enhanced logging
# ==============================================================================

def press(ui: UInput, keycode: int):
    ui.write(e.EV_KEY, keycode, 1)
    ui.syn()


def release(ui: UInput, keycode: int):
    ui.write(e.EV_KEY, keycode, 0)
    ui.syn()


def inject_mouse_event(ui: UInput, buttons, x, y, scroll):
    for bit, button in enumerate([e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE]):
        if buttons & (1 << bit):
            ui.write(e.EV_KEY, button, 1)
        else:
            ui.write(e.EV_KEY, button, 0)

    ui.write(e.EV_REL, e.REL_X, x)
    ui.write(e.EV_REL, e.REL_Y, y)
    if scroll != 0:
        ui.write(e.EV_REL, e.REL_WHEEL, scroll)
    ui.syn()


def key_name(keycode: int) -> str:
    return KEYCODE_TO_NAME.get(keycode, f"KEY_{keycode}")


async def decode_hid_report_and_inject(ui_kb: UInput, ui_mouse: UInput, source: str, data: bytes):
    global key_states, media_pressed_by_source, system_pressed_by_source, current_modifiers, key_press_times, media_press_times, system_press_times
    actions = []
    commands_to_execute = []

    report_id = None
    report_type = None
    payload = data

    resolved = resolve_report_definition(data)
    if resolved:
        report_id, definition, payload = resolved
        report_type = definition["type"]

    # Fallback heuristics if report map is unavailable or ambiguous
    if report_type is None:
        if len(data) in (2, 3):
            report_type = "consumer"
        elif len(data) == 5:
            report_type = "mouse"
        elif len(data) == 8:
            report_type = "keyboard"
        elif len(data) == 1:
            report_type = "system"
        else:
            report_type = "unknown"

    # Consumer control report (2 bytes payload)
    if report_type == "consumer":
        if len(payload) >= 2:
            usage = int.from_bytes(payload[:2], "little")
        else:
            usage = 0
        media_pressed_by_source.setdefault(source, set())

        if usage in MEDIA_USAGE_TO_EVKEY and usage != 0:
            keycode = MEDIA_USAGE_TO_EVKEY[usage]
            current_time = time.time()
            
            if keycode not in media_pressed_by_source[source]:
                press(ui_kb, keycode)
                media_pressed_by_source[source].add(keycode)
                media_press_times[keycode] = current_time
                actions.append(f"{key_name(keycode)} Pressed")
                # Note: We don't execute triggers on press, only on release
        elif usage == 0:
            to_release = list(media_pressed_by_source[source])
            for keycode in to_release:
                release(ui_kb, keycode)
                actions.append(f"{key_name(keycode)} Released")
                
                # Collect commands to execute after logging
                cmds = await handle_key_release_triggers(keycode, media_press_times, current_modifiers, actions)
                commands_to_execute.extend(cmds)
                
            media_pressed_by_source[source].clear()
        else:
            actions.append(f"Unknown media usage {usage}")

    # Keyboard report (8 bytes payload)
    elif report_type == "keyboard":
        modifiers = payload[0] if len(payload) >= 1 else 0
        pressed_keys = {k for k in payload[2:] if k != 0} if len(payload) >= 2 else set()

        # Update global modifier state
        current_modifiers.clear()
        
        for bit, keycode in MOD_BITS_TO_EVKEY.items():
            if modifiers & (1 << bit):
                current_modifiers.add(keycode)
                if keycode not in key_states:
                    press(ui_kb, keycode)
                    key_states.add(keycode)
                    actions.append(f"{key_name(keycode)} Pressed")
            elif keycode in key_states:
                release(ui_kb, keycode)
                key_states.remove(keycode)
                actions.append(f"{key_name(keycode)} Released")

        for key in pressed_keys:
            keycode = USAGE_TO_EVKEY.get(key)
            if keycode:
                current_time = time.time()
                
                if keycode not in key_states:
                    press(ui_kb, keycode)
                    key_states.add(keycode)
                    key_press_times[keycode] = current_time
                    actions.append(f"{key_name(keycode)} Pressed")
                    # Note: We don't execute triggers on press, only on release
            else:
                actions.append(f"Unknown key usage {key}")

        for keycode in list(key_states):
            if keycode in USAGE_TO_EVKEY.values() and keycode not in {USAGE_TO_EVKEY.get(k) for k in pressed_keys}:
                release(ui_kb, keycode)
                key_states.remove(keycode)
                actions.append(f"{key_name(keycode)} Released")
                
                # Collect commands to execute after logging
                cmds = await handle_key_release_triggers(keycode, key_press_times, current_modifiers, actions)
                commands_to_execute.extend(cmds)

    # Mouse report (buttons + X + Y + optional wheel)
    elif report_type == "mouse":
        buttons = payload[0] if len(payload) >= 1 else 0
        x_mov = int.from_bytes(payload[1:2], byteorder="little", signed=True) if len(payload) >= 2 else 0
        y_mov = int.from_bytes(payload[2:3], byteorder="little", signed=True) if len(payload) >= 3 else 0
        scroll = int.from_bytes(payload[3:4], byteorder="little", signed=True) if len(payload) >= 4 else 0
        inject_mouse_event(ui_mouse, buttons, x_mov, y_mov, scroll)
        actions.append(f"Mouse buttons={buttons:02x} x={x_mov} y={y_mov} scroll={scroll}")

    # System control report (bitfield)
    elif report_type == "system":
        value = payload[0] if len(payload) >= 1 else 0
        system_pressed_by_source.setdefault(source, set())
        current_time = time.time()

        for bit, keycode in SYSTEM_BITS_TO_EVKEY.items():
            if value & (1 << bit):
                if keycode not in system_pressed_by_source[source]:
                    press(ui_kb, keycode)
                    system_pressed_by_source[source].add(keycode)
                    system_press_times[keycode] = current_time
                    actions.append(f"{key_name(keycode)} Pressed")
            else:
                if keycode in system_pressed_by_source[source]:
                    release(ui_kb, keycode)
                    system_pressed_by_source[source].remove(keycode)
                    actions.append(f"{key_name(keycode)} Released")
                    cmds = await handle_key_release_triggers(keycode, system_press_times, current_modifiers, actions)
                    commands_to_execute.extend(cmds)

    else:
        actions.append(f"Unsupported HID report length {len(data)}")

    rid_str = f" id={report_id}" if report_id is not None else ""
    action_str = "; ".join(actions) if actions else "No mapped actions"
    printlog(f"[{source}] Report type={report_type}{rid_str} data={data.hex()}  {action_str}")
    
    # Execute commands AFTER logging, so logs appear in correct order
    for command in commands_to_execute:
        await execute_trigger_command(command)


async def notification_handler(client: BleakClient, handle: int, ui_kb: UInput, ui_mouse: UInput):
    try:
        await client.start_notify(
            handle,
            lambda _, data: asyncio.create_task(decode_hid_report_and_inject(ui_kb, ui_mouse, f"HID-{handle}", data)),
        )
        printlog(f"Started notifications for HID report (handle={handle}).")
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        printlog(f"Notification handler for handle {handle} canceled.")
    finally:
        try:
            await client.stop_notify(handle)
        except Exception as e:
            printlog(f"Error stopping notifications: {e}")


async def cleanup(client, tasks):
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except BleakDBusError:
            pass
    if client.is_connected:
        try:
            await client.disconnect()
        except EOFError:
            printlog("Disconnect interrupted (EOFError) during shutdown; ignoring.")
        except Exception as e:
            printlog(f"Error during disconnect: {e}")
    
    # Clear task list to prevent memory leaks on reconnection
    global notification_tasks, key_states, media_pressed_by_source, system_pressed_by_source, current_modifiers, key_press_times, media_press_times, system_press_times
    notification_tasks.clear()
    
    # Reset key states to prevent stuck keys after disconnect
    key_states.clear()
    media_pressed_by_source.clear()
    system_pressed_by_source.clear()
    current_modifiers.clear()
    key_press_times.clear()
    media_press_times.clear()
    system_press_times.clear()


# ==============================================================================
# main
# ==============================================================================

async def main():
    parser = argparse.ArgumentParser(description="BLE HID Bridge with detailed feedback.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--device-mac", help="Bluetooth MAC address.")
    group.add_argument("--device-name", help="Bluetooth device name (e.g., 'HID Remote01').")
    parser.add_argument("--scan-timeout", type=float, default=10.0, help="Timeout in seconds for scanning by name (default: 10).")
    parser.add_argument("--debug", action="store_true", help="Enable messages on console")
    parser.add_argument("--triggers", type=str, help="Path to triggerhappy-style configuration file for executing commands on key events.")
    args = parser.parse_args()

    global stop_loop, debug, triggers, report_definitions

    if args.debug:
        debug = True

    # Load trigger configuration if specified
    if args.triggers:
        if os.path.isfile(args.triggers):
            triggers = parse_triggers_file(args.triggers)
            printlog(f"Loaded {len(triggers)} trigger(s) from {args.triggers}")
        else:
            printlog(f"Warning: Trigger file not found: {args.triggers}")
            printlog("Continuing without trigger handling...")

    while True:
        info = get_controller_power()
        if info["powered"]:
            break
        else:
            printlog("Controller is not ready")
            await asyncio.sleep(2)

    # Resolve MAC address
    if args.device_name:
        device_mac = await find_device_by_name(args.device_name, args.scan_timeout)
        if device_mac is None:
            return
    else:
        device_mac = args.device_mac

    # Prepare the device (disconnect if connected, check bonding, untrust)
    ready = await prepare_device_for_connection(device_mac)
    if not ready:
        return

    stop_event = asyncio.Event()
    
    # Define disconnect callback to detect when device disconnects
    def disconnected_callback(client):
        try:
            if not stop_event.is_set():
                printlog("Device disconnected. Will attempt to reconnect...")
            stop_event.set()
        except Exception as e:
            printlog(f"Error in disconnect callback: {e}")
    
    client = BleakClient(device_mac, disconnected_callback=disconnected_callback)

    def handle_sigint(signum, frame):
        global stop_loop
        stop_event.set()
        if signum != signal.SIGHUP:
            stop_loop = True

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)
    signal.signal(signal.SIGQUIT, handle_sigint)
    signal.signal(signal.SIGHUP, handle_sigint)

    kb_capabilities = {e.EV_KEY: set(USAGE_TO_EVKEY.values()) | set(MEDIA_USAGE_TO_EVKEY.values()) | set(SYSTEM_BITS_TO_EVKEY.values())}
    mouse_capabilities = {e.EV_KEY: {e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE}, e.EV_REL: {e.REL_X, e.REL_Y, e.REL_WHEEL}}
    
    ui_kb = create_uinput_with_retry(kb_capabilities, "pCP BLE HID Keyboard")
    ui_mouse = create_uinput_with_retry(mouse_capabilities, "pCP BLE HID Mouse")

    printlog(f"Virtual keyboard created: {ui_kb.device}")
    printlog(f"Virtual mouse created: {ui_mouse.device}")

    while not stop_loop:
        printlog(f"Connecting to: {device_mac}...")
        
        try:
            await client.connect()
            printlog(f"Connected to BLE device {device_mac}.")

            # Read and parse report map (best-effort)
            try:
                report_map = await client.read_gatt_char(UUID_HID_REPORT)
                report_definitions = parse_hid_report_map(report_map)
                if report_definitions:
                    for rid, definition in report_definitions.items():
                        rid_label = f"ID {rid}" if rid != 0 else "no ID"
                        printlog(f"Report {rid_label}: type={definition['type']} size={definition['size_bytes']} bytes")
                else:
                    printlog("Report map parsed but no report definitions found.")
            except Exception as e:
                report_definitions = {}
                printlog(f"Failed to read/parse Report Map: {e}")

            hid_reports = [
                char for svc in client.services if svc.uuid == UUID_HID_SERVICE
                for char in svc.characteristics if char.uuid == UUID_HID_REPORT and "notify" in char.properties
            ]
            for char in hid_reports:
                task = asyncio.create_task(notification_handler(client, char.handle, ui_kb, ui_mouse))
                notification_tasks.append(task)

            printlog("Waiting for input events. Press Ctrl+C to quit.")
            await stop_event.wait()

        except (asyncio.TimeoutError, asyncio.CancelledError) as err:
            printlog(f"Connect failed: {err}. Will retry...")
        except BleakDBusError as err:
            printlog(f"Bleak DBus error during connect: {err}. Will retry...")
        except Exception as err:
            printlog(f"Unexpected error during connect: {err}. Will retry...")

        finally:
            await cleanup(client, notification_tasks)
            await asyncio.sleep(3)
            stop_event.clear()

    printlog("Cleaning up...")
    ui_kb.close()
    ui_mouse.close()
    printlog("Virtual devices stopped.")


if __name__ == "__main__":
    asyncio.run(main())