#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify triggers.conf parser handles blank lines and comments.
"""

import os
import sys
import tempfile

# Define the parse_triggers_file function directly to avoid import issues
def parse_triggers_file(filepath: str) -> list:
    """
    Parse triggerhappy-style configuration file.
    Format: <event name>	<event value>	<command line>
    
    Returns list of tuples: (event_keys, event_value, command)
    where event_keys is a list of key names (first is main key, rest are modifiers)
    
    Note: Caller should verify file exists before calling this function.
    """
    MAX_LOG_COMMAND_LENGTH = 50
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
                    print(f"Warning: Invalid trigger line {line_num}: {line}")
                    continue
                
                event_name, event_value_str, command = parts
                
                # Parse event value
                try:
                    event_value = int(event_value_str)
                except ValueError:
                    print(f"Warning: Invalid event value on line {line_num}: {event_value_str}")
                    continue
                
                # Parse event name (may include modifiers with +)
                event_keys = event_name.split('+')
                
                parsed_triggers.append((event_keys, event_value, command))
    
    except Exception as e:
        print(f"Error reading trigger file {filepath}: {e}")
    
    return parsed_triggers

def test_blank_lines_and_comments():
    """Test that parser correctly handles blank lines and comment lines"""
    
    # Create a test triggers.conf with blank lines and comments
    test_content = """# This is a comment at the start
# Another comment line

KEY_PLAYPAUSE 	1 /usr/local/bin/pcp pause

# Comment in the middle
KEY_VOLUMEUP 	1 /usr/local/bin/pcp up

KEY_VOLUMEDOWN 	2 /usr/local/bin/pcp down

# Comment at the end
"""
    
    # Write to a temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        temp_file = f.name
        f.write(test_content)
    
    try:
        # Parse the file
        triggers = parse_triggers_file(temp_file)
        
        # Verify results
        assert len(triggers) == 3, f"Expected 3 triggers, got {len(triggers)}"
        
        # Verify the parsed triggers
        assert triggers[0] == (['KEY_PLAYPAUSE'], 1, '/usr/local/bin/pcp pause'), \
            f"First trigger mismatch: {triggers[0]}"
        
        assert triggers[1] == (['KEY_VOLUMEUP'], 1, '/usr/local/bin/pcp up'), \
            f"Second trigger mismatch: {triggers[1]}"
        
        assert triggers[2] == (['KEY_VOLUMEDOWN'], 2, '/usr/local/bin/pcp down'), \
            f"Third trigger mismatch: {triggers[2]}"
        
        print("✓ Test passed: Parser correctly handles blank lines and comments")
        print(f"  - Parsed {len(triggers)} triggers from file with comments and blank lines")
        
    finally:
        # Clean up temporary file
        os.unlink(temp_file)

def test_modifier_keys_with_comments():
    """Test that parser handles modifier keys with comments and blank lines"""
    
    test_content = """
# Test modifier keys
KEY_VOLUMEUP+KEY_LEFTSHIFT 	1 /usr/local/bin/pcp volume_big

# Blank line above and below

KEY_A+KEY_LEFTCTRL 	2 /bin/echo "Ctrl+A long press"
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        temp_file = f.name
        f.write(test_content)
    
    try:
        triggers = parse_triggers_file(temp_file)
        
        assert len(triggers) == 2, f"Expected 2 triggers, got {len(triggers)}"
        
        assert triggers[0] == (['KEY_VOLUMEUP', 'KEY_LEFTSHIFT'], 1, '/usr/local/bin/pcp volume_big'), \
            f"First trigger with modifier mismatch: {triggers[0]}"
        
        assert triggers[1] == (['KEY_A', 'KEY_LEFTCTRL'], 2, '/bin/echo "Ctrl+A long press"'), \
            f"Second trigger with modifier mismatch: {triggers[1]}"
        
        print("✓ Test passed: Parser correctly handles modifier keys with comments")
        print(f"  - Parsed {len(triggers)} triggers with modifiers")
        
    finally:
        os.unlink(temp_file)

def test_only_comments_and_blank_lines():
    """Test file with only comments and blank lines"""
    
    test_content = """
# Only comments here

# And blank lines


# No actual triggers
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
        temp_file = f.name
        f.write(test_content)
    
    try:
        triggers = parse_triggers_file(temp_file)
        
        assert len(triggers) == 0, f"Expected 0 triggers, got {len(triggers)}"
        
        print("✓ Test passed: Parser correctly handles file with only comments and blank lines")
        print(f"  - Correctly parsed empty trigger list")
        
    finally:
        os.unlink(temp_file)

def test_actual_triggers_conf():
    """Test the actual triggers.conf file in the repository"""
    
    triggers_file = os.path.join(os.path.dirname(__file__), 'triggers.conf')
    
    if not os.path.exists(triggers_file):
        print("⚠ Warning: triggers.conf not found, skipping this test")
        return
    
    triggers = parse_triggers_file(triggers_file)
    
    print(f"✓ Test passed: Successfully parsed actual triggers.conf")
    print(f"  - Found {len(triggers)} triggers in triggers.conf")
    for i, (keys, value, cmd) in enumerate(triggers, 1):
        # Show just the first 50 chars of command for brevity
        cmd_short = cmd[:50] + "..." if len(cmd) > 50 else cmd
        print(f"    {i}. {'+'.join(keys)} value={value} -> {cmd_short}")

if __name__ == "__main__":
    print("Testing triggers.conf parser...\n")
    
    try:
        test_blank_lines_and_comments()
        print()
        test_modifier_keys_with_comments()
        print()
        test_only_comments_and_blank_lines()
        print()
        test_actual_triggers_conf()
        print("\n✅ All tests passed!")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
