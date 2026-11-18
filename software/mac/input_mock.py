"""device v2 — keyboard stand-in for the ANO encoder, gesture-faithful.

The keyboard simulates every physical control with the REAL semantics —
the center button runs the same shared gesture machine as the Pi
(shared/encoder.py), so short-press/hold behave exactly like hardware:

    ↑ / ↓          wheel detents (scroll_up / scroll_down)
    Enter / Space  center button — tap = select, HOLD >= 0.6 s = back
                   (fires at the threshold, release swallowed, like the Pi)
    W / S          ring up / down buttons (the app treats them as detents)
    A / D  or ← →  ring left / right buttons
    Backspace      back (keyboard convenience; the device gesture is the hold)
    P              toggle the (soft) power switch
    Esc / close    quit
"""
from __future__ import annotations

import time
from typing import Optional

import pygame

from shared.encoder import CenterButton
from mac.power_mock import MockPowerSwitch

_KEYMAP = {
    pygame.K_UP: "scroll_up",
    pygame.K_DOWN: "scroll_down",
    pygame.K_w: "up",        # ring buttons, same vocabulary as the seesaw
    pygame.K_s: "down",
    pygame.K_a: "left",
    pygame.K_d: "right",
    pygame.K_RIGHT: "right",
    pygame.K_LEFT: "left",
    pygame.K_BACKSPACE: "back",
    pygame.K_ESCAPE: "quit",
}

_CENTER_KEYS = (pygame.K_RETURN, pygame.K_SPACE)

_EXPOSE_EVENTS = {pygame.WINDOWEXPOSED, pygame.WINDOWSHOWN, pygame.WINDOWRESTORED}


class MockANOInput:
    def __init__(self, power: Optional[MockPowerSwitch] = None) -> None:
        self.quit_requested = False
        self._power = power
        self._center = CenterButton()  # the same machine the Pi runs

    def read(self) -> list[str]:
        events: list[str] = []
        now = time.monotonic()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                events.append("quit")
                self.quit_requested = True
            elif e.type == pygame.KEYDOWN and e.key in _CENTER_KEYS:
                self._center.press(now)
            elif e.type == pygame.KEYUP and e.key in _CENTER_KEYS:
                events.extend(self._center.release(now))
            elif e.type == pygame.KEYDOWN and e.key == pygame.K_p and self._power:
                self._power.toggle()  # switch position, not an input event
            elif e.type == pygame.KEYDOWN and e.key in _KEYMAP:
                ev = _KEYMAP[e.key]
                if ev == "quit":
                    self.quit_requested = True
                events.append(ev)
            elif e.type in _EXPOSE_EVENTS:
                # the OS (re)showed the window: force a redraw so it isn't
                # blank; mode handlers ignore the unknown event string
                events.append("expose")
        # hold-to-back fires at the threshold, while the key is still down
        events.extend(self._center.poll(now))
        return events