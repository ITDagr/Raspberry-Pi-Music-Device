"""device v2 — the main loop and mode state machine (runs on Mac and Pi).

Entry point: run(hw, tracks, bluetooth_module). One 30 fps loop with
dirty-flag rendering; all hardware arrives injected via HardwareBundle.

Modes and controls:
    MENU        wheel moves the cursor - select/right activates - left/back up a level
    NOWPLAYING  wheel = volume - select = play/pause - right/left = next/prev
                back returns to menus with music playing
    BLUETOOTH   wheel picks a device - select connects - left/back leaves
    BATTERY / BRIGHTNESS / ABOUT   wheel adjusts/scrolls - left/back leaves

The first press on a dim or sleeping screen only wakes it.
"""
from __future__ import annotations

import random
import time
from collections import deque
from enum import Enum, auto
from typing import Callable, Optional

import pygame

from shared import config, pisugar
from shared import state as state_mod
from shared.hardware import HardwareBundle, Track
from shared.menu_core import MenuController, build_default_menus, extract_play_context
from shared.screen import ABOUT_FEATURES, ABOUT_VISIBLE, SIZE, ScreenRenderer
from shared.screen_dimmer import DimState, ScreenDimmer
from shared.startup import run_startup


class Mode(Enum):
    MENU = auto()
    NOWPLAYING = auto()
    BLUETOOTH = auto()
    BATTERY = auto()
    BRIGHTNESS = auto()
    ABOUT = auto()


