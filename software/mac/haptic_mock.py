"""device v2 — terminal stand-in for the DRV2605L haptic motor.

Each event prints one line with the effect it would play on the Pi.
"""
from __future__ import annotations

from shared import config


class MockHaptic:
    def _play(self, glyph: str, name: str, effect: int) -> None:
        print(f"haptic {glyph}  {name:<7}(effect {effect})")

    def tick(self) -> None:
        self._play("░", "tick", config.EFFECT_TICK)

    def click(self) -> None:
        self._play("●", "click", config.EFFECT_CLICK)

    def back(self) -> None:
        self._play("◀", "back", config.EFFECT_BACK)

    def pulse(self) -> None:
        self._play("◉", "pulse", config.EFFECT_PULSE)
