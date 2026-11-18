"""pizero-llm-demo — DRV2605L haptics. Entirely optional.

Adapted from pimusicdevicev2's pi/haptic_pi.py. Constructing the driver IS the
boot probe (it reads the chip's device ID over I2C); make_haptic() owns the
fallback to a no-op so an absent or unplugged motor is never fatal.

Motor mode matters: the assembled actuator is an ERM disc, and an LRA-mode
drive barely moves it.
"""
from __future__ import annotations

from app import config


class NullHaptic:
    def tick(self) -> None: ...
    def click(self) -> None: ...
    def back(self) -> None: ...
    def pulse(self) -> None: ...


class Haptic:
    def __init__(self) -> None:
        # No try/except: construction is the probe, make_haptic() handles it.
        import board
        import adafruit_drv2605

        drv = adafruit_drv2605.DRV2605(board.I2C(), address=config.DRV2605_ADDR)
        if config.HAPTIC_MOTOR == "lra":
            drv.use_LRM()
        else:
            drv.use_ERM()
        drv.library = config.HAPTIC_LIBRARY
        self._drv = drv
        self._effect = adafruit_drv2605.Effect
        self._warned = False

    def _play(self, effect_id: int) -> None:
        try:
            self._drv.sequence[0] = self._effect(effect_id)
            self._drv.play()
        except Exception as exc:  # unplugged mid-run: log once, go quiet
            if not self._warned:
                print(f"haptic: play failed ({exc})")
                self._warned = True

    def tick(self) -> None:
        self._play(config.EFFECT_TICK)

    def click(self) -> None:
        self._play(config.EFFECT_CLICK)

    def back(self) -> None:
        self._play(config.EFFECT_BACK)

    def pulse(self) -> None:
        self._play(config.EFFECT_PULSE)


def make_haptic():
    try:
        return Haptic()
    except Exception:
        print("haptics: not detected — continuing without")
        return NullHaptic()