class App:
    def __init__(self, hw: HardwareBundle, tracks: list[Track], bluetooth_module,
                 selftest_script: Optional[Callable] = None):
        self.display = hw.display
        self.input = hw.input
        self.haptic = hw.haptic
        self.player = hw.player
        self.tracks = tracks
        self.bt = bluetooth_module
        self.selftest = selftest_script

        self.ctrl = MenuController(build_default_menus(tracks))
        self.renderer = ScreenRenderer()
        self.dimmer = ScreenDimmer(self.display.set_backlight_level,
                                   log=lambda m: print(f"dimmer  {m}"))
        self.mode = Mode.MENU
        self.context: list[int] = []
        self.pos = 0
        self.shuffle = False
        self.brightness = config.DEFAULT_BRIGHTNESS
        self.vol_flash_until = 0.0
        self.about_scroll = 0
        self.bt_devices: list[dict] = []
        self.bt_cursor = 0
        self.bt_connect_info: Optional[dict] = None
        self.bt_connect_start = 0.0

        self.needs_redraw = True
        self._scroll_times: deque = deque()
        self._overlay_was_active = False
        self._last_status: Optional[dict] = None
        self._last_elapsed_int = -1
        self._last_save = time.monotonic()

    # --- status / persistence -------------------------------------------------
    def _status(self) -> dict:
        return {"clock": pisugar.get_time(), "battery": pisugar.get_battery(),
                "charging": pisugar.get_charging()}

    def _save_state(self) -> None:
        track = self.player.track
        state_mod.save({
            "context": self.context,
            "pos": self.pos,
            "shuffle": self.shuffle,
            "track_index": track.index if track else -1,
            "elapsed": round(self.player.elapsed, 2),
            "volume": self.player.volume,
            "brightness": self.brightness,
        })
        self._last_save = time.monotonic()

    def _restore_state(self) -> None:
        data = state_mod.load() or {}
        try:
            volume = int(data.get("volume", config.DEFAULT_VOLUME))
            self.brightness = min(config.BRIGHTNESS_MAX,
                                  max(config.BRIGHTNESS_MIN,
                                      int(data.get("brightness", config.DEFAULT_BRIGHTNESS))))
            self.player.set_volume(volume)
            self.dimmer.set_wake_level(self.brightness / 100)
            ti = int(data.get("track_index", -1))
            if not 0 <= ti < len(self.tracks):
                return
            ctx = data.get("context", [])
            self.context = [i for i in ctx if isinstance(i, int)
                            and 0 <= i < len(self.tracks)] or [ti]
            pos = int(data.get("pos", 0))
            self.pos = pos if 0 <= pos < len(self.context) else 0
            self.shuffle = bool(data.get("shuffle", False))
            self.player.play_track(ti)
            elapsed = float(data.get("elapsed", 0.0))
            if 0 < elapsed < self.tracks[ti].duration:
                self.player.seek_to(elapsed)
        except (TypeError, ValueError):
            pass  # corrupt fields: keep whatever restored cleanly

    # --- playback helpers -------------------------------------------------------
    def _play(self, index: int) -> None:
        self.player.play_track(index)
        self._save_state()

    def _next_track(self) -> None:
        if not self.context:
            return
        if self.shuffle:
            self.pos = random.randrange(len(self.context))
        else:
            self.pos = (self.pos + 1) % len(self.context)
        self._play(self.context[self.pos])

    def _prev_track(self) -> None:
        if not self.context:
            return
        if self.player.elapsed > config.PREV_RESTART_AFTER_S:
            self.player.seek_to(0)  # iPod-style: restart instead of jumping back
        else:
            self.pos = max(0, self.pos - 1)
            self._play(self.context[self.pos])
        self._save_state()

    # --- event handling -----------------------------------------------------------
    def _accel_steps(self) -> int:
        """Encoder acceleration (menus only): fast spinning moves 3 rows/detent."""
        now = time.monotonic()
        self._scroll_times.append(now)
        while self._scroll_times and now - self._scroll_times[0] > config.ACCEL_WINDOW_S:
            self._scroll_times.popleft()
        if config.ENCODER_ACCEL and len(self._scroll_times) > config.ACCEL_DETENTS:
            return config.ACCEL_STEP
        return 1

    def _handle_event(self, ev: str) -> None:
        if ev == "up":
            ev = "scroll_up"
        elif ev == "down":
            ev = "scroll_down"
        handler = {
            Mode.MENU: self._menu_event,
            Mode.NOWPLAYING: self._nowplaying_event,
            Mode.BLUETOOTH: self._bluetooth_event,
            Mode.BATTERY: self._battery_event,
            Mode.BRIGHTNESS: self._brightness_event,
            Mode.ABOUT: self._about_event,
        }[self.mode]
        handler(ev)

    def _menu_event(self, ev: str) -> None:
        if ev in ("scroll_up", "scroll_down"):
            step = self._accel_steps()
            move = self.ctrl.scroll_up if ev == "scroll_up" else self.ctrl.scroll_down
            for _ in range(step):
                move()
            self.haptic.tick()
        elif ev in ("select", "right"):
            result = self.ctrl.select()
            if result in ("enter", "none"):
                self.haptic.click()
            elif result == "back":
                self.haptic.back()
            elif result == "mode":
                self.haptic.click()
                if self.ctrl.last_action == "nowplaying":
                    self.mode = Mode.NOWPLAYING
                elif self.ctrl.last_action == "bluetooth":
                    self._enter_bluetooth()
            elif result == "action":
                self._do_action(self.ctrl.last_action)
        elif ev in ("left", "back"):
            self.haptic.back()
            self.ctrl.back()

    def _do_action(self, act: str) -> None:
        if act.startswith("play:"):
            self.haptic.click()
            index = int(act.split(":", 1)[1])
            name = self.ctrl.current_name
            if name == "songs" or name.startswith(("artist_", "album_")):
                self.context = extract_play_context(self.ctrl.menus[name])
                self.shuffle = False
            if not self.context:
                self.context = [index]
                self.shuffle = False
            self.pos = self.context.index(index) if index in self.context else 0
            self._play(index)
            self.mode = Mode.NOWPLAYING
        elif act == "shuffle":
            self.haptic.click()
            if not self.tracks:
                return
            self.shuffle = True
            self.context = list(range(len(self.tracks)))
            self.pos = random.randrange(len(self.context))
            self._play(self.context[self.pos])
            self.mode = Mode.NOWPLAYING
        elif act == "battery":
            self.haptic.click()
            pisugar.refresh()
            self.mode = Mode.BATTERY
        elif act == "brightness":
            self.haptic.click()
            self.mode = Mode.BRIGHTNESS
        elif act == "about":
            self.haptic.click()
            self.about_scroll = 0
            self.mode = Mode.ABOUT
        else:
            print("ACTION:", act)

    def _nowplaying_event(self, ev: str) -> None:
        if ev == "scroll_up":
            self._nudge_volume(config.VOLUME_STEP)
        elif ev == "scroll_down":
            self._nudge_volume(-config.VOLUME_STEP)
        elif ev == "select":
            self.haptic.click()
            self.player.toggle()
        elif ev == "right":
            self.haptic.click()
            self._next_track()
        elif ev == "left":
            self.haptic.click()
            self._prev_track()
        elif ev == "back":
            self.haptic.back()
            self.mode = Mode.MENU  # v2 fix: music keeps playing

    def _nudge_volume(self, delta: int) -> None:
        self.player.set_volume(self.player.volume + delta)
        self.vol_flash_until = time.monotonic() + config.VOLUME_FLASH_S
        self.haptic.tick()

    def _enter_bluetooth(self) -> None:
        print("Scanning Bluetooth devices…")
        try:
            self.bt_devices = self.bt.scan_devices()
        except Exception as e:  # graceful: a dead adapter must not kill the UI
            print(f"bluetooth: scan failed ({e})")
            self.bt_devices = []
        self.bt_cursor = 0
        self.bt_connect_info = None
        self.mode = Mode.BLUETOOTH

    def _bluetooth_event(self, ev: str) -> None:
        info = self.bt_connect_info
        if ev in ("left", "back"):
            self.haptic.back()
            if info and info["state"] == "connected":
                self.bt_connect_info = None  # back to the device list
            else:
                self.bt_connect_info = None
                self.mode = Mode.MENU
        elif info is None:
            if ev == "scroll_up":
                self.bt_cursor = (self.bt_cursor - 1) % max(1, len(self.bt_devices))
                self.haptic.tick()
            elif ev == "scroll_down":
                self.bt_cursor = (self.bt_cursor + 1) % max(1, len(self.bt_devices))
                self.haptic.tick()
            elif ev in ("select", "right") and self.bt_devices:
                self.haptic.click()
                dev = self.bt_devices[self.bt_cursor]
                self.bt_connect_info = {"name": dev["name"], "address": dev["address"],
                                        "state": "connecting"}
                self.bt_connect_start = time.monotonic()
                try:
                    self.bt.connect_device(dev["address"])
                except Exception as e:
                    print(f"bluetooth: connect failed ({e})")

    def _battery_event(self, ev: str) -> None:
        if ev in ("left", "back"):
            self.haptic.back()
            self.mode = Mode.MENU

    def _brightness_event(self, ev: str) -> None:
        if ev in ("scroll_up", "scroll_down"):
            delta = config.BRIGHTNESS_STEP if ev == "scroll_up" else -config.BRIGHTNESS_STEP
            self.brightness = min(config.BRIGHTNESS_MAX,
                                  max(config.BRIGHTNESS_MIN, self.brightness + delta))
            self.dimmer.set_wake_level(self.brightness / 100)
            self.haptic.tick()
        elif ev in ("select", "right", "left", "back"):
            self.haptic.back()
            self.mode = Mode.MENU

    def _about_event(self, ev: str) -> None:
        max_scroll = max(0, len(ABOUT_FEATURES) - ABOUT_VISIBLE)
        if ev == "scroll_up":
            self.about_scroll = max(0, self.about_scroll - 1)
            self.haptic.tick()
        elif ev == "scroll_down":
            self.about_scroll = min(max_scroll, self.about_scroll + 1)
            self.haptic.tick()
        elif ev in ("left", "back"):
            self.about_scroll = 0
            self.haptic.back()
            self.mode = Mode.MENU

    # --- per-frame updates ------------------------------------------------------
    def _bluetooth_frame(self) -> None:
        info = self.bt_connect_info
        if self.mode is Mode.BLUETOOTH and info and info["state"] == "connecting":
            t = time.monotonic() - self.bt_connect_start
            done = False
            if t > config.BT_CONNECT_MIN_S:
                if t > config.BT_CONNECT_MAX_S:
                    done = True
                else:
                    try:
                        done = self.bt.check_connected(info["address"])
                    except Exception:
                        done = False
            if done:
                info["state"] = "connected"
            self.needs_redraw = True  # animate the spinner / show the change

    def _render(self, surface) -> None:
        st = self._status()
        if self.mode is Mode.MENU:
            self.renderer.draw(surface, self.ctrl.view(), st,
                               playing=self.player.playing)
        elif self.mode is Mode.NOWPLAYING:
            self.renderer.draw_nowplaying(surface, self.player.track, self.player.elapsed,
                                          self.player.playing, self.player.volume, st,
                                          shuffle=self.shuffle)
        elif self.mode is Mode.BLUETOOTH:
            self.renderer.draw_bluetooth(surface, self.bt_devices, self.bt_cursor,
                                         self.bt_connect_info, st)
        elif self.mode is Mode.BATTERY:
            self.renderer.draw_battery_screen(surface, st)
        elif self.mode is Mode.BRIGHTNESS:
            self.renderer.draw_brightness_screen(surface, self.brightness, st)
        elif self.mode is Mode.ABOUT:
            self.renderer.draw_about_screen(surface, self.about_scroll, st)
        if time.monotonic() < self.vol_flash_until:
            self.renderer.draw_volume_overlay(surface, self.player.volume)

    # --- main loop ------------------------------------------------------------------
    def run(self) -> None:
        pisugar.start_polling()
        surface = pygame.Surface((SIZE, SIZE))
        run_startup(surface, self.display, self.haptic, self.ctrl, self.renderer,
                    self._status)
        self.dimmer.start()
        self._restore_state()
        # forced initial frame: never wait for the first input to draw the menu
        self._render(surface)
        self.display.push_frame(surface)
        self.needs_redraw = False
        clock = pygame.time.Clock()

        while True:
            now = time.monotonic()
            for ev in self.input.read():
                if ev == "quit":
                    self._save_state()
                    pygame.quit()
                    return
                # dimmer gate: the first press on a dark screen only wakes it
                was_dark = self.dimmer.state is not DimState.AWAKE
                self.dimmer.wake()
                self.needs_redraw = True
                if was_dark:
                    continue
                self._handle_event(ev)

            # auto-advance, then the player's own bookkeeping
            if self.player.track_finished:
                self._next_track()
                self.needs_redraw = True
            self.player.tick()
            self._bluetooth_frame()

            status = self._status()
            if status != self._last_status:
                self._last_status = status
                self.needs_redraw = True
            if self.dimmer.consume_wake():
                self.needs_redraw = True
            if self.display.consume_level_change():
                self.needs_redraw = True
            if self.mode is Mode.NOWPLAYING and self.player.playing:
                whole = int(self.player.elapsed)
                if whole != self._last_elapsed_int:
                    self._last_elapsed_int = whole
                    self.needs_redraw = True
            overlay_active = now < self.vol_flash_until
            if overlay_active or self._overlay_was_active:
                self.needs_redraw = True  # active, or expired this frame
            self._overlay_was_active = overlay_active

            if self.player.playing and now - self._last_save > config.AUTOSAVE_INTERVAL_S:
                self._save_state()

            if self.needs_redraw:
                self._render(surface)
                self.display.push_frame(surface)
                self.needs_redraw = False
                if config.DEBUG:
                    print("redraw", self.mode.name)

            if self.selftest:
                self.selftest(self)
                clock.tick(0)  # uncapped
            else:
                clock.tick(config.FPS)


def run(hw: HardwareBundle, tracks: list[Track], bluetooth_module, *,
        selftest_script: Optional[Callable] = None) -> None:
    App(hw, tracks, bluetooth_module, selftest_script).run()
