# pizero-llm-demo

A language model running entirely on a Raspberry Pi Zero 2 W — 512 MB of RAM,
four 1 GHz Cortex-A53 cores, no network, no GPU — driving a 240×240 ST7789
panel and an ANO rotary encoder.

The demo is not that it writes sentences. The demo is the stats strip: model,
quantisation, live token rate, and how close the machine is to its RAM ceiling,
visible the whole time it's working.

```
┌────────────────────────────────┐
│ SmolLM2-360M  Q4_0    THINKING │
│ 4.2 tok/s   402/472 MB         │
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░│ ← RAM pressure
├────────────────────────────────┤
│ A transistor is a tiny         │
│ electronic switch. A small     │
│ current at one terminal ▉      │
└────────────────────────────────┘
```

## Hardware

Same recipe as pimusicdevicev2, and the drivers are adapted from it:

| Part | Detail |
|---|---|
| Raspberry Pi Zero 2 W | 64-bit Pi OS **Lite** — a 32-bit userland costs real throughput |
| Adafruit EYESPI Pi Beret | SPI0, DC=25, RST=27, backlight PWM=18 |
| 1.54" 240×240 ST7789 | `y_offset=80`, rotation 180, INVON |
| ANO rotary encoder (seesaw) | I²C `0x49` |
| DRV2605L + ERM disc | I²C `0x5A` — optional, degrades to silent |

## Quick start

```bash
# 1. copy the tree to the Pi
tar czf - --exclude .git . | ssh pi@<host> \
  'mkdir -p ~/pizero-llm-demo && tar xzf - -C ~/pizero-llm-demo'

# 2. on the Pi
cd ~/pizero-llm-demo && ./install.sh
sudo reboot                           # gpu_mem=16 only frees its 48 MB after one
```

Nothing is compiled. `install.sh` pulls llama.cpp's official prebuilt
`bin-ubuntu-arm64` release, which ships several CPU backend variants — including
`libggml-cpu-armv8.0_1.so` — and dispatches at runtime. armv8.0 is exactly this
A53's baseline, so it runs as-is. Verified on the device.

That matters because building `llama-server` here is genuinely painful: its
cpp-httplib translation unit wants over 1 GB of RAM for a single `g++`
invocation, which on 512 MB means 2–4 hours of swap thrashing. `zram` does not
help — it adds no capacity, it trades RAM for RAM.

`tools/cross-build-llama.sh` remains as a fallback if you ever need to build
from a specific commit; it needs Docker and pins `-mcpu=cortex-a53` with
`GGML_NATIVE=OFF`, without which the binary SIGILLs on this CPU.

`install.sh` is idempotent. `--app-only` reinstalls just the Python app and
units for a fast edit loop; `--no-model` skips the download.

> Use `tar` over ssh rather than `scp`, deliberately. An `scp` directory target
> drops files at the repo root as dead files the app never imports — the exact
> failure that cost a whole debugging session on the music device.

## Controls

| Input | Wheel | While answering |
|---|---|---|
| rotate / up / down | pick a prompt | scroll the answer |
| left / right | switch prompt set | — |
| press | run it | stop early |
| press (after) | — | regenerate |
| hold ≈0.6 s | — | back to the wheel |

Three prompt sets ship — `DEMO`, `QUIZ`, `ORACLE` — in `app/prompts.py`. That
file is the one place to change what the device *does*; nothing references its
contents by name, so adding a set is a two-line edit.

There is no text entry. A rotary and five buttons is a selection device, so the
prompts are canned on purpose: hand someone the device and they can use it in
three seconds.

## Choosing the model

Edit `config.sh`. Three profiles are pre-written, with real file sizes:

| Profile | Model | Size | Notes |
|---|---|---|---|
| **SAFE** (default) | SmolLM2-360M-Instruct Q4_0 | 219 MiB | plain Llama arch; **measured 6.90 tok/s** |
| BETTER | LFM2-350M Q4_K_M | 219 MiB | newer, scores higher; needs recent llama.cpp |
| ~~STRETCH~~ | ~~Qwen2.5-0.5B-Instruct Q4_0~~ | 337 MiB | **does not fit** — see below |

The budget, measured on the board rather than estimated:

```
  463 MB  MemTotal (415 MB stock; gpu_mem=16 recovers 48 MB)
− 150 MB  Pi OS 13 Lite with bluetooth trimmed
−  65 MB  Python UI (Pillow + numpy + Blinka + rpi-lgpio)
−  60 MB  llama-server anon: process + compute buffers + KV @ -c 512
= ~190 MB of page cache left to hold mmap'd weights
```

The 219 MiB default already exceeds that slightly, which is why ~100 MB of zram
swap sits in use at rest. It runs fine at 6.9 tok/s, but there is no room above
it: the 337 MiB Qwen profile is **not** viable on this board. It is kept in
`config.sh`, commented, for a board with more memory.

Two things worth knowing before you swap models:

**Bigger is a cliff, not a slope.** llama.cpp mmaps the GGUF, so a model larger
than RAM still *runs* — it just pages weights off the SD card, and a dense model
reads every weight once per token. At ~22 MB/s that is `tok/s ≈ 22 / size_MB`:
a 1 GB model is roughly 45 seconds per token. There is no gentle degradation.

