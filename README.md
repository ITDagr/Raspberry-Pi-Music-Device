# device v2 — pocket music player

A Raspberry Pi pocket music player (rotary wheel, 240×240 TFT, haptics,
PiSugar battery, MPD audio) with a pixel-identical Mac simulator. v2 is a
clean-room rewrite of v1: **one shared main loop** in `shared/`, with `mac/`
and `pi/` providing only hardware implementations and ~30-line launchers.

```
shared/   app loop, menus, renderer, dimmer, state, pisugar   (runs unchanged on both)
mac/      pygame window, keyboard, terminal haptics, synth library, mixer player
pi/       ST7789 SPI display, ANO/seesaw input, DRV2605L, MPD player, bluetoothctl
tests/    pytest for the pure-logic modules
```

## Mac quickstart

```sh
python3 -m venv .venv && . .venv/bin/activate     # Python >= 3.10
pip install -r requirements-mac.txt               # pygame (+ pytest for tests)
python3 mac/prototype.py
```

A 480×480 window ("prototype  —  device simulator") opens after the boot
animation. ~60 short synthetic chip-tunes are generated into `mac/_audio/` on
first run (a few seconds, cached afterwards).

| Key            | Wheel/button      | Does |
|----------------|-------------------|------|
| ↑ / ↓          | wheel detents     | menus: cursor · now playing: volume · brightness/about: adjust |
| Enter / Space  | center press      | select / play-pause |
| →              | right             | select (menus) · next track |
| ←              | left              | back (menus) · previous track (iPod-style: restarts if >3 s in) |
| Backspace      | center hold 600 ms| back — leaves the current screen everywhere |
| Esc / close    | —                 | quit (state saved) |

The screen dims to 15 % after 20 s idle and sleeps after 60 s; the first key
press only wakes it. Verify everything headlessly:

```sh
python3 mac/prototype.py --selftest   # scripted end-to-end run, exit 0 = pass
pytest -q
python -m compileall shared mac pi
```

## Pi setup (Pi Zero 2 W, Pi OS Bookworm Lite)

1. `raspi-config` → enable **SPI** and **I2C**.
2. `sudo apt install python3-pygame python3-numpy python3-spidev python3-rpi.gpio mpd mpc bluez`
   then `pip3 install adafruit-blinka adafruit-circuitpython-seesaw
   adafruit-circuitpython-drv2605 python-mpd2` (or `pip3 install -r requirements-pi.txt`).
3. Clone this repo to `/home/pi/device`, drop music into MPD's music dir,
   `mpc update`.
4. Test: `python3 pi/device.py` — then install the service:

```sh
sudo cp systemd/device.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now device
```

### Wiring (defaults — every pin lives in `shared/config.py`)

| Component | Interface | Defaults |
|---|---|---|
| ST7789V 1.3" 240×240 TFT | SPI0 @ 62.5 MHz | CS=CE0/GPIO8 · DC=GPIO25 · RST=GPIO27 · BL=GPIO18 |
| Backlight | PWM on BL | 1 kHz, duty = level×100 |
| ANO encoder (seesaw) | I²C `0x49` | buttons: select=1 up=2 left=3 down=4 right=5 (verify vs. Adafruit ANO guide) |
| DRV2605L + LRA | I²C `0x5A` | LRA mode, LRA ROM library — tick=14 click=1 back=7 pulse=47 |
| PiSugar 2/3 | TCP `127.0.0.1:8423` | `get battery`, `get rtc_time` (silent fallback if absent) |
| MPD | `localhost:6600` | music dir per `/etc/mpd.conf` |
| Bluetooth | `bluetoothctl` | scan/pair/connect audio sinks |

If your 240×240 panel shows a shifted image, set `DISPLAY_X/Y_OFFSET` in
`shared/config.py`; if the wheel scrolls backwards, flip `ENCODER_REVERSED`.

### Routing MPD → Bluetooth (README task, not code)

The app pairs/connects the sink; audio routing is MPD configuration:

