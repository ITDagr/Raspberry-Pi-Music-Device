"""device v2 — DRV2605L haptic driver (motor mode/library from config).

Effects: tick=14 (scroll detent), click=1 (select), back=7, pulse=47 (boot).
make_haptic() probes the chip once at boot (constructing the driver reads
its device ID over I²C); any failure — import error, no ACK — installs a
NullHaptic instead, with exactly one info line. After boot, every I²C call
is still wrapped so a motor unplugged mid-run never crashes the UI.
"""
from __future__ import annotations

from shared import config
from shared.hardware import Haptic, NullHaptic


class HapticPi:
    def __init__(self) -> None:
        # No try/except here: construction IS the boot probe, and
        # make_haptic() owns the fallback.
        import board
        import adafruit_drv2605

        drv = adafruit_drv2605.DRV2605(board.I2C(), address=config.DRV2605_ADDR)
        if config.HAPTIC_MOTOR == "lra":
            drv.use_LRM()      # LRA motor (resonant AC drive)
        else:
            drv.use_ERM()      # ERM motor, e.g. Adafruit mini vibrating disc
        drv.library = config.HAPTIC_LIBRARY
        self._drv = drv
        self._effect_cls = adafruit_drv2605.Effect
        self._warned = False

    def _play(self, effect_id: int) -> None:
        try:
            self._drv.sequence[0] = self._effect_cls(effect_id)
            self._drv.play()
        except Exception as e:  # unplugged mid-run: log once, go quiet
            if not self._warned:
                print(f"haptic: play failed ({e})")
                self._warned = True

    def tick(self) -> None:
        self._play(config.EFFECT_TICK)

    def click(self) -> None:
        self._play(config.EFFECT_CLICK)

    def back(self) -> None:
        self._play(config.EFFECT_BACK)

    def pulse(self) -> None:
        self._play(config.EFFECT_PULSE)


def make_haptic() -> Haptic:
    """One boot-time probe at I²C 0x5A; NullHaptic on any failure."""
    try:
        return HapticPi()
    except Exception:
        print("haptics: not detected — continuing without")
        return NullHaptic()
