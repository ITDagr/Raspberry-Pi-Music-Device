"""device v2 — LibraryStore: every web-app mutation flows through here.

Filesystem layout under config.MUSIC_ROOT (uploads and retags enforce it;
files loaded by scp/SD-copy may live anywhere below the root):

    <Artist>/<Album>/<NN Title>.<ext>
    .incoming/     upload temp files
    .trash/        deleted tracks (purged after config.TRASH_KEEP_DAYS)

BaseLibraryStore owns the shared flows (upload pipeline, delete-to-trash,
retag-with-move); the targets fill in listing and tag persistence:
MacLibraryStore (mac/store_mac.py) keeps a JSON registry, PiLibraryStore
(pi/store_pi.py) lets file tags + MPD be the truth. All mutations are
serialized by one lock — Flask serves threaded.
"""
from __future__ import annotations

import re
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

from shared import config
from shared.hardware import Track, track_id

AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".ogg", ".wav"}
_HIDDEN_DIRS = {".incoming", ".trash"}


class StoreError(Exception):
    """A mutation the client can be told about: (http_status, message)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def sanitize(part: str) -> str:
    """One safe path component from a tag value."""
    part = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", str(part)).strip(" .")
    return part[:80] or "Unknown"


def read_tags(path: Path) -> dict:
    """Best-effort tags via mutagen: title/artist/album/track_no/duration,
    with the spec'd fallbacks (filename -> title, Unknown Artist/Album)."""
    title = path.stem
    artist, album, track_no, duration = "Unknown Artist", "Unknown Album", 0, 0.0
    try:
        import mutagen

        m = mutagen.File(str(path), easy=True)
        if m is not None:
            if m.info is not None:
                duration = float(getattr(m.info, "length", 0.0) or 0.0)
            tags = m.tags or {}

            def first(key: str) -> Optional[str]:
                v = tags.get(key)
                return str(v[0]).strip() if v else None

            title = first("title") or title
            artist = first("artist") or artist
            album = first("album") or album
            raw_no = first("tracknumber") or ""
            try:
                track_no = int(raw_no.split("/")[0])
            except (ValueError, AttributeError):
                track_no = 0
    except Exception:
        pass  # unreadable tags are exactly what the fallbacks are for
    return {"title": title, "artist": artist, "album": album,
            "track_no": track_no, "duration": duration}


def dest_relpath(meta: dict, ext: str) -> str:
    """`<Artist>/<Album>/<NN Title>.<ext>` — the library's one layout."""
    no = int(meta.get("track_no") or 0)
    stem = sanitize(meta["title"])
    if no > 0:
        stem = f"{no:02d} {stem}"
    return f"{sanitize(meta['artist'])}/{sanitize(meta['album'])}/{stem}{ext}"


