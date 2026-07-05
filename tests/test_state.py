"""Persistence: round-trip, atomicity, corrupt-file tolerance."""
from __future__ import annotations

import json
import os

from shared import state

SAMPLE = {"context": [0, 1, 2], "pos": 1, "shuffle": False, "track_index": 1,
          "elapsed": 12.5, "volume": 60, "brightness": 70}


def test_round_trip(tmp_path):
    path = str(tmp_path / "state.json")
    state.save(SAMPLE, path)
    assert state.load(path) == SAMPLE


def test_atomic_no_tmp_left_behind(tmp_path):
    path = str(tmp_path / "state.json")
    state.save(SAMPLE, path)
    state.save({**SAMPLE, "pos": 2}, path)   # overwrite works
    assert state.load(path)["pos"] == 2
    assert not os.path.exists(path + ".tmp")


def test_missing_file_returns_none(tmp_path):
    assert state.load(str(tmp_path / "nope.json")) is None


def test_corrupt_file_returns_none(tmp_path):
    path = str(tmp_path / "state.json")
    with open(path, "w") as f:
        f.write("{not json at all")
    assert state.load(path) is None


def test_non_dict_json_returns_none(tmp_path):
    path = str(tmp_path / "state.json")
    with open(path, "w") as f:
        json.dump([1, 2, 3], f)
    assert state.load(path) is None
