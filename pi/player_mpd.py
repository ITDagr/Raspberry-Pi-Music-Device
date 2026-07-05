"""device v2 — PlayerState on MPD (python-mpd2) with auto-reconnect.

tick() polls status() at most 5 Hz and caches; elapsed interpolates between
polls. A natural track end shows up as a play -> stop transition (we always
queue exactly one song), which latches track_finished once. Every MPD command
retries once through a reconnect, and failures log once instead of crashing.
"""
from __future__ import annotations

import time
from typing import Optional

from shared import config
from shared.hardware import Track


class PlayerMPD:
    def __init__(self, tracks: list[Track]):
        self._tracks = tracks
        self._client = None
        self._track: Optional[Track] = None
        self._volume = config.DEFAULT_VOLUME
        self._playing = False
        self._elapsed = 0.0
        self._elapsed_at = time.monotonic()
        self._last_state = "stop"
        self._finished = False
        self._last_poll = 0.0
        self._warned = False

    # --- connection -----------------------------------------------------------
    def _connect(self):
        from mpd import MPDClient

        client = MPDClient()
        client.timeout = 2
        client.connect(config.MPD_HOST, config.MPD_PORT)
        return client

    def _cmd(self, name: str, *args):
        """Run an MPD command, reconnecting once on failure. None on error."""
        for attempt in (0, 1):
            try:
                if self._client is None:
                    self._client = self._connect()
                return getattr(self._client, name)(*args)
            except Exception as e:
                self._client = None
                if attempt == 1:
                    if not self._warned:
                        print(f"mpd: {name} failed ({e})")
                        self._warned = True
        return None

    # --- controls ---------------------------------------------------------------
    def play_track(self, index: int) -> None:
        self._track = self._tracks[index]
        self._cmd("clear")
        self._cmd("add", self._track.file)
        self._cmd("setvol", self._volume)
        self._cmd("play", 0)
        self._playing = True
        self._elapsed = 0.0
        self._elapsed_at = time.monotonic()
        self._last_state = "play"
        self._finished = False

    def toggle(self) -> None:
        if self._track is None:
            return
        if self._playing:
            self._cmd("pause", 1)
            self._elapsed = self.elapsed
            self._playing = False
            self._last_state = "pause"
        else:
            self._cmd("pause", 0)
            self._elapsed_at = time.monotonic()
            self._playing = True
            self._last_state = "play"

    def set_volume(self, v: int) -> None:
        self._volume = max(0, min(100, int(v)))
        self._cmd("setvol", self._volume)

    def seek_to(self, seconds: float) -> None:
        if self._track is None:
            return
        seconds = max(0.0, min(float(seconds), self._track.duration))
        self._cmd("seekcur", seconds)
        self._elapsed = seconds
        self._elapsed_at = time.monotonic()

    def tick(self) -> None:
        now = time.monotonic()
        if now - self._last_poll < config.MPD_POLL_S:
            return
        self._last_poll = now
        status = self._cmd("status")
        if not status:
            return
        state = status.get("state", "stop")
        self._elapsed = float(status.get("elapsed", 0.0) or 0.0)
        self._elapsed_at = now
        if self._last_state == "play" and state == "stop" and self._track:
            self._finished = True  # our single-song queue ran out naturally
            self._elapsed = self._track.duration
        self._playing = state == "play"
        self._last_state = state

    # --- state --------------------------------------------------------------------
    @property
    def volume(self) -> int:
        return self._volume

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def elapsed(self) -> float:
        if self._playing:
            return self._elapsed + (time.monotonic() - self._elapsed_at)
        return self._elapsed

    @property
    def track(self) -> Optional[Track]:
        return self._track

    @property
    def track_finished(self) -> bool:
        finished, self._finished = self._finished, False
        return finished
