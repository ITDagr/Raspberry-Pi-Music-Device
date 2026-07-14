"""The center button's gesture machine — the device's main control. Both
targets run this exact code (Pi: seesaw edges, Mac: Enter/Space), so these
tests pin the real-device behavior."""
from __future__ import annotations

from shared import config
from shared.encoder import CenterButton


def test_short_press_fires_select_on_release():
    b = CenterButton()
    b.press(10.0)
    assert b.poll(10.1) == []            # under the threshold: nothing yet
    assert b.release(10.2) == ["select"]
    assert b.poll(10.3) == []            # nothing lingers after release


def test_hold_fires_back_at_threshold_and_swallows_release():
    b = CenterButton()
    b.press(10.0)
    assert b.poll(10.0 + config.BACK_HOLD_S - 0.01) == []
    # frames poll every ~33 ms; the first poll past the threshold fires
    assert b.poll(10.0 + config.BACK_HOLD_S + 0.001) == ["back"]
    assert b.poll(10.0 + config.BACK_HOLD_S + 1.0) == []  # back fires ONCE
    assert b.release(12.0) == []         # the hold's release is not a select


def test_two_taps_are_two_selects():
    b = CenterButton()
    b.press(1.0)
    assert b.release(1.1) == ["select"]
    b.press(1.3)
    assert b.release(1.4) == ["select"]


def test_release_without_press_is_noop():
    assert CenterButton().release(5.0) == []


def test_second_key_aliasing_the_button_is_ignored():
    # Mac: Enter held, Space tapped — one logical button, one gesture
    b = CenterButton()
    b.press(1.0)     # Enter down
    b.press(1.2)     # Space down: ignored, does not reset the hold timer
    assert b.poll(1.0 + config.BACK_HOLD_S + 0.001) == ["back"]


def test_hold_after_tap_still_works():
    b = CenterButton()
    b.press(1.0)
    b.release(1.1)
    b.press(2.0)
    assert b.poll(2.0 + config.BACK_HOLD_S + 0.001) == ["back"]
    assert b.release(3.0) == []
