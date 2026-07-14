"""device v2 — PlayerState on pygame.mixer.music.

Elapsed time is pure monotonic bookkeeping (start time + pause accumulation);
mixer.get_pos() is never trusted across pause/seek. pygame can't seek WAVs,
so seek_to restarts the audio and moves the bookkeeping — the progress display
stays correct even though the synth audio restarts. Track finish is latched
from bookkeeping (elapsed >= duration while unpaused), which also works under
SDL_AUDIODRIVER=dummy.
"""
from __future__ import annotations

import time
from typing import Optional

import pygame

from shared import config
from shared.hardware import Track


class PlayerMac:
    def __init__(self, tracks: list[Track]):
        self._tracks = tracks
        self._audio_ok = True
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except pygame.error as e:
            print(f"player: no audio device, running silent ({e})")
            self._audio_ok = False
        self._track: Optional[Track] = None
        self._volume = config.DEFAULT_VOLUME
        self._playing = False
        self._base = 0.0          # elapsed accumulated up to the last un/pause
        self._started_at = 0.0    # monotonic when playback (re)started
        self._finished = False

    # --- controls ---------------------------------------------------------------
    def play_track(self, index: int) -> None:
        self._track = self._tracks[index]
        if self._audio_ok:
            try:
                pygame.mixer.music.load(self._track.file)
                pygame.mixer.music.set_volume(self._volume / 100)
                pygame.mixer.music.play()
            except pygame.error as e:
                print(f"player: could not play {self._track.file} ({e})")
        self._base = 0.0
        self._started_at = time.monotonic()
        self._playing = True
        self._finished = False

    def toggle(self) -> None:
        if self._track is None:
            return
        if self._playing:
            self._base = self.elapsed
            self._playing = False
            if self._audio_ok:
                pygame.mixer.music.pause()
        elif self._base >= self._track.duration:
            self.play_track(self._track.index)  # ended: restart from the top
        else:
            self._started_at = time.monotonic()
            self._playing = True
            if self._audio_ok:
                pygame.mixer.music.unpause()

    def set_volume(self, v: int) -> None:
        self._volume = max(0, min(100, int(v)))
        if self._audio_ok:
            pygame.mixer.music.set_volume(self._volume / 100)

    def seek_to(self, seconds: float) -> None:
        if self._track is None:
            return
        seconds = max(0.0, min(float(seconds), self._track.duration))
        if self._audio_ok:
            try:
                pygame.mixer.music.play(start=seconds)
            except pygame.error:
                # WAVs can't seek: restart the audio, keep the bookkeeping
                try:
                    pygame.mixer.music.play()
                except pygame.error:
                    pass
        self._base = seconds
        self._started_at = time.monotonic()
        self._playing = True
        self._finished = False

    def stop(self) -> None:
        """Hard stop: the current file vanished (deleted via the web app)."""
        if self._audio_ok:
            try:
                pygame.mixer.music.stop()
            except pygame.error:
                pass
        self._track = None
        self._playing = False
        self._base = 0.0
        self._finished = False

    def tick(self) -> None:
        if self._playing and self._track and self.elapsed >= self._track.duration:
            self._playing = False
            self._base = self._track.duration
            self._finished = True
            if self._audio_ok:
                pygame.mixer.music.stop()

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
            return self._base + (time.monotonic() - self._started_at)
        return self._base

    @property
    def track(self) -> Optional[Track]:
        return self._track

    @property
    def track_finished(self) -> bool:
        finished, self._finished = self._finished, False
        return finished
