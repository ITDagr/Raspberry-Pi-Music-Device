"""device v2 — build TRACKS from the MPD database.

listallinfo, sorted by (artist, album, track_no) with stable indices. Missing
tags degrade to filename/"Unknown". If MPD is unreachable the library is
empty and the UI still runs.
"""
from __future__ import annotations

import os

from shared import config
from shared.hardware import Track


def _track_no(raw) -> int:
    try:
        return int(str(raw).split("/")[0])  # tags like "3/12"
    except (TypeError, ValueError):
        return 0


def load_tracks() -> list[Track]:
    try:
        from mpd import MPDClient

        client = MPDClient()
        client.timeout = 5
        client.connect(config.MPD_HOST, config.MPD_PORT)
        entries = [e for e in client.listallinfo() if "file" in e]
        client.close()
        client.disconnect()
    except Exception as e:
        print(f"library: MPD unavailable ({e}) — empty library")
        return []

    rows = []
    for e in entries:
        name = os.path.splitext(os.path.basename(e["file"]))[0]
        rows.append({
            "title": e.get("title") or name,
            "artist": e.get("artist") or "Unknown Artist",
            "album": e.get("album") or "Unknown Album",
            "track_no": _track_no(e.get("track")),
            "duration": float(e.get("duration") or e.get("time") or 0.0),
            "file": e["file"],
        })
    rows.sort(key=lambda r: (r["artist"].lower(), r["album"].lower(),
                             r["track_no"], r["title"].lower()))
    return [Track(index=i, **row) for i, row in enumerate(rows)]
