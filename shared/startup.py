"""device v2 — boot animation (v1 ARIA choreography, wordmark "device").

Five phases, scaled to config.STARTUP_DURATION_S (v1 ran ~2.9 s total):
  1  0.5s  black silence
  2a 0.4s  center accent line expands (ease-out), haptic click
  2b 0.6s  waveform peaks rise (ease-out), haptic tick
  3  0.8s  wordmark fades in + "loading…" + battery/time, haptic pulse
  4  0.6s  crossfade into the first menu frame

`last_hero_frame` keeps a copy of the fully-revealed phase-3 frame so
`--dump-frames` can save it.
"""
from __future__ import annotations

import math
from typing import Callable, Optional

import pygame

from shared import config
from shared.screen import C_ACCENT, C_BASE, C_DIM, C_TEXT, SIZE, ScreenRenderer

_V1_TOTAL_S = 2.9
last_hero_frame: Optional[pygame.Surface] = None


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def _tick(duration: float, clock: pygame.time.Clock, fps: int = 60):
    frames = max(1, int(duration * fps))
    for i in range(frames):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                raise SystemExit
        yield i / frames
        clock.tick(fps)


def _waveform_surface(alpha: int) -> pygame.Surface:
    surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
    cx, cy = SIZE // 2, SIZE // 2
    w, half_h = 160, 27
    n = 160

    def env(x: int) -> float:
        t = x / (n - 1)
        return math.exp(-8 * (t - 0.5) ** 2)

    def sample(x: int) -> float:
        t = x / (n - 1)
        v = (math.sin(2 * math.pi * t * 4.0) * 0.55
             + math.sin(2 * math.pi * t * 7.3) * 0.30
             + math.sin(2 * math.pi * t * 13.1) * 0.15)
        return v * env(x)

    pts_top, pts_bot = [], []
    for xi in range(n):
        s = sample(xi)
        px = cx - w // 2 + xi
        pts_top.append((px, cy - int(s * half_h)))
        pts_bot.append((px, cy + int(s * half_h)))
    color = (*C_ACCENT, alpha)
    pygame.draw.lines(surf, color, False, pts_top, 2)
    pygame.draw.lines(surf, color, False, pts_bot, 2)
    return surf


def run_startup(surface, display, haptic, ctrl, renderer: ScreenRenderer,
                status_fn: Callable[[], dict]) -> None:
    global last_hero_frame
    k = config.STARTUP_DURATION_S / _V1_TOTAL_S  # scale v1's phase timings
    clock = pygame.time.Clock()
    # v1 sizes (Arial 38/12/11) x the renderer's 1.38 bundled-font scale
    f_word = pygame.font.Font(None, 52)
    f_word.set_bold(True)
    f_sub = pygame.font.Font(None, 17)
    f_stat = pygame.font.Font(None, 15)

    def push() -> None:
        display.push_frame(surface)

    # Phase 1: silence
    surface.fill(C_BASE)
    push()
    for _ in _tick(0.5 * k, clock):
        push()

    # Phase 2a: center line expands + click
    haptic.click()
    cx, cy = SIZE // 2, SIZE // 2
    for t in _tick(0.4 * k, clock):
        half = int(_ease_out(t) * 60)
        surface.fill(C_BASE)
        pygame.draw.line(surface, C_ACCENT, (cx - half, cy), (cx + half, cy), 2)
        push()

    # Phase 2b: waveform rises + tick
    for t in _tick(0.6 * k, clock):
        surface.fill(C_BASE)
        surface.blit(_waveform_surface(int(_ease_out(t) * 255)), (0, 0))
        push()
    haptic.tick()

    # Phase 3: wordmark + loading + battery/time
    haptic.pulse()
    status = status_fn()
    for t in _tick(0.8 * k, clock):
        surface.fill(C_BASE)
        surface.blit(_waveform_surface(255), (0, 0))
        a = min(255, int(t * 2 * 255))
        word = f_word.render("device", True, C_TEXT)
        word.set_alpha(a)
        surface.blit(word, word.get_rect(center=(cx, cy - 18)))
        if t > 0.5:
            sub = f_sub.render("loading…", True, C_DIM)
            sub.set_alpha(min(255, int((t - 0.5) * 4 * 255)))
            surface.blit(sub, sub.get_rect(center=(cx, cy + 18)))
        if status.get("battery") is not None:
            line = f_stat.render(f"{status.get('clock', '')}  {status['battery']}%",
                                 True, C_DIM)
            line.set_alpha(a)
            surface.blit(line, line.get_rect(midbottom=(cx, SIZE - 16)))
        push()
    last_hero_frame = surface.copy()

    # Phase 4: crossfade to the first menu frame
    menu_surf = pygame.Surface((SIZE, SIZE))
    renderer.draw(menu_surf, ctrl.view(), status_fn())
    for t in _tick(0.6 * k, clock):
        e = _ease_out(t)
        out = last_hero_frame.copy()
        fade_old = pygame.Surface((SIZE, SIZE))
        fade_old.fill((int((1 - e) * 255),) * 3)
        out.blit(fade_old, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        fade_new = menu_surf.copy()
        fade_mask = pygame.Surface((SIZE, SIZE))
        fade_mask.fill((int(e * 255),) * 3)
        fade_new.blit(fade_mask, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        out.blit(fade_new, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        display.push_frame(out)

    surface.blit(menu_surf, (0, 0))
    push()
