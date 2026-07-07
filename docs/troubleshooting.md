# Troubleshooting

## Mac simulator

**Window opens but stays blank** — fixed in the current code (frames are
now presented with the SDL event queue pumped). If you ever see it again,
check that `MockDisplay.push_frame` still calls `pygame.event.pump()`.

**Text renders as solid boxes** — fixed: render canvases must be explicit
`depth=24` RGB surfaces. On macOS, plain `pygame.Surface()` inherits the
display's alpha-masked format and SDL draws antialiased text onto it as
filled rectangles. If a new canvas shows boxes, create it with `depth=24`.

**No sound** — the synth WAVs are mono 22 kHz; check the mixer init line in
`mac/prototype.py` and that `mac/_audio/` regenerated (delete it to force).

**`ModuleNotFoundError: pygame`** — you're outside the venv. Run
`.venv/bin/python mac/prototype.py` or activate the venv first.

**Selftest fails** — it prints the failing assertion plus the full saved
state. Re-run once (it deletes `.device_state.json` itself); if it fails
consistently, `--dump-frames /tmp/frames` usually shows what went wrong.

## Pi display

**Blank/white screen** — check DC/RST/BL pins vs `shared/config.py`, SPI
enabled (`ls /dev/spidev0.0`), and the backlight pin actually PWM-ing
(`PIN_BL` default GPIO 18).

**Image shifted or has garbage edges** — set `DISPLAY_X_OFFSET` /
`DISPLAY_Y_OFFSET` (some 240×240 panels start at row 80 in one rotation).

**Colors inverted** — your panel doesn't want `INVON`; remove the `0x21`
command in `pi/display_pi.py`.

**Low FPS** — confirm `SPI_SPEED_HZ = 62_500_000` took (some ribbons cap
lower); a full frame is ~115 KB ≈ 7.4 ms on the wire at 62.5 MHz.

## Pi input / haptics

**Nothing at `0x49` / `0x5a` in `i2cdetect -y 1`** — wiring/power; the UI
runs anyway (input dead ⇒ log line, haptics dead ⇒ log line + silent).

**Wheel scrolls backwards** — flip `ENCODER_REVERSED`.

**Select acts as back too eagerly** — raise `BACK_HOLD_S` (default 0.6 s).

## Music / MPD

**Empty library** — `mpc stats`; if zero, files aren't in MPD's
`music_directory` or `mpc update` hasn't run. The device logs
"library: MPD unavailable" if it can't connect at all.

**Playback dies over Bluetooth** — that's routing, not the UI: see
[bluetooth-audio.md](bluetooth-audio.md) and `journalctl -u mpd`.

## Battery / clock

**Battery shows nothing** — no PiSugar daemon on `127.0.0.1:8423`; that's
the designed silent fallback. The clock falls back to system time.

## Where state lives

- Mac: `<repo>/.device_state.json` · Pi: `/home/pi/.device_state.json`
- Delete it to reset resume/volume/brightness. Corrupt files are ignored.

## Logs

- Mac: the terminal (haptics, dimmer transitions, one-shot warnings).
- Pi: `journalctl -u pimusicdevice -f` (the systemd unit sets
  `PYTHONUNBUFFERED=1`).