- **PipeWire (Bookworm default):** MPD's `pulse` output follows the default
  sink — `wpctl set-default <bt-sink-id>` after connecting, or add an
  `audio_output { type "pulse" ... }` block to `/etc/mpd.conf`.
- **bluealsa:** add
  `audio_output { type "alsa" name "BT" device "bluealsa:DEV=XX:XX:...,PROFILE=a2dp" }`
  and `mpc enable` it.

## Design notes

- **Contracts** (`shared/hardware.py`): `Display`, `InputSource`, `Haptic`,
  `Player` Protocols + `Track`; `shared/app.run(hw, tracks, bluetooth_module)`
  is the single entry point for both targets.
- **State** (`shared/state.py`): atomic JSON (tmp + `os.replace`) at
  `.device_state.json` (repo root on Mac, `/home/pi/` on Pi). Autosaved every
  10 s while playing, on every track change, and on quit; track, position,
  volume and brightness are restored at boot.
- **v2 improvements over v1** (the full list): single shared loop; `back`
  works in every mode (NOWPLAYING returns to menus with music playing);
  iPod-style previous; encoder acceleration in menus (>6 detents/s → 3
  rows/detent, flag `ENCODER_ACCEL`); autosave incl. elapsed/volume/
  brightness; atomic writes; type hints + dataclasses + `config.DEBUG`;
  graceful degradation everywhere (a dead motor/MPD/BT adapter logs once and
  the UI keeps running).

## Assumptions

Decisions made where the spec left room:

1. **Mac state path** is anchored to the repo root (`<repo>/.device_state.json`)
   rather than the process cwd, so relaunching from anywhere resumes correctly.
2. **Selftest tweaks:** the boot animation is shortened to 0.2 s and encoder
   acceleration is disabled during `--selftest` — scripted detents arrive far
   faster than real ones and would otherwise trip the 3-rows-per-detent
   accelerator and the 10 s budget. Normal runs use 1.8 s and acceleration on.
3. **Playback contexts** follow menu order: the songs context is the songs
   menu's (artist, title) order; artist/album contexts are their menus' order.
4. **Track finish on Mac** is detected from monotonic bookkeeping
   (`elapsed >= duration`) instead of `mixer.music.get_busy()` — deterministic
   and correct under `SDL_AUDIODRIVER=dummy`. Durations are sample-exact.
5. **WAV seeking:** pygame can't seek WAVs, so restore/prev-restart restarts
   the audio while the progress bookkeeping keeps the requested offset (the
   spec's endorsed fallback). On the Pi, MPD `seekcur` seeks for real.
6. **Boot resume auto-plays** the saved track at the saved offset (the spec
   says "resumes"), starting in MENU/home.
7. **Synth music:** the "2-oscillator chip-tune" alternates a melody square
   and a bass square on eighth-notes (pentatonic, seeded per track) — keeps
   generation pure-stdlib and under ~3 s for the whole catalog.
8. **Status dict** carries a third key, `charging` (from PiSugar
   `battery_charging`, `None` on Mac), so the battery screen can show its
   "charging" note; clock/battery behavior is otherwise exactly as specced.
9. **Bluetooth spinner** forces a redraw every frame while state is
   "connecting" so it visibly spins; the spec's dirty-flag list only covered
   state *changes*.
10. **Volume overlay** draws on top of whatever screen is active while its
    1.5 s timer runs (spec-literal), even if you back out of Now Playing.
11. **Menu labels** show track titles only (no artist suffix); albums are
    deduped per (artist, album) and listed by album title.
12. **Empty-menu select** returns `"none"` (click haptic, no-op), so an empty
    MPD library still boots to a navigable UI.
13. **PiSugar clock** stores the RTC-to-system offset at each poll and applies
    it in `get_time()`, so the minutes advance between 30 s polls.
14. **Dimmer transitions always print** (per §6); all other chatty prints sit
    behind `config.DEBUG`.
15. **Verification ran on Python 3.12** (uv-managed venv); code targets ≥3.10.
