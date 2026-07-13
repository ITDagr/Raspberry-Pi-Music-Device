# Hardware guide — parts and wiring

## Bill of materials

| Part | Role | Interface |
|---|---|---|
| Raspberry Pi Zero 2 W | host (Pi OS Bookworm Lite) | — |
| Adafruit EYESPI Pi Beret (#5783) | HAT: display + STEMMA QT breakout | SPI0 + I²C bus 1 |
| Adafruit 1.54" 240×240 IPS TFT (ST7789, EYESPI) | screen | SPI0 @ 62.5 MHz via EYESPI cable |
| Adafruit ANO rotary encoder + seesaw breakout | scroll wheel + 5 buttons | I²C `0x49` |
| DRV2605L haptic driver + LRA motor | haptics | I²C `0x5A` |
| PiSugar 2 or 3 | battery % + RTC | TCP `127.0.0.1:8423` (its daemon) |
| Bluetooth (built-in) | audio sinks | `bluetoothctl` |

## Wiring (fixed by the EYESPI Pi Beret — see `shared/config.py`)

All pins are BCM numbering. The Beret is a HAT: seat it on the Pi's
header, connect the display with the 18-pin EYESPI FPC cable, and the
pins below are already routed — there is nothing to wire by hand.

### ST7789 display (SPI0, via the Beret's EYESPI connector)

| Signal | Pi pin (Beret-fixed) | config |
|---|---|---|
| Display CS | SPI0 CE0 | `SPI_DEVICE = 0` |
| DC | GPIO 25 | `PIN_DC` |
| Reset | GPIO 27 | `PIN_RST` |
| Backlight | GPIO 18 | `PIN_BL` (PWM 1 kHz, duty = level×100) |
| Touch CS / IRQ | CE1 / GPIO 24 | unused |
| Display Busy | GPIO 17 | unused (e-ink only) |

Panel geometry (offsets, rotation, inversion, SPI baudrate) comes from
`DISPLAY_PROFILES[DISPLAY_PROFILE]` in `shared/config.py` — the default
`adafruit_154_240x240` profile is Adafruit's canonical init for the
1.54" panel (`y_offset=80`, `rotation=180`, `INVON`). Verify a new panel
with `python3 pi/device.py --display-test`.

### ANO encoder (I²C, seesaw)

SDA → GPIO 2, SCL → GPIO 3, 3V3 + GND. Address `0x49` (`SEESAW_ADDR`).
Button map on seesaw pins (verify against the Adafruit ANO guide):
select=1, up=2, left=3, down=4, right=5 (`SEESAW_BTN_*`).
Wheel direction wrong? Flip `ENCODER_REVERSED`.

### DRV2605L haptics (I²C)

Same I²C bus, address `0x5A` (`DRV2605_ADDR`). Motor: an **LRA** (the
driver is configured for LRA mode + the LRA ROM effect library).
Effect map (fixed): tick=14 (scroll detent) · click=1 (select) ·
back=7 · pulse=47 (boot).

### PiSugar

Mounts on the Pi's pogo pins; no GPIO wiring. Install its power-manager
daemon; the device polls battery %, charging state, and the RTC over
`127.0.0.1:8423` every 30 s (`PISUGAR_*` in config) and falls back
silently when absent.

## Controls (physical)

| Input | Action |
|---|---|
| wheel | scroll menus · volume in Now Playing · adjust brightness/about |
| center press | select / play-pause |
| center hold ≥ 600 ms | back (leave the current screen) |
| ring up/down | same as wheel detents |
| ring left | back in menus · previous track in Now Playing |
| ring right | select in menus · next track in Now Playing |

Timings (`BACK_HOLD_S`, debounce, encoder acceleration) are in
`shared/config.py`.
