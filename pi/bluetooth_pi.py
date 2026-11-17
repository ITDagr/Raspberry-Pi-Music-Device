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
    paired = _paired_addresses()
    devices, seen = [], set()
    for line in _btctl("devices").splitlines():
        m = re.match(r"Device\s+([0-9A-F:]{17})\s+(.+)", line.strip(), re.I)
        if not m or m.group(1) in seen:
            continue
        address, name = m.group(1), m.group(2).strip()
        # devices with no advertised name show their own address as a
        # placeholder (bluetoothctl prints it dash-separated) — nothing you'd
        # ever want to connect audio to, and on a crowded bus they can be
        # most of the scan; drop them so the real device isn't buried
        if name.upper() == address.replace(":", "-"):
            continue
        # Apple devices in "Find My" mode advertise "<name> - Find My" — a
        # beacon, not a connectable audio device. Drop those beacons so the
        # list is unambiguous, but keep the real (paired) device and show its
        # name without the confusing suffix. Only drop when we actually have a
        # paired set, so a failed lookup never hides the only way to connect.
        find_my = "find my" in name.lower()
        if find_my and paired and address.upper() not in paired:
            continue
        name = re.sub(r"\s*[-–]\s*Find My\s*$", "", name, flags=re.I).strip() or name
        seen.add(address)
        devices.append({"name": name, "address": address})
    devices.sort(key=lambda d: d["name"].lower())
    return devices


def _paired_addresses() -> set:
    """Upper-case MACs of already-paired devices (best effort)."""
    addrs = set()
    for line in _btctl("devices", "Paired").splitlines():
        m = re.match(r"Device\s+([0-9A-F:]{17})", line.strip(), re.I)
        if m:
            addrs.add(m.group(1).upper())
    return addrs


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
