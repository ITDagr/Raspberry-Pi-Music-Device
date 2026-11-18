"""device v2 — Mac stand-in for the Beret's slide switch.

A boolean toggled by the P key (MockANOInput calls toggle()); each flip
prints the new position to the terminal.
"""
from __future__ import annotations


class MockPowerSwitch:
    def __init__(self, on: bool = True) -> None:
        self._on = on

    def is_on(self) -> bool:
        return self._on

    def toggle(self) -> None:
        self._on = not self._on
        print(f"power switch: {'ON' if self._on else 'OFF'}")
