# pimusicdevice

A pocket music player you can build without soldering: a Raspberry Pi
Zero 2 W wearing an EYESPI Pi Beret, a 1.54" color screen, and a
click-wheel — plus a **pixel-identical Mac simulator** so you can try it
right now with no hardware at all.

## Getting Started

### Track A — Try it on your Mac (2 minutes)

1. Clone and enter the repo:

   ```sh
   git clone <this-repo> pimusicdevice && cd pimusicdevice
   ```

2. Run it (creates a virtualenv and installs dependencies on first run;
   needs Python 3.10+):

   ```sh
   bash mac/run.sh
   ```

3. A window opens: you should see a short boot animation (accent line →
   waveform → "device" wordmark) and land in a menu with a small synthetic
   music library. Controls:

   | Key | Does |
   |---|---|
   | ↑ / ↓ | wheel detents — scroll menus, volume in Now Playing |
   | Enter / Space | select · play/pause |
   | → / ← | next/previous track · select/back in menus |
   | Backspace | back |
   | P | toggle the (soft) power switch |
   | Esc / close window | quit |

### Track B — Build the real device

**Parts** (Adafruit product names; no soldering anywhere):

- Raspberry Pi Zero 2 W (with a 40-pin header)
- Adafruit **EYESPI Pi Beret** (#5783)
- Adafruit **1.54" 240×240 Wide Angle IPS TFT with EYESPI connector**,
  plus an **18-pin EYESPI FPC cable**
- Adafruit **ANO Rotary Navigation Encoder** breakout, plus a
  **STEMMA QT cable**
- *Optional:* DRV2605L haptic driver + LRA motor (click feedback)
- *Optional:* PiSugar battery board (battery % + real-time clock)
- A battery: a **5,000 mAh-class USB pack is recommended** (see
  "Power & Performance" below for real battery-life numbers)
- A microSD card (8 GB+)

**Assemble** (a couple of minutes): seat the Beret on the Pi's 40-pin
header. Connect the display to the Beret with the EYESPI cable (lift the
small black latch, slide the cable in contacts-down, close the latch).
Plug the encoder's STEMMA QT cable into the Beret's STEMMA QT port. Done —
every pin is fixed by the Beret, there is nothing to wire.

**Flash the SD card** with [Raspberry Pi
Imager](https://www.raspberrypi.com/software/):

1. Choose OS → *Raspberry Pi OS (other)* → **Raspberry Pi OS Lite
   (64-bit)**.
2. Click the **gear / "Edit Settings"** button before writing:
   - *General* tab: set hostname to **`device`**; set username **`pi`**
     and a password; enter your **WiFi network name and password**.
   - *Services* tab: **enable SSH** (password authentication).
3. Write the card, put it in the Pi, power up, give it a minute.

**Install** from your computer (same WiFi network):

```sh
ssh pi@device.local
sudo apt install -y git        # Pi OS Lite doesn't ship git
git clone <this-repo> pimusicdevice && cd pimusicdevice
bash install.sh
sudo reboot
```

`install.sh` is one command and safe to re-run: it installs packages
(mpd, mpc, python3-pip, i2c-tools, …), the Python libraries, enables SPI
and I²C, writes a working MPD config pointing at `~/Music`, applies the
power tweaks, and installs the boot service.

**What success looks like:** after the reboot the screen plays the boot
animation and lands in the menu. Then copy music over and index it:

```sh
scp -r ~/Music/* pi@device.local:Music/   # from your computer
ssh pi@device.local mpc update            # tell MPD to rescan
```

**The physical controls:**

| Input | Does |
|---|---|
| wheel | scroll menus · volume in Now Playing |
| center press | select · play/pause · wakes a dark screen |
| center hold ≥ 600 ms | back |
| ring left/right | back-previous / select-next |
| slide switch (on the Beret) | soft power off / on |

### If something doesn't work

| Symptom | Fix |
|---|---|
| Blank screen | Reseat the EYESPI cable (latch open → cable fully in → latch closed). Then `sudo systemctl stop pimusicdevice` and run `python3 pi/device.py --display-test` — a border/arrow/RGB pattern should appear. Artifacts? Set the display profile's `baudrate` to 24 MHz in `shared/config.py`. |
| Knob does nothing | `i2cdetect -y 1` must show `49`. If not, reseat the STEMMA QT cable at both ends. |
| No sound | Audio goes over Bluetooth: pair your speaker in Settings → Bluetooth on the device, then route MPD per [docs/bluetooth-audio.md](docs/bluetooth-audio.md). |
| Can't reach `device.local` | Hostname and WiFi are set at flash time — re-flash the card with Imager and re-check the settings dialog (step 2 above). |

## Guides

| Guide | Covers |
|---|---|
| [docs/install-mac.md](docs/install-mac.md) | run the simulator on a Mac, verify the install |
| [docs/install-pi.md](docs/install-pi.md) | manual Pi setup (what `install.sh` automates) |
| [docs/hardware.md](docs/hardware.md) | parts list, wiring tables, physical controls |
| [docs/usage.md](docs/usage.md) | controls, every screen, dimming, saved state |
| [docs/bluetooth-audio.md](docs/bluetooth-audio.md) | pairing + routing MPD to Bluetooth sinks |
| [docs/development.md](docs/development.md) | architecture, gates, design system, adding screens |
| [docs/troubleshooting.md](docs/troubleshooting.md) | symptoms → fixes, both targets |

## Repo layout

One shared main loop runs on both targets; `mac/` and `pi/` provide only
hardware drivers and small launchers.

```
shared/    app loop, menus, renderer (v1 "DETENT" design), dimmer, state, pisugar
mac/       pygame window, keyboard, terminal haptics, synth library, mixer player
pi/        ST7789 SPI display, ANO/seesaw input, DRV2605L, MPD player, bluetoothctl
tests/     pytest (logic + pixel render tests)
tools/     dev utilities (i2c scan, v1 frame renders)
systemd/   pimusicdevice.service + powersave unit (installed by install.sh)
docs/      the guides ↑
install.sh one-command Pi setup      mac/run.sh  one-command Mac simulator
```

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

## Connecting: the web app (load music from any browser)

The device hosts its own **library web app** — browse, upload, retag,
delete, and build playlists from any browser on the same WiFi. Nothing to
install on your computer or phone.

1. **Get the Pi on WiFi.** This happened at flash time: Raspberry Pi
   Imager's settings dialog wrote your WiFi name and password onto the SD
   card (Getting Started, Track B, step 2). No WiFi setup happens on the
   device itself.
2. On the device, open **Settings → Web App**. The screen shows the
   address, the numeric IP as a fallback, the WiFi network, and a **QR
   code** — point a phone camera at it and you're in.
3. Or type it yourself: **`http://device.local:8080`** from any Mac,
   iPhone, or iPad on the same network (`install.sh` sets the hostname to
   `device`, and Pi OS's avahi serves `device.local`). On the Mac
   simulator the same screen and the terminal show `http://localhost:8080`.

The web server runs inside the device app that systemd already starts —
there is nothing extra to install, start, or keep running.

**If `device.local:8080` doesn't load:**

1. Same WiFi? The computer/phone must be on the network you gave Imager.
2. Try the numeric IP from the device's Web App screen
   (`http://<ip>:8080`).
3. `ping device.local` — no answer usually means the WiFi credentials
   were mistyped at flash time; re-flash with Imager.
4. Check your router's client list for a device named `device`.

**Security note:** the app is LAN-only and unauthenticated by default —
fine on a home network. On a shared network, set `WEBAPP_PIN` in
`shared/config.py` (e.g. `"1234"`): every browser session then asks for
the PIN once.

**Manual fallbacks** (no browser involved, same as v1):

- `scp your-music/*.mp3 pi@device.local:Music/` (or rsync), then
  `ssh pi@device.local mpc update` — or just reboot; MPD rescans on boot.
- Or pop out the SD card and copy files into `/home/pi/Music` directly.

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

## Power & Performance

*(Written for a non-expert — nothing here needs prior Pi knowledge.)*

### How long a charge lasts

The Pi Zero 2 W idles at ~0.5 W. With this project's power tweaks applied,
expect ~0.9–1.2 W while playing music with the screen asleep and
~1.4–1.7 W in active use. That translates to roughly:

| Battery | Music, screen asleep | Active use |
|---|---|---|
| PiSugar 3 (1,200 mAh) | ~3–4 h | ~2–2.5 h |
| 5,000 mAh class pack | ~12–16 h | ~8–10 h |

**Recommendation: a 5,000 mAh-class battery.** The PiSugar 3 is neat and
adds a real clock + battery gauge, but its 1,200 mAh is a couple of hours
of real use. The honest way to check your own numbers is a cheap inline
USB power meter between the battery and the Pi.

### "Off" comes in two flavors — pick one

The slide switch's behavior is `POWER_SWITCH_ACTION` in `shared/config.py`:

- **`"soft_off"` (default):** the software stops everything and idles.
  Resume is instant (flip the switch back). But Linux keeps running at
  ~0.5 W — a 5,000 mAh pack drains in about **a day and a half while
  "off"**. This stays the default because **a halted Pi cannot be re-woken
  by the slide switch** — only GPIO 3 or a power cycle can boot a halted
  Pi.
- **`"shutdown"`:** saves state, then actually halts Linux
  (`systemctl poweroff`) — near-zero draw. Choose it **only** if you have
  a PiSugar (its own button re-powers the Pi) or a hard switch on the
  battery lead; otherwise flipping the slide switch back on does nothing
  and you must pull power to reboot.

### What makes it fast and frugal

- **Adaptive loop rate:** 30 fps only while the screen is awake; ~10 Hz
  dimmed, ~2 Hz asleep, ~4 Hz soft-off. You can't feel it — the first
  center press only wakes the screen anyway.
- **Partial display updates:** the once-a-second redraws (clock, progress
  bar) push only the strip that changed (~12 KB) instead of the full
  115 KB frame; anything touching layout still pushes a full frame. A
  pixel-identity test proves the two paths render identically.
- **Nothing blocks the loop:** Bluetooth scanning runs on a thread behind
  a spinner (back cancels instantly), the battery refresh is
  fire-and-forget, and MPD is event-driven (`idle` mode) instead of being
  polled 5× a second.
- **OS tweaks the installer applies** (~0.1 W combined, and why):
  HDMI output disabled (nothing is plugged into it), the ACT LED disabled
  (invisible inside a case), and the `powersave` CPU governor (a music
  player never needs burst clocks). **Bluetooth stays on — it carries the
  audio.**
- **SPI fallback:** if `--display-test` shows artifacts at the default
  62.5 MHz, set the display profile's `baudrate` to 24 MHz (the UI caps
  at ~26 fps there — see the Display section).

Friendlier defaults: the screen wakes at 70 % brightness and dims after
15 s idle; both are adjustable in Settings → Brightness / `shared/config.py`.

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
18. **v2.1 hardware-change decisions (Beret retarget):**
    - *Waking presses:* only a **short** center press wakes a dark screen
      ("select" fires on release). Holding the center button on a dark
      screen fires its long-press "back" at 600 ms, which the dark-screen
      gate discards — so a long hold neither wakes nor acts, and there is
      no stale long-press state to reset after a wake.
    - *Soft-off input:* the idle loop drains-and-discards input each poll
      so the Mac's event queue stays alive (P and Esc must register); on
      the Pi that adds one passive I²C read per 250 ms, functionally
      identical to "ignoring" input. "quit" (Esc/window close) is honored
      during soft-off on the Mac — a dev simulator that can't be closed
      would be hostile; the Pi never emits "quit".
    - *Soft-off resume* rebuilds the menu controller and boots into
      MENU/home ("exactly like a normal boot"), rather than restoring the
      pre-off screen.
    - *Partial updates* are gated on the dimmer being AWAKE rather than
      the literal "full backlight": Phase 6's own 70 % default wake
      brightness would otherwise disable the feature permanently. The Mac
      mock's `push_region` applies the same gamma-dim compositing as full
      frames, so there is no dim-overlay interaction at any level.
    - *Volume overlay* frames stay full-frame (its dim underlay spans the
      whole screen); since it is static while visible, it stops pushing
      frames entirely until it expires.
    - *Selftest peripheral probes:* on the Mac the "failed haptics probe"
      is represented by installing `NullHaptic` directly (the real probe
      needs Pi I²C), and PiSugar is forced offline by pointing its port at
      1 before the poll thread starts.
    - *`macapp/` in the acceptance gate:* the repo has no `macapp/`
      directory; `compileall` covers `shared mac pi tools`.
    - *MPD_POLL_S* was removed with the polling it throttled; the idle
      thread's reconnect backoff is `MPD_RETRY_S`.
19. **"Black boxes over text" root cause (fixed):** a second macOS-only bug.
    Under the cocoa driver, plain `pygame.Surface()` inherits the display
    format, which carries an alpha mask — and SDL's blit of antialiased text
    (or any per-pixel-alpha source) onto such a surface renders solid
    color boxes instead of glyphs (reproduced on arm64 with both SDL 2.28
    and 2.32; invisible under the dummy driver, whose surfaces are plain
    RGB). All render canvases are now explicit `depth=24` RGB surfaces, and
    MockDisplay composes scale + dim on an RGB surface before one opaque
    blit to the window. Verified by reading back live window pixels under
    the real cocoa driver.
