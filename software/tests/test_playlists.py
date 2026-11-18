"""Playlists: manifest CRUD, API round-trips, device menus/contexts built
from playlist order, and pruning when a member track is deleted."""
from __future__ import annotations

import io

import pytest

from shared import config, playlists
from shared.hardware import Track
from shared.menu_core import build_default_menus, extract_play_context

from tests.audiofiles import mp3_bytes


@pytest.fixture(autouse=True)
def _manifest_path(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLAYLISTS_PATH", str(tmp_path / "pl.json"))
    yield


# --- manifest unit tests ---------------------------------------------------------

def test_manifest_crud_round_trip():
    assert playlists.create("Road Trip")
    assert not playlists.create("Road Trip")      # duplicate refused
    assert not playlists.create("   ")            # empty refused
    assert playlists.set_tracks("Road Trip", ["a/1.mp3", "b/2.mp3"])
    assert playlists.load() == {"Road Trip": ["a/1.mp3", "b/2.mp3"]}
    assert playlists.rename("Road Trip", "Trip")
    assert not playlists.rename("nope", "x")
    assert playlists.load() == {"Trip": ["a/1.mp3", "b/2.mp3"]}
    assert playlists.delete("Trip")
    assert not playlists.delete("Trip")
    assert playlists.load() == {}


def test_manifest_prune_and_remap():
    playlists.create("P")
    playlists.set_tracks("P", ["a", "b", "c"])
    assert playlists.remap("b", "B2")
    assert playlists.load()["P"] == ["a", "B2", "c"]
    assert playlists.prune({"a", "c"})
    assert playlists.load()["P"] == ["a", "c"]
    assert not playlists.prune({"a", "c"})        # nothing left to prune


# --- device menus from playlist order --------------------------------------------

def _tracks(n: int) -> list[Track]:
    return [Track(index=i, title=f"T{i}", artist="A", album="B", track_no=i + 1,
                  duration=10.0, file=f"/x/{i}.mp3", id=f"A/B/{i:02d}.mp3")
            for i in range(n)]


def test_playlist_menu_context_matches_manifest_order():
    tracks = _tracks(4)
    order = [tracks[2].id, tracks[0].id, tracks[3].id]  # deliberate scramble
    menus = build_default_menus(tracks, {"Mix": order})
    menu = menus["playlist_mix"]
    assert menu.items[0].label == "Shuffle playlist"
    assert menu.items[0].action == "do:plshuffle:playlist_mix"
    ctx = extract_play_context(menu)
    assert [tracks_by(tracks)[i].id for i in ctx] == order


def tracks_by(tracks):
    return {t.index: t for t in tracks}


def test_empty_playlist_shows_hint_row():
    menus = build_default_menus(_tracks(2), {"Empty": []})
    menu = menus["playlist_empty"]
    assert len(menu.items) == 1
    assert "web app" in menu.items[0].label
    assert extract_play_context(menu) == []


def test_no_playlists_shows_hint_row():
    menus = build_default_menus(_tracks(2), {})
    assert "web app" in menus["playlists"].items[0].label


def test_dead_ids_skipped_in_menu():
    tracks = _tracks(2)
    menus = build_default_menus(tracks, {"P": [tracks[1].id, "ghost/track.mp3"]})
    ctx = extract_play_context(menus["playlist_p"])
    assert [tracks_by(tracks)[i].id for i in ctx] == [tracks[1].id]


# --- API round-trips over a real store --------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MUSIC_ROOT", str(tmp_path / "music"))
    from mac.store_mac import MacLibraryStore
    from shared.webapp.server import create_app

    store = MacLibraryStore(root=config.MUSIC_ROOT)
    app = create_app(store, lambda ev: None)
    c = app.test_client()
    for i, title in enumerate(("One", "Two", "Three"), start=1):
        r = c.post("/api/upload",
                   data={"file": (io.BytesIO(
                       mp3_bytes(title, "Artist", "Album", i)), f"{title}.mp3")},
                   content_type="multipart/form-data")
        assert r.status_code == 201, r.get_data(as_text=True)
    return c


def _ids(client):
    return [t["id"] for t in client.get("/api/library").get_json()["tracks"]]


def test_api_playlist_crud_and_order_round_trip(client):
    ids = _ids(client)
    assert client.post("/api/playlists", json={"name": "Mix"}).status_code == 201
    reordered = [ids[2], ids[0], ids[1]]
    r = client.patch("/api/playlists/Mix", json={"tracks": reordered})
    assert r.status_code == 200
    assert r.get_json()["playlists"]["Mix"] == reordered
    # rename keeps contents
    r = client.patch("/api/playlists/Mix", json={"rename": "Best Mix"})
    assert r.get_json()["playlists"]["Best Mix"] == reordered
    # delete
    assert client.delete("/api/playlists/Best Mix").status_code == 200
    assert client.get("/api/playlists").get_json()["playlists"] == {}


def test_api_member_delete_prunes_playlist(client):
    ids = _ids(client)
    client.post("/api/playlists", json={"name": "P"})
    client.patch("/api/playlists/P", json={"tracks": ids})
    victim = ids[1]
    assert client.delete(f"/api/tracks/{victim}").status_code == 200
    remaining = client.get("/api/playlists").get_json()["playlists"]["P"]
    assert victim not in remaining and len(remaining) == 2


def test_api_rejects_unknown_ids_in_membership(client):
    ids = _ids(client)
    client.post("/api/playlists", json={"name": "P"})
    client.patch("/api/playlists/P", json={"tracks": [ids[0], "ghost.mp3"]})
    assert client.get("/api/playlists").get_json()["playlists"]["P"] == [ids[0]]
