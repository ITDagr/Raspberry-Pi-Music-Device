"""device v2 — the main loop and mode state machine (runs on Mac and Pi).

Entry point: run(hw, tracks, bluetooth_module). One 30 fps loop with
dirty-flag rendering; all hardware arrives injected via HardwareBundle.

Modes and controls:
    MENU        wheel moves the cursor - select/right activates - left/back up a level
    NOWPLAYING  wheel = volume - select = play/pause - right/left = next/prev
                back returns to menus with music playing
    BLUETOOTH   wheel picks a device - select connects - left/back leaves
    BATTERY / BRIGHTNESS / ABOUT   wheel adjusts/scrolls - left/back leaves

While the screen is dim or asleep only the center button does anything: it
wakes the screen and is swallowed. The Beret's slide switch (GPIO 13 / the
P key on Mac) is a soft power switch — OFF saves state, stops playback and
sleeps the screen; ON boots like a cold start and resumes playback.
"""
from __future__ import annotations

import random
import threading
import time
from collections import deque
from enum import Enum, auto
from typing import Callable, Optional

import pygame

from shared import config, pisugar
from shared import state as state_mod
from shared.hardware import AlwaysOnPowerSwitch, HardwareBundle, Track
from shared.menu_core import MenuController, build_default_menus, extract_play_context
from shared.screen import (ABOUT_FEATURES, ABOUT_VISIBLE, NOWPLAYING_TICK_RECT,
                           SIZE, STATUS_BAR_RECT, ScreenRenderer)
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
                 selftest_script: Optional[Callable] = None,
                 web_events=None):
        self.web_events = web_events  # queue.Queue fed by the web app thread
        self.display = hw.display
        self.input = hw.input
        self.haptic = hw.haptic
        self.player = hw.player
        self.power = hw.power or AlwaysOnPowerSwitch()
        self.tracks = tracks
        self.bt = bluetooth_module
        self.selftest = selftest_script
        self.boots = 0  # startup-animation runs (boot + every soft-off resume)

        self.ctrl = MenuController(build_default_menus(tracks))
        self.renderer = ScreenRenderer()
        self.dimmer = ScreenDimmer(self.display.set_backlight_level,
                                   log=lambda m: print(f"dimmer  {m}"))
        self.mode = Mode.MENU
        self.context: list[str] = []   # stable track ids, never indices
        self.pos = 0
        self._id_to_index: dict[str, int] = {}
        self._reindex()
        self.toast_msg = ""
        self.toast_until = 0.0
        self.shuffle = False
        self.brightness = config.DEFAULT_BRIGHTNESS
        self.vol_flash_until = 0.0
        self.about_scroll = 0
        self.bt_devices: list[dict] = []
        self.bt_cursor = 0
        self.bt_connect_info: Optional[dict] = None
        self.bt_connect_start = 0.0
        self.bt_scanning = False
        self._bt_scan_gen = 0          # bumped to cancel an in-flight scan
        self._bt_scan_result: Optional[tuple[int, list[dict]]] = None

        self.needs_redraw = True       # full-frame flag; wins over partials
        self._partial_rects: list[pygame.Rect] = []
        self.loop_hz = config.FPS      # rate chosen for the current frame
        self._scroll_times: deque = deque()
        self._overlay_was_active = False
        self._toast_was_active = False
        self._last_status: Optional[dict] = None
        self._last_elapsed_int = -1
        self._last_save = time.monotonic()

    # --- dirty tracking ---------------------------------------------------------
    def _mark_full(self) -> None:
        self.needs_redraw = True
        self._partial_rects.clear()

    def _mark_partial(self, rect: pygame.Rect) -> None:
        """Queue a small region push; a queued full frame always wins."""
        if not self.needs_redraw:
            self._partial_rects.append(rect)

    # --- status / persistence -------------------------------------------------
    def _status(self) -> dict:
        return {"clock": pisugar.get_time(), "battery": pisugar.get_battery(),
                "charging": pisugar.get_charging()}

    # --- track identity ---------------------------------------------------------
    def _reindex(self) -> None:
        self._id_to_index = {t.id: t.index for t in self.tracks}

    def _index_of(self, tid: str) -> Optional[int]:
        return self._id_to_index.get(tid)

    def _resolve_position(self, old_ctx: list, old_pos: int) -> tuple[list[str], Optional[int]]:
        """Prune `old_ctx` to surviving ids and find where to stand: the
        first survivor at/after old_pos (wrapping, to match _next_track's
        modulo advance). (pruned, None) when nothing survives."""
        ctx = [t for t in old_ctx if isinstance(t, str) and t in self._id_to_index]
        if not ctx:
            return [], None
        old_pos = max(0, min(old_pos, len(old_ctx) - 1)) if old_ctx else 0
        for tid in list(old_ctx[old_pos:]) + list(old_ctx[:old_pos]):
            if isinstance(tid, str) and tid in self._id_to_index:
                return ctx, ctx.index(tid)
        return ctx, None

    def _toast(self, message: str) -> None:
        self.toast_msg = message
        self.toast_until = time.monotonic() + config.TOAST_S
        self._mark_full()

    def _playlists_changed(self) -> None:
        """The playlist manifest changed (web app): rebuild the menus so
        Music -> Playlists reflects it, keeping the navigation path."""
        self.ctrl.rebuild(build_default_menus(self.tracks))
        self._mark_full()

    def apply_library(self, new_tracks: list) -> None:
        """The library changed at runtime (web app upload/delete/retag):
        swap TRACKS in place, rebuild menus preserving the navigation path,
        re-resolve the id-based context, and never keep playing a ghost."""
        playing = self.player.track
        playing_id = playing.id if playing else None
        self.tracks[:] = new_tracks
        self._reindex()
        self.ctrl.rebuild(build_default_menus(self.tracks))
        self.context, pos = self._resolve_position(self.context, self.pos)
        self.pos = pos if pos is not None else 0
        if playing_id is not None and playing_id not in self._id_to_index:
            # the playing file was deleted out from under us
            if self.context:
                self._play(self.context[self.pos])
                self._toast("Track removed — playing next")
            else:
                self.player.stop()
                self._toast("Track removed")
        self._mark_full()

    def _save_state(self) -> None:
        track = self.player.track
        state_mod.save({
            "context": self.context,
            "pos": self.pos,
            "shuffle": self.shuffle,
            "track_id": track.id if track else "",
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
            tid = data.get("track_id", "")
            if not isinstance(tid, str) or not tid:
                return
            saved_ctx = data.get("context", [])
            if not isinstance(saved_ctx, list) or tid not in saved_ctx:
                saved_ctx = [tid]
            saved_pos = int(data.get("pos", 0))
            self.shuffle = bool(data.get("shuffle", False))
            self.context, pos = self._resolve_position(saved_ctx, saved_pos)
            if pos is None:
                self.pos = 0
                return  # nothing saved survives: stopped
            self.pos = pos
            survivor = self.context[pos]
            index = self._index_of(survivor)
            self.player.play_track(index)
            if survivor == tid:  # same song: resume mid-track
                elapsed = float(data.get("elapsed", 0.0))
                if 0 < elapsed < self.tracks[index].duration:
                    self.player.seek_to(elapsed)
        except (TypeError, ValueError):
            pass  # corrupt fields: keep whatever restored cleanly

    # --- playback helpers -------------------------------------------------------
    def _play(self, tid: str) -> None:
        index = self._index_of(tid)
        if index is None:
            return  # pruned between selection and play: ignore
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
            tid = self.tracks[index].id
            name = self.ctrl.current_name
            if name == "songs" or name.startswith(("artist_", "album_",
                                                   "playlist_")):
                self.context = [self.tracks[i].id for i in
                                extract_play_context(self.ctrl.menus[name])]
                self.shuffle = False
            if not self.context:
                self.context = [tid]
                self.shuffle = False
            self.pos = self.context.index(tid) if tid in self.context else 0
            self._play(tid)
            self.mode = Mode.NOWPLAYING
        elif act == "shuffle":
            self.haptic.click()
            if not self.tracks:
                return
            self.shuffle = True
            self.context = [t.id for t in self.tracks]
            self.pos = random.randrange(len(self.context))
            self._play(self.context[self.pos])
            self.mode = Mode.NOWPLAYING
        elif act.startswith("plshuffle:"):
            # shuffle within one playlist: its order is the context, the
            # cursor lands anywhere in it
            menu_name = act.split(":", 1)[1]
            menu = self.ctrl.menus.get(menu_name)
            ids = [self.tracks[i].id for i in
                   extract_play_context(menu)] if menu else []
            if not ids:
                return
            self.haptic.click()
            self.shuffle = True
            self.context = ids
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
        """Kick off the scan on a thread: the spinner shows immediately and
        the loop never blocks on the (Pi: ~6 s) bluetoothctl window."""
        print("Scanning Bluetooth devices…")
        self.bt_devices = []
        self.bt_cursor = 0
        self.bt_connect_info = None
        self.bt_scanning = True
        self._bt_scan_gen += 1
        gen = self._bt_scan_gen
        self.mode = Mode.BLUETOOTH

        def scan() -> None:
            try:
                devices = self.bt.scan_devices()
            except Exception as e:  # graceful: a dead adapter must not kill the UI
                print(f"bluetooth: scan failed ({e})")
                devices = []
            # handed to the main thread; _bluetooth_frame applies it
            self._bt_scan_result = (gen, devices)

        threading.Thread(target=scan, daemon=True, name="bt-scan").start()

    def _bluetooth_event(self, ev: str) -> None:
        info = self.bt_connect_info
        if ev in ("left", "back"):
            self.haptic.back()
            if info and info["state"] == "connected":
                self.bt_connect_info = None  # back to the device list
            else:
                self.bt_connect_info = None
                if self.bt_scanning:  # cancel: a late result is discarded
                    self.bt_scanning = False
                    self._bt_scan_gen += 1
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
        result = self._bt_scan_result
        if result is not None:
            gen, devices = result
            self._bt_scan_result = None
            if gen == self._bt_scan_gen:  # not cancelled meanwhile
                self.bt_scanning = False
                self.bt_devices = devices
                self._mark_full()
        if self.mode is Mode.BLUETOOTH and self.bt_scanning:
            self._mark_full()  # animate the scanning spinner
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
            self._mark_full()  # animate the spinner / show the change

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
                                         self.bt_connect_info, st,
                                         scanning=self.bt_scanning)
        elif self.mode is Mode.BATTERY:
            self.renderer.draw_battery_screen(surface, st)
        elif self.mode is Mode.BRIGHTNESS:
            self.renderer.draw_brightness_screen(surface, self.brightness, st)
        elif self.mode is Mode.ABOUT:
            self.renderer.draw_about_screen(surface, self.about_scroll, st)
        if time.monotonic() < self.vol_flash_until:
            self.renderer.draw_volume_overlay(surface, self.player.volume)
        if time.monotonic() < self.toast_until:
            self.renderer.draw_toast(surface, self.toast_msg)

    # --- soft power -------------------------------------------------------------
    def _boot(self, surface) -> None:
        """Startup animation + state restore + forced first frame — the same
        sequence for a cold boot and a soft-off resume."""
        self.boots += 1
        run_startup(surface, self.display, self.haptic, self.ctrl, self.renderer,
                    self._status)
        self._restore_state()
        self._render(surface)
        self.display.push_frame(surface)
        self.needs_redraw = False
        self._partial_rects.clear()

    def _soft_off_wait(self) -> str:
        """Idle while soft-off: poll only the switch at ~4 Hz. All input is
        drained and discarded — center button included — except 'quit', which
        must always work on the Mac (Esc / window close). Returns 'on'|'quit'."""
        poll_s = 1.0 / config.SOFT_OFF_POLL_HZ
        while True:
            for ev in self.input.read():
                if ev == "quit":
                    return "quit"
            if self.power.is_on():
                return "on"
            if self.selftest:
                self.selftest(self)
                time.sleep(0.01)  # scripted: fast, but never a hard spin
            else:
                time.sleep(poll_s)

    def _soft_off(self, surface) -> str:
        """Slide switch flipped OFF while running: save everything, stop
        playback, screen fully off, then wait. Flipping back ON re-runs the
        normal boot sequence (animation + state restore)."""
        self._save_state()
        if self.player.playing:
            self.player.toggle()
        if config.POWER_SWITCH_ACTION == "shutdown" and not config.IS_MAC:
            # near-zero draw, but GPIO 13 cannot re-boot a halted Pi — the
            # config comment spells out when this is safe to choose
            print("power: shutdown (POWER_SWITCH_ACTION)")
            self.display.set_backlight_level(0.0)
            self.display.sleep()
            import subprocess
            subprocess.call(["sudo", "-n", "systemctl", "poweroff"])
            return "quit"
        print("power: soft off")
        self.dimmer.suspend()
        self.display.set_backlight_level(0.0)
        self.display.sleep()
        if self._soft_off_wait() == "quit":
            return "quit"
        print("power: on")
        self.display.wake()
        self.dimmer.resume()
        # boot from scratch: fresh menus, MENU mode, animation, restore
        self.ctrl = MenuController(build_default_menus(self.tracks))
        self.mode = Mode.MENU
        self._boot(surface)
        return "on"

    # --- main loop ------------------------------------------------------------------
    def run(self) -> None:
        pisugar.start_polling()
        # depth=24: a plain Surface inherits the display format, which on
        # macOS carries an alpha channel that SDL's text/alpha blits mangle
        # into solid boxes. An explicit RGB canvas sidesteps that entirely.
        surface = pygame.Surface((SIZE, SIZE), depth=24)
        if not self.power.is_on():
            # booted with the switch OFF: no startup animation, stay dark
            self.display.set_backlight_level(0.0)
            self.display.sleep()
            if self._soft_off_wait() == "quit":
                pygame.quit()
                return
            self.display.wake()
            self.display.set_backlight_level(self.dimmer.wake_level)
        self._boot(surface)
        self.dimmer.start()
        clock = pygame.time.Clock()

        while True:
            now = time.monotonic()
            if not self.power.is_on():
                if self._soft_off(surface) == "quit":
                    pygame.quit()
                    return
            for ev in self.input.read():
                if ev == "quit":
                    self._save_state()
                    pygame.quit()
                    return
                if self.dimmer.state is not DimState.AWAKE:
                    # dark screen: only the center button does anything — it
                    # wakes, and the waking press is swallowed (no select)
                    if ev == "select":
                        self.dimmer.wake()
                        self._mark_full()
                    continue
                self.dimmer.wake()
                self._mark_full()
                self._handle_event(ev)

            # library changes arriving from the web app thread
            if self.web_events is not None:
                while True:
                    try:
                        ev = self.web_events.get_nowait()
                    except Exception:
                        break
                    if ev.get("tracks") is not None:
                        self.apply_library(ev["tracks"])
                    if ev.get("playlists"):
                        self._playlists_changed()
                    if ev.get("msg"):
                        self._toast(ev["msg"])

            # auto-advance, then the player's own bookkeeping
            if self.player.track_finished:
                self._next_track()
                self._mark_full()
            self.player.tick()
            self._bluetooth_frame()

            overlay_active = now < self.vol_flash_until
            status = self._status()
            if status != self._last_status:
                self._last_status = status
                # a clock/battery tick only repaints the status bar strip;
                # other screens echo status in the body, so repaint fully
                if self.mode in (Mode.MENU, Mode.NOWPLAYING) and not overlay_active:
                    self._mark_partial(STATUS_BAR_RECT)
                else:
                    self._mark_full()
            if self.dimmer.consume_wake():
                self._mark_full()
            if self.display.consume_level_change():
                self._mark_full()
            if self.mode is Mode.NOWPLAYING and self.player.playing:
                whole = int(self.player.elapsed)
                if whole != self._last_elapsed_int:
                    self._last_elapsed_int = whole
                    if overlay_active:  # overlay dims the whole frame: full
                        self._mark_full()
                    else:
                        self._mark_partial(NOWPLAYING_TICK_RECT)
            # the overlay itself is static while visible (volume changes are
            # events -> full); only its expiry needs a repaint underneath
            if self._overlay_was_active and not overlay_active:
                self._mark_full()
            self._overlay_was_active = overlay_active
            toast_active = now < self.toast_until
            if self._toast_was_active and not toast_active:
                self._mark_full()  # toast expired: repaint beneath it
            self._toast_was_active = toast_active

            if self.player.playing and now - self._last_save > config.AUTOSAVE_INTERVAL_S:
                self._save_state()

            if self.needs_redraw or self._partial_rects:
                self._render(surface)
                # partial pushes only while fully awake — DIM/SLEEP levels go
                # through full frames so the Mac's dim compositing stays exact
                if not self.needs_redraw and self.dimmer.state is DimState.AWAKE:
                    seen: set = set()
                    for rect in self._partial_rects:
                        key = (rect.x, rect.y, rect.w, rect.h)
                        if key not in seen:
                            seen.add(key)
                            self.display.push_region(surface, rect)
                    if config.DEBUG:
                        print("redraw (partial)", self.mode.name)
                else:
                    self.display.push_frame(surface)
                    if config.DEBUG:
                        print("redraw", self.mode.name)
                self.needs_redraw = False
                self._partial_rects.clear()

            # adaptive loop rate: nobody feels 10/2 Hz on a dim/dark screen
            if self.dimmer.state is DimState.AWAKE:
                self.loop_hz = config.FPS
            elif self.dimmer.state is DimState.DIM:
                self.loop_hz = config.FPS_DIM
            else:
                self.loop_hz = config.FPS_SLEEP
            if self.selftest:
                self.selftest(self)
                clock.tick(0)  # uncapped
            else:
                clock.tick(self.loop_hz)


def run(hw: HardwareBundle, tracks: list[Track], bluetooth_module, *,
        selftest_script: Optional[Callable] = None, web_events=None) -> None:
    App(hw, tracks, bluetooth_module, selftest_script, web_events).run()
