"""device v2 — single source of truth for pins, addresses, timings and tunables.

Every hardware pin, I2C address, timing constant and feature flag lives here.
Edit the pin block to match your wiring; nothing else in the tree hardcodes
hardware details.
"""
from __future__ import annotations

import sys
from pathlib import Path

DEBUG = False           # gate for chatty per-frame prints ("redraw", etc.)
# Adaptive loop rate: full speed only while the screen is awake. Nobody can
# feel the lower rates — the first press on a dark screen only wakes it.
FPS = 30                # main loop rate while AWAKE
FPS_DIM = 10            # while DIM
FPS_SLEEP = 2           # while SLEEP (soft-off has its own ~4 Hz poll)

# --- platform / persistence -------------------------------------------------
# the browser demo (web/, "emscripten") runs the Mac stand-ins, so it counts as Mac
IS_MAC = sys.platform in ("darwin", "emscripten")
_REPO_ROOT = Path(__file__).resolve().parent.parent
# Mac: state lives next to the repo. Pi: home of the default `pi` user.
STATE_PATH = (
    str(_REPO_ROOT / ".device_state.json") if IS_MAC else "/home/pi/.device_state.json"
)
AUTOSAVE_INTERVAL_S = 10.0      # save while playing, every N seconds
# The music root anchors stable track ids (paths relative to it). On the Pi
# it must equal MPD's music_directory (install.sh writes both from here).
MUSIC_ROOT = str(_REPO_ROOT / "mac" / "_audio") if IS_MAC else "/home/pi/Music"
TOAST_S = 2.5                   # on-screen toast lifetime

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

# --- I2C topology -------------------------------------------------------------
# Everything I2C hangs off the Pi's default bus 1, exposed by the Beret's
# STEMMA QT port. The Adafruit 5-Port Hub (#5625) is a passive splitter —
# all five ports share the same power/GND/SDA/SCL — so plugging devices
# through it is electrically identical to plugging into the Beret directly:
# same bus, same addresses, zero code changes. The only rule is that every
# device needs a unique address (map mirrored in the README):
#   0x49  ANO encoder seesaw (jumpers exist if it must move)
#   0x5A  DRV2605L haptics   (fixed; optional)
#   0x57 + 0x68  PiSugar battery + RTC (only if attached; optional —
#                and reached via its daemon on TCP 8423, not directly)
I2C_BUS = 1

# --- input: Adafruit ANO rotary encoder on seesaw ---------------------------
SEESAW_ADDR = 0x49              # I2C bus 1 via the Beret's STEMMA QT port
SEESAW_BTN_SELECT = 1           # seesaw pin numbers per the Adafruit ANO guide
SEESAW_BTN_UP = 2               # match your wiring
SEESAW_BTN_LEFT = 3             # match your wiring
SEESAW_BTN_DOWN = 4             # match your wiring
SEESAW_BTN_RIGHT = 5            # match your wiring
DEBOUNCE_S = 0.005              # 5 ms button debounce
BACK_HOLD_S = 0.6               # hold select this long -> "back"
ENCODER_REVERSED = False        # flip if CW scrolls the wrong way
MAX_ENCODER_DELTA = 40          # discard a single read past this — a real spin
                                 # can't hit it; a flaky I2C read can
ENCODER_FAULT_WINDOW_S = 2.0    # trailing window for the noise-rate breaker
ENCODER_FAULT_MAX_DETENTS = 120  # >60 detents/s sustained — 10x the fastest
                                  # real spin (see ACCEL_DETENTS below); past
                                  # this it's a noisy connection, not a human
ENCODER_INIT_RETRY_WINDOW_S = 20.0  # on a cold boot the I2C bus / seesaw can
                                     # need several seconds to settle, so its
                                     # own hardware-ID read comes back corrupt
                                     # at first; keep retrying init for this
                                     # long within one launch rather than
                                     # crashing and leaning on systemd (which
                                     # gives up after StartLimitBurst crashes)
ENCODER_INIT_RETRY_DELAY_S = 0.5

# v2 improvement: encoder acceleration, menus only (feature flag)
ENCODER_ACCEL = True
ACCEL_DETENTS = 6               # more than this many detents ...
ACCEL_WINDOW_S = 1.0            # ... within this window ...
ACCEL_STEP = 3                  # ... makes each detent move this many rows

# --- haptics: DRV2605L ------------------------------------------------------
DRV2605_ADDR = 0x5A             # fixed chip address, I2C bus 1 (optional device)
# Motor type must match the physical actuator or it barely moves: an ERM
# (Adafruit vibrating mini motor disc) needs ERM mode + an ERM ROM library;
# an LRA needs LRA mode + library 6. HAPTIC_LIBRARY: 1-5 = ERM, 6 = LRA.
HAPTIC_MOTOR = "erm"            # "erm" or "lra"
HAPTIC_LIBRARY = 1              # DRV2605 ROM waveform library for the motor
EFFECT_TICK = 14                # scroll detent
EFFECT_CLICK = 1                # select
EFFECT_BACK = 7                 # navigate back
EFFECT_PULSE = 47               # boot flourish

