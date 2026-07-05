"""device v2 — all drawing for the 240x240 screen.

Pure pygame.font + pygame.draw so it renders identically in the Mac window
and under SDL_VIDEODRIVER=dummy on the Pi. Dark theme, ~26 px status header
(clock left, battery right) on every screen.
"""
from __future__ import annotations

import math
import time

import pygame

from shared.menu_core import MenuView

SIZE = 240
HEADER_H = 26

BG = (16, 16, 20)
FG = (235, 235, 240)
MUTED = (140, 140, 155)
DIM = (90, 90, 105)
ACCENT = (120, 190, 255)
PILL = (44, 48, 66)
BAR_BG = (50, 52, 64)
GREEN = (120, 220, 140)

ABOUT_FEATURES = [
    "device v2.0",
    "one core, two targets",
    "240x240 ST7789 IPS",
    "ANO wheel + 5 keys",
    "DRV2605L haptics",
    "MPD / pygame audio",
    "Bluetooth sinks",
    "PiSugar battery + RTC",
    "auto dim + sleep",
    "resume on boot",
]
ABOUT_VISIBLE = 5


def _mss(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


class ScreenRenderer:
    def __init__(self) -> None:
        if not pygame.font.get_init():
            pygame.font.init()
        self._fonts: dict[int, pygame.font.Font] = {}

    # --- primitives -----------------------------------------------------------
    def _font(self, size: int) -> pygame.font.Font:
        if size not in self._fonts:
            self._fonts[size] = pygame.font.Font(None, size)
        return self._fonts[size]

    def _text(self, surf, txt, size, color, x, y, align="left"):
        img = self._font(size).render(txt, True, color)
        if align == "right":
            x -= img.get_width()
        elif align == "center":
            x -= img.get_width() // 2
        surf.blit(img, (x, y))
        return img.get_rect(topleft=(x, y))

    def _fit(self, txt: str, size: int, max_w: int) -> str:
        font = self._font(size)
        if font.size(txt)[0] <= max_w:
            return txt
        while txt and font.size(txt + "...")[0] > max_w:
            txt = txt[:-1]
        return txt + "..."

    def _header(self, surf, status: dict) -> None:
        self._text(surf, status.get("clock", "--:--"), 18, MUTED, 10, 6)
        batt = status.get("battery")
        # battery glyph: body + nub + proportional fill
        bx, by, bw, bh = SIZE - 30, 8, 20, 11
        pygame.draw.rect(surf, MUTED, (bx, by, bw, bh), 1, border_radius=2)
        pygame.draw.rect(surf, MUTED, (bx + bw, by + 3, 2, bh - 6))
        if batt is not None:
            fill = max(1, round((bw - 4) * min(100, max(0, batt)) / 100))
            color = GREEN if batt > 20 else (240, 120, 110)
            pygame.draw.rect(surf, color, (bx + 2, by + 2, fill, bh - 4))
        label = f"{batt}%" if batt is not None else "--"
        self._text(surf, label, 18, MUTED, bx - 6, 6, align="right")
        pygame.draw.line(surf, (36, 36, 46), (0, HEADER_H), (SIZE, HEADER_H))

    def _scrollbar(self, surf, y0: int, h: int, total: int, visible: int, scroll: int):
        if total <= visible:
            return
        pygame.draw.rect(surf, BAR_BG, (SIZE - 6, y0, 3, h), border_radius=2)
        th = max(12, h * visible // total)
        ty = y0 + (h - th) * scroll // max(1, total - visible)
        pygame.draw.rect(surf, MUTED, (SIZE - 6, ty, 3, th), border_radius=2)

    def _big_bar_screen(self, surf, status, title, big, pct, note=""):
        """Shared layout for the battery and brightness screens."""
        surf.fill(BG)
        self._header(surf, status)
        self._text(surf, title, 22, ACCENT, SIZE // 2, 40, align="center")
        self._text(surf, big, 64, FG, SIZE // 2, 84, align="center")
        bx, bw = 40, SIZE - 80
        pygame.draw.rect(surf, BAR_BG, (bx, 150, bw, 14), border_radius=7)
        if pct is not None:
            fill = round(bw * min(100, max(0, pct)) / 100)
            pygame.draw.rect(surf, ACCENT, (bx, 150, max(6, fill), 14), border_radius=7)
        if note:
            self._text(surf, note, 17, MUTED, SIZE // 2, 178, align="center")

    # --- screens ---------------------------------------------------------------
    def draw(self, surface, view: MenuView, status: dict) -> None:
        """Menu screen: title, up to 5 rows, pill cursor, scrollbar on overflow."""
        surface.fill(BG)
        self._header(surface, status)
        self._text(surface, view.title, 24, ACCENT, 12, 34)
        y0, row_h = 66, 33
        for i, label in enumerate(view.items):
            y = y0 + i * row_h
            if i == view.cursor:
                pygame.draw.rect(surface, PILL, (6, y - 3, SIZE - 18, row_h - 4),
                                 border_radius=13)
            color = FG if i == view.cursor else MUTED
            self._text(surface, self._fit(label, 22, SIZE - 40), 22, color, 18, y + 2)
        self._scrollbar(surface, y0, 5 * row_h - 8,
                        view.total, len(view.items), view.scroll)

    def draw_nowplaying(self, surface, track, elapsed, playing, volume, status) -> None:
        surface.fill(BG)
        self._header(surface, status)
        if track is None:
            self._text(surface, "Nothing playing", 22, MUTED, SIZE // 2, 100, align="center")
            self._text(surface, "pick a song in Music", 17, DIM, SIZE // 2, 128, align="center")
            return
        self._text(surface, self._fit(track.title, 24, SIZE - 30), 24, FG, 15, 44)
        self._text(surface, self._fit(track.artist, 19, SIZE - 30), 19, MUTED, 15, 72)
        self._text(surface, self._fit(track.album, 16, SIZE - 30), 16, DIM, 15, 94)
        # progress bar + times
        bx, bw, by = 20, SIZE - 40, 132
        pygame.draw.rect(surface, BAR_BG, (bx, by, bw, 6), border_radius=3)
        if track.duration > 0:
            fill = round(bw * min(1.0, elapsed / track.duration))
            pygame.draw.rect(surface, ACCENT, (bx, by, max(3, fill), 6), border_radius=3)
        self._text(surface, _mss(elapsed), 15, MUTED, bx, by + 12)
        self._text(surface, _mss(track.duration), 15, MUTED, bx + bw, by + 12, align="right")
        # play / pause glyph
        cx, cy = SIZE // 2, 185
        if playing:
            pygame.draw.rect(surface, FG, (cx - 10, cy - 12, 7, 24), border_radius=2)
            pygame.draw.rect(surface, FG, (cx + 3, cy - 12, 7, 24), border_radius=2)
        else:
            pygame.draw.polygon(surface, FG, [(cx - 8, cy - 13), (cx - 8, cy + 13), (cx + 12, cy)])
        self._text(surface, f"vol {volume}", 15, DIM, SIZE - 12, SIZE - 22, align="right")

    def draw_volume_overlay(self, surface, volume: int) -> None:
        panel = pygame.Surface((170, 96), pygame.SRCALPHA)
        pygame.draw.rect(panel, (28, 30, 42, 232), panel.get_rect(), border_radius=16)
        f = self._font(15).render("VOLUME", True, MUTED)
        panel.blit(f, ((170 - f.get_width()) // 2, 10))
        n = self._font(44).render(str(volume), True, FG)
        panel.blit(n, ((170 - n.get_width()) // 2, 26))
        pygame.draw.rect(panel, BAR_BG, (20, 74, 130, 8), border_radius=4)
        pygame.draw.rect(panel, ACCENT, (20, 74, max(4, round(130 * volume / 100)), 8),
                         border_radius=4)
        surface.blit(panel, ((SIZE - 170) // 2, (SIZE - 96) // 2))

    def draw_bluetooth(self, surface, devices, cursor, connect_info, status) -> None:
        surface.fill(BG)
        self._header(surface, status)
        self._text(surface, "Bluetooth", 24, ACCENT, 12, 34)
        if connect_info:
            name = self._fit(connect_info["name"], 22, SIZE - 40)
            if connect_info["state"] == "connecting":
                # spinner: rotating arc
                a = (time.monotonic() * 5.0) % (2 * math.pi)
                pygame.draw.arc(surface, ACCENT, (SIZE // 2 - 18, 96, 36, 36),
                                a, a + 4.4, 3)
                self._text(surface, name, 22, FG, SIZE // 2, 148, align="center")
                self._text(surface, "connecting...", 17, MUTED, SIZE // 2, 176, align="center")
            else:
                cx, cy = SIZE // 2, 112
                pygame.draw.lines(surface, GREEN, False,
                                  [(cx - 12, cy), (cx - 4, cy + 9), (cx + 13, cy - 10)], 4)
                self._text(surface, name, 22, FG, SIZE // 2, 148, align="center")
                self._text(surface, "connected", 17, GREEN, SIZE // 2, 176, align="center")
            return
        if not devices:
            self._text(surface, "No devices found", 20, MUTED, SIZE // 2, 110, align="center")
            self._text(surface, "back to rescan", 16, DIM, SIZE // 2, 136, align="center")
            return
        y0, row_h = 66, 33
        scroll = max(0, min(cursor - 4, len(devices) - 5))
        for i, dev in enumerate(devices[scroll : scroll + 5]):
            y = y0 + i * row_h
            selected = scroll + i == cursor
            if selected:
                pygame.draw.rect(surface, PILL, (6, y - 3, SIZE - 18, row_h - 4),
                                 border_radius=13)
            self._text(surface, self._fit(dev["name"], 22, SIZE - 40), 22,
                       FG if selected else MUTED, 18, y + 2)
        self._scrollbar(surface, y0, 5 * row_h - 8, len(devices), 5, scroll)

    def draw_battery_screen(self, surface, status: dict) -> None:
        batt = status.get("battery")
        charging = status.get("charging")
        note = "charging" if charging else ("on battery" if charging is False else "")
        big = f"{batt}%" if batt is not None else "--"
        self._big_bar_screen(surface, status, "Battery", big, batt, note)

    def draw_brightness_screen(self, surface, pct: int, status: dict) -> None:
        self._big_bar_screen(surface, status, "Brightness", f"{pct}%", pct,
                             "wheel adjusts - press to exit")

    def draw_about_screen(self, surface, scroll: int, status: dict) -> None:
        surface.fill(BG)
        self._header(surface, status)
        self._text(surface, "About", 24, ACCENT, 12, 34)
        y0, row_h = 68, 31
        for i, line in enumerate(ABOUT_FEATURES[scroll : scroll + ABOUT_VISIBLE]):
            color = ACCENT if scroll + i == 0 else MUTED
            self._text(surface, self._fit(line, 20, SIZE - 40), 20, color, 18, y0 + i * row_h)
        self._scrollbar(surface, y0, ABOUT_VISIBLE * row_h - 8,
                        len(ABOUT_FEATURES), ABOUT_VISIBLE, scroll)
