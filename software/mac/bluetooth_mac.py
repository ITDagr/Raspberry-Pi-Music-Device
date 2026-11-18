"""device v2 — fake Bluetooth for the Mac prototype.

scan_devices() blocks ~0.8 s and returns four plausible sinks. connect_device
records the address so check_connected() turns True — this exercises the app's
2.5 s "connecting" path exactly like the Pi build.
"""
from __future__ import annotations

import time

_DEVICES = [
    {"name": "AirPods Pro", "address": "A4:83:E7:12:9B:01"},
    {"name": "JBL Flip 6", "address": "F8:5C:7D:44:20:6E"},
    {"name": "Pixel Buds A", "address": "D0:03:DF:8A:31:55"},
    {"name": "Car Stereo", "address": "00:1B:DC:0F:72:C3"},
]

_connected_addr: str | None = None


def scan_devices() -> list[dict]:
    time.sleep(0.8)  # pretend to scan
    return [dict(d) for d in _DEVICES]


def connect_device(address: str) -> None:
    global _connected_addr
    _connected_addr = address


def check_connected(address: str) -> bool:
    return address == _connected_addr
