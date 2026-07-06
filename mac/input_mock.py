"""device v2 — keyboard stand-in for the ANO wheel.

    ↑ / ↓        scroll_up / scroll_down (wheel detents)
    Enter/Space  select
    →  /  ←      right / left
    Backspace    back
    Esc / close  quit
"""
from __future__ import annotations

import pygame

_KEYMAP = {
    pygame.K_UP: "scroll_up",
    pygame.K_DOWN: "scroll_down",
    pygame.K_RETURN: "select",
    pygame.K_SPACE: "select",
    pygame.K_RIGHT: "right",
    pygame.K_LEFT: "left",
    pygame.K_BACKSPACE: "back",
    pygame.K_ESCAPE: "quit",
}


_EXPOSE_EVENTS = {pygame.WINDOWEXPOSED, pygame.WINDOWSHOWN, pygame.WINDOWRESTORED}


class MockANOInput:
    def __init__(self) -> None:
        self.quit_requested = False

    def read(self) -> list[str]:
        events: list[str] = []
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                events.append("quit")
                self.quit_requested = True
            elif e.type == pygame.KEYDOWN and e.key in _KEYMAP:
                ev = _KEYMAP[e.key]
                if ev == "quit":
                    self.quit_requested = True
                events.append(ev)
            elif e.type in _EXPOSE_EVENTS:
                # the OS (re)showed the window: force a redraw so it isn't
                # blank; mode handlers ignore the unknown event string
                events.append("expose")
        return events
