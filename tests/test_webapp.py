"""The web app's backend, driven through Flask's test client: upload
pipeline (happy/bad-ext/oversize/duplicate), retag = file move + playlist
remap, delete -> trash + prune, status, and the optional PIN gate."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from shared import config, playlists

from tests.audiofiles import mp3_bytes, wav_bytes


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MUSIC_ROOT", str(tmp_path / "music"))
    monkeypatch.setattr(config, "PLAYLISTS_PATH", str(tmp_path / "pl.json"))
    from mac.store_mac import MacLibraryStore
    from shared.webapp.server import create_app

    store = MacLibraryStore(root=config.MUSIC_ROOT)
    events: list[dict] = []
    app = create_app(store, events.append)
    return store, app.test_client(), events


def _upload(client, data: bytes, name: str, replace: bool = False):
    return client.post("/api/upload" + ("?replace=1" if replace else ""),
                       data={"file": (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


def test_upload_happy_path_lands_sorted(env):
    store, client, events = env
    r = _upload(client, mp3_bytes("Neon Nights", "Test Artist", "Test Album", 3),
                "whatever.mp3")
    assert r.status_code == 201, r.get_data(as_text=True)
    t = r.get_json()["track"]
    assert t["id"] == "Test Artist/Test Album/03 Neon Nights.mp3"
    assert (Path(config.MUSIC_ROOT) / t["id"]).is_file()
    assert events and events[-1]["msg"] == "Added: Neon Nights"
    assert any(x.id == t["id"] for x in events[-1]["tracks"])


def test_upload_wav_uses_filename_fallbacks(env):
    _, client, _ = env
    r = _upload(client, wav_bytes(), "My Jam.wav")
    assert r.status_code == 201
    t = r.get_json()["track"]
    assert t["title"] == "My Jam" and t["artist"] == "Unknown Artist"
    assert t["id"] == "Unknown Artist/Unknown Album/My Jam.wav"


def test_upload_rejects_bad_extension(env):
    _, client, _ = env
    r = _upload(client, b"not audio", "notes.txt")
    assert r.status_code == 400
    assert "unsupported" in r.get_json()["error"]


def test_upload_rejects_oversize(env, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WEBAPP_MAX_UPLOAD_MB", 1)
    from mac.store_mac import MacLibraryStore
    from shared.webapp.server import create_app

    client = create_app(MacLibraryStore(root=config.MUSIC_ROOT),
                        lambda e: None).test_client()
    r = _upload(client, b"z" * (2 * 1024 * 1024), "big.mp3")
    assert r.status_code == 413
    assert "cap" in r.get_json()["error"]


def test_duplicate_refused_then_replaced(env):
    _, client, _ = env
    data = mp3_bytes("Same", "A", "B", 1)
    assert _upload(client, data, "same.mp3").status_code == 201
    r = _upload(client, data, "same.mp3")
    assert r.status_code == 409 and "replace" in r.get_json()["error"]
    assert _upload(client, data, "same.mp3", replace=True).status_code == 201


def test_retag_moves_file_and_remaps_playlists(env):
    _, client, _ = env
    old_id = _upload(client, mp3_bytes("Song", "Old Artist", "Old Album", 1),
                     "s.mp3").get_json()["track"]["id"]
    client.post("/api/playlists", json={"name": "P"})
    client.patch("/api/playlists/P", json={"tracks": [old_id]})

    r = client.patch(f"/api/tracks/{old_id}",
                     json={"artist": "New Artist", "album": "New Album"})
    assert r.status_code == 200
    new_id = r.get_json()["track"]["id"]
    assert new_id == "New Artist/New Album/01 Song.mp3"
    assert (Path(config.MUSIC_ROOT) / new_id).is_file()
    assert not (Path(config.MUSIC_ROOT) / "Old Artist").exists()  # dir pruned
    assert playlists.load()["P"] == [new_id]                      # remapped


def test_delete_goes_to_trash_and_prunes(env):
    store, client, _ = env
    tid = _upload(client, mp3_bytes("Bye", "A", "B", 1),
                  "bye.mp3").get_json()["track"]["id"]
    client.post("/api/playlists", json={"name": "P"})
    client.patch("/api/playlists/P", json={"tracks": [tid]})

    assert client.delete(f"/api/tracks/{tid}").status_code == 200
    trash = list((Path(config.MUSIC_ROOT) / ".trash").iterdir())
    assert len(trash) == 1                       # soft-deleted, not gone
    assert playlists.load()["P"] == []           # pruned
    assert store.list_tracks() == []
    assert client.delete(f"/api/tracks/{tid}").status_code == 404


def test_trash_purge_honors_age(env, tmp_path):
    import os
    import time

    store, client, _ = env
    tid = _upload(client, wav_bytes(), "old.wav").get_json()["track"]["id"]
    client.delete(f"/api/tracks/{tid}")
    item = next((Path(config.MUSIC_ROOT) / ".trash").iterdir())
    store.purge_trash()                          # fresh: survives
    assert item.exists()
    old = time.time() - (config.TRASH_KEEP_DAYS + 1) * 86400
    os.utime(item, (old, old))
    store.purge_trash()                          # aged out: gone
    assert not item.exists()


def test_chunked_upload_streams_intact(env):
    """A multi-megabyte upload goes through the 64 KB cooperative-yield
    streaming path and must land byte-identical."""
    import hashlib

    _, client, _ = env
    blob = wav_bytes(seconds=60)  # ~2.6 MB, dozens of chunks
    assert len(blob) > 10 * config.UPLOAD_CHUNK
    r = _upload(client, blob, "long.wav")
    assert r.status_code == 201
    tid = r.get_json()["track"]["id"]
    stored = (Path(config.MUSIC_ROOT) / tid).read_bytes()
    assert hashlib.sha256(stored).digest() == hashlib.sha256(blob).digest()


def test_status_endpoint(env):
    _, client, _ = env
    _upload(client, wav_bytes(), "one.wav")
    s = client.get("/api/status").get_json()
    assert s["tracks"] == 1
    assert s["disk_free"] > 0 and s["disk_total"] >= s["disk_free"]
    assert "name" in s and "battery" in s


def test_pin_gate_when_configured(env, monkeypatch):
    _, client, _ = env
    monkeypatch.setattr(config, "WEBAPP_PIN", "4321")
    assert client.get("/").status_code == 200            # the page itself loads
    assert client.get("/api/library").status_code == 401  # API needs the PIN
    r = client.get("/api/library", headers={"X-Device-Pin": "4321"})
    assert r.status_code == 200
    assert client.get("/api/library",
                      headers={"X-Device-Pin": "0000"}).status_code == 401
