"""device v2 — the playlist manifest: {name: [track ids…]}.

One JSON file at config.PLAYLISTS_PATH, written atomically. The device's
copy is the single source of truth; the web app edits it only through
these functions (via the API). Track membership is by stable id, so
library rebuilds never corrupt a playlist — deleted tracks are pruned,
retagged tracks are remapped.
"""
from __future__ import annotations

import json
import os
import threading

from shared import config

_lock = threading.Lock()


def _load_unlocked() -> dict[str, list[str]]:
    try:
        with open(config.PLAYLISTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): [t for t in v if isinstance(t, str)]
            for k, v in data.items() if isinstance(v, list)}


def _save_unlocked(data: dict[str, list[str]]) -> None:
    tmp = config.PLAYLISTS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, config.PLAYLISTS_PATH)  # atomic on POSIX


def load() -> dict[str, list[str]]:
    with _lock:
        return _load_unlocked()


def create(name: str) -> bool:
    """False if the name is empty or already taken."""
    name = name.strip()
    if not name:
        return False
    with _lock:
        data = _load_unlocked()
        if name in data:
            return False
        data[name] = []
        _save_unlocked(data)
        return True


def rename(old: str, new: str) -> bool:
    new = new.strip()
    with _lock:
        data = _load_unlocked()
        if old not in data or not new or new in data:
            return False
        data = {new if k == old else k: v for k, v in data.items()}
        _save_unlocked(data)
        return True


def delete(name: str) -> bool:
    with _lock:
        data = _load_unlocked()
        if name not in data:
            return False
        del data[name]
        _save_unlocked(data)
        return True


def set_tracks(name: str, ids: list[str]) -> bool:
    """Replace a playlist's contents — this is how reorder, add and remove
    all arrive from the web app."""
    with _lock:
        data = _load_unlocked()
        if name not in data:
            return False
        data[name] = [t for t in ids if isinstance(t, str)]
        _save_unlocked(data)
        return True


def prune(alive: set[str]) -> bool:
    """Drop ids that no longer exist in the library. True if anything changed."""
    with _lock:
        data = _load_unlocked()
        pruned = {k: [t for t in v if t in alive] for k, v in data.items()}
        if pruned != data:
            _save_unlocked(pruned)
            return True
        return False


def remap(old_id: str, new_id: str) -> bool:
    """A retag moved a file: keep playlist membership pointing at it."""
    with _lock:
        data = _load_unlocked()
        remapped = {k: [new_id if t == old_id else t for t in v]
                    for k, v in data.items()}
        if remapped != data:
            _save_unlocked(remapped)
            return True
        return False
