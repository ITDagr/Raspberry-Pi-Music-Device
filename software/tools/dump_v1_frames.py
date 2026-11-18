"""Throwaway: render v1's screens to PNGs for side-by-side comparison with v2.

    python3 tools/dump_v1_frames.py [/path/to/v1] [outdir]

Imports v1's ScreenRenderer directly (v1's shared modules import each other as
top-level names, so v1's shared/ goes on sys.path).
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

V1 = sys.argv[1] if len(sys.argv) > 1 else "/Users/iandagerman/Downloads/device"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/v1frames"
sys.path.insert(0, os.path.join(V1, "shared"))

import pygame  # noqa: E402

pygame.init()
import screen as v1  # noqa: E402  (v1's shared/screen.py)

os.makedirs(OUT, exist_ok=True)
r = v1.ScreenRenderer()
status = {"clock": "12:34", "battery": 84}


def save(name: str, surf: pygame.Surface) -> None:
    pygame.image.save(surf, os.path.join(OUT, f"{name}.png"))
    print(f"v1 frame: {OUT}/{name}.png")


def fresh() -> pygame.Surface:
    return pygame.Surface((v1.SIZE, v1.SIZE))


items = [{"label": l, "action": a, "glyph": "", "section": ""} for l, a in [
    ("Fading Again", "do:play:0"), ("Gliding Again", "do:play:1"),
    ("Hiding Backwards", "do:play:2"), ("Hiding Sideways", "do:play:3"),
    ("Calling North", "do:play:4"), ("Dreaming Twice", "do:play:5"),
]]
ctrl = SimpleNamespace(view=lambda: items, cursor=1, page=0, current_name="songs")
s = fresh()
r.draw(s, ctrl, status, playing=True)
save("menu_songs", s)

home_items = [{"label": l, "action": a, "glyph": "", "section": ""} for l, a in [
    ("Music", "menu:music"), ("Now Playing", "mode:nowplaying"),
    ("Shuffle All", "do:shuffle"), ("Settings", "menu:settings"),
]]
ctrl_home = SimpleNamespace(view=lambda: home_items, cursor=0, page=0,
                            current_name="root")
s = fresh()
r.draw(s, ctrl_home, status, playing=False)
save("menu_home", s)

track = {"title": "Hiding Sideways", "artist": "Echo Circuit", "duration": 180}
s = fresh()
r.draw_nowplaying(s, track, 42.0, status, volume=60, shuffle=False, playing=True)
save("nowplaying", s)

r.draw_volume_overlay(s, 60, status)
save("volume_overlay", s)

devices = [{"name": n, "address": a} for n, a in [
    ("AirPods Pro", "A1"), ("JBL Flip 6", "B2"), ("Pixel Buds A", "C3"),
    ("Car Stereo", "D4")]]
s = fresh()
r.draw_bluetooth(s, devices, 0, status, connecting_addr="A1")
save("bluetooth_connecting", s)
s = fresh()
r.draw_bluetooth(s, devices, 0, status, connected_addr="A1")
save("bluetooth_connected", s)

s = fresh()
r.draw_battery_screen(s, 84, status)
save("battery", s)

s = fresh()
r.draw_brightness_screen(s, 0.7, status)
save("brightness", s)

s = fresh()
r.draw_about_screen(s, 2, status)
save("about", s)
