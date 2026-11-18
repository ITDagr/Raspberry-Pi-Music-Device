"""Tiny valid audio files for webapp tests: an ID3-tagged MP3 (silent,
hand-built MPEG1 Layer III frames — mutagen only parses headers) and an
untagged WAV."""
from __future__ import annotations

import io
import struct
import wave
from pathlib import Path

# MPEG1 Layer III, 64 kbps, 48 kHz, mono, no padding -> exactly 192 B/frame
_FRAME = bytes([0xFF, 0xFB, 0x54, 0xC0]) + b"\x00" * 188


def make_mp3(path: Path, title: str, artist: str, album: str,
             track_no: int = 0, frames: int = 30) -> Path:
    path.write_bytes(_FRAME * frames)
    from mutagen.easyid3 import EasyID3
    from mutagen.mp3 import MP3

    m = MP3(str(path))
    m.add_tags()
    m.save()
    tags = EasyID3(str(path))
    tags["title"], tags["artist"], tags["album"] = title, artist, album
    if track_no:
        tags["tracknumber"] = str(track_no)
    tags.save()
    return path


def mp3_bytes(title: str, artist: str, album: str, track_no: int = 0,
              tmp_dir: Path = None) -> bytes:
    import tempfile

    with tempfile.TemporaryDirectory(dir=tmp_dir) as d:
        p = make_mp3(Path(d) / "t.mp3", title, artist, album, track_no)
        return p.read_bytes()


def wav_bytes(seconds: float = 0.5, rate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(seconds * rate))
    return buf.getvalue()
