"""device v2 — Pi LibraryStore: the files are the truth, MPD reads them.

Uploads and retags write real tags into the files with mutagen, then ask
MPD to rescan; list_tracks() is library_mpd.load_tracks(), so the web app
and the device UI always agree with MPD's database.
"""
from __future__ import annotations

import time
from pathlib import Path

from shared import config
from shared.hardware import Track
from shared.webapp.store import BaseLibraryStore, read_tags


class PiLibraryStore(BaseLibraryStore):
    # --- target hooks ------------------------------------------------------------
    def list_tracks(self) -> list[Track]:
        from pi import library_mpd

        return library_mpd.load_tracks()

    def _get_meta(self, tid: str) -> dict:
        return read_tags(self.root / tid)

    def _write_tags(self, path: Path, meta: dict) -> None:
        try:
            import mutagen

            m = mutagen.File(str(path), easy=True)
            if m is None or m.tags is None and not hasattr(m, "add_tags"):
                return
            if m.tags is None:
                m.add_tags()
            m["title"] = meta["title"]
            m["artist"] = meta["artist"]
            m["album"] = meta["album"]
            if int(meta.get("track_no") or 0) > 0:
                m["tracknumber"] = str(meta["track_no"])
            m.save()
        except Exception as e:  # tagless formats: the filename still carries it
            print(f"store: could not write tags ({e})")

    def _refresh(self) -> None:
        """`mpd update` and wait (bounded) for the rescan to finish, so the
        track list handed back to the UI already includes the change."""
        try:
            from mpd import MPDClient

            client = MPDClient()
            client.timeout = 5
            client.connect(config.MPD_HOST, config.MPD_PORT)
            client.update()
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if "updating_db" not in client.status():
                    break
                time.sleep(0.2)
            client.close()
            client.disconnect()
        except Exception as e:
            print(f"store: mpd update failed ({e})")
