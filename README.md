# pimusicdevice

A pocket music player: Raspberry Pi Zero 2 W, a 240×240 TFT, a click-wheel
(ANO rotary encoder), real haptics, a PiSugar battery, and MPD audio — with
a **pixel-identical Mac simulator** for development. One shared main loop
runs on both targets; `mac/` and `pi/` provide only hardware drivers and
~30-line launchers.

```
shared/    app loop, menus, renderer (v1 "DETENT" design), dimmer, state, pisugar
mac/       pygame window, keyboard, terminal haptics, synth library, mixer player
pi/        ST7789 SPI display, ANO/seesaw input, DRV2605L, MPD player, bluetoothctl
tests/     pytest (logic + pixel render tests)
tools/     dev utilities (v1 frame renders for design comparison)
systemd/   pimusicdevice.service (start on boot)
docs/      the guides ↓
```

## Guides

| Guide | Covers |
|---|---|
| [docs/install-mac.md](docs/install-mac.md) | run the simulator on a Mac, verify the install |
| [docs/install-pi.md](docs/install-pi.md) | full Pi setup: OS, interfaces, deps, MPD, systemd |
| [docs/hardware.md](docs/hardware.md) | parts list, wiring tables, physical controls |
| [docs/usage.md](docs/usage.md) | controls, every screen, dimming, saved state |
| [docs/bluetooth-audio.md](docs/bluetooth-audio.md) | pairing + routing MPD to Bluetooth sinks |
| [docs/development.md](docs/development.md) | architecture, gates, design system, adding screens |
| [docs/troubleshooting.md](docs/troubleshooting.md) | symptoms → fixes, both targets |

## Quickstart (Mac)

```sh
python3 -m venv .venv && source .venv/bin/activate   # Python >= 3.10
pip install -r requirements-mac.txt
python3 mac/prototype.py
```

↑/↓ wheel · Enter select · →/← next-prev/select-back · Backspace back ·
Esc quit. Verify with `python3 mac/prototype.py --selftest` and `pytest -q`.

## Quickstart (Pi)

Wire per [docs/hardware.md](docs/hardware.md), then follow
[docs/install-pi.md](docs/install-pi.md). Short version: enable SPI+I2C,
install deps + MPD, clone to `/home/pi/pimusicdevice`,
`python3 pi/device.py`, then install `systemd/pimusicdevice.service`.

## Display: EYESPI Pi Beret + 1.54" TFT

