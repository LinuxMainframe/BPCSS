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
import system_info
import prepare_protein

CONFIG_DIR = Path.home() / ".bpcss"
INFO_FILE = CONFIG_DIR / "system_info.json"


def print_formatted_info(info):
    """Print system info in a readable formatted manner."""
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

logo = r"""
  ____  ____  ____  ____  ____  
 ||B |||P |||C |||S |||S || 
 ||__|||__|||__|||__|||__|| 
 |/__\|/__\|/__\|/__\|/__\| 
"""

def clear_screen():
    """Clear the terminal screen."""
    try:
        if os.name == 'nt':
            os.system('cls')
        else:
            os.system('clear')
    except Exception:
        pass


def main():
    print(logo.strip())
    print("BioPhysics Computation Server System (BPCSS)")
    print("Author: Aidan Bradley")
    print("© 2025 Aidan Bradley. All rights reserved.")
    print()

    print()
    print("=== BPCSS Toolkit is now running! ===")
    try:
        system_info.main()
    except Exception as e:
        print(f"Error during system info gathering: {e}")
    info = load_info()
    """ Was previously used for debug. Should be resurrected for low-level checks
    if info:
        print("\n-- System Information --")
        print_formatted_info(info)
    else:
        print("No system information to display.")
    """

    print("\nEnter 'show' to display system info, 'clear' to clear screen, or 'exit' to quit.")
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
        elif cmd == 'clear':
            clear_screen()
        elif cmd in ('help', '?'):
            print("Commands:\n  show/info - display system info\n  clear - clear the screen\n  pp - prepare protein\n  exit/quit - exit the program")
        elif cmd == 'pp':
            prepare_protein.prepare_protein()
        elif cmd == '':
            continue
        else:
            print(f"Unknown command: '{cmd}'. Type 'help' for options.")

    print("Exiting BPCSS Toolkit.")


if __name__ == '__main__':
    main()

