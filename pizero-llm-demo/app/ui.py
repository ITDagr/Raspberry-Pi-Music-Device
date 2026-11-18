"""pizero-llm-demo — 240x240 rendering with Pillow.

The stats strip is the point of the demo. A box that writes sentences is a toy;
a box that writes sentences while showing the model name, the quantisation, the
live token rate and how close to the RAM ceiling it is, is a demonstration.

The renderer keeps one persistent Image and repaints only the half that changed,
returning dirty rectangles so display.py can push ~12 KB instead of ~115 KB.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

from app import config

Rect = tuple[int, int, int, int]

STRIP_RECT: Rect = (0, 0, config.SIZE, config.STRIP_H)
BODY_RECT: Rect = (0, config.BODY_Y, config.SIZE, config.SIZE - config.BODY_Y)


@dataclass
class ViewState:
    mode: str = "WHEEL"              # WHEEL | GEN | DONE | ERROR | BOOT
    set_name: str = ""
    rows: list[str] = field(default_factory=list)
    sel: int = 0
    text: str = ""
    scroll: int = 0                  # first visible wrapped line
    tok_s: float | None = None
    ram_used: int = 0
    ram_total: int = 0
    note: str = ""                   # error / status line


def _font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:       # Pillow < 10
            return ImageFont.load_default()


class Renderer:
    def __init__(self) -> None:
        self.img = Image.new("RGB", (config.SIZE, config.SIZE), config.COL_BG)
        self.d = ImageDraw.Draw(self.img)
        self.f_body = _font(config.FONT_PATH, config.FONT_BODY)
        self.f_small = _font(config.FONT_PATH, config.FONT_SMALL)
        self.f_bold = _font(config.FONT_BOLD_PATH, config.FONT_SMALL)
        self._strip_sig: tuple | None = None
        self._body_sig: tuple | None = None
        self._wrap_cache: tuple[str, tuple[str, ...]] = ("", ())

    # --- helpers ------------------------------------------------------------
    def _width(self, text: str, font) -> float:
        try:
            return font.getlength(text)
        except AttributeError:       # very old Pillow
            return font.getsize(text)[0]

    def wrap(self, text: str, font, max_w: int) -> list[str]:
        """Word-wrap, hard-breaking words too long to fit on their own line."""
        if self._wrap_cache[0] == text:
            return list(self._wrap_cache[1])
        lines: list[str] = []
        for para in text.split("\n"):
            if not para.strip():
                lines.append("")
                continue
            cur = ""
            for word in para.split():
                probe = f"{cur} {word}".strip()
                if self._width(probe, font) <= max_w:
                    cur = probe
                    continue
                if cur:
                    lines.append(cur)
                # a single word wider than the line: break it by characters
                while self._width(word, font) > max_w:
                    cut = len(word)
                    while cut > 1 and self._width(word[:cut], font) > max_w:
                        cut -= 1
                    lines.append(word[:cut])
                    word = word[cut:]
                cur = word
            if cur:
                lines.append(cur)
        self._wrap_cache = (text, tuple(lines))
        return lines

    @property
    def body_lines(self) -> int:
        return (config.SIZE - config.BODY_Y) // config.LINE_H

    # --- stats strip --------------------------------------------------------
    def _draw_strip(self, st: ViewState) -> None:
        d = self.d
        d.rectangle([0, 0, config.SIZE, config.STRIP_H - 1], fill=config.COL_STRIP)

        label = f"{config.MODEL_LABEL}"
        d.text((6, 3), label, font=self.f_bold, fill=config.COL_TEXT)
        qx = 6 + self._width(label, self.f_bold) + 5
        d.text((qx, 3), config.MODEL_QUANT, font=self.f_small, fill=config.COL_ACCENT)

        badge = {"GEN": "THINKING", "DONE": "READY", "WHEEL": "READY",
                 "ERROR": "ERROR", "BOOT": "LOADING"}.get(st.mode, st.mode)
        bw = self._width(badge, self.f_small)
        bcol = (config.COL_ERR if st.mode == "ERROR"
                else config.COL_WARN if st.mode in ("GEN", "BOOT")
                else config.COL_DIM)
        d.text((config.SIZE - 6 - bw, 3), badge, font=self.f_small, fill=bcol)

        rate = f"{st.tok_s:.1f} tok/s" if st.tok_s else "-- tok/s"
        mem = f"{st.ram_used}/{st.ram_total} MB" if st.ram_total else "-- MB"
        d.text((6, 18), f"{rate}   {mem}", font=self.f_small, fill=config.COL_DIM)

        # RAM pressure as the strip's bottom edge: the closer this runs to full,
        # the closer the page cache is to evicting the weights it just read.
        y = config.STRIP_H - 3
        d.rectangle([0, y, config.SIZE, config.STRIP_H - 1], fill=(30, 36, 43))
        if st.ram_total:
            frac = max(0.0, min(1.0, st.ram_used / st.ram_total))
            col = (config.COL_ERR if frac > 0.93
                   else config.COL_WARN if frac > 0.85 else config.COL_ACCENT)
            d.rectangle([0, y, int(config.SIZE * frac), config.STRIP_H - 1], fill=col)

    # --- wheel --------------------------------------------------------------
    def _draw_wheel(self, st: ViewState) -> None:
        d = self.d
        d.rectangle([0, config.BODY_Y, config.SIZE, config.SIZE], fill=config.COL_BG)

        header = f"◀  {st.set_name}  ▶"
        hx = (config.SIZE - self._width(header, self.f_small)) / 2
        d.text((hx, config.BODY_Y + 3), header, font=self.f_small, fill=config.COL_DIM)

        rows, sel = st.rows, st.sel
        visible = min(config.WHEEL_ROWS, len(rows))
        # keep the selection inside the window
        first = max(0, min(sel - visible // 2, len(rows) - visible)) if rows else 0

        top, rh = config.BODY_Y + 22, 22
        for i in range(visible):
            idx = first + i
            y = top + i * rh
            chosen = idx == sel
            if chosen:
                d.rectangle([4, y, config.SIZE - 5, y + rh - 3], fill=(24, 34, 29))
                d.rectangle([4, y, 6, y + rh - 3], fill=config.COL_ACCENT)
            d.text((13, y + 4), rows[idx], font=self.f_body,
                   fill=config.COL_TEXT if chosen else config.COL_DIM)

        if len(rows) > visible:
            pos = f"{sel + 1}/{len(rows)}"
            d.text((config.SIZE - 6 - self._width(pos, self.f_small), config.SIZE - 15),
                   pos, font=self.f_small, fill=config.COL_DIM)
        d.text((6, config.SIZE - 15), "press to run", font=self.f_small,
               fill=config.COL_DIM)

    # --- output -------------------------------------------------------------
    def _draw_output(self, st: ViewState) -> None:
        d = self.d
        d.rectangle([0, config.BODY_Y, config.SIZE, config.SIZE], fill=config.COL_BG)

        if st.mode == "ERROR":
            lines = self.wrap(st.note or "unknown error", self.f_body, config.SIZE - 14)
            for i, line in enumerate(lines[: self.body_lines]):
                d.text((7, config.BODY_Y + 4 + i * config.LINE_H), line,
                       font=self.f_body, fill=config.COL_ERR)
            return

        body = st.text or ("…" if st.mode == "GEN" else "")
        lines = self.wrap(body, self.f_body, config.SIZE - 18)
        vis = self.body_lines
        first = max(0, min(st.scroll, max(0, len(lines) - vis)))
        shown = lines[first:first + vis]

        for i, line in enumerate(shown):
            d.text((7, config.BODY_Y + 4 + i * config.LINE_H), line,
                   font=self.f_body, fill=config.COL_TEXT)

        # caret: makes a 4 tok/s stream look alive instead of stalled
        if st.mode == "GEN" and int(time.monotonic() * 2) % 2 == 0:
            ly = config.BODY_Y + 4 + max(0, len(shown) - 1) * config.LINE_H
            lx = 7 + (self._width(shown[-1], self.f_body) if shown else 0) + 2
            if lx < config.SIZE - 10:
                d.rectangle([lx, ly + 2, lx + 6, ly + 12], fill=config.COL_ACCENT)

        if len(lines) > vis:
            track_h = config.SIZE - config.BODY_Y - 8
            bar = max(12, int(track_h * vis / len(lines)))
            off = int((track_h - bar) * first / max(1, len(lines) - vis))
            x = config.SIZE - 5
            d.rectangle([x, config.BODY_Y + 4, x + 2, config.BODY_Y + 4 + track_h],
                        fill=(28, 34, 40))
            d.rectangle([x, config.BODY_Y + 4 + off, x + 2,
                         config.BODY_Y + 4 + off + bar], fill=config.COL_DIM)

    # --- public -------------------------------------------------------------
    def render(self, st: ViewState) -> list[Rect]:
        """Repaint what changed. Returns the rectangles that need pushing."""
        dirty: list[Rect] = []

        strip_sig = (st.mode, round(st.tok_s or -1, 1), st.ram_used, st.ram_total)
        if strip_sig != self._strip_sig:
            self._draw_strip(st)
            self._strip_sig = strip_sig
            dirty.append(STRIP_RECT)

        if st.mode == "WHEEL":
            body_sig = ("W", st.set_name, st.sel, tuple(st.rows))
        elif st.mode == "GEN":
            # the caret blinks, so include its phase in the signature
            body_sig = ("G", len(st.text), st.scroll, int(time.monotonic() * 2) % 2)
        else:
            body_sig = (st.mode, len(st.text), st.scroll, st.note)

        if body_sig != self._body_sig:
            if st.mode == "WHEEL":
                self._draw_wheel(st)
            else:
                self._draw_output(st)
            self._body_sig = body_sig
            dirty.append(BODY_RECT)

        return dirty

    def splash(self, message: str) -> Image.Image:
        """Full-frame boot card, shown while llama-server pages the model in."""
        d = self.d
        d.rectangle([0, 0, config.SIZE, config.SIZE], fill=config.COL_BG)
        title = "local llm"
        tx = (config.SIZE - self._width(title, self.f_bold)) / 2
        d.text((tx, 88), title, font=self.f_bold, fill=config.COL_ACCENT)
        sub = f"{config.MODEL_LABEL} {config.MODEL_QUANT}"
        d.text(((config.SIZE - self._width(sub, self.f_body)) / 2, 108),
               sub, font=self.f_body, fill=config.COL_TEXT)
        d.text(((config.SIZE - self._width(message, self.f_small)) / 2, 134),
               message, font=self.f_small, fill=config.COL_DIM)
        self._strip_sig = self._body_sig = None   # force a full repaint next
        return self.img
