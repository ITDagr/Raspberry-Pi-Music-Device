"""Headless render smoke tests: every screen must put real pixels on the
surface — text in FG, cursor pill in HIGHLIGHT_BG — so a renderer/view-model
mismatch or a dead font can never silently ship blank screens again."""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from shared import screen as scr
from shared.hardware import Track
from shared.menu_core import MenuView

STATUS = {"clock": "12:34", "battery": 76, "charging": None}
TRACK = Track(index=0, title="Falling Sideways", artist="Neon Harbor",
              album="Golden Hours", track_no=3, duration=180.0, file="/x.wav")
MENU = MenuView(title="Music", items=["Alpha", "Bravo", "Charlie", "Delta", "Echo"],
                cursor=1, window_start=0, total=9)


@pytest.fixture(scope="module")
def renderer():
    pygame.init()
    return scr.ScreenRenderer()


def _surface() -> pygame.Surface:
    return pygame.Surface((scr.SIZE, scr.SIZE), depth=24)  # matches app canvas


def _frac_non_bg(surface) -> float:
    data = pygame.image.tobytes(surface, "RGB")
    bg = bytes(scr.BG)
    hits = sum(1 for i in range(0, len(data), 3) if data[i:i + 3] != bg)
    return hits / (scr.SIZE * scr.SIZE)

def _rect_has_color(surface, rect, color, tolerance: int = 30) -> bool:
    data = pygame.image.tobytes(surface.subsurface(rect), "RGB")
    r, g, b = color
    return any(
        abs(data[i] - r) <= tolerance
        and abs(data[i + 1] - g) <= tolerance
        and abs(data[i + 2] - b) <= tolerance
        for i in range(0, len(data), 3)
    )


def _row_rect(row: int) -> pygame.Rect:
    return pygame.Rect(6, scr.LIST_Y0 + row * scr.ROW_H - 3,
                       scr.SIZE - 24, scr.ROW_H - 4)


def test_menu_draws_text_and_highlight(renderer):
    s = _surface()
    renderer.draw(s, MENU, STATUS)
    assert _frac_non_bg(s) >= 0.02, "menu is (nearly) blank"
    assert _rect_has_color(s, _row_rect(MENU.cursor), scr.HIGHLIGHT_BG, 8), \
        "cursor row has no highlight pill"
    assert _rect_has_color(s, _row_rect(3), scr.FG), \
        "non-cursor row has no FG text"


def test_moving_cursor_changes_frame(renderer):
    a, b = _surface(), _surface()
    renderer.draw(a, MENU, STATUS)
    renderer.draw(b, MenuView(title=MENU.title, items=MENU.items, cursor=2,
                              window_start=0, total=MENU.total), STATUS)
    assert pygame.image.tobytes(a, "RGB") != pygame.image.tobytes(b, "RGB")


def test_nowplaying_draws(renderer):
    s = _surface()
    renderer.draw_nowplaying(s, TRACK, 42.0, True, 60, STATUS)
    assert _frac_non_bg(s) >= 0.02


def test_volume_overlay_draws(renderer):
    s = _surface()
    s.fill(scr.BG)
    renderer.draw_volume_overlay(s, 60)
    assert _frac_non_bg(s) >= 0.02


@pytest.mark.parametrize("connect_info", [
    None,
    {"name": "JBL Flip 6", "address": "aa", "state": "connecting"},
    {"name": "JBL Flip 6", "address": "aa", "state": "connected"},
])
def test_bluetooth_draws(renderer, connect_info):
    s = _surface()
    devices = [{"name": n, "address": "aa"} for n in
               ("AirPods Pro", "JBL Flip 6", "Pixel Buds A", "Car Stereo")]
    renderer.draw_bluetooth(s, devices, 1, connect_info, STATUS)
    assert _frac_non_bg(s) >= 0.02


def test_battery_draws(renderer):
    s = _surface()
    renderer.draw_battery_screen(s, {"clock": "12:34", "battery": 84, "charging": True})
    assert _frac_non_bg(s) >= 0.02


def test_brightness_draws(renderer):
    s = _surface()
    renderer.draw_brightness_screen(s, 70, STATUS)
    assert _frac_non_bg(s) >= 0.02


