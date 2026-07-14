"""Menu grammar: wrap, nav stack, select semantics, payloads, context extraction."""
from __future__ import annotations

import pytest

from shared.hardware import Track
from shared.menu_core import (Menu, MenuController, build_default_menus,
                              extract_play_context)


@pytest.fixture
def tracks():
    data = [
        ("Alpha", "First", 1, "Aa Song"),
        ("Alpha", "First", 2, "Bb Song"),
        ("Alpha", "Second", 1, "Cc Song"),
        ("Beta", "Third", 1, "Dd Song"),
        ("Beta", "Third", 2, "Ee Song"),
        ("Beta", "Third", 3, "Ff Song"),
    ]
    return [
        Track(index=i, title=t, artist=a, album=al, track_no=n, duration=10.0,
              file=f"/x/{i}.wav")
        for i, (a, al, n, t) in enumerate(data)
    ]


@pytest.fixture
def ctrl(tracks):
    return MenuController(build_default_menus(tracks))


def test_cursor_wraps_both_ways(ctrl):
    assert ctrl.cursor == 0
    ctrl.scroll_up()
    assert ctrl.cursor == 3  # home has 4 rows
    ctrl.scroll_down()
    assert ctrl.cursor == 0


def test_enter_and_back_stack(ctrl):
    assert ctrl.select() == "enter"          # Music
    assert ctrl.current_name == "music"
    ctrl.back()
    assert ctrl.current_name == "home"
    ctrl.back()                              # no-op at root
    assert ctrl.current_name == "home"


def test_back_restores_cursor(ctrl):
    for _ in range(3):
        ctrl.scroll_down()                   # Settings
    ctrl.select()
    assert ctrl.current_name == "settings"
    ctrl.back()
    assert ctrl.current_name == "home" and ctrl.cursor == 3


def test_select_result_semantics(ctrl):
    ctrl.scroll_down()                       # Now Playing
    assert ctrl.select() == "mode"
    assert ctrl.last_action == "nowplaying"
    ctrl.scroll_down()                       # Shuffle All
    assert ctrl.select() == "action"
    assert ctrl.last_action == "shuffle"


def test_bluetooth_is_a_mode(ctrl):
    for _ in range(3):
        ctrl.scroll_down()
    ctrl.select()                            # settings
    assert ctrl.select() == "mode"
    assert ctrl.last_action == "bluetooth"


def test_play_payload_from_songs(ctrl):
    ctrl.select()                            # music
    ctrl.scroll_down(); ctrl.scroll_down(); ctrl.scroll_down()
    ctrl.select()                            # songs (after Playlists/Artists/Albums)
    assert ctrl.current_name == "songs"
    assert ctrl.select() == "action"
    assert ctrl.last_action.startswith("play:")


def test_empty_menu_selects_none():
    c = MenuController({"home": Menu("empty", [])})
    assert c.select() == "none"
    c.scroll_down()                          # must not raise
    assert c.cursor == 0


def test_artist_context_album_track_order(ctrl):
    assert extract_play_context(ctrl.menus["artist_alpha"]) == [0, 1, 2]
    assert extract_play_context(ctrl.menus["artist_beta"]) == [3, 4, 5]


def test_album_context(ctrl):
    assert extract_play_context(ctrl.menus["album_beta_third"]) == [3, 4, 5]


def test_songs_context_sorted_artist_title(ctrl):
    assert extract_play_context(ctrl.menus["songs"]) == [0, 1, 2, 3, 4, 5]


def test_view_window_and_scroll(tracks):
    ctrl = MenuController(build_default_menus(tracks))
    ctrl.select()                            # music
    ctrl.scroll_down(); ctrl.scroll_down(); ctrl.scroll_down()
    ctrl.select()                            # songs, 6 rows > 5 visible
    for _ in range(5):
        ctrl.scroll_down()
    v = ctrl.view()
    assert v.total == 6 and len(v.items) == 5
    assert v.window_start == 1 and v.cursor == 4  # cursor pinned to the last row
