"""device v2 — the center button's gesture machine, shared by both targets.

The ANO encoder's center button carries two gestures:
    short press   -> "select", fired on RELEASE
    hold >= config.BACK_HOLD_S -> "back", fired once AT the threshold while
                     still held; the eventual release is swallowed

This exact machine runs on the Pi (pi/input_pi.py, fed by seesaw edges)
and on the Mac (mac/input_mock.py, fed by Enter/Space key down/up), so the
simulator exercises the real control scheme — including the dark-screen
wake gate, which relies on a waking press being a short press.
"""
from __future__ import annotations

from shared import config


class CenterButton:
    def __init__(self) -> None:
        self._down_at: float | None = None
        self._hold_fired = False

    @property
    def held(self) -> bool:
        return self._down_at is not None

    def press(self, now: float) -> None:
        if self._down_at is None:  # ignore a second physical key aliasing it
            self._down_at = now
            self._hold_fired = False

    def release(self, now: float) -> list[str]:
        """A short press fires select on release; a hold already fired back."""
        if self._down_at is None:
            return []
        fired = self._hold_fired
        self._down_at = None
        self._hold_fired = False
        return [] if fired else ["select"]

    def poll(self, now: float) -> list[str]:
        """Call every frame: fires back exactly once when the hold crosses
        the threshold, while the button is still down."""
        if (self._down_at is not None and not self._hold_fired
                and now - self._down_at >= config.BACK_HOLD_S):
            self._hold_fired = True
            return ["back"]
        return []
