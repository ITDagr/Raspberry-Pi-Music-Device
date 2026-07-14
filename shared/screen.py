"""device v2 — all drawing for the 240x240 screen (v1 "DETENT" visual system).

Ported from v1's shared/screen.py: same tokens, grid, and layouts, adapted to
v2's MenuView dataclass and Display protocol. Fonts are pygame's bundled
Font(None, ...) — never SysFont, which is unreliable across machines and
headless — so glyphs the bundled font lacks (check mark, sun) are drawn with
primitives.

DETENT tokens (@ SIZE=240):
  Colors    base #0E0F13  surface #1B1E26  line #2A2E38
            text #F2F3F5  dim #8A8F9C
            accent #FF6A3D  (focus / active progress — FOCUS ONLY)
            state  #5BD6A6  (connected / playing / battery-ok — STATUS ONLY)
  Grid      margin 12 · status-bar 24 · row 38 (pill 32, r 10) · card r 18
"""
from __future__ import annotations

import math
from typing import Optional

import pygame

from shared.hardware import Track
from shared.menu_core import MenuView

SIZE = 240

# --- tokens -------------------------------------------------------------------
C_BASE = (14, 15, 19)      # #0E0F13  screen background
C_SURFACE = (27, 30, 38)   # #1B1E26  selection pill / cards
C_LINE = (42, 46, 56)      # #2A2E38  hairlines, inactive track
C_TEXT = (242, 243, 245)   # #F2F3F5  primary text
C_DIM = (138, 143, 156)    # #8A8F9C  secondary / labels
C_ACCENT = (255, 106, 61)  # #FF6A3D  focus / active progress
C_STATE = (91, 214, 166)   # #5BD6A6  positive status

# Semantic aliases — every draw call uses one of these names, nothing ad hoc.
BG = C_BASE
FG = C_TEXT
MUTED = C_DIM
ACCENT = C_ACCENT
HIGHLIGHT_BG = C_SURFACE    # cursor pill
HIGHLIGHT_FG = C_TEXT       # cursor row text
GREEN = C_STATE

# Grid
MARGIN = 12
STATUSH = 24
ROW_H = 38
PILL_H = 32
PILL_R = 10
CARD_R = 18
LIST_Y0 = STATUSH + 20      # first row of a titled (non-root) list

# Dirty rects for the partial-update path (shared.app pushes only these
# through Display.push_region for the small per-second redraws; anything
# touching layout still pushes a full frame). A pixel-identity test in
# tests/test_render.py proves each rect covers everything that changes.
STATUS_BAR_RECT = pygame.Rect(0, 0, SIZE, STATUSH + 1)       # bar + hairline
NOWPLAYING_TICK_RECT = pygame.Rect(0, 144, SIZE, 46)         # progress + times

ABOUT_FEATURES = [
    "Now Playing screen",
    "Artist / Album browsing",
    "Shuffle mode",
    "Context-aware track advance",
    "Bluetooth audio",
    "Haptic feedback",
    "Boot animation",
    "Battery percentage (PiSugar)",
    "Live clock (RTC)",
    "Screen dimmer + sleep",
    "Persistent playback state",
    "Encoder acceleration",
    "Volume overlay",
    "Scroll wheel navigation",
]
ABOUT_VISIBLE = 4

_FONT_SPECS = [(s, False) for s in (10, 11, 12, 13, 14, 16, 17, 18, 22, 28, 36, 38)]
_FONT_SPECS += [(s, True) for s in (10, 11, 12, 13, 17, 18, 22, 28, 36, 38)]
# Sizes in this file are v1's Arial point sizes; the bundled font renders
# ~1.38x smaller at the same nominal size (measured), so scale on creation.
_FONT_SCALE = 1.38


