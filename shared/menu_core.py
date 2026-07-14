"""device v2 — menu data model and navigation controller.

Menu grammar (MenuItem.action):
    menu:<name>            descend into another menu
    back                   pop one level
    mode:<nowplaying|bluetooth>   switch app mode
    do:<verb[:arg]>        app-level action, e.g. do:play:17, do:shuffle

MenuController keeps a navigation stack of (menu, cursor, scroll) so backing
out restores the exact row you left. view() returns the render model for
shared.screen. build_default_menus() assembles the whole tree from TRACKS.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from shared import config
from shared.hardware import Track


@dataclass(frozen=True)
class MenuItem:
    label: str
    action: str


@dataclass(frozen=True)
class Menu:
    title: str
    items: list[MenuItem]


@dataclass(frozen=True)
class MenuView:
    """The one render model for menus: produced by MenuController.view(),
    consumed by ScreenRenderer.draw(). No duck typing between the two."""

    title: str
    items: list[str]
    cursor: int        # index within the visible window
    window_start: int  # first visible row's absolute index
    total: int
    chevrons: tuple[bool, ...] = ()  # per visible row: descends into a submenu


@dataclass
class _Frame:
    name: str
    cursor: int = 0
    scroll: int = 0


class MenuController:
    def __init__(self, menus: dict[str, Menu], root: str = "home"):
        self.menus = menus
        self._root = root
        self._stack: list[_Frame] = [_Frame(root)]
        self.last_action: str = ""

    def rebuild(self, menus: dict[str, Menu]) -> None:
        """Swap in a freshly built tree (the library changed at runtime),
        preserving as much of the current navigation path as still exists:
        a vanished menu truncates the stack there, cursors clamp to the new
        row counts."""
        self.menus = menus
        kept: list[_Frame] = []
        for frame in self._stack:
            if frame.name not in menus:
                break
            frame.cursor = min(frame.cursor, max(0, len(menus[frame.name].items) - 1))
            kept.append(frame)
        self._stack = kept or [_Frame(self._root)]

    # --- navigation ----------------------------------------------------------
    @property
    def _frame(self) -> _Frame:
        return self._stack[-1]

    @property
    def current_name(self) -> str:
        return self._frame.name

    @property
    def cursor(self) -> int:
        return self._frame.cursor

    def _items(self) -> list[MenuItem]:
        return self.menus[self._frame.name].items

    def scroll_down(self) -> None:
        items = self._items()
        if items:
            self._frame.cursor = (self._frame.cursor + 1) % len(items)

    def scroll_up(self) -> None:
        items = self._items()
        if items:
            self._frame.cursor = (self._frame.cursor - 1) % len(items)

    def select(self) -> str:
        """Activate the cursor row: 'enter' | 'back' | 'mode' | 'action' | 'none'."""
        items = self._items()
        if not items:
            return "none"
        action = items[self._frame.cursor].action
        if action.startswith("menu:"):
            self._stack.append(_Frame(action[5:]))
            return "enter"
        if action == "back":
            self.back()
            return "back"
        if action.startswith("mode:"):
            self.last_action = action[5:]
            return "mode"
        if action.startswith("do:"):
            self.last_action = action[3:]
            return "action"
        return "none"

    def back(self) -> None:
        """Pop one level; no-op at the root."""
        if len(self._stack) > 1:
            self._stack.pop()

    def view(self) -> MenuView:
        menu = self.menus[self._frame.name]
        f = self._frame
        visible = config.MENU_VISIBLE
        # v1-style windowing: keep the cursor centered where possible
        start = max(0, min(f.cursor - visible // 2, len(menu.items) - visible))
        f.scroll = start
        window = menu.items[start : start + visible]
        return MenuView(
            title=menu.title,
            items=[i.label for i in window],
            cursor=f.cursor - start,
            window_start=start,
            total=len(menu.items),
            chevrons=tuple(i.action.startswith("menu:") for i in window),
        )


def extract_play_context(menu: Menu) -> list[int]:
    """The track indices a menu would play, in listed order."""
    return [
        int(i.action.rsplit(":", 1)[1])
        for i in menu.items
        if i.action.startswith("do:play:")
    ]


def _slug(text: str, used: set) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "x"
    slug, n = base, 2
    while slug in used:
        slug, n = f"{base}_{n}", n + 1
    used.add(slug)
    return slug


def build_default_menus(tracks: list[Track]) -> dict[str, Menu]:
    menus: dict[str, Menu] = {}
    used: set = set()

    menus["home"] = Menu("device", [
        MenuItem("Music", "menu:music"),
        MenuItem("Now Playing", "mode:nowplaying"),
        MenuItem("Shuffle All", "do:shuffle"),
        MenuItem("Settings", "menu:settings"),
    ])
    menus["music"] = Menu("Music", [
        MenuItem("Artists", "menu:artists"),
        MenuItem("Albums", "menu:albums"),
        MenuItem("Songs", "menu:songs"),
        MenuItem("Shuffle", "do:shuffle"),
    ])
    menus["settings"] = Menu("Settings", [
        MenuItem("Bluetooth", "mode:bluetooth"),
        MenuItem("Battery", "do:battery"),
        MenuItem("Brightness", "do:brightness"),
        MenuItem("About", "do:about"),
    ])

    # Artists -> artist_<slug> menus (tracks in album/track order)
    artist_rows = []
    for artist in sorted({t.artist for t in tracks}, key=str.lower):
        name = f"artist_{_slug(artist, used)}"
        ts = sorted(
            (t for t in tracks if t.artist == artist),
            key=lambda t: (t.album.lower(), t.track_no, t.title.lower()),
        )
        menus[name] = Menu(artist, [MenuItem(t.title, f"do:play:{t.index}") for t in ts])
        artist_rows.append(MenuItem(artist, f"menu:{name}"))
    menus["artists"] = Menu("Artists", artist_rows)

    # Albums -> album_<slug> menus (unique per artist+album, tracks by track_no)
    album_rows = []
    seen: set = set()
    for t in sorted(tracks, key=lambda t: (t.artist.lower(), t.album.lower(), t.track_no)):
        key = (t.artist, t.album)
        if key in seen:
            continue
        seen.add(key)
        name = f"album_{_slug(f'{t.artist}_{t.album}', used)}"
        ts = sorted(
            (x for x in tracks if (x.artist, x.album) == key),
            key=lambda x: (x.track_no, x.title.lower()),
        )
        menus[name] = Menu(t.album, [MenuItem(x.title, f"do:play:{x.index}") for x in ts])
        album_rows.append(MenuItem(t.album, f"menu:{name}"))
    menus["albums"] = Menu("Albums", album_rows)

    # Songs: every track sorted (artist, title)
    songs = sorted(tracks, key=lambda t: (t.artist.lower(), t.title.lower()))
    menus["songs"] = Menu("Songs", [MenuItem(t.title, f"do:play:{t.index}") for t in songs])

    return menus
