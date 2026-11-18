"""device v2 — Mac stand-in for the WiFi radio: instant on/off, logged.

Lets the entire on-demand policy run in the selftest: off at boot, on
when the Web App screen opens, held up through an in-flight transfer,
off after leaving.
"""
from __future__ import annotations


class MockRadio:
    def __init__(self, on: bool = False) -> None:
        self._on = on

    def is_on(self) -> bool:
        return self._on

    def set(self, on: bool) -> None:
        if on != self._on:
            print(f"radio: wifi {'on' if on else 'off'}")
        self._on = on
