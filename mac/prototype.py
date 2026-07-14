"""device v2 — Mac prototype launcher.

Run it:            python3 mac/prototype.py
Headless selftest: python3 mac/prototype.py --selftest   (exit 0 = pass)
Frame dumps:       python3 mac/prototype.py --dump-frames <dir>
                   (selftest run that also saves a PNG of every screen)

Opens a 480x480 window (2x scale of the 240x240 TFT) and runs the exact same
shared.app main loop as the Pi, with keyboard/terminal stand-ins for hardware.
Every encoder control is simulated with its REAL gesture semantics (the
center button runs the same shared machine as the Pi):

    ↑ / ↓          wheel detents (scroll)
    Enter/Space    center button — tap select · HOLD >= 0.6 s back
    W / S          ring up / down buttons
    A / D or ← →   ring left / right buttons
    Backspace      back (keyboard convenience)
    P              power switch    Esc / close  quit

--selftest swaps the keyboard for a scripted input source, runs the real loop
uncapped under SDL dummy drivers, and walks menus, playback, volume, bright-
ness, about, battery and bluetooth, asserting app state along the way.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def _arg_value(flag: str) -> str | None:
    if flag in sys.argv and sys.argv.index(flag) + 1 < len(sys.argv):
        return sys.argv[sys.argv.index(flag) + 1]
    return None


SELFTEST = "--selftest" in sys.argv
DUMP_DIR = _arg_value("--dump-frames")
if SELFTEST or DUMP_DIR:  # must land before pygame initializes SDL
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame  # noqa: E402

from shared import app, config, pisugar  # noqa: E402
from shared.hardware import HardwareBundle, NullHaptic  # noqa: E402
from shared.menu_core import build_default_menus, extract_play_context  # noqa: E402
from mac import bluetooth_mac, library_mac  # noqa: E402
from shared.screen_dimmer import DimState  # noqa: E402
from mac.display_mock import MockDisplay  # noqa: E402
from mac.haptic_mock import MockHaptic  # noqa: E402
from mac.input_mock import MockANOInput  # noqa: E402
from mac.player_mac import PlayerMac  # noqa: E402
from mac.power_mock import MockPowerSwitch  # noqa: E402
from mac.radio_mock import MockRadio  # noqa: E402


class SelfTestError(AssertionError):
    pass


class ScriptedInput:
    """InputSource fed by the selftest script instead of the keyboard."""

    def __init__(self) -> None:
        self._queue: deque = deque()
        self.quit_requested = False

    def push(self, *events: str) -> None:
        self._queue.extend(events)

    def read(self) -> list[str]:
        pygame.event.get()  # keep SDL drained
        events = list(self._queue)
        self._queue.clear()
        return events


class CaptureDisplay(MockDisplay):
    """MockDisplay that keeps copies of the last few pushed frames."""

    def __init__(self) -> None:
        super().__init__()
        self.frames: deque = deque(maxlen=8)

    def push_frame(self, surface: pygame.Surface) -> None:
        self.frames.append(surface.copy())
        super().push_frame(surface)


class SelfTestRunner:
    """Called once per frame by the app loop; drives and checks the script.

    With dump_dir set it also saves a PNG of every distinct screen it visits.
    """

    def __init__(self, inp: ScriptedInput, tracks, dump_dir: str | None = None,
                 display: CaptureDisplay | None = None,
                 port: int | None = None) -> None:
        self.inp = inp
        self.songs_ctx = extract_play_context(build_default_menus(tracks)["songs"])
        self.songs_ids = [tracks[i].id for i in self.songs_ctx]
        self.dump_dir = dump_dir
        self.display = display
        self.port = port                 # the ephemeral web app port (Phase E)
        self.e2e_deleted_id = None
        self._gen = None
        self._resume_at = 0.0
        self.done = False

    # --- real-HTTP driver for the web app E2E ------------------------------------
    def _http(self, method: str, path: str, payload: dict | None = None) -> dict:
        import urllib.request

        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                     data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    def _http_upload(self, filename: str, blob: bytes) -> dict:
        import urllib.request

        boundary = "----deviceSelftest"
        body = (
            (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
             f"filename=\"{filename}\"\r\n"
             "Content-Type: application/octet-stream\r\n\r\n").encode()
            + blob + f"\r\n--{boundary}--\r\n".encode()
        )
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/upload", data=body, method="POST")
        req.add_header("Content-Type",
                       f"multipart/form-data; boundary={boundary}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    def _snap(self, label: str, frame: pygame.Surface | None = None) -> None:
        """Save `frame` (default: the most recently pushed frame) as a PNG."""
        if not self.dump_dir:
            return
        if frame is None and self.display and self.display.frames:
            frame = self.display.frames[-1]
        if frame is not None:
            path = os.path.join(self.dump_dir, f"{label}.png")
            pygame.image.save(frame, path)
            print(f"frame: {path}")

    def __call__(self, application) -> None:
        if self.done or time.monotonic() < self._resume_at:
            return
        if self._gen is None:
            self._gen = self._script(application)
        try:
            wait = next(self._gen)
        except StopIteration:
            self.done = True
            self.inp.push("quit")
            return
        self._resume_at = time.monotonic() + wait

    def _script(self, a):
        Mode = app.Mode
        press = self.inp.push

        def expect(cond: bool, msg: str) -> None:
            if not cond:
                raise SelfTestError(msg)

        from shared import startup as startup_mod

        self._snap("startup_final", startup_mod.last_hero_frame)
        self._snap("menu_home")
        # Phase 2: both peripheral probes were forced to fail (dead PiSugar
        # port, NullHaptic) — boot reached here cleanly, battery must be "--"
        st = a._status()
        expect(st["battery"] is None,
               f"expected battery None with PiSugar offline, got {st['battery']}")
        expect(isinstance(a.haptic, NullHaptic), "expected NullHaptic installed")
        expect(not a.radio.is_on(),
               "WiFi radio must be OFF at boot under the on_demand policy")
        press("select"); yield 0  # home -> Music
        expect(a.ctrl.current_name == "music", f"expected music menu, got {a.ctrl.current_name}")
        press("scroll_down", "scroll_down", "scroll_down", "select"); yield 0  # -> Songs
        expect(a.ctrl.current_name == "songs", f"expected songs menu, got {a.ctrl.current_name}")
        self._snap("menu_songs")
        press("scroll_down", "scroll_down", "scroll_down", "select"); yield 0  # track 3
        expect(a.mode is Mode.NOWPLAYING and a.player.playing,
               f"expected NOWPLAYING+playing, got {a.mode} playing={a.player.playing}")
        expect(a.player.track.index == self.songs_ctx[3],
               f"wrong track: {a.player.track.index} != {self.songs_ctx[3]}")
        self._snap("nowplaying")
        press("scroll_up", "scroll_up"); yield 0  # volume 50 -> 60
        expect(a.player.volume == 60, f"expected volume 60, got {a.player.volume}")
        self._snap("volume_overlay")
        if self.dump_dir:
            yield 1.6  # let the overlay expire so later dumps are clean
        press("right"); yield 0  # next track
        expect(a.pos == 4 and a.player.track.index == self.songs_ctx[4],
               f"next track did not advance (pos={a.pos})")
        press("back"); yield 0
        expect(a.mode is Mode.MENU and a.player.playing,
               "back should return to MENU with music still playing")
        press("back", "back"); yield 0  # songs -> music -> home
        expect(a.ctrl.current_name == "home", f"expected home, got {a.ctrl.current_name}")
        press("scroll_down", "scroll_down", "scroll_down", "select"); yield 0  # Settings
        expect(a.ctrl.current_name == "settings", f"expected settings, got {a.ctrl.current_name}")
        press("scroll_down", "scroll_down", "select"); yield 0  # Brightness
        expect(a.mode is Mode.BRIGHTNESS, f"expected BRIGHTNESS, got {a.mode}")
        press("scroll_down", "scroll_down", "scroll_down"); yield 0  # 70 -> 40
        expect(a.brightness == 40, f"expected brightness 40, got {a.brightness}")
        expect(abs(a.dimmer.wake_level - 0.4) < 1e-6,
               f"expected wake_level 0.4, got {a.dimmer.wake_level}")
        press("scroll_up", "scroll_up", "scroll_up"); yield 0  # back to 70
        expect(a.brightness == 70, f"expected brightness 70, got {a.brightness}")
        expect(abs(a.dimmer.wake_level - 0.7) < 1e-6,
               f"expected wake_level 0.7, got {a.dimmer.wake_level}")
        self._snap("brightness")
        press("back"); yield 0
        expect(a.mode is Mode.MENU, "back should leave brightness")
        press("scroll_down", "select"); yield 0  # About
        expect(a.mode is Mode.ABOUT, f"expected ABOUT, got {a.mode}")
        press("scroll_down", "scroll_down"); yield 0
        expect(a.about_scroll == 2, f"expected about scroll 2, got {a.about_scroll}")
        self._snap("about")
        press("back"); yield 0
        expect(a.mode is Mode.MENU and a.about_scroll == 0, "about should reset on back")
        press("scroll_up", "scroll_up", "select"); yield 0  # Battery
        expect(a.mode is Mode.BATTERY, f"expected BATTERY, got {a.mode}")
        self._snap("battery")
        press("back"); yield 0
        # --- Phase 6: the scan runs on a thread; the UI must stay responsive.
        # Make the fake scan slow enough to observe the scanning state.
        real_scan = bluetooth_mac.scan_devices

        def slow_scan():
            time.sleep(1.2)
            return real_scan()

        bluetooth_mac.scan_devices = slow_scan
        press("scroll_up", "select"); yield 0.2  # Bluetooth, scan in flight
        expect(a.mode is Mode.BLUETOOTH and a.bt_scanning,
               f"expected scanning state, got {a.mode} scanning={a.bt_scanning}")
        expect(len(a.bt_devices) == 0, "device list must be empty mid-scan")
        press("back"); yield 0.2  # input accepted DURING the scan
        expect(a.mode is Mode.MENU, "back during a scan must cancel immediately")
        press("select"); yield 3.0  # re-enter; slow (1.2s) + real (0.8s) scan
        expect(a.mode is Mode.BLUETOOTH and not a.bt_scanning
               and len(a.bt_devices) > 0,
               f"expected devices after scan, got scanning={a.bt_scanning} "
               f"n={len(a.bt_devices)}")
        bluetooth_mac.scan_devices = real_scan
        self._snap("bluetooth_list")
        press("select"); yield 0  # connect first device
        expect(a.bt_connect_info and a.bt_connect_info["state"] == "connecting",
               f"expected connecting, got {a.bt_connect_info}")
        self._snap("bluetooth_connecting")
        yield 4.5  # simulate the connection window
        expect(a.bt_connect_info and a.bt_connect_info["state"] == "connected",
               f"expected connected, got {a.bt_connect_info}")
        self._snap("bluetooth_connected")
        press("back"); yield 0
        expect(a.mode is Mode.BLUETOOTH and a.bt_connect_info is None,
               "back from connected should return to the device list")
        press("back"); yield 0
        expect(a.mode is Mode.MENU, "back should leave bluetooth")

        # --- Web App screen + Phase F radio policy -------------------------------
        press("scroll_up", "scroll_up", "select"); yield 0.2  # wrap to Web App
        expect(a.mode is Mode.WEBAPP, f"expected WEBAPP, got {a.mode}")
        expect(a.radio.is_on(), "entering the Web App screen must power WiFi on")
        self._snap("webapp")
        # leave while a transfer is in flight: the radio is held up
        from shared.webapp import server as webapp_server
        webapp_server._begin_transfer()  # a simulated in-flight upload
        press("back"); yield 0.3
        expect(a.mode is Mode.MENU, "back should leave the web app screen")
        expect(a.radio.is_on(), "radio must stay up while a transfer is in flight")
        webapp_server._end_transfer()
        yield 0.3
        expect(not a.radio.is_on(), "radio must drop once the queue drains")
        # the WiFi pin: On until toggled back to Auto
        press("scroll_down", "select"); yield 0.2  # WiFi row, below Web App
        expect(a.wifi_pinned and a.radio.is_on(),
               "WiFi toggle must pin the radio on")
        press("select"); yield 0.2
        expect(not a.wifi_pinned and not a.radio.is_on(),
               "toggling back must unpin and drop the radio")

        # --- Phase 3a: wake only by center press -------------------------------
        old_dim, old_sleep = config.DIM_AFTER_S, config.SLEEP_AFTER_S
        config.DIM_AFTER_S, config.SLEEP_AFTER_S = 0.3, 0.6
        yield 1.3  # dimmer thread ticks at 0.25 s: DIM then SLEEP by now
        expect(a.dimmer.state is DimState.SLEEP,
               f"expected SLEEP after shrunk timeouts, got {a.dimmer.state}")
        expect(a.loop_hz == config.FPS_SLEEP,
               f"loop must drop to {config.FPS_SLEEP} Hz asleep, got {a.loop_hz}")
        cursor_before = a.ctrl.cursor
        press("scroll_down"); yield 0.3
        expect(a.dimmer.state is not DimState.AWAKE,
               "an arrow must not wake a dark screen")
        expect(a.ctrl.cursor == cursor_before,
               "an arrow moved the menu while the screen was dark")
        press("select"); yield 0.3
        expect(a.dimmer.state is DimState.AWAKE, "center press must wake")
        expect(a.ctrl.cursor == cursor_before,
               "the waking press must be swallowed, not select")
        expect(a.loop_hz == config.FPS,
               f"loop must return to {config.FPS} Hz awake, got {a.loop_hz}")
        config.DIM_AFTER_S, config.SLEEP_AFTER_S = old_dim, old_sleep

        # --- Phase 3b: soft power off -> on with state round-trip --------------
        track_before = a.player.track.index
        tid_before = a.player.track.id
        elapsed_before = a.player.elapsed
        boots_before = a.boots
        a.power.toggle()  # the selftest's "press P": switch OFF
        yield 0.4
        expect(not a.player.playing, "soft-off must stop playback")
        expect(a.display.level == 0.0, "soft-off must turn the backlight off")
        with open(config.STATE_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        expect(saved.get("track_id") == tid_before,
               f"state file track {saved.get('track_id')} != {tid_before}")
        expect(abs(float(saved.get("elapsed", -99)) - elapsed_before) < 2.0,
               f"state file elapsed {saved.get('elapsed')} far from {elapsed_before}")
        press("scroll_down", "scroll_down", "select"); yield 0.4  # ignored while off
        expect(not a.player.playing and a.display.level == 0.0,
               "input leaked into soft-off")
        a.power.toggle()  # switch ON
        yield 1.2  # startup animation (0.2 s in selftest) + restore
        expect(a.boots == boots_before + 1,
               "power-on did not run the startup animation")
        expect(a.player.playing, "power-on did not resume playback")
        expect(a.player.track.index == track_before,
               f"resumed wrong track {a.player.track.index} != {track_before}")
        expect(abs(a.player.elapsed - float(saved["elapsed"])) < 3.0,
               f"resumed at {a.player.elapsed:.1f}, saved {saved['elapsed']}")
        expect(a.mode is Mode.MENU, "power-on should boot into MENU")

        # --- Phase E: drive the web app over real HTTP --------------------------
        import urllib.parse

        from shared.menu_core import extract_play_context as _ctx
        from tests.audiofiles import mp3_bytes

        n_before = len(a.tracks)
        up = self._http_upload(
            "e2e.mp3", mp3_bytes("E2E Song", "E2E Artist", "E2E Album", 1))
        new_id = up["track"]["id"]
        yield 0.5  # let the main loop drain the event queue
        expect(len(a.tracks) == n_before + 1, "TRACKS did not grow after upload")
        expect(any(t.id == new_id for t in a.tracks),
               f"uploaded id {new_id} missing from TRACKS")
        expect(a.toast_msg.startswith("Added"),
               f"expected an Added toast, got {a.toast_msg!r}")
        labels = [i.label for i in a.ctrl.menus["songs"].items]
        expect("E2E Song" in labels, "uploaded song missing from the Songs menu")
        self._snap("webapp_upload_toast")

        # playlist of 3 (incl. the upload), deliberately reordered
        others = [t.id for t in a.tracks if t.id != new_id][:2]
        order = [others[1], new_id, others[0]]
        self._http("POST", "/api/playlists", {"name": "E2E"})
        self._http("PATCH", "/api/playlists/E2E", {"tracks": order})
        yield 0.5
        menu = a.ctrl.menus.get("playlist_e2e")
        expect(menu is not None, "playlist menu missing after creation")
        expect(menu.items[0].label == "Shuffle playlist", "shuffle row missing")
        got = [a.tracks[i].id for i in _ctx(menu)]
        expect(got == order,
               f"device playlist order {got} != web order {order}")

        # delete the uploaded track: gone from menus, playlist, and state
        self._http("DELETE",
                   "/api/tracks/" + urllib.parse.quote(new_id, safe="/"))
        yield 0.5
        expect(all(t.id != new_id for t in a.tracks),
               "deleted track still in TRACKS")
        labels = [i.label for i in a.ctrl.menus["songs"].items]
        expect("E2E Song" not in labels, "deleted song still in the Songs menu")
        remaining = self._http("GET", "/api/playlists")["playlists"]["E2E"]
        expect(remaining == [others[1], others[0]],
               f"playlist not pruned correctly: {remaining}")
        self.e2e_deleted_id = new_id
        # StopIteration -> runner pushes quit; state file checked afterwards

    def verify_state_file(self) -> None:
        if not self.done:
            raise SelfTestError("script did not run to completion")
        try:
            with open(config.STATE_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise SelfTestError(f"state file not written cleanly: {e}")
        expected = {"track_id": self.songs_ids[4], "pos": 4, "volume": 60,
                    "brightness": 70}
        for key, want in expected.items():
            if data.get(key) != want:
                raise SelfTestError(
                    f"state[{key!r}] = {data.get(key)!r}, expected {want!r} "
                    f"(full state: {data})")
        if data.get("context") != self.songs_ids:
            raise SelfTestError("state context does not match the songs context")
        if self.e2e_deleted_id and (
                self.e2e_deleted_id in data.get("context", [])
                or data.get("track_id") == self.e2e_deleted_id):
            raise SelfTestError("a deleted track leaked into the saved state")


def _run_selftest(tracks, dump_dir: str | None = None) -> int:
    import queue
    import shutil
    import tempfile

    from shared.hardware import Track
    from mac.store_mac import MacLibraryStore
    from shared.webapp.server import start_webapp

    config.STARTUP_DURATION_S = 0.2   # keep the run inside the time budget
    config.ENCODER_ACCEL = False      # scripted detents fire faster than 1 s
    config.PISUGAR_PORT = 1           # force the boot probe to fail: offline mode
    config.PLAYLISTS_PATH = config.STATE_PATH + ".selftest-playlists"
    for stray in (config.STATE_PATH, config.PLAYLISTS_PATH):
        if os.path.exists(stray):
            os.remove(stray)
    if dump_dir:
        os.makedirs(dump_dir, exist_ok=True)

    # The web app manages a DISPOSABLE music root: a temp dir seeded with a
    # slice of the synthetic catalog, so E2E uploads/deletes never touch
    # mac/_audio. The whole selftest runs against this smaller library.
    tmp_root = tempfile.mkdtemp(prefix="device_selftest_music_")
    config.MUSIC_ROOT = tmp_root
    seed = []
    for t in tracks[:12]:
        name = os.path.basename(t.file)
        shutil.copy(t.file, os.path.join(tmp_root, name))
        seed.append(Track(index=len(seed), title=t.title, artist=t.artist,
                          album=t.album, track_no=t.track_no,
                          duration=t.duration,
                          file=os.path.join(tmp_root, name), id=t.id))
    store = MacLibraryStore(root=tmp_root, seed=seed)
    tracks = store.list_tracks()
    web_events = queue.Queue()
    port = start_webapp(store, web_events.put, port=0)  # ephemeral port

    inp = ScriptedInput()
    display = CaptureDisplay()
    runner = SelfTestRunner(inp, tracks, dump_dir, display, port=port)
    # NullHaptic = the failed-haptics-probe result; the whole run must work
    # with it installed, proving no code path needs a real motor
    hw = HardwareBundle(display, inp, NullHaptic(), PlayerMac(tracks),
                        power=MockPowerSwitch(), radio=MockRadio())
    t0 = time.monotonic()
    try:
        app.run(hw, tracks, bluetooth_mac, selftest_script=runner,
                web_events=web_events, webapp_port=port)
        runner.verify_state_file()
    except SelfTestError as e:
        print(f"SELFTEST FAIL: {e}")
        return 1
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
    print(f"SELFTEST PASS ({time.monotonic() - t0:.1f}s)")
    return 0


def main() -> int:
    pygame.mixer.pre_init(22050, -16, 1, 1024)
    pygame.init()
    print("device v2 — Mac prototype")
    print("generating synthetic audio… (first run only)")
    library_mac.ensure_audio()
    tracks = library_mac.TRACKS
    print("ready.")
    if SELFTEST or DUMP_DIR:
        # no start_polling() yet: _run_selftest points PiSugar at a dead
        # port first, then app.run() starts the (probing) poll thread
        return _run_selftest(tracks, DUMP_DIR)
    pisugar.start_polling()
    web_events = None
    webapp_port = None
    if config.WEBAPP_ENABLED:
        import queue

        from mac.store_mac import MacLibraryStore
        from shared.webapp.server import start_webapp

        store = MacLibraryStore(seed=tracks)  # registry seeded from the catalog
        tracks = store.list_tracks()          # includes earlier uploads/edits
        web_events = queue.Queue()
        webapp_port = start_webapp(store, web_events.put)
        print(f"web app:  http://localhost:{webapp_port}")
    print("controls: ↑/↓ wheel · Enter tap select / HOLD 0.6s back · "
          "W/S ring up/down · A/D or ←/→ ring left/right · "
          "Backspace back · P power switch · Esc quit")
    print("Haptic events print here:")
    power = MockPowerSwitch()
    hw = HardwareBundle(MockDisplay(), MockANOInput(power), MockHaptic(),
                        PlayerMac(tracks), power=power, radio=MockRadio())
    try:
        app.run(hw, tracks, bluetooth_mac, web_events=web_events,
                webapp_port=webapp_port)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
