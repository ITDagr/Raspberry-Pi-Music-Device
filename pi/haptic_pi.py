"""device v2 — DRV2605L haptic driver (LRA motor, LRA ROM library).

Effects: tick=14 (scroll detent), click=1 (select), back=7, pulse=47 (boot).
Every I2C call is wrapped so a missing or flaky motor never crashes the UI —
it logs once and goes quiet.
"""
from __future__ import annotations

from shared import config


class HapticPi:
    def __init__(self) -> None:
        self._drv = None
        self._effect_cls = None
        self._warned = False
        try:
            import board
            import adafruit_drv2605

            drv = adafruit_drv2605.DRV2605(board.I2C(), address=config.DRV2605_ADDR)
            drv.use_LRM()          # LRA motor
            drv.library = 6        # LRA ROM effect library
            self._drv = drv
            self._effect_cls = adafruit_drv2605.Effect
        except Exception as e:
            print(f"haptic: disabled ({e})")
            self._warned = True

    def _play(self, effect_id: int) -> None:
        if self._drv is None:
            return
        try:
            self._drv.sequence[0] = self._effect_cls(effect_id)
            self._drv.play()
        except Exception as e:
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
