"""device v2 — Mac LibraryStore: filesystem + a JSON metadata registry.

The synthetic catalog's WAVs carry no tags (their metadata lives in
library_mac's generated catalog), so the Mac store keeps one registry —
`<music_root>/.library.json`, {id: {title, artist, album, track_no,
duration}} — as the source of truth for every track's tags. It is seeded
from the catalog on first run, uploads insert mutagen-read tags, retags
edit it in place, and files that appear out of band (scp, Finder) are
adopted with tag fallbacks on the next listing.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from shared.hardware import Track, track_id
from shared.webapp.store import BaseLibraryStore, read_tags


class MacLibraryStore(BaseLibraryStore):
    def __init__(self, root: str = None, seed: list[Track] = None):
        super().__init__(root)
        self._registry_path = self.root / ".library.json"
        self._registry: dict[str, dict] = self._load_registry()
        if not self._registry and seed:
            for t in seed:
                self._registry[t.id] = {
                    "title": t.title, "artist": t.artist, "album": t.album,
                    "track_no": t.track_no, "duration": t.duration,
                }
            self._save_registry()
        self._adopt_and_prune()

    # --- registry ---------------------------------------------------------------
    def _load_registry(self) -> dict:
        try:
            with open(self._registry_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_registry(self) -> None:
        tmp = str(self._registry_path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._registry, f, indent=1)
        os.replace(tmp, self._registry_path)

    def _adopt_and_prune(self) -> None:
        """Registry <-> filesystem sync: adopt out-of-band files with tag
        fallbacks, drop entries whose file vanished."""
        on_disk = {track_id(str(p.relative_to(self.root)))
                   for p in self.audio_files()}
        changed = False
        for tid in on_disk - self._registry.keys():
            self._registry[tid] = read_tags(self.root / tid)
            changed = True
        for tid in list(self._registry.keys() - on_disk):
            del self._registry[tid]
            changed = True
        if changed:
            self._save_registry()

    # --- target hooks ------------------------------------------------------------
    def list_tracks(self) -> list[Track]:
        rows = sorted(
            self._registry.items(),
            key=lambda kv: (kv[1]["artist"].lower(), kv[1]["album"].lower(),
                            kv[1]["track_no"], kv[1]["title"].lower()),
        )
        return [
            Track(index=i, title=m["title"], artist=m["artist"],
                  album=m["album"], track_no=int(m["track_no"]),
                  duration=float(m["duration"]), file=str(self.root / tid),
                  id=tid)
            for i, (tid, m) in enumerate(rows)
        ]

    def _get_meta(self, tid: str) -> dict:
        meta = self._registry.get(tid)
        if meta is None:
            meta = read_tags(self.root / tid)
        return dict(meta)

    def _on_added(self, tid: str, meta: dict) -> None:
        self._registry[tid] = {k: meta[k] for k in
                               ("title", "artist", "album", "track_no",
                                "duration")}
        self._save_registry()

    def _on_removed(self, tid: str) -> None:
        self._registry.pop(tid, None)
        self._save_registry()

    def _on_retagged(self, old_id: str, new_id: str, meta: dict) -> None:
        entry = self._registry.pop(old_id, {})
        entry.update({k: meta[k] for k in
                      ("title", "artist", "album", "track_no")})
        entry.setdefault("duration", meta.get("duration", 0.0))
        self._registry[new_id] = entry
        self._save_registry()

    # _write_tags: no-op — WAVs don't tag well and the registry is the
    # Mac's source of truth. _refresh: no-op — the registry IS the library.