The screen is the **Adafruit 1.54" 240×240 wide-angle IPS TFT (ST7789,
EYESPI connector)** attached through the **Adafruit EYESPI Pi Beret
(#5783)** with an 18-pin EYESPI FPC cable. There is no manual display
wiring — the Beret is a HAT and fixes every pin:

| Signal | Pi pin (fixed by the Beret) |
|---|---|
| Display CS | SPI0 CE0 |
| Display DC | GPIO 25 |
| Display Reset | GPIO 27 |
| Backlight | GPIO 18 (PWM; the Beret's backlight jumper is assumed intact) |
| Touch CS / Touch IRQ | CE1 / GPIO 24 (unused here) |
| Display Busy | GPIO 17 (e-ink only, unused) |
| STEMMA QT | the Pi's default I²C bus (bus 1) |

**Panel parameters** live in `DISPLAY_PROFILES` in `shared/config.py`,
selected by `DISPLAY_PROFILE` (default `adafruit_154_240x240`): 240×240,
`x_offset=0`, `y_offset=80`, `rotation=180`, inversion on — Adafruit's
canonical init for this panel. The ST7789's RAM is 240×320, so wrong
offsets show up as an 80-pixel garbage band or a wrapped image. An
`adafruit_13_240x240` profile is kept for the older 1.3" panel.

**SPI speed:** 62.5 MHz by default (~15 ms per full frame). At 24 MHz a
frame takes ~38 ms, capping the UI at ~26 fps and making scrolling feel
mushy. If the display shows artifacts at 62.5 MHz, set the profile's
`baudrate` to `SPI_SPEED_FALLBACK_HZ` (24 MHz).

**Display test:** `python3 pi/device.py --display-test` renders a static
pattern — a 1-pixel border on all four edges, TL/TR/BL/BR corner labels,
an UP arrow, and labeled pure R/G/B bars — then holds. Any offset,
rotation, or color-order mistake is visible in one second. The same
pattern is pixel-checked by `tests/test_render.py` on the Mac.

## Power model: center-button wake + soft power switch

- **Waking the screen:** while the screen is dim or asleep, only a center
  press does anything — it wakes the screen and is swallowed. Rotation and
  every other button are ignored on a dark screen (no hidden actions, no
  haptics). Music keeps playing with the screen off.
- **The Beret's slide switch (GPIO 13) is a *soft* power switch.** Per
  Adafruit it is just a GPIO input, so "off" happens in software: flipping
  OFF saves the full state, stops playback, blanks and sleeps the panel,
  and drops into an idle loop that polls only the switch at ~4 Hz —
  every input including the center button is ignored. Flipping ON runs
  the startup animation and restores state exactly like a normal boot,
  resuming playback at the saved position. Booting with the switch OFF
  stays dark (no animation) until it flips ON.
- On the Mac, the **P** key is the switch (state prints to the terminal);
  Esc / window-close still quits even while dark or soft-off.

## I²C topology

Everything I²C lives on the Pi's default **bus 1**, exposed by the Beret's
STEMMA QT port. Two wirings, identical electrically and to the software:

- **Default:** the ANO encoder's STEMMA QT cable plugs **directly into the
  Beret's STEMMA QT port**.
- **With the Adafruit 5-Port STEMMA QT Hub (#5625):** the hub is a
  **passive splitter** — all five ports share the same power, GND, SDA and
  SCL — so Beret → hub → devices is the same bus with the same addresses.
  **Zero code changes**; the software just opens `config.I2C_BUS = 1` and
  talks to addresses.

| Address | Device | Notes |
|---|---|---|
| `0x49` | ANO encoder (seesaw) | required; address jumpers exist if it must move |
| `0x5A` | DRV2605L haptics | fixed address; optional |
| `0x57` | PiSugar battery | only if attached; optional |
| `0x68` | PiSugar RTC | only if attached; optional |

No collisions, and the hub leaves headroom for future STEMMA QT devices —
the only rule is that every device on the bus needs a **unique address**.
At boot the device verifies the encoder ACKs at `0x49`; if it doesn't, it
exits with a message listing everything found on the bus. Diagnose with
`i2cdetect -y 1` or `python3 tools/i2c_scan.py`.

## Optional peripherals: haptics and PiSugar

The device runs fully with **only the display and encoder attached**.

- **Haptics (DRV2605L, I²C `0x5A`):** probed once at boot; on any failure
  (library missing, no ACK) a `NullHaptic` with no-op effects is installed
  and one line is logged ("haptics: not detected — continuing without").
  App code calls `haptic.tick()/click()/back()/pulse()` unconditionally —
  there are no `if haptic:` checks, and runtime I²C errors are wrapped too,
  so a motor unplugged mid-run cannot crash the UI.
- **PiSugar (TCP `127.0.0.1:8423`):** one boot-time probe with a short
  timeout. Absent → offline mode: the clock is the system clock, the
  battery reads "--" everywhere, `refresh()` is a no-op, and the only
  traffic is a silent re-probe every 5 minutes. No retry storms, no log
  spam. The Mac simulator runs this exact code path on every launch.

The selftest forces both probes to fail and asserts a clean boot, working
navigation, and the "--" battery.

## Design notes

- **Contracts** (`shared/hardware.py`): `Display`, `InputSource`, `Haptic`,
  `Player` Protocols + `Track`; `shared/app.run(hw, tracks, bluetooth_module)`
  is the single entry point for both targets.
- **State** (`shared/state.py`): atomic JSON at `.device_state.json`
  (repo root on Mac, `/home/pi/` on Pi), autosaved every 10 s while playing,
  on track changes, and on quit; track/position/volume/brightness restore at
  boot.
- **v2 improvements over v1**: single shared loop; `back` works in every
  mode (Now Playing returns to menus with music playing); iPod-style
  previous; encoder acceleration in menus (>6 detents/s → 3 rows/detent);
  autosave incl. elapsed/volume/brightness; atomic writes; type hints +
  dataclasses + `config.DEBUG`; graceful degradation everywhere.
- **Visuals**: v1's "DETENT" system ported wholesale — see
  [docs/development.md](docs/development.md).

## Assumptions

Decisions made where the spec left room:

1. **Mac state path** is anchored to the repo root (`<repo>/.device_state.json`)
   rather than the process cwd, so relaunching from anywhere resumes correctly.
2. **Selftest tweaks:** the boot animation is shortened to 0.2 s and encoder
   acceleration is disabled during `--selftest` — scripted detents arrive far
   faster than real ones and would otherwise trip the 3-rows-per-detent
   accelerator and the 10 s budget. Normal runs use the full animation and
   acceleration on.
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
   "Charging" caption; clock/battery behavior is otherwise exactly as specced.
9. **Bluetooth connecting** forces a redraw every frame while state is
   "connecting" so its indicator stays live; the spec's dirty-flag list only
   covered state *changes*.
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
16. **v1 design port:** v2's visuals are v1's "DETENT" system (tokens, grid,
    status bar with equalizer bars, pill rows with accent edge + chevrons,
    knobbed sliders, scroll rails, ARIA boot choreography) adapted to v2's
    MenuView/Display contracts. Deliberate deltas: fonts are pygame's bundled
    `Font(None)` scaled 1.38× to match Arial's optical size (SysFont is banned
    for headless reliability); v1's `✓`/`☀` glyphs — which render as tofu
    boxes in v1 itself — are drawn with primitives; the battery indicator
    shows "--" when no PiSugar data exists (v2.1 change — v1 omitted it);
    bluetooth
    connecting/connected are inline list markers ("…"/check) per v1, not a
    dedicated card; the battery screen says "Charging" when PiSugar reports
    it; ABOUT_VISIBLE is 4 with v1-style header + bullets.
17. **Blank-menu root cause (fixed):** drawing was always correct (headless
    captures proved it), but on macOS SDL never maps/presents a window unless
    its event queue is pumped — the boot animation and the single initial menu
    frame were all flipped before the main loop's first `pygame.event.get()`,
    and dirty-flag rendering then went idle, so the window stayed blank.
    `MockDisplay.push_frame` now pumps events on every flip, window-expose
    events force a redraw, and the app pushes a forced initial frame after
    boot. `tests/test_render.py` and `--dump-frames` guard the drawing path.
18. **"Black boxes over text" root cause (fixed):** a second macOS-only bug.
    Under the cocoa driver, plain `pygame.Surface()` inherits the display
    format, which carries an alpha mask — and SDL's blit of antialiased text
    (or any per-pixel-alpha source) onto such a surface renders solid
    color boxes instead of glyphs (reproduced on arm64 with both SDL 2.28
    and 2.32; invisible under the dummy driver, whose surfaces are plain
    RGB). All render canvases are now explicit `depth=24` RGB surfaces, and
    MockDisplay composes scale + dim on an RGB surface before one opaque
    blit to the window. Verified by reading back live window pixels under
    the real cocoa driver.
