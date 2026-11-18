# Using the device

## Controls

| Mac key | Device control | Does |
|---|---|---|
| ↑ / ↓ | wheel detents | menus: cursor · Now Playing: volume ±5 · brightness/about: adjust |
| Enter / Space (tap) | center press | select / play-pause |
| Enter / Space (**hold ≥ 0.6 s**) | center hold | **back — leaves the current screen everywhere** (fires at the threshold; the release is swallowed, exactly like the hardware) |
| W / S | ring up / down | same as wheel detents |
| D or → | ring right | select (menus) · next track (Now Playing) |
| A or ← | ring left | back (menus) · previous track (Now Playing) |
| Backspace | — | back (keyboard convenience; the device gesture is the hold) |
| P | slide switch | soft power off / on |
| Esc / close | — | quit (state saved) |

The center button's tap/hold gesture machine is one piece of shared code
(`shared/encoder.py`) driven by both the Pi's seesaw and the Mac's
keyboard, so what you feel in the simulator is what the hardware does —
including the rule that only a short center press wakes a dark screen.

Spinning the wheel fast (>6 detents within 1 s) accelerates menu scrolling
to 3 rows per detent (`ENCODER_ACCEL` in config).

## Boot

A ~3 s animation (accent line → waveform → wordmark → crossfade) plays,
then the device resumes exactly where it left off: same track, position,
volume, and brightness. Playback starts automatically if something was
playing.

## Menus

```
home ── Music ── Artists ── <artist> ── tracks
     │        ├─ Albums ─── <album> ─── tracks
     │        ├─ Songs (all tracks, by artist/title)
     │        └─ Shuffle
     ├─ Now Playing
     ├─ Shuffle All
     └─ Settings ── Bluetooth · Battery · Brightness · About
```

The status bar shows the clock (left), animated equalizer bars while music
plays (center), and battery % (right, when a PiSugar is present).
Selecting a track plays it and jumps to Now Playing; the queue ("context")
becomes the list you picked from, so auto-advance walks that artist, album,
or the whole song list. Shuffle randomizes across everything.

## Now Playing

Title, artist, progress bar with knob, elapsed/remaining timecodes, a
`shuf` indicator, play/pause glyph, and a mini volume readout.

- wheel: volume (a volume card pops over the screen for 1.5 s)
- center: play/pause · right: next · left: previous
- **previous is iPod-style**: more than 3 s into a track restarts it;
  otherwise it goes to the previous track
- back returns to the menus **with music still playing**

## Settings screens

- **Playlists** (Music → Playlists): one submenu per playlist, in the
  order set in the web app — that order is the play order. "Shuffle
  playlist" at the top randomizes within it. Playlists are created and
  edited in the web app only; an empty one shows a hint row.
- **Bluetooth**: entering rescans (~6 s on the Pi). Select a device to
  connect; "…" marks connecting, a green check marks connected. Back from
  a connected view returns to the list; back again leaves. Audio routing
  setup: [bluetooth-audio.md](bluetooth-audio.md).
- **Battery**: big battery glyph, percentage, and a status caption
  ("Charging" when the PiSugar reports it).
- **Brightness**: wheel adjusts 10–100 %; takes effect immediately and is
  the screen's "awake" level. Any button exits.
- **About**: version and scrollable feature list.

## Screen dimming & wake

After 15 s idle the screen dims; after 60 s it sleeps (backlight off).
Music keeps playing either way. **Only the center button wakes a dim or
sleeping screen** — the waking press is swallowed (it never also selects),
and the wheel and other buttons do nothing at all while the screen is
dark. Timings: `DIM_AFTER_S` / `SLEEP_AFTER_S`.

## Soft power (the Beret's slide switch, or P on the Mac)

The slide switch is a GPIO input, not a real power cut, so "off" is soft:
flipping it OFF saves the full state (track, position, volume, shuffle,
brightness), stops playback, and puts the screen to sleep; the device then
only watches the switch (~4 Hz). Every other input is ignored while off.
Flipping it ON runs the startup animation and resumes exactly where you
were — booting with the switch already OFF stays dark until you flip it.

## Saved state

`context, position, shuffle, track, elapsed, volume, brightness` persist to
`.device_state.json` (repo root on Mac, `/home/pi/` on the Pi) — written
atomically every 10 s while playing, on every track change, and on quit.
Corrupt or missing state files are ignored safely.
