"""device v2 — bluetoothctl wrapper for audio sinks.

scan_devices() powers the adapter, scans for ~6 s (blocking) and returns the
deduped device list. connect_device() fires a background thread doing
trust/pair (best effort) then connect. check_connected() greps
`bluetoothctl info`. Routing MPD's output to the sink is a README task.
"""
from __future__ import annotations

import re
import subprocess
import threading

from shared import config

_warned = False


def _btctl(*args: str, timeout: float = 10.0) -> str:
    global _warned
    try:
        out = subprocess.run(["bluetoothctl", *args], capture_output=True,
                             text=True, timeout=timeout)
        return out.stdout
    except Exception as e:
        if not _warned:
            print(f"bluetooth: bluetoothctl failed ({e})")
            _warned = True
        return ""


def scan_devices() -> list[dict]:
    _btctl("power", "on")
    _btctl("--timeout", str(int(config.BT_SCAN_S)), "scan", "on",
           timeout=config.BT_SCAN_S + 4)
    devices, seen = [], set()
    for line in _btctl("devices").splitlines():
        m = re.match(r"Device\s+([0-9A-F:]{17})\s+(.+)", line.strip(), re.I)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            devices.append({"name": m.group(2).strip(), "address": m.group(1)})
    devices.sort(key=lambda d: d["name"].lower())
    return devices


def _connect_worker(address: str) -> None:
    _btctl("trust", address)
    _btctl("pair", address, timeout=15)  # best effort; may already be paired
    _btctl("connect", address, timeout=15)


def connect_device(address: str) -> None:
    """Non-blocking, fire-and-forget."""
    threading.Thread(target=_connect_worker, args=(address,), daemon=True,
                     name="bt-connect").start()


def check_connected(address: str) -> bool:
    return "Connected: yes" in _btctl("info", address)
