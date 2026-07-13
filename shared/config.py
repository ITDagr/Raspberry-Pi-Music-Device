"""device v2 — single source of truth for pins, addresses, timings and tunables.

Every hardware pin, I2C address, timing constant and feature flag lives here.
Edit the pin block to match your wiring; nothing else in the tree hardcodes
hardware details.
"""
from __future__ import annotations

import sys
from pathlib import Path

DEBUG = False           # gate for chatty per-frame prints ("redraw", etc.)
FPS = 30                # main loop frame rate

# --- platform / persistence -------------------------------------------------
IS_MAC = sys.platform == "darwin"
_REPO_ROOT = Path(__file__).resolve().parent.parent
# Mac: state lives next to the repo. Pi: home of the default `pi` user.
STATE_PATH = (
    str(_REPO_ROOT / ".device_state.json") if IS_MAC else "/home/pi/.device_state.json"
)
AUTOSAVE_INTERVAL_S = 10.0      # save while playing, every N seconds

# --- display: ST7789 TFT via the Adafruit EYESPI Pi Beret (#5783) -----------
# The Beret is a HAT: every pin below is fixed by its routing, not user
# wiring. (Also on the Beret, unused here: touch CS on CE1, touch IRQ on
# GPIO 24, e-ink busy on GPIO 17.) The backlight jumper is assumed intact.
SPI_BUS = 0                     # Beret-fixed
SPI_DEVICE = 0                  # display CS on SPI0 CE0 — Beret-fixed
PIN_DC = 25                     # data/command — Beret-fixed
PIN_RST = 27                    # reset — Beret-fixed
PIN_BL = 18                     # backlight, PWM-capable — Beret-fixed
BACKLIGHT_PWM_HZ = 1000         # duty = level * 100

# Panel profiles. The ST7789 RAM is 240x320; a 240x240 panel shows a window
# of it, so the offsets/rotation below are part of the panel's identity —
# wrong values mean an 80px garbage band or a wrapped image. Values are
# Adafruit's canonical Python init for each product; do not tune by eye.
DISPLAY_PROFILE = "adafruit_154_240x240"
DISPLAY_PROFILES = {
    # Adafruit 1.54" 240x240 wide-angle IPS TFT, EYESPI connector
    "adafruit_154_240x240": {
        "width": 240, "height": 240,
        "x_offset": 0, "y_offset": 80,
        "rotation": 180,            # MADCTL flip; offsets are RAM-window coords
        "invert": True,             # IPS panels want INVON
        "baudrate": 62_500_000,     # ~15 ms/frame; see SPI_SPEED_FALLBACK_HZ
    },
    # Adafruit 1.3" 240x240 IPS TFT (same controller window)
    "adafruit_13_240x240": {
        "width": 240, "height": 240,
        "x_offset": 0, "y_offset": 80,
        "rotation": 180,
        "invert": True,
        "baudrate": 62_500_000,
    },
}
# At 24 MHz a full 240x240x16-bit frame takes ~38 ms (caps the UI at ~26 fps);
# at 62.5 MHz it's ~15 ms. If `--display-test` shows artifacts at 62.5 MHz,
# set the active profile's baudrate to this fallback.
SPI_SPEED_FALLBACK_HZ = 24_000_000
SPI_SPEED_HZ = DISPLAY_PROFILES[DISPLAY_PROFILE]["baudrate"]

# --- input: Adafruit ANO rotary encoder on seesaw ---------------------------
SEESAW_ADDR = 0x49              # match your wiring
SEESAW_BTN_SELECT = 1           # seesaw pin numbers per the Adafruit ANO guide
SEESAW_BTN_UP = 2               # match your wiring
SEESAW_BTN_LEFT = 3             # match your wiring
SEESAW_BTN_DOWN = 4             # match your wiring
SEESAW_BTN_RIGHT = 5            # match your wiring
DEBOUNCE_S = 0.005              # 5 ms button debounce
BACK_HOLD_S = 0.6               # hold select this long -> "back"
ENCODER_REVERSED = False        # flip if CW scrolls the wrong way

# v2 improvement: encoder acceleration, menus only (feature flag)
ENCODER_ACCEL = True
ACCEL_DETENTS = 6               # more than this many detents ...
ACCEL_WINDOW_S = 1.0            # ... within this window ...
ACCEL_STEP = 3                  # ... makes each detent move this many rows

# --- haptics: DRV2605L, LRA mode + LRA ROM library --------------------------
DRV2605_ADDR = 0x5A             # match your wiring
EFFECT_TICK = 14                # scroll detent
EFFECT_CLICK = 1                # select
EFFECT_BACK = 7                 # navigate back
EFFECT_PULSE = 47               # boot flourish

# --- audio -------------------------------------------------------------------
MPD_HOST = "127.0.0.1"
MPD_PORT = 6600
MPD_POLL_S = 0.2                # status() poll throttle (<= 5 Hz)
DEFAULT_VOLUME = 50             # 0-100
VOLUME_STEP = 5
VOLUME_FLASH_S = 1.5            # volume overlay lifetime
PREV_RESTART_AFTER_S = 3.0      # iPod-style previous: restart if elapsed > this

# --- PiSugar (optional — one boot probe decides online/offline mode) ---------
PISUGAR_HOST = "127.0.0.1"
PISUGAR_PORT = 8423
PISUGAR_POLL_S = 30.0
PISUGAR_TIMEOUT_S = 0.5
PISUGAR_REPROBE_S = 300.0       # silent re-probe cadence while offline

# --- screen dimmer ------------------------------------------------------------
DIM_AFTER_S = 20.0              # idle seconds before dimming
SLEEP_AFTER_S = 60.0            # idle seconds before backlight off
DIM_LEVEL = 0.15
WAKE_LEVEL = 1.0                # default awake brightness (0.1-1.0)
DEFAULT_BRIGHTNESS = 100        # brightness screen value, percent
BRIGHTNESS_STEP = 10
BRIGHTNESS_MIN = 10
BRIGHTNESS_MAX = 100

# --- bluetooth ------------------------------------------------------------------
BT_CONNECT_MIN_S = 2.5          # minimum time shown in "connecting" state
BT_CONNECT_MAX_S = 4.0          # after this we assume connected regardless
BT_SCAN_S = 6.0                 # Pi: bluetoothctl scan window

# --- ui -------------------------------------------------------------------------
MENU_VISIBLE = 5                # menu rows on screen
STARTUP_DURATION_S = 2.9        # total boot animation (v1 ARIA choreography, scaled)