class BaseLibraryStore:
    def __init__(self, root: str = None):
        self.root = Path(root or config.MUSIC_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ".incoming").mkdir(exist_ok=True)
        (self.root / ".trash").mkdir(exist_ok=True)
        self._lock = threading.Lock()
        self.purge_trash()

    # --- target hooks -----------------------------------------------------------
    def list_tracks(self) -> list[Track]:
        raise NotImplementedError

    def _get_meta(self, tid: str) -> dict:
        """Current tags for an existing track."""
        raise NotImplementedError

    def _on_added(self, tid: str, meta: dict) -> None: ...
    def _on_removed(self, tid: str) -> None: ...
    def _on_retagged(self, old_id: str, new_id: str, meta: dict) -> None: ...

    def _write_tags(self, path: Path, meta: dict) -> None:
        """Persist tags into the file itself (Pi: MPD reads them; Mac: the
        registry is the truth and this may no-op)."""

    def _refresh(self) -> None:
        """Make the backing library notice filesystem changes (Pi: mpd
        update; Mac: no-op — the registry was updated directly)."""

    # --- helpers ------------------------------------------------------------------
    def _path_of(self, tid: str) -> Path:
        clean = track_id(tid)
        if not clean or clean.startswith("..") or "/../" in f"/{clean}/":
            raise StoreError(400, f"bad track id: {tid!r}")
        path = self.root / clean
        if not path.is_file():
            raise StoreError(404, f"no such track: {clean}")
        return path

    def title_of(self, tid: str) -> str:
        for t in self.list_tracks():
            if t.id == tid:
                return t.title
        return tid.rsplit("/", 1)[-1]

    # --- shared flows ---------------------------------------------------------------
    def add_upload(self, tmp_path: Path, original_name: str,
                   replace: bool = False) -> dict:
        """The upload pipeline: temp file -> checks -> tags -> sanitized
        <Artist>/<Album>/<NN Title>.<ext> home -> registration."""
        ext = Path(original_name).suffix.lower()
        if ext not in AUDIO_EXTS:
            tmp_path.unlink(missing_ok=True)
            raise StoreError(
                400, f"unsupported type {ext or '(none)'} — "
                     f"accepted: {' '.join(sorted(AUDIO_EXTS))}")
        if tmp_path.stat().st_size == 0:
            tmp_path.unlink(missing_ok=True)
            raise StoreError(400, "empty file")
        meta = read_tags(tmp_path)
        if meta["title"] == tmp_path.stem:  # tmp name is meaningless
            meta["title"] = Path(original_name).stem
        with self._lock:
            rel = dest_relpath(meta, ext)
            dest = self.root / rel
            if dest.exists() and not replace:
                tmp_path.unlink(missing_ok=True)
                raise StoreError(
                    409, f"'{rel}' already exists — re-send with replace=1 "
                         "to overwrite")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp_path), dest)
            self._write_tags(dest, meta)
            tid = track_id(rel)
            self._on_added(tid, meta)
        self._refresh()
        return {"id": tid, **meta}

    def delete(self, tid: str) -> None:
        """To .trash/, never a hard delete; purged after TRASH_KEEP_DAYS."""
        with self._lock:
            path = self._path_of(tid)
            mangled = f"{int(time.time())}_{track_id(tid).replace('/', '__')}"
            shutil.move(str(path), self.root / ".trash" / mangled)
            self._prune_empty_dirs(path.parent)
            self._on_removed(track_id(tid))
        self._refresh()

    def retag(self, tid: str, changes: dict) -> dict:
        """Edit tags; artist/album/track-number changes move the file to its
        new home (organization IS the tags). Returns meta incl. the new id."""
        tid = track_id(tid)
        with self._lock:
            path = self._path_of(tid)
            meta = self._get_meta(tid)
            for key in ("title", "artist", "album"):
                if key in changes and str(changes[key]).strip():
                    meta[key] = str(changes[key]).strip()
            if "track_no" in changes:
                try:
                    meta["track_no"] = max(0, int(changes["track_no"]))
                except (TypeError, ValueError):
                    raise StoreError(400, "track_no must be a number")
            new_rel = dest_relpath(meta, path.suffix.lower())
            new_id = track_id(new_rel)
            if new_id != tid:
                dest = self.root / new_rel
                if dest.exists():
                    raise StoreError(409, f"'{new_rel}' already exists")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), dest)
                self._prune_empty_dirs(path.parent)
                path = dest
            self._write_tags(path, meta)
            self._on_retagged(tid, new_id, meta)
        self._refresh()
        return {"id": new_id, "old_id": tid, **meta}

    def _prune_empty_dirs(self, folder: Path) -> None:
        """Remove now-empty Artist/Album dirs a move/delete left behind."""
        while folder != self.root and folder.is_dir():
            try:
                folder.rmdir()  # fails (correctly) unless empty
            except OSError:
                break
            folder = folder.parent

    def purge_trash(self, keep_days: int = None) -> None:
        keep = (config.TRASH_KEEP_DAYS if keep_days is None else keep_days)
        cutoff = time.time() - keep * 86400
        trash = self.root / ".trash"
        for item in trash.iterdir() if trash.is_dir() else []:
            try:
                if item.stat().st_mtime < cutoff:
                    item.unlink()
            except OSError:
                pass

    def audio_files(self) -> list[Path]:
        """Every audio file under the root, hidden work-dirs excluded."""
        found = []
        for path in sorted(self.root.rglob("*")):
            if any(part in _HIDDEN_DIRS or part.startswith(".")
                   for part in path.relative_to(self.root).parts[:-1]):
                continue
            if path.is_file() and path.suffix.lower() in AUDIO_EXTS:
                found.append(path)
        return found

    def stats(self) -> dict:
        usage = shutil.disk_usage(self.root)
        return {"tracks": len(self.list_tracks()), "disk_free": usage.free,
                "disk_total": usage.total}
