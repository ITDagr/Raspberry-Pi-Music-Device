"""device v2 — PiSugar battery + RTC polling with silent fallback.

Talks to the PiSugar daemon's text protocol on 127.0.0.1:8423 ("get battery",
"get rtc_time", "get battery_charging"). One boot-time TCP probe with a
short timeout decides the mode: absent (a Mac, or a Pi without a PiSugar)
means offline — get_battery()/get_charging() return None (the header
renders "--"), get_time() is the system clock, refresh() is a no-op, and
the only traffic is a silent re-probe every config.PISUGAR_REPROBE_S.
Exactly one info line is printed when the probe fails; there are no retry
storms and no repeated logs. Both targets share this module unchanged.
Assignments are plain attribute writes guarded by the GIL — no lock needed.
"""
from __future__ import annotations

import socket
import threading
import time
from datetime import datetime

from shared import config

_battery: int | None = None
_charging: bool | None = None
_rtc_offset: float | None = None  # rtc_epoch - system_epoch at last poll
_available = False                # set by the boot probe in the poll thread
_wake = threading.Event()
_started = False


def _query(cmd: str) -> str | None:
    try:
        with socket.create_connection(
            (config.PISUGAR_HOST, config.PISUGAR_PORT), timeout=config.PISUGAR_TIMEOUT_S
        ) as s:
            s.settimeout(config.PISUGAR_TIMEOUT_S)
            s.sendall(cmd.encode() + b"\n")
            return s.recv(256).decode(errors="replace").strip()
    except OSError:
        return None


def _value(reply: str | None) -> str | None:
    """'battery: 84.2' -> '84.2'; None on malformed replies."""
    if reply and ":" in reply:
        return reply.split(":", 1)[1].strip()
    return None


def _poll_once() -> None:
    global _battery, _charging, _rtc_offset
    v = _value(_query("get battery"))
    if v is not None:
        try:
            _battery = int(float(v))
        except ValueError:
            pass
    v = _value(_query("get battery_charging"))
    if v is not None:
        _charging = v.lower() == "true"
    r = _query("get rtc_time")
    if r and ":" in r:
        iso = r.split(":", 1)[1].strip().replace("Z", "+00:00")
        try:
            _rtc_offset = datetime.fromisoformat(iso).timestamp() - time.time()
        except ValueError:
            pass


def _probe() -> bool:
    """One TCP connect with a short timeout: is the daemon there at all?"""
    try:
        with socket.create_connection(
            (config.PISUGAR_HOST, config.PISUGAR_PORT), timeout=config.PISUGAR_TIMEOUT_S
        ):
            return True
    except OSError:
        return False


def _run(interval: float) -> None:
    global _available
    _available = _probe()
    if not _available:
        print("pisugar: not detected — offline mode (system clock, battery --)")
    while True:
        if _available:
            _poll_once()
            _wake.wait(interval)
        else:
            _wake.wait(config.PISUGAR_REPROBE_S)  # silent re-probe, >= 5 min apart
            _available = _probe()
        _wake.clear()


def start_polling(interval: float = config.PISUGAR_POLL_S) -> None:
    """Start the daemon poll thread. Safe to call more than once."""
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_run, args=(interval,), daemon=True, name="pisugar").start()


def refresh() -> None:
    """Force an immediate poll (wakes the poll thread). No-op while offline —
    waking the thread early would turn the 5-minute re-probe into a storm."""
    if _available:
        _wake.set()


def get_battery() -> int | None:
    return _battery


def get_charging() -> bool | None:
    return _charging


def get_time() -> str:
    """'HH:MM' — RTC-corrected on the Pi, plain system time elsewhere."""
    t = time.time() + (_rtc_offset or 0.0)
    return time.strftime("%H:%M", time.localtime(t))
