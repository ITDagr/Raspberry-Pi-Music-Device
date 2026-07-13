"""device v2 — scan the I2C bus for ACKing addresses (a mini i2cdetect).

Library use:   from tools.i2c_scan import scan_bus
               scan_bus(1) -> sorted list of ints, or None if no scan
               method exists on this machine (no smbus2, no i2cdetect).
Command line:  python3 tools/i2c_scan.py [bus]
"""
from __future__ import annotations

import re
import subprocess
import sys


def _scan_smbus(bus_num: int) -> list[int] | None:
    try:
        from smbus2 import SMBus
    except ImportError:
        return None
    found = []
    try:
        with SMBus(bus_num) as bus:
            for addr in range(0x03, 0x78):
                try:
                    bus.read_byte(addr)
                    found.append(addr)
                except OSError:
                    pass
    except (OSError, FileNotFoundError):
        return None
    return found


def _scan_i2cdetect(bus_num: int) -> list[int] | None:
    try:
        out = subprocess.run(["i2cdetect", "-y", str(bus_num)],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    found = []
    for line in out.stdout.splitlines()[1:]:  # skip the column header
        m = re.match(r"^([0-9a-f]0):(.*)$", line.strip())
        if not m:
            continue
        base = int(m.group(1), 16)
        for i, cell in enumerate(m.group(2).split()):
            if cell not in ("--", ""):
                # cells are either an address ("49") or "UU" (kernel-owned)
                found.append(base + i if cell == "UU" else int(cell, 16))
    return found


def scan_bus(bus_num: int = 1) -> list[int] | None:
    """All ACKing 7-bit addresses on the bus; None if scanning is impossible."""
    for method in (_scan_smbus, _scan_i2cdetect):
        found = method(bus_num)
        if found is not None:
            return sorted(set(found))
    return None


if __name__ == "__main__":
    bus = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    result = scan_bus(bus)
    if result is None:
        print(f"i2c: cannot scan bus {bus} (need smbus2 or i2c-tools)")
        sys.exit(1)
    if not result:
        print(f"i2c bus {bus}: no devices found")
    else:
        print(f"i2c bus {bus}: " + ", ".join(f"0x{a:02X}" for a in result))
