"""device v2 — best-effort network facts for the Web App screen.

Everything returns None instead of raising: the screen renders "--" and
the troubleshooting ladder in the README takes it from there.
"""
from __future__ import annotations

import socket
import subprocess

from shared import config


def get_ip() -> str | None:
    """The LAN IP, found by routing (no packet is actually sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.2)
            s.connect(("192.0.2.1", 80))  # TEST-NET-1: routes, never sends
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def get_ssid() -> str | None:
    """Connected WiFi network name (Pi: iwgetid; Mac: simulated)."""
    if config.IS_MAC:
        return "simulated-wifi"
    try:
        out = subprocess.run(["iwgetid", "-r"], capture_output=True,
                             text=True, timeout=2)
        ssid = out.stdout.strip()
        return ssid or None
    except OSError:
        return None
