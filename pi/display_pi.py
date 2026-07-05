"""device v2 — ST7789V 240x240 over SPI0 + PWM backlight.

Full-frame RGB565 pushes: a 240x240x2 frame is ~115 KB, ~7.4 ms on the wire
at 62.5 MHz, comfortably 30 fps. Backlight is RPi.GPIO PWM at 1 kHz with
duty = level x 100. spidev/RPi.GPIO/numpy are imported lazily so this module
loads on a Mac.
"""
from __future__ import annotations

import time

import pygame

from shared import config
from shared.screen import SIZE


class DisplayPi:
    def __init__(self) -> None:
        import numpy
        import spidev
        import RPi.GPIO as GPIO

        self._np = numpy
        self._gpio = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(config.PIN_DC, GPIO.OUT)
        GPIO.setup(config.PIN_RST, GPIO.OUT)
        GPIO.setup(config.PIN_BL, GPIO.OUT)
        self._pwm = GPIO.PWM(config.PIN_BL, config.BACKLIGHT_PWM_HZ)
        self._pwm.start(100)

        self._spi = spidev.SpiDev()
        self._spi.open(config.SPI_BUS, config.SPI_DEVICE)
        self._spi.max_speed_hz = config.SPI_SPEED_HZ
        self._spi.mode = 0

        self.level = 1.0
        self._level_changed = False
        self._warned = False
        self._reset()
        self._init_panel()

    # --- low-level -------------------------------------------------------------
    def _reset(self) -> None:
        gpio = self._gpio
        gpio.output(config.PIN_RST, gpio.HIGH)
        time.sleep(0.05)
        gpio.output(config.PIN_RST, gpio.LOW)
        time.sleep(0.05)
        gpio.output(config.PIN_RST, gpio.HIGH)
        time.sleep(0.15)

    def _cmd(self, command: int, *data: int) -> None:
        self._gpio.output(config.PIN_DC, self._gpio.LOW)
        self._spi.writebytes([command])
        if data:
            self._gpio.output(config.PIN_DC, self._gpio.HIGH)
            self._spi.writebytes(list(data))

    def _init_panel(self) -> None:
        self._cmd(0x01)              # SWRESET
        time.sleep(0.15)
        self._cmd(0x11)              # SLPOUT
        time.sleep(0.12)
        self._cmd(0x3A, 0x55)        # COLMOD: 16-bit RGB565
        self._cmd(0x36, 0x00)        # MADCTL
        self._cmd(0x21)              # INVON (IPS panels want inversion)
        self._cmd(0x13)              # NORON
        self._cmd(0x29)              # DISPON
        time.sleep(0.1)

    def _set_window(self) -> None:
        x0 = config.DISPLAY_X_OFFSET
        y0 = config.DISPLAY_Y_OFFSET
        x1, y1 = x0 + SIZE - 1, y0 + SIZE - 1
        self._cmd(0x2A, x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)  # CASET
        self._cmd(0x2B, y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)  # RASET

    # --- Display protocol ---------------------------------------------------------
    def push_frame(self, surface: pygame.Surface) -> None:
        try:
            np = self._np
            rgb = pygame.surfarray.array3d(surface).transpose(1, 0, 2).astype(np.uint16)
            pixels = (
                ((rgb[:, :, 0] & 0xF8) << 8)
                | ((rgb[:, :, 1] & 0xFC) << 3)
                | (rgb[:, :, 2] >> 3)
            )
            buf = pixels.byteswap().tobytes()  # panel wants big-endian pixels
            self._set_window()
            self._cmd(0x2C)  # RAMWR
            self._gpio.output(config.PIN_DC, self._gpio.HIGH)
            self._spi.writebytes2(buf)
        except Exception as e:  # a flaky panel must not kill the UI
            if not self._warned:
                print(f"display: push failed ({e})")
                self._warned = True

    def set_backlight_level(self, level: float) -> None:
        self.level = max(0.0, min(1.0, float(level)))
        try:
            self._pwm.ChangeDutyCycle(self.level * 100)
        except Exception:
            pass
        self._level_changed = True

    def consume_level_change(self) -> bool:
        changed, self._level_changed = self._level_changed, False
        return changed

    def set_backlight(self, on: bool) -> None:
        self.set_backlight_level(1.0 if on else 0.0)