def test_about_draws(renderer):
    s = _surface()
    renderer.draw_about_screen(s, 0, STATUS)
    assert _frac_non_bg(s) >= 0.02


class _FrameBuffer:
    """Minimal Display double: keeps the composed 240x240 frame so partial
    and full push paths can be compared byte for byte."""

    def __init__(self) -> None:
        self.fb = pygame.Surface((scr.SIZE, scr.SIZE), depth=24)

    def push_frame(self, s: pygame.Surface) -> None:
        self.fb.blit(s, (0, 0))

    def push_region(self, s: pygame.Surface, rect: pygame.Rect) -> None:
        self.fb.blit(s, rect.topleft, rect)


def test_partial_nowplaying_tick_pixel_identical(renderer):
    """Two consecutive now-playing seconds: pushing only NOWPLAYING_TICK_RECT
    must land exactly where two full frames land — proves the rect covers
    everything that changes between seconds."""
    def frame(elapsed: float) -> pygame.Surface:
        s = _surface()
        renderer.draw_nowplaying(s, TRACK, elapsed, True, 60, STATUS)
        return s

    full, partial = _FrameBuffer(), _FrameBuffer()
    first = frame(41.0)
    full.push_frame(first)
    partial.push_frame(first)
    second = frame(42.0)
    full.push_frame(second)
    partial.push_region(second, scr.NOWPLAYING_TICK_RECT)
    assert (pygame.image.tobytes(full.fb, "RGB")
            == pygame.image.tobytes(partial.fb, "RGB"))


def test_partial_status_bar_pixel_identical(renderer):
    """A clock tick in the menu: STATUS_BAR_RECT alone must reproduce the
    full-frame result."""
    def frame(clock: str) -> pygame.Surface:
        s = _surface()
        renderer.draw(s, MENU, {"clock": clock, "battery": 76, "charging": None})
        return s

    full, partial = _FrameBuffer(), _FrameBuffer()
    first = frame("12:34")
    full.push_frame(first)
    partial.push_frame(first)
    second = frame("12:35")
    full.push_frame(second)
    partial.push_region(second, scr.STATUS_BAR_RECT)
    assert (pygame.image.tobytes(full.fb, "RGB")
            == pygame.image.tobytes(partial.fb, "RGB"))


def test_bluetooth_scanning_spinner_draws(renderer):
    s = _surface()
    renderer.draw_bluetooth(s, [], 0, None, STATUS, scanning=True)
    assert _frac_non_bg(s) >= 0.005, "scanning state renders (nearly) nothing"
    # spinner dots circle (cx, SIZE/2-16) at r=20; the accent dot's position
    # depends on the tick, so search the whole spinner area
    assert _rect_has_color(s, pygame.Rect(0, 60, scr.SIZE, 90), scr.ACCENT), \
        "spinner has no accent dot"


def test_status_bar_offline_battery(renderer):
    """No PiSugar data: the header must render an explicit '--'."""
    s = _surface()
    renderer.draw(s, MENU, {"clock": "12:34", "battery": None, "charging": None})
    top_right = pygame.Rect(scr.SIZE - 60, 0, 60, scr.STATUSH)
    assert _rect_has_color(s, top_right, scr.MUTED), "header shows no '--' marker"


def test_display_test_pattern(renderer):
    """The --display-test pattern: border on every edge, exact R/G/B bars."""
    s = _surface()
    renderer.draw_display_test(s)
    mid = scr.SIZE // 2
    for x, y in ((mid, 0), (mid, scr.SIZE - 1), (0, mid), (scr.SIZE - 1, mid),
                 (0, 0), (scr.SIZE - 1, scr.SIZE - 1)):
        assert s.get_at((x, y))[:3] == (255, 255, 255), f"border missing at {(x, y)}"
    # bar geometry from draw_display_test: x 40..SIZE-40, rows of 24px from y=120
    for i, color in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255))):
        y = 120 + i * 34 + 12
        assert s.get_at((mid, y))[:3] == color, f"bar {i} is not {color}"
    # corner labels + arrow put text pixels inside the border
    assert _frac_non_bg(s) >= 0.02
