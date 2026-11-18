"""device v2 — browser demo (WebAssembly, built with pygbag).

Runs the same shared.app main loop as the Pi and the Mac prototype, with the
Mac stand-ins for the hardware, inside a web page. A browser gives Python no
threads and no blocking waits, so this entry point:

  * drives App._frame() from an async loop, yielding to the page every frame
  * ticks the screen dimmer itself instead of starting its thread
  * runs the Bluetooth "scan" on a timer instead of a thread
  * records the boot animation, then plays it back frame by frame
  * renders each synthetic track the first time it plays (not all at boot)
  * leaves out the Flask web app, the PiSugar poll and the power switch

Controls (keyboard or mouse/touch):
    up / down, mouse wheel, drag      wheel detents (scroll)
    Enter / Space, click or tap        center button: tap select, HOLD 0.6 s back
    W / S, A / D, arrow left / right   ring buttons
    Backspace, right click             back

Build it locally:  python3 web/build.py   (site lands in web/build/device/build/web/)
"""
from __future__ import annotations

import asyncio
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# built: shared/ and mac/ sit beside this file; from source: one level up
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

from shared import app as app_mod  # noqa: E402
from shared import config  # noqa: E402
from shared import startup as startup_mod  # noqa: E402
from shared.hardware import HardwareBundle  # noqa: E402
from shared.encoder import CenterButton  # noqa: E402
from mac import bluetooth_mac, library_mac  # noqa: E402
from mac.display_mock import MockDisplay  # noqa: E402
from mac.haptic_mock import MockHaptic  # noqa: E402
from mac.input_mock import _CENTER_KEYS, _EXPOSE_EVENTS, _KEYMAP  # noqa: E402
from mac.player_mac import PlayerMac  # noqa: E402
from mac.power_mock import MockPowerSwitch  # noqa: E402
from mac.radio_mock import MockRadio  # noqa: E402

config.WEBAPP_ENABLED = False  # no server can run inside a web page

# --- timers standing in for threads ---------------------------------------------
_timers: list = []  # (due monotonic, callable)


class _TimerThread:
    """threading.Thread look-alike: runs the target on the main loop a moment
    later (the Mac Bluetooth fake 'scans' for ~0.8 s)."""

    def __init__(self, target, daemon=True, name=None, args=()):
        self._target, self._args = target, args

    def start(self) -> None:
        _timers.append((time.monotonic() + 0.8, lambda: self._target(*self._args)))


def _run_due_timers() -> None:
    now = time.monotonic()
    for item in [t for t in _timers if t[0] <= now]:
        _timers.remove(item)
        item[1]()


app_mod.threading = types.SimpleNamespace(Thread=_TimerThread)

bluetooth_web = types.SimpleNamespace(
    scan_devices=lambda: [dict(d) for d in bluetooth_mac._DEVICES],  # no sleep
    connect_device=bluetooth_mac.connect_device,
    check_connected=bluetooth_mac.check_connected,
)


# --- hardware stand-ins ------------------------------------------------------------
class WebPlayer(PlayerMac):
    """PlayerMac that renders a track's WAV on first play."""

    def play_track(self, index: int) -> None:
        path = Path(self._tracks[index].file)
        if not path.exists() and index in library_mac._PARAMS:
            path.parent.mkdir(parents=True, exist_ok=True)
            library_mac._gen_track(path, *library_mac._PARAMS[index])
        super().play_track(index)


class WebDisplay(MockDisplay):
    """MockDisplay that can record frames instead of showing them."""

    def __init__(self) -> None:
        super().__init__()
        self.recording: list | None = None

    def push_frame(self, surface: pygame.Surface) -> None:
        if self.recording is not None:
            self.recording.append(surface.copy())
        else:
            super().push_frame(surface)


class WebInput:
    """Keyboard plus mouse/touch, through the same center-button machine."""

    DRAG_STEP = 28  # px of vertical drag per wheel detent

    def __init__(self) -> None:
        self.quit_requested = False
        self._center = CenterButton()
        self._down_y: int | None = None
        self._drag = 0
        self._dragged = False

    def read(self) -> list[str]:
        events: list[str] = []
        now = time.monotonic()
        for e in pygame.event.get():
            if e.type == pygame.KEYDOWN and e.key in _CENTER_KEYS:
                self._center.press(now)
            elif e.type == pygame.KEYUP and e.key in _CENTER_KEYS:
                events.extend(self._center.release(now))
            elif e.type == pygame.KEYDOWN and e.key in _KEYMAP:
                if _KEYMAP[e.key] != "quit":  # Esc can't close a web page
                    events.append(_KEYMAP[e.key])
            elif e.type == pygame.MOUSEWHEEL:
                events.append("scroll_up" if e.y > 0 else "scroll_down")
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:
                events.append("back")
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                self._down_y, self._drag, self._dragged = e.pos[1], 0, False
                self._center.press(now)
            elif e.type == pygame.MOUSEMOTION and self._down_y is not None:
                self._drag += e.rel[1]
                while abs(self._drag) >= self.DRAG_STEP:
                    if not self._dragged:
                        self._dragged = True
                        self._center = CenterButton()  # a drag is not a press
                    events.append("scroll_down" if self._drag < 0 else "scroll_up")
                    self._drag -= self.DRAG_STEP if self._drag > 0 else -self.DRAG_STEP
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                if self._down_y is not None and not self._dragged:
                    events.extend(self._center.release(now))
                self._down_y = None
            elif e.type in _EXPOSE_EVENTS:
                events.append("expose")
        if not self._dragged:
            events.extend(self._center.poll(now))
        return events


class _InstantClock:
    def tick(self, *_args) -> int:
        return 0


# --- the async main loop -------------------------------------------------------
async def main() -> None:
    print("demo: starting")
    pygame.mixer.pre_init(22050, -16, 1, 1024)
    pygame.init()
    tracks = library_mac.TRACKS
    display = WebDisplay()
    hw = HardwareBundle(display, WebInput(), MockHaptic(), WebPlayer(tracks),
                        power=MockPowerSwitch(), radio=MockRadio())
    a = app_mod.App(hw, tracks, bluetooth_web, None, None, None)
    if a.radio is not None:
        a.radio.set(a.wifi_pinned)
    surface = pygame.Surface((app_mod.SIZE, app_mod.SIZE), depth=24)

    # boot: record the startup animation without waiting, then play it back
    display.recording = []
    real_clock = startup_mod.pygame.time.Clock
    startup_mod.pygame.time.Clock = _InstantClock
    try:
        a._boot(surface)
    finally:
        startup_mod.pygame.time.Clock = real_clock
    frames, display.recording = display.recording, None
    for frame in frames:
        display.push_frame(frame)
        await asyncio.sleep(1 / 60)
    del frames
    print("demo: running")  # the smoke test waits for this line

    clock = pygame.time.Clock()
    next_dim = 0.0
    while True:
        now = time.monotonic()
        if now >= next_dim:
            a.dimmer.tick()
            next_dim = now + 0.25
        _run_due_timers()
        if not a._frame(surface):
            return
        clock.tick(a.loop_hz)
        await asyncio.sleep(0)


asyncio.run(main())
