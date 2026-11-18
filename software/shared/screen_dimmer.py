"""device v2 — idle screen dimmer.

Daemon thread walking AWAKE -> DIM (20 s, level 0.15) -> SLEEP (60 s, level
0.0). All level changes go through the injected set_level callback: on Mac
that darkens the window, on the Pi it drives the backlight PWM. Every
transition calls log(msg). consume_wake() is a one-shot flag so the main loop
can force a redraw after the screen wakes.
"""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Callable

from shared import config


class DimState(Enum):
    AWAKE = "awake"
    DIM = "dim"
    SLEEP = "sleep"


class ScreenDimmer:
    def __init__(self, set_level: Callable[[float], None], log: Callable[[str], None] = print):
        self._set_level = set_level
        self._log = log
        self._lock = threading.Lock()
        self._state = DimState.AWAKE
        self._last_activity = time.monotonic()
        self._wake_level = config.WAKE_LEVEL
        self._woke = False
        self._suspended = False

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="dimmer").start()

    def _run(self) -> None:
        while True:
            time.sleep(0.25)
            with self._lock:
                if self._suspended:
                    continue
                idle = time.monotonic() - self._last_activity
                if self._state is DimState.AWAKE and idle >= config.DIM_AFTER_S:
                    self._state = DimState.DIM
                    self._set_level(config.DIM_LEVEL)
                    self._log(f"dim after {config.DIM_AFTER_S:.0f}s idle")
                elif self._state is DimState.DIM and idle >= config.SLEEP_AFTER_S:
                    self._state = DimState.SLEEP
                    self._set_level(0.0)
                    self._log(f"sleep after {config.SLEEP_AFTER_S:.0f}s idle")

    def wake(self) -> None:
        """Reset the idle timer and restore the awake brightness."""
        with self._lock:
            self._last_activity = time.monotonic()
            if self._state is not DimState.AWAKE:
                self._state = DimState.AWAKE
                self._woke = True
                self._log("wake")
            self._set_level(self._wake_level)

    def set_wake_level(self, level: float) -> None:
        """Set awake brightness (0.1-1.0); applies immediately if awake."""
        with self._lock:
            self._wake_level = max(0.1, min(1.0, float(level)))
            if self._state is DimState.AWAKE:
                self._set_level(self._wake_level)

    def suspend(self) -> None:
        """Soft-off: stop walking the DIM/SLEEP ladder; the level is owned
        by whoever suspended us until resume()."""
        with self._lock:
            self._suspended = True

    def resume(self) -> None:
        """Back from soft-off: awake at the stored brightness, timer reset."""
        with self._lock:
            self._suspended = False
            self._last_activity = time.monotonic()
            self._state = DimState.AWAKE
            self._set_level(self._wake_level)

    def consume_wake(self) -> bool:
        """One-shot: True once after a DIM/SLEEP -> AWAKE transition."""
        with self._lock:
            woke, self._woke = self._woke, False
            return woke

    @property
    def state(self) -> DimState:
        return self._state

    @property
    def wake_level(self) -> float:
        return self._wake_level
