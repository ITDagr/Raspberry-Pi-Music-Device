"""pizero-llm-demo — Adafruit ANO rotary encoder + 5 buttons over seesaw I2C.

Adapted from pimusicdevicev2's pi/input_pi.py, including both hard-won
resilience features, because the underlying hardware fault is the same:

  * a per-frame delta clamp AND a trailing-window detent-rate breaker, so a
    marginal STEMMA QT connection cannot flood the event queue and wedge the UI
  * a patient init retry, because on a cold boot the seesaw's own hardware-ID
    read comes back corrupt for several seconds. Crashing here would lean on
    systemd's restart limit and produce the "never comes back after a power
    cycle" failure.

Event vocabulary: scroll_up, scroll_down, select, back, up, down, left, right.
A short centre press fires `select` on release; holding it past BACK_HOLD_S
fires `back` once at the threshold and swallows the release.
"""
from __future__ import annotations

import time
from collections import deque

from app import config

_BUTTONS = {
    "select": config.SEESAW_BTN_SELECT,
    "up": config.SEESAW_BTN_UP,
    "left": config.SEESAW_BTN_LEFT,
    "down": config.SEESAW_BTN_DOWN,
    "right": config.SEESAW_BTN_RIGHT,
}


class _CenterButton:
    """Short press -> select on release; hold -> back at the threshold."""

    def __init__(self) -> None:
        self._down_at: float | None = None
        self._hold_fired = False

    def press(self, now: float) -> None:
        if self._down_at is None:
            self._down_at = now
            self._hold_fired = False

    def release(self, now: float) -> list[str]:
        if self._down_at is None:
            return []
        fired = self._hold_fired
        self._down_at = None
        self._hold_fired = False
        return [] if fired else ["select"]

    def poll(self, now: float) -> list[str]:
        if (self._down_at is not None and not self._hold_fired
                and now - self._down_at >= config.BACK_HOLD_S):
            self._hold_fired = True
            return ["back"]
        return []


class ANOInput:
    def __init__(self) -> None:
        import board
        from adafruit_seesaw import rotaryio
        from adafruit_seesaw.seesaw import Seesaw

        mask = 0
        for pin in _BUTTONS.values():
            mask |= 1 << pin

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
            except Exception as exc:
                if time.monotonic() >= deadline:
                    raise
                if attempt == 1:  # one line, not one per retry
                    print(f"input: encoder not ready, retrying up to "
                          f"{config.ENCODER_INIT_RETRY_WINDOW_S:.0f}s ({exc})")
                time.sleep(config.ENCODER_INIT_RETRY_DELAY_S)

        self._mask = mask
        # Measured on this board: the first position read after init reliably
        # comes back as 0xFFFFFF rather than a real count, which the rate
        # breaker then has to absorb on every single boot. Swallow one read
        # instead, so a genuine fault is the only thing that ever trips it.
        self._primed = False
        now = time.monotonic()
        self._pressed = {name: False for name in _BUTTONS}
        self._changed_at = {name: now for name in _BUTTONS}
        self._center = _CenterButton()
        self._warned = False
        self._delta_warned = False
        self._detent_window: deque[tuple[float, int]] = deque()

    def read(self) -> list[str]:
        try:
            return self._read()
        except Exception as exc:  # flaky I2C must not kill the UI
            if not self._warned:
                print(f"input: read failed ({exc})")
                self._warned = True
            return []

    def _read(self) -> list[str]:
        events: list[str] = []
        now = time.monotonic()

        position = self._encoder.position
        delta = position - self._last_position
        self._last_position = position
        if not self._primed:
            self._primed = True
            delta = 0   # resync on the first read; emit nothing

        # A noisy connection can trickle small-but-individually-plausible
        # deltas every frame forever, which a per-read magnitude check cannot
        # see. Track total detents over a trailing window as well.
        self._detent_window.append((now, min(abs(delta), config.MAX_ENCODER_DELTA)))
        while (self._detent_window
               and now - self._detent_window[0][0] > config.ENCODER_FAULT_WINDOW_S):
            self._detent_window.popleft()
        recent = sum(n for _, n in self._detent_window)

        if abs(delta) > config.MAX_ENCODER_DELTA \
                or recent > config.ENCODER_FAULT_MAX_DETENTS:
            if not self._delta_warned:
                print(f"input: ignoring implausible encoder activity "
                      f"(delta={delta}, {recent} detents/"
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

        events.extend(self._center.poll(now))
        return events
