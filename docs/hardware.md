# Hardware guide — parts and wiring

## Bill of materials

| Part | Role | Interface |
|---|---|---|
| Raspberry Pi Zero 2 W | host (Pi OS Bookworm Lite) | — |
| ST7789V 1.3" 240×240 IPS TFT | screen | SPI0 @ 62.5 MHz |
| Adafruit ANO rotary encoder + seesaw breakout | scroll wheel + 5 buttons | I²C `0x49` |
| DRV2605L haptic driver + LRA motor | haptics | I²C `0x5A` |
| PiSugar 2 or 3 | battery % + RTC | TCP `127.0.0.1:8423` (its daemon) |
| Bluetooth (built-in) | audio sinks | `bluetoothctl` |

## Wiring (defaults — every pin lives in `shared/config.py`)

All pins are BCM numbering. If your wiring differs, edit the config —
nothing else in the tree hardcodes hardware details.

### ST7789 display (SPI0)

| TFT pin | Pi pin | config |
|---|---|---|
| VCC | 3V3 | — |
| GND | GND | — |
| SCL/SCK | GPIO 11 (SCLK) | SPI0 |
| SDA/MOSI | GPIO 10 (MOSI) | SPI0 |
| CS | GPIO 8 (CE0) | `SPI_DEVICE = 0` |
| DC | GPIO 25 | `PIN_DC` |
| RST | GPIO 27 | `PIN_RST` |
| BL (backlight) | GPIO 18 | `PIN_BL` (PWM 1 kHz, duty = level×100) |

Panel quirks: some 240×240 modules need a pixel offset — set
`DISPLAY_X_OFFSET` / `DISPLAY_Y_OFFSET`. IPS panels want inversion on
(the driver sends `INVON`; if colors look negative, your panel differs).

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
