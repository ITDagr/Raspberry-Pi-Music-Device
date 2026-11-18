"""pizero-llm-demo — hardware + UI constants.

The hardware block is lifted from pimusicdevicev2's shared/config.py so this
project drives the same physical device with the same proven numbers (panel
offsets, seesaw pin map, ERM haptic mode, the encoder noise breaker). If you
re-wire one device, re-check the other.

Runtime values that install.sh knows and this file cannot (model path, label,
ports) arrive via app/runtime.json, written at install time.
"""
from __future__ import annotations

import json
import os

# --- runtime.json ------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULTS = {
    "model_path": "",
    "model_label": "unknown",
    "model_quant": "",
    "llama_host": "127.0.0.1",
    "llama_port": 8081,
    "n_predict": 200,
    "ctx_size": 512,
    "ui_lean": 0,
}
try:
    with open(os.path.join(_HERE, "runtime.json")) as fh:
        _RT = {**_DEFAULTS, **json.load(fh)}
except (OSError, ValueError) as exc:  # running from a checkout, pre-install
    print(f"config: runtime.json unavailable ({exc}) — using defaults")
    _RT = dict(_DEFAULTS)

MODEL_PATH = _RT["model_path"]
MODEL_LABEL = _RT["model_label"]
MODEL_QUANT = _RT["model_quant"]
LLAMA_HOST = _RT["llama_host"]
LLAMA_PORT = int(_RT["llama_port"])
N_PREDICT = int(_RT["n_predict"])
CTX_SIZE = int(_RT["ctx_size"])
UI_LEAN = bool(int(_RT["ui_lean"]))

# --- display: ST7789 via the EYESPI Pi Beret --------------------------------
SIZE = 240
SPI_BUS = 0                     # Beret-fixed
SPI_DEVICE = 0                  # display CS on SPI0 CE0 — Beret-fixed
PIN_DC = 25                     # Beret-fixed
PIN_RST = 27                    # Beret-fixed
PIN_BL = 18                     # backlight, PWM-capable — Beret-fixed
BACKLIGHT_PWM_HZ = 1000         # duty = level * 100

# Adafruit 1.54" 240x240 wide-angle IPS. Offsets are RAM-window coordinates for
# this rotation — the rotation and the offsets travel together, never edit one.
PANEL = {
    "x_offset": 0,
    "y_offset": 80,
    "rotation": 180,
    "invert": True,             # IPS panels want INVON
    "baudrate": 62_500_000,     # ~15 ms for a full frame
}
BACKLIGHT_LEVEL = 0.85

# --- input: Adafruit ANO rotary encoder on seesaw ---------------------------
SEESAW_ADDR = 0x49
SEESAW_BTN_SELECT = 1           # seesaw pin numbers per the Adafruit ANO guide
SEESAW_BTN_UP = 2
SEESAW_BTN_LEFT = 3
SEESAW_BTN_DOWN = 4
SEESAW_BTN_RIGHT = 5
DEBOUNCE_S = 0.005
BACK_HOLD_S = 0.6               # hold select this long -> "back"
ENCODER_REVERSED = False        # flip if CW scrolls the wrong way

# The chronic failure on this hardware is a marginal STEMMA QT connection
# injecting corrupt I2C reads. Both breakers below exist because of it.
MAX_ENCODER_DELTA = 40          # discard a single read past this
ENCODER_FAULT_WINDOW_S = 2.0
ENCODER_FAULT_MAX_DETENTS = 120  # sustained rate past this is noise, not a human
ENCODER_INIT_RETRY_WINDOW_S = 20.0   # cold-boot I2C settle; retry, don't crash
ENCODER_INIT_RETRY_DELAY_S = 0.5

# --- haptics: DRV2605L (optional) -------------------------------------------
DRV2605_ADDR = 0x5A
HAPTIC_MOTOR = "erm"            # the assembled motor is an ERM disc, not an LRA
HAPTIC_LIBRARY = 1              # 1-5 = ERM, 6 = LRA
EFFECT_TICK = 14                # scroll detent
EFFECT_CLICK = 1                # select
EFFECT_BACK = 7                 # back
EFFECT_PULSE = 47               # generation finished

# --- UI ---------------------------------------------------------------------
FPS = 15                        # cap; full-frame push measures ~40 ms on this
                                # board, so 20 fps would eat a core. Dirty-rect
                                # pushes (UI_LEAN) keep the real cost far lower.
STRIP_H = 38                    # stats strip height
BODY_Y = STRIP_H + 2
WHEEL_ROWS = 5
LINE_H = 16


def _first_font(*candidates: str) -> str:
    """DejaVu on the Pi (install.sh apt-installs fonts-dejavu-core); the macOS
    fallbacks exist only so tools/preview.py renders a realistic layout off
    device. Returns the first candidate regardless if none are present, and
    ui._font() degrades to Pillow's built-in face."""
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


FONT_PATH = _first_font(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)
FONT_BOLD_PATH = _first_font(
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    FONT_PATH,
)
FONT_BODY = 13
FONT_SMALL = 11
STATS_REFRESH_S = 0.5           # how often the strip re-samples RAM

COL_BG = (11, 14, 17)
COL_STRIP = (21, 26, 31)
COL_TEXT = (229, 231, 235)
COL_DIM = (107, 114, 128)
COL_ACCENT = (74, 222, 128)
COL_WARN = (251, 191, 36)
COL_ERR = (248, 113, 113)

# --- generation -------------------------------------------------------------
# ChatML, which is what SmolLM2, Qwen2.5 and LFM2 all use. If you swap in a
# model with a different template (Llama 3, Gemma), change this and STOP.
PROMPT_TEMPLATE = (
    "<|im_start|>system\n{system}<|im_end|>\n"
    "<|im_start|>user\n{user}<|im_end|>\n"
    "<|im_start|>assistant\n"
)
SYSTEM_PROMPT = (
    "You are a concise assistant running on a tiny computer. "
    "Answer in at most three short sentences."
)
STOP = ["<|im_end|>", "<|endoftext|>", "<|im_start|>"]
TEMPERATURE = 0.7
TOP_P = 0.9
