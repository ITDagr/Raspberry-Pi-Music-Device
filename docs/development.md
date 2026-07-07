# Development guide

## Architecture

One shared core, two thin entry points:

```
shared/          all app logic — runs unchanged on Mac and Pi
  app.py         main loop + mode state machine (MENU/NOWPLAYING/BLUETOOTH/…)
  hardware.py    Protocols: Display, InputSource, Haptic, Player + Track
  menu_core.py   MenuController + menu tree; MenuView is the one render model
  screen.py      ScreenRenderer — v1 "DETENT" visual system, all drawing
  startup.py     five-phase boot animation
  screen_dimmer.py  AWAKE→DIM→SLEEP thread
  state.py       atomic JSON persistence
  pisugar.py     battery/RTC polling, silent fallback
  config.py      every pin, address, timing, and tunable
mac/             pygame window, keyboard, terminal haptics, synth library,
                 mixer player, fake bluetooth + the launcher (prototype.py)
pi/              ST7789 SPI display, seesaw input, DRV2605L, MPD player,
                 bluetoothctl wrapper + the launcher (device.py)
tests/           pytest: menu logic, state, player, config, and render tests
tools/           dev utilities (dump_v1_frames.py renders the v1 design)
```

Rules that keep it healthy:

- **Hardware only via the Protocols.** `shared/` never imports drivers.
- Pi modules lazy-import hardware libs so `import pi.device` works anywhere.
- Every tunable lives in `shared/config.py`.
- Debug prints sit behind `config.DEBUG`; dimmer transitions always log.
- Any hardware/MPD/Bluetooth failure logs once and the UI keeps running.

## The verification gates

```sh
.venv/bin/python -m pytest -q                     # 32 tests
.venv/bin/python mac/prototype.py --selftest      # scripted E2E, exit 0
.venv/bin/python -m compileall shared mac pi
.venv/bin/python -c "import pi.device"
```

The selftest swaps the keyboard for a scripted input source, runs the real
loop uncapped under SDL dummy drivers, and walks menus → playback → volume
→ brightness → about → battery → bluetooth, asserting app state and the
saved state file. Keep it green; it runs in ~6 s.

## Visual verification

```sh
.venv/bin/python mac/prototype.py --dump-frames /tmp/frames
```

saves a PNG of every screen from the selftest run (11 frames). Rendering
changes should be eyeballed there, and `tests/test_render.py` pixel-checks
each screen (non-blank, highlight on the cursor row, FG text elsewhere).

**Two macOS lessons baked into the code** (details in README Assumptions
16–18): frames must be presented with the event queue pumped, and render
canvases must be explicit `depth=24` RGB — plain Surfaces inherit the cocoa
display's alpha-masked format, on which SDL draws antialiased text as solid
boxes. Neither bug is visible under the dummy driver, so window-level
changes deserve a real-driver spot check (open the window at
`SDL_VIDEO_WINDOW_POS=5000,5000` and read back pixels).

## Design system

The visuals are v1's "DETENT" tokens, ported: base `#0E0F13`, surface
`#1B1E26`, line `#2A2E38`, text `#F2F3F5`, dim `#8A8F9C`, accent `#FF6A3D`
(focus only), state `#5BD6A6` (status only); 24 px status bar, 38 px rows
with 32 px pills, 2 px scroll rails. Fonts are pygame's bundled
`Font(None, size)` scaled 1.38× to Arial's optical size — **never
SysFont**. Compare against real v1 renders with
`tools/dump_v1_frames.py` if you change the renderer.

## Adding a screen (checklist)

1. Add a `Mode`, its event handler, and its render call in `shared/app.py`.
2. Add `draw_<name>()` to `shared/screen.py` using the tokens + helpers.
3. Reach it from the menu tree (`menu_core.build_default_menus`).
4. Add a render test and, if it has state worth guarding, extend the
   selftest script in `mac/prototype.py` (plus a `_snap` for dumps).
