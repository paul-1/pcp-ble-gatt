#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for validating HID Report Map parsing and report resolution.
Tests the two report maps provided in the issue.
"""

import sys

# Import the functions we're testing
from hid_ble_bridge import parse_hid_report_map, resolve_report_definition

# Set global variables needed by resolve_report_definition
import hid_ble_bridge
hid_ble_bridge.report_definitions = {}
hid_ble_bridge.report_ids_present = False

def test_device_1():
    """Test Device 1 HID Report Map from the issue."""
    print("\n" + "="*80)
    print("Testing Device 1")
    print("="*80)
    
    report_map_hex = "050c0901a101850119002a9c021500269c0295017510810009" \
                     "02a10205091901290a1501250a950175088140c0c005010906" \
                     "a1018502050775089506150026a400050719002aa4008100c0" \
                     "05010902a1010901a10085030501093009311580257f750895" \
                     "02810605091901290515002501950575018102950175038103" \
                     "c0c00601ff0901a10285040914750895501580257f81228504" \
                     "0904750895019102c0"
    
    report_map = bytes.fromhex(report_map_hex)
    
    # Parse the report map
    definitions = parse_hid_report_map(report_map)
    
    print(f"\nParsed {len(definitions)} report definitions:")
    for rid, definition in sorted(definitions.items()):
        rid_label = f"ID {rid}" if rid != 0 else "no ID"
        print(f"  Report {rid_label}:")
        print(f"    Type: {definition['type']}")
        print(f"    Size: {definition['size_bytes']} bytes ({definition['bits']} bits)")
        print(f"    Direction: {definition['direction']}")
        print(f"    Usage pairs: {definition['usage_pairs']}")
    
    # Update global state for resolve_report_definition
    hid_ble_bridge.report_definitions = definitions
    hid_ble_bridge.report_ids_present = any(rid != 0 for rid in definitions.keys())
    
    print(f"\nReport IDs present: {hid_ble_bridge.report_ids_present}")
    
    # Test resolving different report types
    print("\n" + "-"*80)
    print("Testing report resolution:")
    print("-"*80)
    
    # Test consumer report (ID 1, 2 bytes)
    test_consumer_report = bytes([0x01, 0x00, 0x00])  # Report ID 1, consumer report
    result = resolve_report_definition(test_consumer_report)
    if result:
        rid, defn, payload, id_included, reason = result
        print(f"\nConsumer report (3 bytes with padding):")
        print(f"  Resolved: Report ID {rid}, Type: {defn['type']}, Reason: {reason}")
        print(f"  ID included: {id_included}, Payload length: {len(payload)} bytes")
        print(f"  Payload: {payload.hex()}")
    
    # Test keyboard report (ID 2, 9 bytes)
    test_keyboard_report = bytes([0x02] + [0x00]*9)  # Report ID 2, keyboard report
    result = resolve_report_definition(test_keyboard_report)
    if result:
        rid, defn, payload, id_included, reason = result
        print(f"\nKeyboard report (10 bytes total):")
        print(f"  Resolved: Report ID {rid}, Type: {defn['type']}, Reason: {reason}")
        print(f"  ID included: {id_included}, Payload length: {len(payload)} bytes")
    
    # Test mouse report (ID 3, 2 bytes)
    test_mouse_report = bytes([0x03, 0x00, 0x00])  # Report ID 3, mouse report
    result = resolve_report_definition(test_mouse_report)
    if result:
        rid, defn, payload, id_included, reason = result
        print(f"\nMouse report (3 bytes total):")
        print(f"  Resolved: Report ID {rid}, Type: {defn['type']}, Reason: {reason}")
        print(f"  ID included: {id_included}, Payload length: {len(payload)} bytes")


def test_device_2():
    """Test Device 2 HID Report Map from the issue."""
    print("\n" + "="*80)
    print("Testing Device 2")
    print("="*80)
    
    report_map_hex = "05010902a10185010901a10005091901290815002501750195" \
                     "08810205010930093109381581257f750895038106c0c00501" \
                     "0906a1018502050719e029e715002501750195088102950175" \
                     "08810195057501050819012905910295017503910195067508" \
                     "1500257f0507190029658100c0050c0901a101850375109501" \
                     "1501268c0219012a8c028160c005010980a101850405011981" \
                     "298315002501950375018106950175058101c0"
    
    report_map = bytes.fromhex(report_map_hex)
    
    # Parse the report map
    definitions = parse_hid_report_map(report_map)
    
    print(f"\nParsed {len(definitions)} report definitions:")
    for rid, definition in sorted(definitions.items()):
        rid_label = f"ID {rid}" if rid != 0 else "no ID"
        print(f"  Report {rid_label}:")
        print(f"    Type: {definition['type']}")
        print(f"    Size: {definition['size_bytes']} bytes ({definition['bits']} bits)")
        print(f"    Direction: {definition['direction']}")
        print(f"    Usage pairs: {definition['usage_pairs']}")
    
    # Update global state for resolve_report_definition
    hid_ble_bridge.report_definitions = definitions
    hid_ble_bridge.report_ids_present = any(rid != 0 for rid in definitions.keys())
    
    print(f"\nReport IDs present: {hid_ble_bridge.report_ids_present}")
    
    # Test resolving different report types
    print("\n" + "-"*80)
    print("Testing report resolution:")
    print("-"*80)
    
    # Test mouse report (ID 1, should be 6 bytes based on descriptor)
    test_mouse_report = bytes([0x01] + [0x00]*6)  # Report ID 1, mouse report
    result = resolve_report_definition(test_mouse_report)
    if result:
        rid, defn, payload, id_included, reason = result
        print(f"\nMouse report (7 bytes total):")
        print(f"  Resolved: Report ID {rid}, Type: {defn['type']}, Reason: {reason}")
        print(f"  ID included: {id_included}, Payload length: {len(payload)} bytes")
    
    # Test keyboard report (ID 2)
    for rid, defn in definitions.items():
        if defn['type'] == 'keyboard':
            expected_size = defn['size_bytes']
            test_report = bytes([rid] + [0x00]*expected_size)
            result = resolve_report_definition(test_report)
            if result:
                r_id, r_defn, payload, id_included, reason = result
                print(f"\nKeyboard report ({len(test_report)} bytes total):")
                print(f"  Resolved: Report ID {r_id}, Type: {r_defn['type']}, Reason: {reason}")
                print(f"  ID included: {id_included}, Payload length: {len(payload)} bytes")
    
    # Test consumer report (ID 3, 2 bytes)
    test_consumer_report = bytes([0x03, 0x00, 0x00])  # Report ID 3, consumer with padding
    result = resolve_report_definition(test_consumer_report)
    if result:
        rid, defn, payload, id_included, reason = result
        print(f"\nConsumer report (3 bytes with padding):")
        print(f"  Resolved: Report ID {rid}, Type: {defn['type']}, Reason: {reason}")
        print(f"  ID included: {id_included}, Payload length: {len(payload)} bytes")
        print(f"  Payload: {payload.hex()}")


def test_padding_scenarios():
    """Test various padding scenarios."""
    print("\n" + "="*80)
    print("Testing Padding Scenarios")
    print("="*80)
    
    # Create a simple test report map with a 2-byte consumer report
    hid_ble_bridge.report_definitions = {
        1: {
            "type": "consumer",
            "direction": "input",
            "size_bytes": 2,
            "bits": 16,
            "usage_pairs": {(0x0C, 0x01)}
        }
    }
    hid_ble_bridge.report_ids_present = True
    
    print("\nTest report definition:")
    print("  Report ID 1: consumer, 2 bytes")
    
    # Test exact match (no padding)
    print("\n1. Exact match (no padding):")
    data = bytes([0x01, 0xE9, 0x00])  # Report ID 1, volume up
    result = resolve_report_definition(data)
    if result:
        rid, defn, payload, id_included, reason = result
        print(f"   Data: {data.hex()} -> Resolved as {defn['type']}, reason: {reason}")
        print(f"   Payload: {payload.hex()} ({len(payload)} bytes)")
        assert len(payload) == 2, "Payload should be 2 bytes"
        assert reason == "report_id_exact", "Should resolve with exact match"
        print("   ✓ PASS")
    else:
        print("   ✗ FAIL: Could not resolve")
    
    # Test with padding
    print("\n2. With padding (3 bytes instead of 2):")
    data = bytes([0x01, 0xE9, 0x00, 0x00])  # Report ID 1, volume up, with padding
    result = resolve_report_definition(data)
    if result:
        rid, defn, payload, id_included, reason = result
        print(f"   Data: {data.hex()} -> Resolved as {defn['type']}, reason: {reason}")
        print(f"   Payload: {payload.hex()} ({len(payload)} bytes)")
        assert len(payload) == 2, f"Payload should be trimmed to 2 bytes, got {len(payload)}"
        assert reason == "report_id_padded", "Should resolve with padded match"
        print("   ✓ PASS")
    else:
        print("   ✗ FAIL: Could not resolve")
    
    # Test with non-zero padding (should not match)
    print("\n3. With non-zero padding (should not match):")
    data = bytes([0x01, 0xE9, 0x00, 0xFF])  # Report ID 1, volume up, with non-zero padding
    result = resolve_report_definition(data)
    if result is None:
        print(f"   Data: {data.hex()} -> Not resolved (as expected)")
        print("   ✓ PASS")
    else:
        print(f"   ✗ FAIL: Should not resolve with non-zero padding")
    
    # Test without report ID (length matching)
    print("\n4. Without report ID in data (length matching):")
    hid_ble_bridge.report_ids_present = False
    data = bytes([0xE9, 0x00])  # Just the payload, no report ID
    result = resolve_report_definition(data)
    if result:
        rid, defn, payload, id_included, reason = result
        print(f"   Data: {data.hex()} -> Resolved as {defn['type']}, reason: {reason}")
        print(f"   ID included: {id_included}, Payload: {payload.hex()} ({len(payload)} bytes)")
        assert not id_included, "ID should not be included"
        assert reason == "length_exact", "Should resolve by length"
        print("   ✓ PASS")
    else:
        print("   ✗ FAIL: Could not resolve")
    
    # Test without report ID but with padding
    print("\n5. Without report ID, with padding (length matching):")
    data = bytes([0xE9, 0x00, 0x00])  # Payload with padding, no report ID
    result = resolve_report_definition(data)
    if result:
        rid, defn, payload, id_included, reason = result
        print(f"   Data: {data.hex()} -> Resolved as {defn['type']}, reason: {reason}")
        print(f"   Payload: {payload.hex()} ({len(payload)} bytes)")
        assert len(payload) == 2, f"Payload should be trimmed to 2 bytes, got {len(payload)}"
        assert reason == "length_padded", "Should resolve with padded length match"
        print("   ✓ PASS")
    else:
        print("   ✗ FAIL: Could not resolve")


if __name__ == "__main__":
    try:
        test_device_1()
        test_device_2()
        test_padding_scenarios()
        
        print("\n" + "="*80)
        print("All tests completed successfully!")
        print("="*80)
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