def _mss(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


class ScreenRenderer:
    def __init__(self) -> None:
        if not pygame.font.get_init():
            pygame.font.init()
        # Cache the bundled font once, up front; a broken font install must
        # fail loudly, not render invisible screens.
        try:
            self._fonts: dict[tuple[int, bool], pygame.font.Font] = {}
            for size, bold in _FONT_SPECS:
                self._font(size, bold)
        except (pygame.error, OSError) as e:
            raise RuntimeError(f"renderer: cannot create fonts ({e})") from e

    # --- primitives -----------------------------------------------------------
    def _font(self, size: int, bold: bool = False) -> pygame.font.Font:
        key = (size, bold)
        if key not in self._fonts:
            f = pygame.font.Font(None, max(8, round(size * _FONT_SCALE)))
            f.set_bold(bold)
            self._fonts[key] = f
        return self._fonts[key]

    def _mono(self, size: int) -> pygame.font.Font:
        # v1 used Courier here; the bundled font stands in (see module docstring)
        return self._font(size)

    def _render(self, surf, text, font: pygame.font.Font, color, x: int, y: int,
                anchor: str = "topleft") -> None:
        img = font.render(str(text), True, color)
        r = img.get_rect()
        setattr(r, anchor, (x, y))
        surf.blit(img, r)

    def _fit(self, text: str, font: pygame.font.Font, max_w: int) -> str:
        if font.size(text)[0] <= max_w:
            return text
        while text and font.size(text + "…")[0] > max_w:
            text = text[:-1]
        return text + "…"

    def _check(self, surf, cx: int, cy: int, color) -> None:
        pygame.draw.lines(surf, color, False,
                          [(cx - 6, cy), (cx - 2, cy + 4), (cx + 6, cy - 5)], 2)

    def _sun(self, surf, cx: int, cy: int, color) -> None:
        pygame.draw.circle(surf, color, (cx, cy), 7)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1),
                       (-1, 1), (-1, -1)):
            n = 1.414 if dx and dy else 1.0
            pygame.draw.line(surf, color,
                             (cx + int(10 * dx / n), cy + int(10 * dy / n)),
                             (cx + int(14 * dx / n), cy + int(14 * dy / n)), 2)

    # --- shared components ---------------------------------------------------
    def _status_bar(self, surf, status: dict, playing: bool = False) -> None:
        """Top 24px: clock left, equalizer glyph center while playing, battery right."""
        pygame.draw.rect(surf, C_BASE, (0, 0, SIZE, STATUSH))
        pygame.draw.line(surf, C_LINE, (0, STATUSH), (SIZE, STATUSH))

        clock_str = status.get("clock", "")
        if clock_str:
            self._render(surf, clock_str, self._mono(11), C_DIM,
                         MARGIN, STATUSH // 2, "midleft")

        if playing:
            bar_w, gap = 3, 2
            bx = SIZE // 2 - (4 * bar_w + 3 * gap) // 2
            for i, h in enumerate((8, 12, 9, 14)):
                pygame.draw.rect(surf, C_STATE,
                                 (bx + i * (bar_w + gap), STATUSH // 2 - h // 2, bar_w, h),
                                 border_radius=1)

        bat = status.get("battery")
        if bat is None:
            # offline PiSugar: an explicit "--" beats a silently missing icon
            self._render(surf, "--", self._mono(11), C_DIM,
                         SIZE - MARGIN, STATUSH // 2, "midright")
        else:
            frac = max(0.0, min(1.0, bat / 100.0))
            bat_color = C_STATE if bat > 20 else C_ACCENT
            bw, bh = 26, 12
            bx = SIZE - MARGIN - bw - 4
            by = (STATUSH - bh) // 2
            pygame.draw.rect(surf, C_LINE, (bx, by, bw, bh), border_radius=3)
            pygame.draw.rect(surf, bat_color,
                             (bx + 2, by + 2, max(2, int((bw - 4) * frac)), bh - 4),
                             border_radius=2)
            pygame.draw.rect(surf, C_LINE, (bx + bw, by + 3, 3, bh - 6), border_radius=1)
            bat_str = f"{bat}%"
            fw = self._mono(10).size(bat_str)[0]
            self._render(surf, bat_str, self._mono(10), C_DIM,
                         bx - fw - 4, STATUSH // 2, "midleft")

    def _list_row(self, surf, y: int, label: str, selected: bool,
                  chevron: bool = False, glyph: str = "", right_label: str = "",
                  right_color=None) -> None:
        """One 38px list row: surface pill + 3px accent left edge when selected."""
        px, pw = MARGIN, SIZE - MARGIN * 2
        if selected:
            pill_y = y + (ROW_H - PILL_H) // 2
            pygame.draw.rect(surf, C_SURFACE, (px, pill_y, pw, PILL_H),
                             border_radius=PILL_R)
            pygame.draw.rect(surf, C_ACCENT, (px, pill_y, 3, PILL_H), border_radius=2)
        cy = y + ROW_H // 2
        text_x = px + 16
        if glyph:
            fg = self._font(13)
            self._render(surf, glyph, fg, C_ACCENT if selected else C_DIM,
                         text_x, cy, "midleft")
            text_x += fg.size(glyph)[0] + 6
        label_font = self._font(17, bold=selected)
        self._render(surf, self._fit(label, label_font, SIZE - MARGIN - text_x - 32),
                     label_font, C_TEXT, text_x, cy, "midleft")
        right_x = SIZE - MARGIN - 6
        if right_label:
            self._render(surf, right_label, self._font(12), right_color or C_DIM,
                         right_x, cy, "midright")
        elif chevron and selected:
            self._render(surf, "›", self._font(18, bold=True), C_ACCENT,
                         right_x, cy, "midright")
        elif chevron:
            self._render(surf, "›", self._font(16), C_DIM, right_x, cy, "midright")

    def _slider(self, surf, x: int, y: int, w: int, frac: float,
                knob: bool = True, height: int = 4) -> None:
        """Horizontal slider: inactive track -> accent fill -> optional knob."""
        frac = max(0.0, min(1.0, frac))
        fill_w = int(w * frac)
        pygame.draw.rect(surf, C_LINE, (x, y, w, height), border_radius=height // 2)
        if fill_w > 0:
            pygame.draw.rect(surf, C_ACCENT, (x, y, fill_w, height),
                             border_radius=height // 2)
        if knob:
            kx, ky = x + fill_w, y + height // 2
            pygame.draw.circle(surf, C_TEXT, (kx, ky), 6)
            pygame.draw.circle(surf, C_ACCENT, (kx, ky), 4)

    def _scroll_rail(self, surf, top: int, height: int,
                     frac_start: float, frac_len: float) -> None:
        rx, rw = SIZE - 4, 2
        pygame.draw.rect(surf, C_LINE, (rx, top, rw, height), border_radius=1)
        thumb_y = top + int(height * frac_start)
        thumb_h = max(12, int(height * frac_len))
        pygame.draw.rect(surf, C_DIM, (rx, thumb_y, rw, thumb_h), border_radius=1)

    # --- screens ---------------------------------------------------------------
    def draw(self, surface, view: MenuView, status: dict,
             playing: bool = False) -> None:
        """Menu / library list."""
        surface.fill(C_BASE)
        self._status_bar(surface, status, playing)
        is_root = view.title == "device"  # the home menu ≙ v1's untitled root
        if not is_root:
            self._render(surface, view.title.upper(), self._font(10, bold=True),
                         C_DIM, MARGIN, STATUSH + 6, "topleft")
        content_top = STATUSH + (20 if not is_root else 4)
        y = content_top
        for i, label in enumerate(view.items):
            if y >= SIZE:
                break
            chevron = view.chevrons[i] if i < len(view.chevrons) else False
            self._list_row(surface, y, label, i == view.cursor, chevron=chevron)
            y += ROW_H
        if view.total > len(view.items):
            frac_start = view.window_start / max(1, view.total - len(view.items))
            self._scroll_rail(surface, content_top, SIZE - content_top - MARGIN,
                              frac_start, len(view.items) / view.total)

    def draw_nowplaying(self, surface, track: Optional[Track], elapsed: float,
                        playing: bool, volume: int, status: dict,
                        shuffle: bool = False) -> None:
        surface.fill(C_BASE)
        self._status_bar(surface, status, playing)
        if track is None:
            self._render(surface, "Nothing playing", self._font(17, bold=True),
                         C_TEXT, SIZE // 2, SIZE // 2 - 10, "midtop")
            self._render(surface, "pick a song in Music", self._font(11), C_DIM,
                         SIZE // 2, SIZE // 2 + 16, "midtop")
            return

        self._render(surface, "NOW PLAYING", self._font(10, bold=True), C_ACCENT,
                     MARGIN, STATUSH + 8, "topleft")

        # Track title, wrapped to at most 2 lines
        f_title = self._font(22, bold=True)
        lines: list[str] = []
        current: list[str] = []
        for word in track.title.split():
            test = " ".join(current + [word])
            if f_title.size(test)[0] > SIZE - MARGIN * 2 and current:
                lines.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(" ".join(current))
        ty = STATUSH + 28
        for line in lines[:2]:
            self._render(surface, line, f_title, C_TEXT, MARGIN, ty, "topleft")
            ty += f_title.get_linesize() + 2
        self._render(surface, track.artist, self._font(14), C_DIM,
                     MARGIN, ty + 4, "topleft")

        # Progress bar + knob
        prog_y, bar_h = 156, 4
        prog_w = SIZE - MARGIN * 2
        frac = elapsed / max(1.0, track.duration)
        pygame.draw.rect(surface, C_LINE, (MARGIN, prog_y, prog_w, bar_h),
                         border_radius=bar_h // 2)
        fill_w = max(0, min(prog_w, int(prog_w * frac)))
        if fill_w:
            pygame.draw.rect(surface, C_ACCENT, (MARGIN, prog_y, fill_w, bar_h),
                             border_radius=bar_h // 2)
        kx, ky = MARGIN + fill_w, prog_y + bar_h // 2
        pygame.draw.circle(surface, C_TEXT, (kx, ky), 6)
        pygame.draw.circle(surface, C_ACCENT, (kx, ky), 4)

        f_tc = self._mono(11)
        self._render(surface, _mss(elapsed), f_tc, C_DIM,
                     MARGIN, prog_y + bar_h + 6, "topleft")
        self._render(surface, f"-{_mss(track.duration - elapsed)}", f_tc, C_DIM,
                     SIZE - MARGIN, prog_y + bar_h + 6, "topright")

        # Transport row: shuffle label - play/pause - volume
        cy = 192 + 14
        shuf_color = C_STATE if shuffle else C_DIM
        self._render(surface, "shuf", self._font(11, bold=shuffle), shuf_color,
                     MARGIN + 22, cy, "midleft")
        cx = SIZE // 2
        if playing:
            pygame.draw.rect(surface, C_TEXT, (cx - 10, cy - 10, 5, 20))
            pygame.draw.rect(surface, C_TEXT, (cx + 5, cy - 10, 5, 20))
        else:
            pygame.draw.polygon(surface, C_TEXT,
                                [(cx - 8, cy - 10), (cx - 8, cy + 10), (cx + 12, cy)])
        vol_num = str(volume)
        f_vol = self._mono(11)
        num_w = f_vol.size(vol_num)[0]
        bar_w = 32
        left_x = SIZE - MARGIN - (num_w + 5 + bar_w)
        self._render(surface, vol_num, f_vol, C_DIM, left_x, cy, "midleft")
        self._slider(surface, left_x + num_w + 5, cy - 2, bar_w, volume / 100,
                     knob=False, height=3)

    def draw_volume_overlay(self, surface, volume: int) -> None:
        """Transient volume overlay: dim underlay + centered card."""
        dim = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
        dim.fill((*C_BASE, 200))
        surface.blit(dim, (0, 0))
        cw, ch = 160, 100
        cx, cy = (SIZE - cw) // 2, (SIZE - ch) // 2
        pygame.draw.rect(surface, C_SURFACE, (cx, cy, cw, ch), border_radius=CARD_R)
        self._render(surface, "VOLUME", self._font(10, bold=True), C_DIM,
                     SIZE // 2, cy + 14, "midtop")
        self._render(surface, str(volume), self._font(36, bold=True), C_TEXT,
                     SIZE // 2, cy + 32, "midtop")
        self._slider(surface, cx + 16, cy + 78, cw - 32, volume / 100,
                     knob=True, height=4)

    def draw_bluetooth(self, surface, devices: list, cursor: int,
                       connect_info: Optional[dict], status: dict,
                       scanning: bool = False) -> None:
        surface.fill(C_BASE)
        self._status_bar(surface, status)
        self._render(surface, "BLUETOOTH", self._font(10, bold=True), C_DIM,
                     MARGIN, STATUSH + 6, "topleft")
        if scanning and not devices:
            # 8-dot spinner, one accent dot chasing; the scan thread fills
            # the list when it finishes, back cancels immediately
            cx, cy = SIZE // 2, SIZE // 2 - 16
            active = (pygame.time.get_ticks() // 120) % 8
            for i in range(8):
                ang = math.tau * i / 8
                pos = (cx + int(20 * math.cos(ang)), cy + int(20 * math.sin(ang)))
                pygame.draw.circle(surface, C_ACCENT if i == active else C_LINE,
                                   pos, 3)
            self._render(surface, "Scanning…", self._font(13), C_DIM,
                         SIZE // 2, cy + 36, "midtop")
            return
        if not devices:
            self._render(surface, "No devices found", self._font(17, bold=True),
                         C_TEXT, SIZE // 2, SIZE // 2 - 10, "midtop")
            self._render(surface, "back to rescan", self._font(11), C_DIM,
                         SIZE // 2, SIZE // 2 + 16, "midtop")
            return
        connecting_addr = connected_addr = ""
        if connect_info:
            if connect_info["state"] == "connecting":
                connecting_addr = connect_info.get("address", "")
            else:
                connected_addr = connect_info.get("address", "")

        top = STATUSH + 26
        visible = (SIZE - top) // ROW_H
        start = max(0, min(cursor - visible // 2, len(devices) - visible))
        y = top
        for i, dev in enumerate(devices[start : start + visible]):
            addr = dev.get("address", "")
            right, right_color = "", None
            if addr == connecting_addr:
                right, right_color = "…", C_ACCENT
            self._list_row(surface, y, dev.get("name", addr), start + i == cursor,
                           glyph="B", right_label=right, right_color=right_color)
            if addr == connected_addr:
                self._check(surface, SIZE - MARGIN - 12, y + ROW_H // 2, C_STATE)
            y += ROW_H
        if len(devices) > visible:
            self._scroll_rail(surface, top, SIZE - top - MARGIN,
                              start / max(1, len(devices) - visible),
                              visible / len(devices))

    def draw_battery_screen(self, surface, status: dict) -> None:
        surface.fill(C_BASE)
        self._status_bar(surface, status)
        self._render(surface, "BATTERY", self._font(10, bold=True), C_DIM,
                     MARGIN, STATUSH + 6, "topleft")
        battery = status.get("battery")
        cy = SIZE // 2
        bat_color = C_STATE if (battery or 0) > 20 else C_ACCENT

        bw, bh = 80, 40
        bx, by = (SIZE - bw) // 2, cy - 50
        pygame.draw.rect(surface, C_LINE, (bx, by, bw, bh), border_radius=6, width=3)
        pygame.draw.rect(surface, C_LINE, (bx + bw, by + 12, 6, 16), border_radius=2)
        if battery is not None:
            fill_w = max(4, int((bw - 8) * battery / 100))
            pygame.draw.rect(surface, bat_color, (bx + 4, by + 6, fill_w, bh - 12),
                             border_radius=4)
        label = f"{battery}%" if battery is not None else "--"
        self._render(surface, label, self._font(28, bold=True), C_TEXT,
                     SIZE // 2, cy - 2, "midtop")
        if battery is None:
            caption = "No battery data"
        elif status.get("charging"):
            caption = "Charging"
        elif battery > 20:
            caption = "Battery good"
        elif battery > 10:
            caption = "Battery low"
        else:
            caption = "Charge soon"
        self._render(surface, caption, self._font(13), C_DIM,
                     SIZE // 2, cy + 36, "midtop")

    def draw_brightness_screen(self, surface, pct: int, status: dict) -> None:
        surface.fill(C_BASE)
        self._status_bar(surface, status)
        self._render(surface, "BRIGHTNESS", self._font(10, bold=True), C_DIM,
                     MARGIN, STATUSH + 6, "topleft")
        cy = SIZE // 2
        self._sun(surface, SIZE // 2, cy - 22, C_ACCENT)
        self._render(surface, f"{pct}%", self._font(22, bold=True), C_TEXT,
                     SIZE // 2, cy - 2, "midtop")
        self._slider(surface, MARGIN * 2, cy + 36, SIZE - MARGIN * 4, pct / 100,
                     knob=True, height=6)
        self._render(surface, "Rotate wheel to adjust", self._font(11), C_DIM,
                     SIZE // 2, cy + 60, "midtop")

    def draw_toast(self, surface, message: str) -> None:
        """Transient notification card along the bottom edge (library
        changes arriving from the web app: added / removed / playlist)."""
        f = self._font(12, bold=True)
        text = self._fit(message, f, SIZE - MARGIN * 4 - 16)
        w = f.size(text)[0] + 28
        h = 30
        x = (SIZE - w) // 2
        y = SIZE - h - 10
        pygame.draw.rect(surface, C_SURFACE, (x, y, w, h), border_radius=h // 2)
        pygame.draw.rect(surface, C_ACCENT, (x, y + 6, 3, h - 12), border_radius=2)
        self._render(surface, text, f, C_TEXT, x + w // 2 + 2, y + h // 2, "center")

    def draw_display_test(self, surface) -> None:
        """Static hardware test pattern (`--display-test` on the Pi).

        Reads wrong in one second if the panel init is off: the 1px border
        vanishes on any offset error, TL/TR/BL/BR + the UP arrow expose
        rotation/mirroring, and the labeled pure R/G/B bars expose color
        order. Colors are deliberately raw, not DETENT tokens.
        """
        surface.fill((0, 0, 0))
        white = (255, 255, 255)
        # 1px border on all four edges
        pygame.draw.rect(surface, white, (0, 0, SIZE, SIZE), width=1)
        # corner labels, inset so the border stays visible
        f = self._font(12, bold=True)
        self._render(surface, "TL", f, white, 6, 6, "topleft")
        self._render(surface, "TR", f, white, SIZE - 6, 6, "topright")
        self._render(surface, "BL", f, white, 6, SIZE - 6, "bottomleft")
        self._render(surface, "BR", f, white, SIZE - 6, SIZE - 6, "bottomright")
        # UP arrow
        cx = SIZE // 2
        pygame.draw.polygon(surface, white,
                            [(cx, 34), (cx - 16, 62), (cx + 16, 62)])
        pygame.draw.rect(surface, white, (cx - 5, 62, 10, 18))
        self._render(surface, "UP", f, white, cx, 88, "midtop")
        # labeled pure R/G/B bars
        bar_x, bar_w, bar_h = 40, SIZE - 80, 24
        for i, (label, color) in enumerate(
                (("R", (255, 0, 0)), ("G", (0, 255, 0)), ("B", (0, 0, 255)))):
            y = 120 + i * (bar_h + 10)
            pygame.draw.rect(surface, color, (bar_x, y, bar_w, bar_h))
            self._render(surface, label, f, white,
                         bar_x - 8, y + bar_h // 2, "midright")

    def draw_about_screen(self, surface, scroll: int, status: dict) -> None:
        surface.fill(C_BASE)
        self._status_bar(surface, status)
        self._render(surface, "ABOUT", self._font(10, bold=True), C_DIM,
                     MARGIN, STATUSH + 6, "topleft")
        y = STATUSH + 26
        self._render(surface, "device", self._font(18, bold=True), C_TEXT,
                     MARGIN, y, "topleft")
        y += 22
        self._render(surface, "by Ian Dagerman  •  v2.0", self._font(11), C_DIM,
                     MARGIN, y, "topleft")
        y += 20
        pygame.draw.line(surface, C_LINE, (MARGIN, y), (SIZE - MARGIN, y))
        y += 8
        total = len(ABOUT_FEATURES)
        start = max(0, min(scroll, total - ABOUT_VISIBLE))
        for feat in ABOUT_FEATURES[start : start + ABOUT_VISIBLE]:
            self._render(surface, f"• {feat}", self._font(13), C_TEXT,
                         MARGIN + 4, y, "topleft")
            y += 22
        if total > ABOUT_VISIBLE:
            self._scroll_rail(surface, STATUSH + 68, SIZE - STATUSH - 68 - MARGIN,
                              start / max(1, total - ABOUT_VISIBLE),
                              ABOUT_VISIBLE / total)
