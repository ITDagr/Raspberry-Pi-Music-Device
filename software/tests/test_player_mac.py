"""PlayerMac under SDL dummy audio: volume clamp + finished latch."""
from __future__ import annotations

import os
import time
import wave
from array import array

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from mac.player_mac import PlayerMac
from shared.hardware import Track


def _make_track(tmp_path, seconds: float) -> Track:
    path = tmp_path / "t.wav"
    n = int(22050 * seconds)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(array("h", [0] * n).tobytes())
    return Track(index=0, title="T", artist="A", album="B", track_no=1,
                 duration=seconds, file=str(path))


@pytest.fixture
def player(tmp_path):
    return PlayerMac([_make_track(tmp_path, 0.2)])


def test_volume_clamps(player):
    player.set_volume(250)
    assert player.volume == 100
    player.set_volume(-10)
    assert player.volume == 0


def test_finished_latches_exactly_once(player):
    player.play_track(0)
    assert player.playing
    time.sleep(0.3)
    player.tick()
    assert not player.playing
    assert player.track_finished is True     # latched...
    assert player.track_finished is False    # ...and reset


def test_pause_freezes_elapsed_and_blocks_finish(player):
    player.play_track(0)
    time.sleep(0.05)
    player.toggle()                          # pause
    frozen = player.elapsed
    time.sleep(0.3)                          # well past the 0.2 s duration
    player.tick()
    assert player.elapsed == frozen
    assert player.track_finished is False    # paused tracks never "finish"
