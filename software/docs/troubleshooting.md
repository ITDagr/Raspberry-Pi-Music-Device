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

First move for any display symptom: `sudo systemctl stop pimusicdevice`,
then `python3 pi/device.py --display-test` — the border / corner-labels /
UP-arrow / R-G-B pattern makes the failure class obvious in one look.

**Blank/white screen** — reseat the EYESPI cable at both ends (latch open,
cable contacts-down, latch closed), confirm SPI is enabled
(`ls /dev/spidev0.0`). The pins themselves are fixed by the Beret, so
wiring mistakes are limited to the two cables.

**Image shifted / garbage band / wrapped** — the active profile's
offsets don't match the panel. Check `DISPLAY_PROFILE` in
`shared/config.py` points at your panel (`adafruit_154_240x240` for the
1.54", `adafruit_13_240x240` for the 1.3").

**Colors inverted** — your panel doesn't want inversion; set
`"invert": False` in its `DISPLAY_PROFILES` entry.

**Wrong color order (R and B bars swapped in `--display-test`)** — panel
variant with BGR order; note it and adjust the MADCTL value in
`pi/display_pi.py` (bit 0x08).

**Artifacts / speckles at full speed** — drop the profile's `baudrate` to
`SPI_SPEED_FALLBACK_HZ` (24 MHz); some ribbons cap below 62.5 MHz.

## Pi input / haptics

**Nothing at `0x49` in `i2cdetect -y 1`** — reseat the encoder's STEMMA QT
cable (Beret port or hub, electrically identical). The encoder is
mandatory: boot exits with a bus listing when it's missing. Also:
`python3 tools/i2c_scan.py`.

**Nothing at `0x5a`** — haptics are optional; boot logs one line
("haptics: not detected — continuing without") and runs silently.

**Wheel scrolls backwards** — flip `ENCODER_REVERSED`.

**Select acts as back too eagerly** — raise `BACK_HOLD_S` (default 0.6 s).

## Music / MPD

**Empty library** — `mpc stats`; if zero, files aren't in MPD's
`music_directory` or `mpc update` hasn't run. The device logs
"library: MPD unavailable" if it can't connect at all.

**Playback dies over Bluetooth** — that's routing, not the UI: see
[bluetooth-audio.md](bluetooth-audio.md) and `journalctl -u mpd`.

## Battery / clock

**Battery shows "--"** — no PiSugar daemon on `127.0.0.1:8423`; that's
the designed offline mode (one log line at boot, silent 5-minute
re-probes). The clock falls back to system time.

## Where state lives

- Mac: `<repo>/.device_state.json` · Pi: `/home/pi/.device_state.json`
- Delete it to reset resume/volume/brightness. Corrupt files are ignored.

## Logs

- Mac: the terminal (haptics, dimmer transitions, one-shot warnings).
- Pi: `journalctl -u pimusicdevice -f` (the systemd unit sets
  `PYTHONUNBUFFERED=1`).
