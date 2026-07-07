# Using the device

## Controls

| Mac key | Device control | Does |
|---|---|---|
| ↑ / ↓ | wheel detents | menus: cursor · Now Playing: volume ±5 · brightness/about: adjust |
| Enter / Space | center press | select / play-pause |
| → | right | select (menus) · next track (Now Playing) |
| ← | left | back (menus) · previous track (Now Playing) |
| Backspace | center hold 600 ms | **back — leaves the current screen everywhere** |
| Esc / close | — | quit (state saved) |

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

- **Bluetooth**: entering rescans (~6 s on the Pi). Select a device to
  connect; "…" marks connecting, a green check marks connected. Back from
  a connected view returns to the list; back again leaves. Audio routing
  setup: [bluetooth-audio.md](bluetooth-audio.md).
- **Battery**: big battery glyph, percentage, and a status caption
  ("Charging" when the PiSugar reports it).
- **Brightness**: wheel adjusts 10–100 %; takes effect immediately and is
  the screen's "awake" level. Any button exits.
- **About**: version and scrollable feature list.

## Screen dimming

After 20 s idle the screen dims to 15 %; after 60 s it sleeps (backlight
off). Any input wakes it — **the waking press is swallowed**, so you never
mis-click on a dark screen. Timings: `DIM_AFTER_S` / `SLEEP_AFTER_S`.

## Saved state

`context, position, shuffle, track, elapsed, volume, brightness` persist to
`.device_state.json` (repo root on Mac, `/home/pi/` on the Pi) — written
atomically every 10 s while playing, on every track change, and on quit.
Corrupt or missing state files are ignored safely.
