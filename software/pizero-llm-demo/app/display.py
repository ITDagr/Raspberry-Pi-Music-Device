"""pizero-llm-demo — ST7789 panel over raw spidev, fed PIL Images.

Adapted from pimusicdevicev2's pi/display_pi.py. Same panel init, same
numpy -> RGB565 full-frame path; the only change is the input type (a PIL
Image instead of a pygame Surface), which is what lets this project skip
pygame entirely and hand ~35 MB back to the model.

A 240x240x2 frame is ~115 KB, about 15 ms on the wire at 62.5 MHz. Region
pushes (config.UI_LEAN) send only a dirty rectangle — ~12 KB for the stats
strip — which keeps SPI and CPU out of the inference threads' way.
"""
from __future__ import annotations

import time

import numpy as np
from PIL import Image

from app import config

_MADCTL = {0: 0x00, 90: 0x60, 180: 0xC0, 270: 0xA0}


class Display:
    def __init__(self) -> None:
        import spidev
        import RPi.GPIO as GPIO

        self._gpio = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in (config.PIN_DC, config.PIN_RST, config.PIN_BL):
            GPIO.setup(pin, GPIO.OUT)
        self._pwm = GPIO.PWM(config.PIN_BL, config.BACKLIGHT_PWM_HZ)
        self._pwm.start(0)

        self._spi = spidev.SpiDev()
        self._spi.open(config.SPI_BUS, config.SPI_DEVICE)
        self._spi.max_speed_hz = config.PANEL["baudrate"]
        self._spi.mode = 0

        self._warned = False
        self._reset()
        self._init_panel()
        self.set_backlight(config.BACKLIGHT_LEVEL)

    # --- low level ----------------------------------------------------------
    def _reset(self) -> None:
        g = self._gpio
        g.output(config.PIN_RST, g.HIGH); time.sleep(0.05)
        g.output(config.PIN_RST, g.LOW);  time.sleep(0.05)
        g.output(config.PIN_RST, g.HIGH); time.sleep(0.15)

    def _cmd(self, command: int, *data: int) -> None:
        self._gpio.output(config.PIN_DC, self._gpio.LOW)
        self._spi.writebytes([command])
        if data:
            self._gpio.output(config.PIN_DC, self._gpio.HIGH)
            self._spi.writebytes(list(data))

    def _init_panel(self) -> None:
        self._cmd(0x01); time.sleep(0.15)          # SWRESET
        self._cmd(0x11); time.sleep(0.12)          # SLPOUT
        self._cmd(0x3A, 0x55)                      # COLMOD: 16-bit RGB565
        self._cmd(0x36, _MADCTL[config.PANEL["rotation"]])
        self._cmd(0x21 if config.PANEL["invert"] else 0x20)
        self._cmd(0x13)                            # NORON
        self._cmd(0x29); time.sleep(0.1)           # DISPON

    def _set_window(self, x: int, y: int, w: int, h: int) -> None:
        x0 = config.PANEL["x_offset"] + x
        y0 = config.PANEL["y_offset"] + y
        x1, y1 = x0 + w - 1, y0 + h - 1
        self._cmd(0x2A, x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)   # CASET
        self._cmd(0x2B, y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)   # RASET

    @staticmethod
    def _to_rgb565(arr: np.ndarray) -> bytes:
        a = arr.astype(np.uint16)
        px = (((a[:, :, 0] & 0xF8) << 8)
              | ((a[:, :, 1] & 0xFC) << 3)
              | (a[:, :, 2] >> 3))
        return px.byteswap().tobytes()  # the panel wants big-endian pixels

    # --- public -------------------------------------------------------------
    def push(self, img: Image.Image, rect: tuple[int, int, int, int] | None = None) -> None:
        """Blit `img`. rect = (x, y, w, h) sends only that sub-rectangle."""
        try:
            arr = np.asarray(img if img.mode == "RGB" else img.convert("RGB"))
            if rect is None:
                x, y, w, h = 0, 0, config.SIZE, config.SIZE
            else:
                x, y, w, h = rect
                arr = arr[y:y + h, x:x + w]
            buf = self._to_rgb565(arr)
            self._set_window(x, y, w, h)
            self._cmd(0x2C)  # RAMWR
            self._gpio.output(config.PIN_DC, self._gpio.HIGH)
            self._spi.writebytes2(buf)
        except Exception as exc:  # a flaky panel must never kill the UI
            if not self._warned:
                print(f"display: push failed ({exc})")
                self._warned = True

    def set_backlight(self, level: float) -> None:
        try:
            self._pwm.ChangeDutyCycle(max(0.0, min(1.0, level)) * 100)
        except Exception:
            pass

    def close(self) -> None:
        """Blank the panel so a restart doesn't leave a frozen frame up."""
        try:
            self.set_backlight(0.0)
            self._cmd(0x28)  # DISPOFF
            self._cmd(0x10)  # SLPIN
        except Exception:
            pass
        try:
            self._pwm.stop()
            self._spi.close()
            self._gpio.cleanup()
        except Exception:
            pass
