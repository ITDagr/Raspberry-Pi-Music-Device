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


def _check_encoder_bus() -> bool:
    """The encoder is mandatory: verify the seesaw ACKs before booting.
    On failure, print one clear message listing everything on the bus."""
    from shared import config
    from tools.i2c_scan import scan_bus

    found = scan_bus(config.I2C_BUS)
    if found is None:
        print("input: cannot scan the I2C bus (no smbus2/i2c-tools) — "
              "skipping the encoder probe")
        return True
    if config.SEESAW_ADDR in found:
        return True
    listing = ", ".join(f"0x{a:02X}" for a in found) or "none"
    print(f"input: no ANO encoder (seesaw) at 0x{config.SEESAW_ADDR:02X} "
          f"on I2C bus {config.I2C_BUS}.")
    print(f"       addresses found on the bus: {listing}")
    print("       Check the encoder's STEMMA QT cable (into the Beret or the "
          "5-port hub), then verify with: i2cdetect -y 1")
    return False


def main() -> int:
    import pygame

    pygame.init()

    from shared import app, pisugar
    from shared.hardware import HardwareBundle
    from pi import bluetooth_pi, library_mpd
    from pi.display_pi import DisplayPi
    from pi.haptic_pi import make_haptic
    from pi.input_pi import ANOInput
    from pi.player_mpd import PlayerMPD
    from pi.power_pi import PowerSwitchPi

    if not _check_encoder_bus():
        return 1
    pisugar.start_polling()
    tracks = library_mpd.load_tracks()
    print(f"device v2 — Pi, {len(tracks)} tracks from MPD")
    hw = HardwareBundle(DisplayPi(), ANOInput(), make_haptic(), PlayerMPD(tracks),
                        power=PowerSwitchPi())
    try:
        app.run(hw, tracks, bluetooth_pi)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    if "--display-test" in sys.argv:
        sys.exit(display_test())
    sys.exit(main())
