"""device v2 — Raspberry Pi launcher.

Run it:       python3 pi/device.py    (or via systemd/pimusicdevice.service)
Display test: python3 pi/device.py --display-test
              (static pattern: 1px border, TL/TR/BL/BR, UP arrow, R/G/B
               bars — any offset, rotation, or color-order mistake is
               visible in one second; Ctrl-C to exit)

Sets SDL's dummy video/audio drivers (the ST7789 gets frames over SPI, MPD
owns the audio), builds the real hardware drivers, and hands everything to
the shared main loop. This module must import cleanly on a Mac with no
hardware libraries installed — all hardware imports happen inside main().

Controls (ANO encoder over seesaw):
    wheel            scroll / volume
    center press     select        center hold >= 600 ms   back
    up/down/left/right   the ring buttons
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def display_test() -> int:
    import time

    import pygame

    pygame.init()
    from shared import config
    from shared.screen import SIZE, ScreenRenderer
    from pi.display_pi import DisplayPi

    surface = pygame.Surface((SIZE, SIZE), depth=24)
    ScreenRenderer().draw_display_test(surface)
    display = DisplayPi()
    display.push_frame(surface)
    print(f"display test — profile {config.DISPLAY_PROFILE}: "
          "border on all edges, TL/TR/BL/BR in the corners, arrow points up, "
          "bars read R/G/B top to bottom. Ctrl-C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    return 0


def main() -> int:
    import pygame

    pygame.init()

    from shared import app, pisugar
    from shared.hardware import HardwareBundle
    from pi import bluetooth_pi, library_mpd
    from pi.display_pi import DisplayPi
    from pi.haptic_pi import HapticPi
    from pi.input_pi import ANOInput
    from pi.player_mpd import PlayerMPD

    pisugar.start_polling()
    tracks = library_mpd.load_tracks()
    print(f"device v2 — Pi, {len(tracks)} tracks from MPD")
    hw = HardwareBundle(DisplayPi(), ANOInput(), HapticPi(), PlayerMPD(tracks))
    try:
        app.run(hw, tracks, bluetooth_pi)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    if "--display-test" in sys.argv:
        sys.exit(display_test())
    sys.exit(main())
