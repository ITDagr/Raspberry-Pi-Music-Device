"""device v2 — hardware contracts shared by the Mac prototype and the Pi.

Pure typing: Protocol classes for the four hardware roles plus the Track
dataclass and the HardwareBundle handed to shared.app.run(). No hardware
imports here — implementations live in mac/ and pi/.

Input event vocabulary (InputSource.read):
    scroll_up scroll_down   wheel detents
    up down left right select   the five buttons
    back                    leave the current screen
    quit                    shut down cleanly
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Protocol

if TYPE_CHECKING:  # pygame only needed for type hints
    import pygame


@dataclass(frozen=True)
class Track:
    """One playable song. `file` is a path on Mac, an MPD URI on the Pi."""

    index: int
    title: str
    artist: str
    album: str
    track_no: int
    duration: float
    file: str


class Display(Protocol):
    def push_frame(self, surface: "pygame.Surface") -> None: ...

    def set_backlight_level(self, level: float) -> None:
        """Clamp to 0.0-1.0 and set; must raise the level_changed flag."""

    def consume_level_change(self) -> bool:
        """One-shot: True if the level changed since the last call."""

    def set_backlight(self, on: bool) -> None:
        """Convenience: level 1.0 / 0.0."""


class InputSource(Protocol):
    def read(self) -> list[str]:
        """Drain pending events; called once per frame."""


class Haptic(Protocol):
    def tick(self) -> None: ...     # scroll detent (effect 14)
    def click(self) -> None: ...    # select       (effect 1)
    def back(self) -> None: ...     # navigate back (effect 7)
    def pulse(self) -> None: ...    # boot flourish (effect 47)


class NullHaptic:
    """Haptic for boots without a DRV2605L: every effect is a silent no-op,
    so app code never needs an `if haptic:` check."""

    def tick(self) -> None: pass
    def click(self) -> None: pass
    def back(self) -> None: pass
    def pulse(self) -> None: pass


class Player(Protocol):
    def play_track(self, index: int) -> None: ...
    def toggle(self) -> None: ...
    def set_volume(self, v: int) -> None: ...
    def seek_to(self, seconds: float) -> None: ...

    def tick(self) -> None:
        """Call every frame; does throttled polling/bookkeeping."""

    @property
    def volume(self) -> int: ...
    @property
    def playing(self) -> bool: ...
    @property
    def elapsed(self) -> float: ...
    @property
    def track(self) -> Optional[Track]: ...

    @property
    def track_finished(self) -> bool:
        """Latches True exactly once when a track ends naturally, then resets."""


@dataclass
class HardwareBundle:
    display: Display
    input: InputSource
    haptic: Haptic
    player: Player
