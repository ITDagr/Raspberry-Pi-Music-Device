"""device v2 — WiFi radio control via rfkill (the on-demand WiFi policy).

`rfkill block/unblock wifi` toggles ONLY the wlan radio: Bluetooth is a
separate rfkill class and keeps carrying the audio, untouched. Failures
degrade to "always on" — worst case the battery win is lost, never the
web app.
"""
from __future__ import annotations

import subprocess


class RadioPi:
    def __init__(self) -> None:
        self._warned = False

    def is_on(self) -> bool:
        try:
            out = subprocess.run(["rfkill", "list", "wifi"],
                                 capture_output=True, text=True, timeout=3)
            return "Soft blocked: yes" not in out.stdout
        except OSError:
            return True  # cannot ask: assume on (degrade to always_on)

    def set(self, on: bool) -> None:
        try:
            subprocess.run(["rfkill", "unblock" if on else "block", "wifi"],
                           capture_output=True, timeout=3)
            print(f"radio: wifi {'on' if on else 'off'}")
        except OSError as e:
            if not self._warned:
                print(f"radio: rfkill failed ({e}) — leaving WiFi as-is")
                self._warned = True
