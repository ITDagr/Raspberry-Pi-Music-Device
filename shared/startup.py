"""device v2 — boot animation.

~1.8 s: black -> the device wordmark fades and slides in, an underline sweeps
beneath it, a small "v2.0" tag appears. Rendered through the injected Display
so it plays on both targets; ends with a haptic pulse and falls through to the
first menu frame.
"""
from __future__ import annotations

import time
from typing import Callable

import pygame

from shared import config
from shared.screen import ACCENT, BG, FG, MUTED, SIZE, ScreenRenderer


def _ease_out(p: float) -> float:
    return 1 - (1 - p) ** 3


def run_startup(surface, display, haptic, ctrl, renderer: ScreenRenderer,
                status_fn: Callable[[], dict]) -> None:
    duration = config.STARTUP_DURATION_S
    clock = pygame.time.Clock()
    word_font = pygame.font.Font(None, 56)
    tag_font = pygame.font.Font(None, 20)
    t0 = time.monotonic()
    while True:
        t = time.monotonic() - t0
        if t >= duration:
            break
        p = t / duration
        e = _ease_out(p)
        surface.fill(BG)
        word = word_font.render("device", True, FG)
        word.set_alpha(int(255 * min(1.0, p * 1.6)))
        wx = (SIZE - word.get_width()) // 2
        wy = 92 + int(26 * (1 - e))
        surface.blit(word, (wx, wy))
        # underline sweep
        sweep = min(1.0, max(0.0, (p - 0.15) / 0.6))
        uw = int(word.get_width() * sweep)
        if uw > 2:
            pygame.draw.rect(surface, ACCENT, (wx, 148, uw, 3), border_radius=2)
        if p > 0.7:
            tag = tag_font.render("v2.0", True, MUTED)
            tag.set_alpha(int(255 * min(1.0, (p - 0.7) / 0.25)))
            surface.blit(tag, (wx + word.get_width() - tag.get_width(), 158))
        display.push_frame(surface)
        clock.tick(config.FPS)
    haptic.pulse()
    renderer.draw(surface, ctrl.view(), status_fn())
    display.push_frame(surface)
