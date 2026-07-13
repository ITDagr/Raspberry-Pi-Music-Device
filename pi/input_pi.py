"""device v2 — Adafruit ANO rotary encoder + 5 buttons via seesaw I2C,
plus the Beret's two tactile buttons on GPIO.

Encoder detents become scroll_up/scroll_down (one event per detent, CW =
scroll_down unless config.ENCODER_REVERSED). Buttons are active-low with
internal pull-ups, edge-detected with a ~5 ms debounce. Holding select for
>= 600 ms fires "back" at the threshold and suppresses the release's select
— the physical stand-in for the Mac's Backspace.

Beret buttons (GPIO 5/6): mapped through config.BERET_BUTTONS to events
from the standard vocabulary, or None (default) for no behavior. GPIO is
only claimed for mapped buttons.
"""
from __future__ import annotations

import time

from shared import config

_BUTTONS = {
    "select": config.SEESAW_BTN_SELECT,
    "up": config.SEESAW_BTN_UP,
    "left": config.SEESAW_BTN_LEFT,
    "down": config.SEESAW_BTN_DOWN,
    "right": config.SEESAW_BTN_RIGHT,
}


class ANOInput:
    def __init__(self) -> None:
        import board
        from adafruit_seesaw import rotaryio
        from adafruit_seesaw.seesaw import Seesaw

        self._ss = Seesaw(board.I2C(), addr=config.SEESAW_ADDR)
        self._mask = 0
        for pin in _BUTTONS.values():
            self._mask |= 1 << pin
        self._ss.pin_mode_bulk(self._mask, self._ss.INPUT_PULLUP)
        self._encoder = rotaryio.IncrementalEncoder(self._ss)
        self._last_position = self._encoder.position

        now = time.monotonic()
        self._pressed = {name: False for name in _BUTTONS}
        self._changed_at = {name: now for name in _BUTTONS}
        self._select_down_at = 0.0
        self._select_hold_fired = False
        self._warned = False
        self.quit_requested = False

        # Beret tactile buttons: claim GPIO only for pins mapped to an event
        self._beret = {pin: ev for pin, ev in config.BERET_BUTTONS.items() if ev}
        self._beret_pressed = {pin: False for pin in self._beret}
        self._beret_changed_at = {pin: now for pin in self._beret}
        if self._beret:
            import RPi.GPIO as GPIO

            self._beret_gpio = GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            for pin in self._beret:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def read(self) -> list[str]:
        try:
            return self._read()
        except Exception as e:  # flaky I2C must not kill the UI
            if not self._warned:
                print(f"input: read failed ({e})")
                self._warned = True
            return []

    def _read(self) -> list[str]:
        events: list[str] = []
        now = time.monotonic()

        # encoder: one event per detent since the last frame
        position = self._encoder.position
        delta = position - self._last_position
        self._last_position = position
        if config.ENCODER_REVERSED:
            delta = -delta
        if delta > 0:
            events.extend(["scroll_down"] * delta)
        elif delta < 0:
            events.extend(["scroll_up"] * -delta)

        # buttons: active-low, debounced edges
        bulk = self._ss.digital_read_bulk(self._mask)
        for name, pin in _BUTTONS.items():
            pressed = not (bulk & (1 << pin))
            if pressed != self._pressed[name]:
                if now - self._changed_at[name] < config.DEBOUNCE_S:
                    continue  # bounce
                self._pressed[name] = pressed
                self._changed_at[name] = now
                if name == "select":
                    if pressed:
                        self._select_down_at = now
                        self._select_hold_fired = False
                    elif not self._select_hold_fired:
                        events.append("select")  # short press fires on release
                elif pressed:
                    events.append(name)

        # long-press select -> back, fired at the threshold while still held
        if (self._pressed["select"] and not self._select_hold_fired
                and now - self._select_down_at >= config.BACK_HOLD_S):
            self._select_hold_fired = True
            events.append("back")

        # Beret tactile buttons: active-low, debounced edges, fire on press
        for pin, ev in self._beret.items():
            pressed = not self._beret_gpio.input(pin)
            if pressed != self._beret_pressed[pin]:
                if now - self._beret_changed_at[pin] < config.DEBOUNCE_S:
                    continue  # bounce
                self._beret_pressed[pin] = pressed
                self._beret_changed_at[pin] = now
                if pressed:
                    events.append(ev)

        return events
