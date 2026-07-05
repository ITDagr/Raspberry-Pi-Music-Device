"""device v2 — JSON persistence for playback/UI state.

Schema: {context: [int], pos: int, shuffle: bool, track_index: int,
         elapsed: float, volume: int, brightness: int}

Writes are atomic (tmp file + os.replace). load() tolerates missing or
corrupt files by returning None.
"""
from __future__ import annotations

import json
import os

from shared import config

_warned = False


def save(data: dict, path: str = None) -> None:
    """Atomically write `data` as JSON. Failures log once and are ignored."""
    global _warned
    path = path or config.STATE_PATH
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)  # atomic on POSIX
    except OSError as e:
        if not _warned:
            print(f"state: could not save ({e})")
            _warned = True


def load(path: str = None) -> dict | None:
    """Read saved state; None if missing, unreadable, or not a JSON object."""
    path = path or config.STATE_PATH
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
