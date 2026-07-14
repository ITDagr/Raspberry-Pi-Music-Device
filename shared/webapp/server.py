"""device v2 — the Flask server behind the library web app.

start_webapp(store, notify) runs werkzeug on a daemon thread and returns
the bound port (pass port=0 for an ephemeral one — the selftest does).
The server never touches app state directly: mutations go through the
LibraryStore / playlist manifest, and every completed change calls
notify({msg, tracks?, playlists?}) — the main loop drains that queue each
frame, rebuilds TRACKS + menus, and shows the toast.
"""
from __future__ import annotations

import threading
import uuid
from pathlib import Path

from shared import config, pisugar, playlists
from shared.hardware import track_id
from shared.webapp.store import BaseLibraryStore, StoreError


def _track_json(t) -> dict:
    if isinstance(t, dict):
        return {"id": t["id"], "title": t["title"], "artist": t["artist"],
                "album": t["album"], "track_no": int(t.get("track_no") or 0),
                "duration": float(t.get("duration") or 0.0)}
    return {"id": t.id, "title": t.title, "artist": t.artist,
            "album": t.album, "track_no": t.track_no, "duration": t.duration}


def create_app(store: BaseLibraryStore, notify):
    from flask import Flask, jsonify, request, send_from_directory

    static_dir = Path(__file__).resolve().parent / "static"
    app = Flask(__name__, static_folder=str(static_dir), static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = config.WEBAPP_MAX_UPLOAD_MB * 1024 * 1024

    @app.before_request
    def _pin_gate():
        """Optional shared PIN for shared networks (config.WEBAPP_PIN).
        The page itself loads; every API call must carry the header —
        the frontend prompts once and remembers it for the session."""
        if not config.WEBAPP_PIN:
            return None
        if not request.path.startswith("/api/"):
            return None
        if request.headers.get("X-Device-Pin") == str(config.WEBAPP_PIN):
            return None
        return jsonify(error="PIN required"), 401

    def push_library(msg: str) -> None:
        notify({"msg": msg, "tracks": store.list_tracks()})

    def push_playlists(msg: str) -> None:
        notify({"msg": msg, "playlists": True})

    @app.errorhandler(StoreError)
    def _store_error(e: StoreError):
        return jsonify(error=e.message), e.status

    @app.errorhandler(413)
    def _too_big(e):
        return jsonify(error=f"file exceeds the "
                             f"{config.WEBAPP_MAX_UPLOAD_MB} MB upload cap"), 413

    @app.get("/")
    def index():
        return send_from_directory(str(static_dir), "index.html")

    # --- library -----------------------------------------------------------------
    @app.get("/api/library")
    def api_library():
        return jsonify(tracks=[_track_json(t) for t in store.list_tracks()])

    @app.post("/api/upload")
    def api_upload():
        f = request.files.get("file")
        if f is None or not f.filename:
            return jsonify(error="no file in the request"), 400
        tmp = store.root / ".incoming" / f"up_{uuid.uuid4().hex}"
        f.save(str(tmp))
        replace = request.args.get("replace") == "1"
        added = store.add_upload(tmp, f.filename, replace=replace)
        push_library(f"Added: {added['title']}")
        return jsonify(track=_track_json(added)), 201

    @app.delete("/api/tracks/<path:tid>")
    def api_delete(tid):
        title = store.title_of(track_id(tid))
        store.delete(tid)
        alive = {t.id for t in store.list_tracks()}
        playlists.prune(alive)
        push_library(f"Removed: {title}")
        return jsonify(ok=True, id=track_id(tid))

    @app.patch("/api/tracks/<path:tid>")
    def api_retag(tid):
        changes = request.get_json(silent=True) or {}
        updated = store.retag(tid, changes)
        if updated["id"] != updated["old_id"]:
            playlists.remap(updated["old_id"], updated["id"])
        push_library(f"Updated: {updated['title']}")
        return jsonify(track=_track_json(updated), old_id=updated["old_id"])

    # --- playlists ----------------------------------------------------------------
    @app.get("/api/playlists")
    def api_playlists():
        return jsonify(playlists=playlists.load())

    @app.post("/api/playlists")
    def api_playlist_create():
        name = (request.get_json(silent=True) or {}).get("name", "").strip()
        if not playlists.create(name):
            return jsonify(error="playlist name is empty or already taken"), 400
        push_playlists(f"Playlist created: {name}")
        return jsonify(playlists=playlists.load()), 201

    @app.patch("/api/playlists/<name>")
    def api_playlist_update(name):
        body = request.get_json(silent=True) or {}
        if "rename" in body:
            new = str(body["rename"]).strip()
            if not playlists.rename(name, new):
                return jsonify(error="cannot rename (missing, empty or taken)"), 400
            name = new
        if "tracks" in body:
            alive = {t.id for t in store.list_tracks()}
            wanted = [t for t in body["tracks"]
                      if isinstance(t, str) and t in alive]
            if not playlists.set_tracks(name, wanted):
                return jsonify(error=f"no playlist named '{name}'"), 404
        push_playlists(f"Playlist updated: {name}")
        return jsonify(playlists=playlists.load())

    @app.delete("/api/playlists/<name>")
    def api_playlist_delete(name):
        if not playlists.delete(name):
            return jsonify(error=f"no playlist named '{name}'"), 404
        push_playlists(f"Playlist deleted: {name}")
        return jsonify(playlists=playlists.load())

    # --- status -------------------------------------------------------------------
    @app.get("/api/status")
    def api_status():
        import socket

        s = store.stats()
        return jsonify(name=socket.gethostname().split(".")[0],
                       tracks=s["tracks"], disk_free=s["disk_free"],
                       disk_total=s["disk_total"],
                       battery=pisugar.get_battery())

    return app


def _advertise(port: int) -> None:
    """Best-effort zeroconf HTTP service record so the device shows up in
    network browsers. avahi already serves device.local; this is gravy —
    any failure (module missing on the Mac, no network) is non-fatal."""
    try:
        import socket

        from zeroconf import ServiceInfo, Zeroconf

        from shared import netinfo

        ip = netinfo.get_ip()
        if not ip:
            return
        name = socket.gethostname().split(".")[0] or "device"
        info = ServiceInfo(
            "_http._tcp.local.",
            f"{name} music library._http._tcp.local.",
            addresses=[socket.inet_aton(ip)], port=port,
            properties={"path": "/"}, server=f"{name}.local.",
        )
        Zeroconf().register_service(info)
    except Exception as e:
        print(f"webapp: zeroconf advertise skipped ({e})")


def start_webapp(store: BaseLibraryStore, notify, port: int = None) -> int:
    """Serve on a daemon thread; returns the actual bound port."""
    from werkzeug.serving import make_server

    app = create_app(store, notify)
    server = make_server(config.WEBAPP_HOST,
                         config.WEBAPP_PORT if port is None else port,
                         app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True,
                     name="webapp").start()
    _advertise(server.server_port)
    return server.server_port
