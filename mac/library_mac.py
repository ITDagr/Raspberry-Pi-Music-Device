"""device v2 — deterministic synthetic music catalog for the Mac prototype.

Seed 42 builds ~7 artists x 1-2 albums x 4-7 tracks (~60 tracks, 12-25 s
each). ensure_audio() renders each one as a mono 16-bit 22050 Hz WAV in
mac/_audio/ using only stdlib (math/array/wave): a seeded chip-tune with two
square-wave oscillators alternating melody and bass eighth-notes. Durations
are sample-exact so the player's finish detection is accurate. Existing files
are never regenerated.
"""
from __future__ import annotations

import random
import wave
from array import array
from pathlib import Path

from shared.hardware import Track

RATE = 22050
AUDIO_DIR = Path(__file__).resolve().parent / "_audio"

_ARTIST_A = ["Neon", "Velvet", "Crystal", "Echo", "Solar", "Midnight", "Paper",
             "Silver", "Lunar", "Static"]
_ARTIST_B = ["Foxes", "Harbor", "Circuit", "Meadow", "Signal", "Parade",
             "Atlas", "Drift", "Chorus", "Motel"]
_ALBUM_A = ["Golden", "Quiet", "Electric", "Distant", "Broken", "Endless",
            "Hidden", "Violet", "Paper", "Slow"]
_ALBUM_B = ["Hours", "Maps", "Waves", "Gardens", "Lights", "Rooms", "Roads",
            "Skies", "Winters", "Engines"]
_TITLE_A = ["Falling", "Waiting", "Running", "Dreaming", "Turning", "Shining",
            "Fading", "Burning", "Gliding", "Drifting", "Calling", "Hiding"]
_TITLE_B = ["Home", "Alone", "Tonight", "Again", "Away", "Slowly", "Forever",
            "Underneath", "Sideways", "North", "Backwards", "Twice"]

_PENTA = [0, 3, 5, 7, 10]  # minor pentatonic intervals

TRACKS: list[Track] = []
_PARAMS: dict[int, tuple[int, int, int]] = {}  # index -> (eighth_samples, n_notes, seed)


def _pick_pairs(rng: random.Random, a: list[str], b: list[str], n: int) -> list[str]:
    names: set = set()
    while len(names) < n:
        names.add(f"{rng.choice(a)} {rng.choice(b)}")
    return sorted(names)


def _build_catalog() -> None:
    rng = random.Random(42)
    entries = []  # (artist, album, track_no, title, eighth_samples, n_notes, seed)
    for artist in _pick_pairs(rng, _ARTIST_A, _ARTIST_B, 7):
        for album in _pick_pairs(rng, _ALBUM_A, _ALBUM_B, rng.randint(1, 2)):
            titles = _pick_pairs(rng, _TITLE_A, _TITLE_B, rng.randint(4, 7))
            rng.shuffle(titles)
            for track_no, title in enumerate(titles, start=1):
                bpm = rng.choice(range(96, 169, 8))
                eighth_samples = int(RATE * 60 / bpm / 2)
                target = rng.uniform(12.0, 25.0)
                n_notes = max(8, round(target * RATE / eighth_samples))
                seed = rng.randrange(1 << 30)
                entries.append((artist, album, track_no, title,
                                eighth_samples, n_notes, seed))
    entries.sort(key=lambda e: (e[0].lower(), e[1].lower(), e[2]))
    for index, (artist, album, track_no, title, ei, nn, seed) in enumerate(entries):
        TRACKS.append(Track(
            index=index, title=title, artist=artist, album=album,
            track_no=track_no, duration=nn * ei / RATE,
            file=str(AUDIO_DIR / f"track_{index:03d}.wav"),
        ))
        _PARAMS[index] = (ei, nn, seed)


_build_catalog()


def _square_block(freq: float, n_samples: int, amp: int) -> list[int]:
    """One note of square wave, built with C-speed list ops, faded at the edges."""
    if amp == 0 or freq <= 0:
        return [0] * n_samples
    period = max(2, int(RATE / freq))
    half = period // 2
    cycle = [amp] * half + [-amp] * (period - half)
    block = (cycle * (n_samples // period + 1))[:n_samples]
    fade = min(80, n_samples // 2)
    for i in range(fade):  # soften note boundaries so they don't click
        f = i / fade
        block[i] = int(block[i] * f)
        block[-1 - i] = int(block[-1 - i] * f)
    return block


def _midi_hz(m: int) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _gen_track(path: Path, eighth_samples: int, n_notes: int, seed: int) -> None:
    rng = random.Random(seed)
    root = rng.randint(45, 57)  # A2..A3
    samples = array("h")
    for i in range(n_notes):
        if i % 2 == 0:  # oscillator 1: melody, an octave (or two) up
            if rng.random() < 0.15:
                block = [0] * eighth_samples  # rest
            else:
                note = root + 12 + rng.choice(_PENTA) + 12 * rng.choice((0, 0, 1))
                block = _square_block(_midi_hz(note), eighth_samples, 9000)
        else:  # oscillator 2: bass on the root/fifth
            note = root + rng.choice((0, 0, 5, 7))
            block = _square_block(_midi_hz(note), eighth_samples, 7000)
        samples.extend(block)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(samples.tobytes())


def ensure_audio() -> None:
    """Generate any missing WAVs (skipped entirely once the cache exists)."""
    AUDIO_DIR.mkdir(exist_ok=True)
    for t in TRACKS:
        p = Path(t.file)
        if not p.exists():
            _gen_track(p, *_PARAMS[t.index])
