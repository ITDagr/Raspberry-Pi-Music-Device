"""device v2 — Mac display stand-in.

A pygame window at 2x scale of the 240x240 TFT. Backlight dimming is faked
with a black overlay; alpha uses a gamma curve so the 0.15 "dim" level still
reads on a Mac monitor.
"""
from __future__ import annotations

import pygame

from shared.screen import SIZE


class MockDisplay:
    def __init__(self, scale: int = 2):
        side = SIZE * scale
        self._scale = scale
        self.window = pygame.display.set_mode((side, side))
        pygame.display.set_caption("prototype  —  device simulator")
        self.level = 1.0
        self._level_changed = False
        self._overlay = pygame.Surface((side, side), depth=24)  # black, plain RGB

    def _dim(self, scaled: pygame.Surface) -> None:
        """Gamma-dim `scaled` in place so the 0.15 level still reads on a Mac."""
        if self.level < 0.99:
            overlay = self._overlay
            if scaled.get_size() != overlay.get_size():
                overlay = pygame.Surface(scaled.get_size(), depth=24)
            overlay.set_alpha(int((1 - self.level ** 0.5) * 255))
            scaled.blit(overlay, (0, 0))

    def push_frame(self, surface: pygame.Surface) -> None:
        # macOS never maps/presents an SDL window unless events are serviced;
        # pump on every flip so frames pushed before the main loop's first
        # event.get() (boot animation, initial menu) actually reach the screen.
        # pump() does not drain the queue, so MockANOInput still sees keys.
        pygame.event.pump()
        # Scale + dim on an RGB surface, then blit opaquely: alpha-format
        # blits straight onto the cocoa display surface render as boxes.
        scaled = pygame.transform.scale(surface, self.window.get_size())
        self._dim(scaled)
        self.window.blit(scaled, (0, 0))
        pygame.display.flip()

    def push_region(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        pygame.event.pump()
        k = self._scale
        region = pygame.Surface(rect.size, depth=24)
        region.blit(surface, (0, 0), rect)
        scaled = pygame.transform.scale(region, (rect.w * k, rect.h * k))
        self._dim(scaled)  # same compositing as full frames at any level
        self.window.blit(scaled, (rect.x * k, rect.y * k))
        pygame.display.flip()

    def set_backlight_level(self, level: float) -> None:
        self.level = max(0.0, min(1.0, float(level)))
        self._level_changed = True

    def consume_level_change(self) -> bool:
        changed, self._level_changed = self._level_changed, False
        return changed

    def set_backlight(self, on: bool) -> None:
        self.set_backlight_level(1.0 if on else 0.0)

    def sleep(self) -> None:
        pass  # backlight level 0 already blacks the window

    def wake(self) -> None:
        pass
