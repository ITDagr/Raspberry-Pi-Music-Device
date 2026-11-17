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
from collections import deque

from shared import config
from shared.encoder import CenterButton

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

        mask = 0
        for pin in _BUTTONS.values():
            mask |= 1 << pin

        # On a cold boot the I2C bus and the seesaw itself can need several
        # seconds to settle — until then its own hardware-ID read comes back
        # corrupt and Seesaw() raises. That's transient, not a wiring fault,
        # so keep retrying init for a generous window within this single
        # launch. Crashing instead would lean on systemd's restart, which
        # gives up permanently after StartLimitBurst crashes — the exact
        # "doesn't come back after a power cycle" failure.
        deadline = time.monotonic() + config.ENCODER_INIT_RETRY_WINDOW_S
        attempt = 0
        while True:
            attempt += 1
            try:
                self._ss = Seesaw(board.I2C(), addr=config.SEESAW_ADDR)
                self._ss.pin_mode_bulk(mask, self._ss.INPUT_PULLUP)
                self._encoder = rotaryio.IncrementalEncoder(self._ss)
                self._last_position = self._encoder.position
                if attempt > 1:
                    print(f"input: encoder init succeeded on attempt {attempt}")
                break
            except Exception as e:
                if time.monotonic() >= deadline:
                    raise
                if attempt == 1:  # one line, not one per retry
                    print(f"input: encoder not ready, retrying up to "
                          f"{config.ENCODER_INIT_RETRY_WINDOW_S:.0f}s ({e})")
                time.sleep(config.ENCODER_INIT_RETRY_DELAY_S)

        self._mask = mask

        now = time.monotonic()
        self._pressed = {name: False for name in _BUTTONS}
        self._changed_at = {name: now for name in _BUTTONS}
        self._center = CenterButton()  # shared select/hold-to-back machine
        self._warned = False
        self._delta_warned = False
        self._detent_window: deque[tuple[float, int]] = deque()
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

        # a noisy connection can trickle small-but-individually-plausible
        # deltas every single frame, forever — a magnitude check on one read
        # can't see that, so track total |detents| over a trailing window
        # regardless of per-frame size (see config.ENCODER_FAULT_MAX_DETENTS)
        self._detent_window.append((now, min(abs(delta), config.MAX_ENCODER_DELTA)))
        while (self._detent_window
               and now - self._detent_window[0][0] > config.ENCODER_FAULT_WINDOW_S):
            self._detent_window.popleft()
        recent_total = sum(count for _, count in self._detent_window)

        if abs(delta) > config.MAX_ENCODER_DELTA or recent_total > config.ENCODER_FAULT_MAX_DETENTS:
            # a real spin can't produce this many detents in one frame, or
            # this many sustained over the window — a flaky I2C read/noisy
            # connection can. Drop it rather than flood the event queue.
            if not self._delta_warned:
                print(f"input: ignoring implausible encoder activity "
                      f"(delta={delta}, {recent_total} detents/"
                      f"{config.ENCODER_FAULT_WINDOW_S:.0f}s) — "
                      "check the STEMMA QT connection")
                self._delta_warned = True
            delta = 0
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
                        self._center.press(now)
                    else:
                        events.extend(self._center.release(now))
                elif pressed:
                    events.append(name)

        # long-press select -> back, fired at the threshold while still held
        events.extend(self._center.poll(now))

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