# --- audio -------------------------------------------------------------------
MPD_HOST = "127.0.0.1"
MPD_PORT = 6600
MPD_RETRY_S = 2.0               # idle-thread reconnect backoff when MPD is down
DEFAULT_VOLUME = 50             # 0-100
VOLUME_STEP = 2                 # per wheel detent in Now Playing — small for
                                 # precise control (wheel is direction-reversed
                                 # there: up = quieter, down = louder)
VOLUME_FLASH_S = 1.5            # volume overlay lifetime
PREV_RESTART_AFTER_S = 3.0      # iPod-style previous: restart if elapsed > this

# --- web app: the library manager the device serves itself -------------------
WEBAPP_ENABLED = True
WEBAPP_HOST = "0.0.0.0"         # reachable from the LAN (it's the whole point)
WEBAPP_PORT = 8080
WEBAPP_MAX_UPLOAD_MB = 200      # per-file cap; oversize returns 413
WEBAPP_PIN = None               # e.g. "1234": require a PIN on shared networks
TRASH_KEEP_DAYS = 7             # deleted tracks sit in <music>/.trash this long
# A connected-but-idle WiFi radio draws ~0.15-0.35 W — roughly 20-30% of this
# device's total budget — and is only needed while the web app is in use.
#   "on_demand"  (default) radio off until Settings -> Web App opens it;
#                leaving the screen turns it off (transfers finish first)
#   "always_on"  radio stays up (same as the Settings -> WiFi pin)
WIFI_POLICY = "on_demand"
UPLOAD_CHUNK = 64 * 1024        # streamed-upload chunk size (cooperative yields)
PLAYLISTS_PATH = (
    str(_REPO_ROOT / ".device_playlists.json") if IS_MAC
    else "/home/pi/.device_playlists.json"
)

# --- PiSugar (optional — one boot probe decides online/offline mode) ---------
PISUGAR_HOST = "127.0.0.1"
PISUGAR_PORT = 8423
PISUGAR_POLL_S = 30.0
PISUGAR_TIMEOUT_S = 0.5
PISUGAR_REPROBE_S = 300.0       # silent re-probe cadence while offline

# --- Beret tactile buttons (GPIO 5 and GPIO 6, active-low, debounced) --------
# Map each to an event from the standard vocabulary (see shared/hardware.py)
# or None to disable. Both default to None — no behavior change out of the
# box; "back" and "select" are natural choices if you want them live.
BERET_BUTTONS: dict[int, str | None] = {5: None, 6: None}

# --- soft power: the Beret's slide switch on GPIO 13 -------------------------
# Per Adafruit the slide switch is NOT a real power switch — just a GPIO that
# reads high or low — so "off" is implemented in software (save state, stop
# playback, screen off, idle loop). A halted Pi cannot be re-woken by GPIO 13.
PIN_POWER_SWITCH = 13           # Beret-fixed
POWER_SWITCH_ON_LEVEL = 1       # GPIO level meaning ON; flip if yours reads reversed
POWER_SWITCH_DEBOUNCE_S = 0.05
SOFT_OFF_POLL_HZ = 4.0          # switch poll rate while soft-off
# What flipping the switch OFF does:
#   "soft_off"  (default) idle in software — instant resume, but Linux still
#               draws ~0.5 W, so a 5,000 mAh pack drains in ~a day and a half
#   "shutdown"  save state then `systemctl poweroff` — near-zero draw, BUT a
#               halted Pi CANNOT be re-woken by GPIO 13 (only GPIO 3 boots a
#               halted Pi). Choose it only with a PiSugar (its button
#               re-powers the Pi) or a hard switch on the battery lead.
POWER_SWITCH_ACTION = "soft_off"

# --- screen dimmer ------------------------------------------------------------
DIM_AFTER_S = 25.0              # idle seconds before dimming
SLEEP_AFTER_S = 60.0            # idle seconds before backlight off (black)
DIM_LEVEL = 0.15
WAKE_LEVEL = 0.7                # default awake brightness (0.1-1.0)
DEFAULT_BRIGHTNESS = 70         # brightness screen value, percent
BRIGHTNESS_STEP = 10
BRIGHTNESS_MIN = 10
BRIGHTNESS_MAX = 100

# --- bluetooth ------------------------------------------------------------------
BT_CONNECT_MIN_S = 2.5          # minimum time shown in "connecting" state
BT_CONNECT_MAX_S = 15.0         # poll BlueZ for a real connection up to here
                                 # (a first-time pair+connect is slow); past
                                 # this, report failure — never a false check
BT_CONNECTED_SHOW_S = 2.0       # show "Connected" this long, then auto-return
                                 # to the menu (no dead-end confirmation screen)
BT_SCAN_S = 6.0                 # Pi: bluetoothctl scan window

# --- ui -------------------------------------------------------------------------
MENU_VISIBLE = 5                # menu rows on screen
STARTUP_DURATION_S = 2.9        # total boot animation (v1 ARIA choreography, scaled)
