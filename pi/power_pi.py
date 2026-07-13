"""device v2 — the Beret's slide switch (GPIO 13) as a soft power switch.

Per Adafruit the switch is just a GPIO input that reads high or low, so
this only *reports* position; shared.app implements the actual soft-off.
Polarity is config.POWER_SWITCH_ON_LEVEL; the pull keeps a floating pin
reading "off". Debounce: a new position must hold ~50 ms before is_on()
reports it.
"""
from __future__ import annotations

import time

from shared import config


class PowerSwitchPi:
    def __init__(self) -> None:
        import RPi.GPIO as GPIO

        self._gpio = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        pull = GPIO.PUD_DOWN if config.POWER_SWITCH_ON_LEVEL else GPIO.PUD_UP
        GPIO.setup(config.PIN_POWER_SWITCH, GPIO.IN, pull_up_down=pull)
        self._state = self._raw()
        self._last_raw = self._state
        self._changed_at = time.monotonic()

    def _raw(self) -> bool:
        level = self._gpio.input(config.PIN_POWER_SWITCH)
        return bool(level) == bool(config.POWER_SWITCH_ON_LEVEL)

    def is_on(self) -> bool:
        raw = self._raw()
        now = time.monotonic()
        if raw != self._last_raw:
            self._last_raw = raw
            self._changed_at = now
        elif raw != self._state and now - self._changed_at >= config.POWER_SWITCH_DEBOUNCE_S:
            self._state = raw
        return self._state
