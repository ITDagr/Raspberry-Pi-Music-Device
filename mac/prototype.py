"""device v2 — Mac prototype launcher.

Run it:            python3 mac/prototype.py
Headless selftest: python3 mac/prototype.py --selftest   (exit 0 = pass)
Frame dumps:       python3 mac/prototype.py --dump-frames <dir>
                   (selftest run that also saves a PNG of every screen)

Opens a 480x480 window (2x scale of the 240x240 TFT) and runs the exact same
shared.app main loop as the Pi, with keyboard/terminal stand-ins for hardware:

    ↑ / ↓        wheel detents (scroll)
    Enter/Space  select
    →  /  ←      right / left
    Backspace    back
    Esc / close  quit

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
from shared.hardware import HardwareBundle  # noqa: E402
from shared.menu_core import build_default_menus, extract_play_context  # noqa: E402
from mac import bluetooth_mac, library_mac  # noqa: E402
from mac.display_mock import MockDisplay  # noqa: E402
from mac.haptic_mock import MockHaptic  # noqa: E402
from mac.input_mock import MockANOInput  # noqa: E402
from mac.player_mac import PlayerMac  # noqa: E402


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
                 display: CaptureDisplay | None = None) -> None:
        self.inp = inp
        self.songs_ctx = extract_play_context(build_default_menus(tracks)["songs"])
        self.dump_dir = dump_dir
        self.display = display
        self._gen = None
        self._resume_at = 0.0
        self.done = False

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
        press("select"); yield 0  # home -> Music
        expect(a.ctrl.current_name == "music", f"expected music menu, got {a.ctrl.current_name}")
        press("scroll_down", "scroll_down", "select"); yield 0  # -> Songs
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
        press("scroll_down", "scroll_down", "scroll_down"); yield 0  # 100 -> 70
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
        press("scroll_up", "select"); yield 0  # Bluetooth (blocking fake scan)
        expect(a.mode is Mode.BLUETOOTH and len(a.bt_devices) > 0,
               f"expected BLUETOOTH with devices, got {a.mode} n={len(a.bt_devices)}")
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
        # StopIteration -> runner pushes quit; state file checked afterwards

    def verify_state_file(self) -> None:
        if not self.done:
            raise SelfTestError("script did not run to completion")
        try:
            with open(config.STATE_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            raise SelfTestError(f"state file not written cleanly: {e}")
        expected = {"track_index": self.songs_ctx[4], "pos": 4, "volume": 60,
                    "brightness": 70}
        for key, want in expected.items():
            if data.get(key) != want:
                raise SelfTestError(
                    f"state[{key!r}] = {data.get(key)!r}, expected {want!r} "
                    f"(full state: {data})")
        if data.get("context") != self.songs_ctx:
            raise SelfTestError("state context does not match the songs context")


def _run_selftest(tracks, dump_dir: str | None = None) -> int:
    config.STARTUP_DURATION_S = 0.2   # keep the run inside the time budget
    config.ENCODER_ACCEL = False      # scripted detents fire faster than 1 s
    if os.path.exists(config.STATE_PATH):
        os.remove(config.STATE_PATH)
    if dump_dir:
        os.makedirs(dump_dir, exist_ok=True)
    inp = ScriptedInput()
    display = CaptureDisplay()
    runner = SelfTestRunner(inp, tracks, dump_dir, display)
    hw = HardwareBundle(display, inp, MockHaptic(), PlayerMac(tracks))
    t0 = time.monotonic()
    try:
        app.run(hw, tracks, bluetooth_mac, selftest_script=runner)
        runner.verify_state_file()
    except SelfTestError as e:
        print(f"SELFTEST FAIL: {e}")
        return 1
    print(f"SELFTEST PASS ({time.monotonic() - t0:.1f}s)")
    return 0


def main() -> int:
    pygame.mixer.pre_init(22050, -16, 1, 1024)
    pygame.init()
    pisugar.start_polling()
    print("device v2 — Mac prototype")
    print("generating synthetic audio… (first run only)")
    library_mac.ensure_audio()
    tracks = library_mac.TRACKS
    print("ready.")
    if SELFTEST or DUMP_DIR:
        return _run_selftest(tracks, DUMP_DIR)
    print("controls: ↑/↓ wheel · Enter/Space select · → right · ← left · "
          "Backspace back · Esc quit")
    print("Haptic events print here:")
    hw = HardwareBundle(MockDisplay(), MockANOInput(), MockHaptic(), PlayerMac(tracks))
    try:
        app.run(hw, tracks, bluetooth_mac)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
