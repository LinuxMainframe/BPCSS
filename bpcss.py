#!/usr/bin/env python3
"""
BPCSS main entrypoint.
Runs system_info to gather/update system info, then displays formatted info and enters a simple REPL.
"""
import os
import sys
import json
from pathlib import Path

MODULES_DIR = os.path.abspath('./modules')
sys.path.append(MODULES_DIR)

# Attempt to import system_info module (assumed in same directory)
try:
    import system_info
except ImportError:
    print("Error: system_info.py not found or not in PYTHONPATH.")
    sys.exit(1)

CONFIG_DIR = Path.home() / ".bpcss"
INFO_FILE = CONFIG_DIR / "system_info.json"


def print_formatted_info(info):
    """Print system info in a readable formatted manner."""
    # Use JSON pretty-print for simplicity
    try:
        formatted = json.dumps(info, indent=2)
        print(formatted)
    except Exception as e:
        print(f"Failed to format system info: {e}")


def load_info():
    """Load stored system info JSON."""
    if INFO_FILE.exists():
        try:
            with open(INFO_FILE) as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading system info JSON: {e}")
            return None
    else:
        print(f"System info file not found at {INFO_FILE}.")
        return None


def main():
    print("=== BPCSS Toolkit ===")
    # Gather and update system info
    try:
        # system_info.main handles interactive prompts and saving
        system_info.main()
    except Exception as e:
        print(f"Error during system info gathering: {e}")
    # Load and display info
    info = load_info()
    if info:
        print("\n-- System Information --")
        print_formatted_info(info)
    else:
        print("No system information to display.")

    # Simple REPL
    print("\nEnter 'show' to display system info again, or 'exit' to quit.")
    while True:
        try:
            cmd = input("bpcss> ").strip().lower()
        except EOFError:
            print()
            break
        if cmd in ('exit', 'quit'):
            break
        elif cmd in ('show', 'info'):
            info = load_info()
            if info:
                print_formatted_info(info)
        elif cmd == 'help' or cmd == '?':
            print("Commands:\n  show/info - display system info\n  exit/quit - exit the program")
        elif cmd == '':
            continue
        else:
            print(f"Unknown command: '{cmd}'. Type 'help' for options.")

    print("Exiting BPCSS Toolkit.")


if __name__ == '__main__':
    main()
