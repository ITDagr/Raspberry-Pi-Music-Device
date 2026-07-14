"""Stable track identity: saved state and contexts store ids (music-root-
relative paths), survive library rebuilds, prune deleted tracks, and never
keep playing a ghost."""
from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from shared import app as app_mod
from shared import config
from shared.hardware import HardwareBundle, NullHaptic, Track


def _tracks(n: int, prefix: str = "Artist") -> list[Track]:
    return [
        Track(index=i, title=f"Song {i}", artist=prefix, album="Album",
              track_no=i + 1, duration=100.0, file=f"/root/{prefix}/{i}.mp3",
              id=f"{prefix}/Album/{i:02d} Song.mp3")
        for i in range(n)
    ]


class FakeDisplay:
    level = 1.0

    def push_frame(self, s): pass
    def push_region(self, s, r): pass
    def set_backlight_level(self, level): self.level = level
    def consume_level_change(self): return False
    def set_backlight(self, on): pass
    def sleep(self): pass
    def wake(self): pass


class FakeInput:
    def read(self): return []


class FakePlayer:
    def __init__(self, tracks):
        self._tracks = tracks
        self.track = None
        self.playing = False
        self.elapsed = 0.0
        self.volume = 50
        self.track_finished = False
        self.stopped = False

    def play_track(self, index):
        self.track = self._tracks[index]
        self.playing = True
        self.stopped = False

    def toggle(self): self.playing = not self.playing
    def set_volume(self, v): self.volume = v
    def seek_to(self, s): self.elapsed = s
    def tick(self): pass

    def stop(self):
        self.track = None
        self.playing = False
        self.stopped = True


@pytest.fixture(autouse=True)
def _pygame_and_state(tmp_path, monkeypatch):
    pygame.init()
    monkeypatch.setattr(config, "STATE_PATH", str(tmp_path / "state.json"))
    yield


def _make_app(tracks):
    hw = HardwareBundle(FakeDisplay(), FakeInput(), NullHaptic(),
                        FakePlayer(tracks))
    return app_mod.App(hw, tracks, bluetooth_module=None)


def test_state_id_round_trip():
    tracks = _tracks(5)
    a = _make_app(tracks)
    a.context = [t.id for t in tracks]
    a.pos = 3
    a.player.play_track(3)
    a.player.elapsed = 42.0
    a._save_state()

    b = _make_app(_tracks(5))  # fresh app, same library
    b._restore_state()
    assert b.context == [t.id for t in tracks]
    assert b.pos == 3
    assert b.player.track.id == tracks[3].id
    assert b.player.elapsed == pytest.approx(42.0)


def test_restore_prunes_and_resolves_next_survivor():
    tracks = _tracks(5)
    a = _make_app(tracks)
    a.context = [t.id for t in tracks]
    a.pos = 2
    a.player.play_track(2)
    a._save_state()

    survivors = [tracks[0], tracks[1], tracks[4]]  # 2 and 3 deleted
    rebuilt = [Track(index=i, title=t.title, artist=t.artist, album=t.album,
                     track_no=t.track_no, duration=t.duration, file=t.file,
                     id=t.id) for i, t in enumerate(survivors)]
    b = _make_app(rebuilt)
    b._restore_state()
    assert b.context == [t.id for t in rebuilt]
    # saved now-playing (2) is gone: the next survivor in context order is 4
    assert b.player.track.id == tracks[4].id
    assert b.pos == b.context.index(tracks[4].id)


def test_restore_with_nothing_surviving_stays_stopped():
    tracks = _tracks(3)
    a = _make_app(tracks)
    a.context = [t.id for t in tracks]
    a.pos = 1
    a.player.play_track(1)
    a._save_state()

    b = _make_app(_tracks(3, prefix="Other"))  # totally different library
    b._restore_state()
    assert b.context == []
    assert b.player.track is None and not b.player.playing


def test_delete_while_playing_advances_with_toast():
    tracks = _tracks(4)
    a = _make_app(tracks)
    a.context = [t.id for t in tracks]
    a.pos = 1
    a.player.play_track(1)

    deleted_id, next_id = tracks[1].id, tracks[2].id
    survivors = [t for t in tracks if t.index != 1]
    rebuilt = [Track(index=i, title=t.title, artist=t.artist, album=t.album,
                     track_no=t.track_no, duration=t.duration, file=t.file,
                     id=t.id) for i, t in enumerate(survivors)]
    a.apply_library(rebuilt)  # note: mutates the `tracks` list in place
    assert a.player.track.id == next_id  # auto-advanced to the next survivor
    assert a.player.playing
    assert a.toast_msg  # toast fired
    assert deleted_id not in a.context


def test_delete_everything_stops_cleanly():
    tracks = _tracks(2)
    a = _make_app(tracks)
    a.context = [t.id for t in tracks]
    a.pos = 0
    a.player.play_track(0)

    a.apply_library([])
    assert a.context == []
    assert a.player.stopped and a.player.track is None
    assert a.toast_msg


def test_rebuild_preserves_navigation_path():
    tracks = _tracks(4)
    a = _make_app(tracks)
    a.ctrl.select()  # home -> music
    assert a.ctrl.current_name == "music"
    a.apply_library(_tracks(3))
    assert a.ctrl.current_name == "music"  # path survived the rebuild