**Vocabulary size dominates at this scale.** Qwen's *official* 0.5B GGUFs are
all ≥396 MiB — even `Q2_K` — because they keep the embedding tensor at f16 and
a 151k-token vocab makes that ~272 MB on its own. The STRETCH profile uses
bartowski's requant, which doesn't. Always check the real file size rather than
estimating from parameter count.

**Q4_0 beats Q4_K_M here**, which is backwards from most hardware. The A53 has
no `dotprod` or `i8mm` instructions, and llama.cpp runtime-repacks Q4_0 into an
ARM-friendly layout on load. It is smaller *and* faster. Since generation is
memory-bandwidth-bound, fewer bytes per token is the whole game.

## Architecture

Two services, deliberately separate:

- **`llamad.service`** — `llama-server` on loopback. Keeps the model mmap'd and
  warm between prompts, so only the first answer pays the page-in cost. Runs
  `Nice=5` with `OOMScoreAdjust=-500`: if something must die under memory
  pressure it should be the UI, which systemd brings straight back.
- **`llmdemo.service`** — the Python UI. ~20 fps, single-threaded, with
  generation on a worker thread that only pushes into a queue. A 4 tok/s stream
  never blocks the encoder read or the panel write.

No pygame: Pillow + numpy render the frame for roughly 35 MB less resident
memory, which is most of a quantisation step's worth of model.

The UI handles `SIGTERM` and blanks the panel on exit, so `systemctl restart`
returns in well under a second instead of hanging until the stop timeout — the
music device's `pkill -9` workaround is not needed here.

Both encoder resilience features are carried over from pimusicdevicev2, because
the underlying hardware fault is the same: a per-frame delta clamp *and* a
trailing-window detent-rate breaker, so a marginal STEMMA QT connection cannot
flood the event queue and wedge the UI; plus a 20-second patient init retry,
because on a cold boot the seesaw's own hardware-ID read comes back corrupt for
several seconds.

## Tuning and troubleshooting

```bash
journalctl -u llamad -f          # model load, token rates, OOM
journalctl -u llmdemo -f         # display, encoder, HTTP errors
./tools/bench.sh                 # real prefill + generation rates
free -m                          # the number that decides everything
python3 tools/i2c_scan.py 1      # (from the music repo) expect 0x49 and 0x5A
```

- **Screen black, service running** → I²C. Per your own notes on this hardware,
  a marginal STEMMA QT connection is the usual culprit, not the code.
- **`tok/s` far below ~4** → the weights aren't staying resident. Check
  `free -m` for swap in use, then drop a quant level in `config.sh`.
- **RAM bar red and generation crawls** → the model is too big for what's left.
  This is the cliff, not a tuning problem.
- **`llama-server` dies instantly after cross-compiling** → SIGILL. Rebuild with
  `-mcpu=cortex-a53` and `-DGGML_NATIVE=OFF`; `install.sh` detects exit code 132
  and says so.
- **Unknown architecture in the llamad log** → the model needs a newer
  llama.cpp than `LLAMA_REF` pinned. Fall back to the SAFE profile.

## Developing off-device

```bash
uv run --python 3.12 --with pillow --with numpy python tools/preview.py
```

Renders every UI state to `preview.png` at 4× with no hardware, and asserts the
word-wrap stays inside the text column and that an unchanged frame reports no
dirty rectangles.

## Measured on the real device

Raspberry Pi Zero 2 W Rev 1.0, Raspberry Pi OS 13 (trixie) Lite arm64,
kernel 6.18, Python 3.13, llama.cpp b10930, SmolLM2-360M-Instruct Q4_0:

| | |
|---|---|
| generation | **6.90 tok/s** (`llama-bench` tg32) |
| prefill | **10.87 tok/s** (`llama-bench` pp64) |
| model on disk | 217.39 MiB, 361.82 M params |
| MemTotal | 415 MiB stock → **463 MiB** after `gpu_mem=16` |
| llama-server RSS | ~261 MB |
| model load → healthy | 14 s from cold |
| full-frame panel push | ~40 ms (numpy RGB565 dominates, not SPI) |
| stats-strip region push | ~5 ms |

A repeated prompt prefills in one token because `cache_prompt` keeps the system
prefix warm, so only the first question of a session pays the full prefill.

Caveat: ~100 MB of zram swap is in use at rest. It works, but there is no
headroom — the 337 MiB STRETCH profile is not viable on this board.

## Status

Installed and running on the device. Verified end to end: prebuilt llama.cpp
runs on the A53, the model loads, inference returns correct answers at the rate
above, both systemd units parse clean, the panel initialises and accepts frames,
the encoder enumerates over I2C, and SIGTERM shuts the UI down promptly.

Not yet confirmed **by eye**: that the rendered UI looks right on the physical
panel, and that turning/pressing the encoder drives it as intended.

No DRV2605L is attached to this build (0x5A absent from the I2C scan), so
haptics degrade to silent — as designed.
