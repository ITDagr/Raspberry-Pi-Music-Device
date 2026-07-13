"""Config sanity: pins are ints, timings positive, levels in range."""
from __future__ import annotations

from shared import config

PIN_NAMES = ["PIN_DC", "PIN_RST", "PIN_BL", "PIN_POWER_SWITCH", "SPI_BUS",
             "SPI_DEVICE", "I2C_BUS", "SEESAW_ADDR", "DRV2605_ADDR",
             "SEESAW_BTN_SELECT", "SEESAW_BTN_UP", "SEESAW_BTN_LEFT",
             "SEESAW_BTN_DOWN", "SEESAW_BTN_RIGHT", "EFFECT_TICK",
             "EFFECT_CLICK", "EFFECT_BACK", "EFFECT_PULSE"]

TIMING_NAMES = ["FPS", "FPS_DIM", "FPS_SLEEP", "AUTOSAVE_INTERVAL_S",
                "DIM_AFTER_S", "SLEEP_AFTER_S", "VOLUME_FLASH_S",
                "STARTUP_DURATION_S", "MPD_RETRY_S", "PISUGAR_POLL_S",
                "PISUGAR_REPROBE_S", "BT_CONNECT_MIN_S", "BT_CONNECT_MAX_S",
                "BACK_HOLD_S", "DEBOUNCE_S", "POWER_SWITCH_DEBOUNCE_S",
                "SOFT_OFF_POLL_HZ", "SPI_SPEED_HZ"]


def test_pins_are_ints():
    for name in PIN_NAMES:
        assert isinstance(getattr(config, name), int), name


def test_timings_positive():
    for name in TIMING_NAMES:
        assert getattr(config, name) > 0, name
    assert config.SLEEP_AFTER_S > config.DIM_AFTER_S
    assert config.BT_CONNECT_MAX_S > config.BT_CONNECT_MIN_S


def test_levels_and_ranges():
    assert 0.0 < config.DIM_LEVEL < 1.0
    assert 0.1 <= config.WAKE_LEVEL <= 1.0
    assert 0 <= config.DEFAULT_VOLUME <= 100
    assert config.BRIGHTNESS_MIN < config.BRIGHTNESS_MAX <= 100
    assert config.MENU_VISIBLE >= 3
    assert config.ACCEL_STEP >= 1 and config.ACCEL_DETENTS >= 1
