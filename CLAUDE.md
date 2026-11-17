# CLAUDE.md — pimusicdevice development notes

Project overview, architecture, and design decisions live in `README.md`
("Assumptions" section especially). This file captures **operational context
for developing against the real Pi** that isn't obvious from the code — read it
before deploying or debugging hardware behavior.

## Current physical hardware (as assembled, Aug 2026)

- Raspberry Pi Zero 2 W + Adafruit EYESPI Pi Beret + 1.54" 240×240 ST7789 display.
- ANO rotary encoder (seesaw) at I²C `0x49`, via a STEMMA QT **hub**.
- DRV2605L haptic driver at I²C `0x5A`, also via the hub, driving an **ERM**
  motor (Adafruit vibrating mini disc) — **not** an LRA. Config is set for this:
  `HAPTIC_MOTOR = "erm"`, `HAPTIC_LIBRARY = 1` in `shared/config.py`.
- **No PiSugar** — runs in offline mode (system clock, battery shows "--").
- Audio is Bluetooth-only (Pi Zero has no speaker/jack).

## ⚠️ The chronic root cause: a flaky STEMMA QT connection

Most "freeze / won't boot / not detected" symptoms this device has shown trace
back to a **marginal STEMMA QT / hub connection** injecting corrupt I²C reads,
not to software. The software has been hardened to degrade gracefully at every
stage (see the bring-up log below), but **a fresh STEMMA QT cable / reseating
the hub is the real hardware fix.** When a new symptom appears, check the
connection before assuming a code regression. `python3 tools/i2c_scan.py 1`
should show `0x49` and `0x5A`.

## Deploying to the Pi (the workflow that actually works)

- Host: `pi@device.local` (IP `192.168.1.250`), user `pi`. **The login password
  is stored in Claude's private memory** (see the `pimusicdevice-pi-access`
  memory) — it is deliberately NOT in this repo. There is no passwordless SSH.
- Drive `ssh`/`scp` non-interactively with `expect` feeding the password. `sudo`
  on the Pi works without a TTY only via the `expect`-driven ssh.
- **scp MUST target the full destination subdirectory**, e.g.
  `scp shared/app.py pi@device.local:pimusicdevice/shared/app.py`. A directory
  target like `…:pimusicdevice/` drops files at the repo **root** as dead files
  the app never imports — this silently wasted a whole debugging session.
  Always `grep` a marker on the Pi afterward to confirm the file landed in the
  right place. (Batched multi-file scp in one `expect` block sometimes only
  transfers the first file — verify each, or scp one at a time.)
- **The app does not respond to SIGTERM.** `systemctl stop`/`restart` hangs in
  `stop-sigterm` for the full timeout. To restart: `sudo pkill -9 -f pi/device.py`
  (or `kill -9 <MainPID>`), then if the unit went to `failed`,
  `sudo systemctl reset-failed pimusicdevice && sudo systemctl start pimusicdevice`.
- `i2cdetect` is not on PATH for the `pi` user — use `/usr/sbin/i2cdetect -y 1`,
  or prefer `python3 tools/i2c_scan.py 1`.
- After a code push, restart the service (above) — the app only reads config and
  probes hardware **once at boot**, so newly-plugged peripherals or config
  changes need a restart to take effect.
- `sudo py-spy dump --pid <MainPID>` (py-spy is installed on the Pi) is the go-to
  for diagnosing a freeze: a healthy idle loop sits in the encoder read
  (`seesaw.py`) or `push_frame`; a freeze pinned in `_handle_event` processing
  `scroll_down` = encoder event flood.

## ‼️ System-level Pi config that is NOT in the repo (would be lost on reinstall)

These were applied by hand on the live Pi this session. `install.sh` does **not**
set them up — a fresh `install.sh` would lose them. If you re-image or reinstall,
redo these (and consider folding them into `install.sh`):

1. **Bluetooth audio backend**: `sudo apt install bluez-alsa-utils`. The
   `bluealsa` daemon runs as an **A2DP source** (`-p a2dp-source`) so the Pi
   sends audio *to* speakers/headphones.
2. **MPD Bluetooth output**: `/etc/mpd.conf` has an added `audio_output` named
   `"Bluetooth"` using `device "bluealsa:DEV=00:00:00:00:00:00,PROFILE=a2dp"`
   (the all-zeros MAC = most-recently-connected device, so it follows whatever
   the Bluetooth screen connects). Backup at `/etc/mpd.conf.bak-bt`. Enable with
   `mpc enable`; the wired output goes nowhere on this board.
3. **NetworkManager-wait-online** is (or will be) masked to speed up boot — see
   pending work below.

## What this session changed (hardware bring-up log, Jul–Aug 2026)

All changes are **uncommitted working-tree edits** (verify with `git status`) —
they were deployed to the Pi file-by-file via scp but **not committed** to git.
Consider committing them. Files touched: `tools/i2c_scan.py`, `pi/input_pi.py`,
`pi/bluetooth_pi.py`, `pi/haptic_pi.py`, `shared/app.py`, `shared/config.py`,
`shared/menu_core.py`, `systemd/pimusicdevice.service`, `install.sh`,
`tests/test_menu_core.py`, `tests/test_track_ids.py`, and new `pi/unblock_bluetooth.sh`.

1. **Encoder boot probe** (`tools/i2c_scan.py`): switched from `read_byte()` to
   `write_quick()` — the seesaw NAKs a bare receive-byte, so the old probe
   wrongly reported "no encoder" and the app crash-looped at boot.
2. **Encoder resilience** (`pi/input_pi.py` + config): (a) per-frame
   `MAX_ENCODER_DELTA` clamp and (b) a rolling-window rate breaker
   (`ENCODER_FAULT_WINDOW_S`, `ENCODER_FAULT_MAX_DETENTS`) so a noisy connection
   can't flood the event queue and freeze the UI; (c) patient init retry with a
   `ENCODER_INIT_RETRY_WINDOW_S` (20 s) deadline so a cold-boot I²C glitch
   retries instead of crashing.
3. **systemd** (`systemd/pimusicdevice.service`, `install.sh`):
   `StartLimitIntervalSec=0` (never permanently give up restarting), and an
   `ExecStartPre=` that runs `pi/unblock_bluetooth.sh` (clears the Bluetooth
   rfkill soft-block that some boots come up with).
4. **Bluetooth honesty & UX** (`shared/app.py`, `pi/bluetooth_pi.py`, config):
   only shows "Connected" when BlueZ actually confirms (was a false 4 s
   timeout); shows a "Couldn't connect" toast on failure; the connected screen
   auto-returns to the menu (was a dead-end that dimmed to black and trapped the
   user). Scan list filters out Apple "Find My" beacons and strips the
   "- Find My" suffix. `BT_CONNECT_MAX_S = 15`, `BT_CONNECTED_SHOW_S = 2`.
5. **UI tweaks** (config, `menu_core.py`, `app.py`): home menu order is now
   **Now Playing, Music, Shuffle All, Settings**; Now Playing volume wheel is
   **reversed** (up = quieter) with a finer `VOLUME_STEP = 2`; screen dims at
   `DIM_AFTER_S = 25`, black at `SLEEP_AFTER_S = 60`; a dark screen wakes on a
   center **tap OR hold** (`select` or `back`). The Beret slide switch remains
   the only full power toggle.
6. **Haptics** (`pi/haptic_pi.py`, config): motor mode is config-driven
   (`use_ERM()`/`use_LRM()` from `HAPTIC_MOTOR`); set to ERM for the current
   motor. Was hard-coded LRA, which barely moves an ERM.

## Pending / next steps

- **Boot speed** (in progress, staged but NOT deployed): the repo's
  `systemd/pimusicdevice.service` and `install.sh` were edited to **drop
  `network-online.target` from `After=`** — the app manages WiFi itself (off by
  default) and the web app binds without a live network, so every cold boot was
  wasting ~10–20 s waiting for DHCP for a radio it then turns off. **This is not
  yet on the live Pi** (device was unplugged). To finish: rewrite the live unit
  without `network-online.target`, `sudo systemctl mask
  NetworkManager-wait-online.service`, `daemon-reload`, power-cycle, and measure
  with `systemd-analyze blame` / `critical-chain pimusicdevice.service`.
- **Cold-boot floor**: even fully optimized, the Pi Zero 2 W kernel+systemd
  startup is ~10–15 s — pulling power can't be made truly "instant." For instant
  on/off during use, the **Beret slide switch** in the default `soft_off` mode
  resumes instantly (it idles the Pi rather than powering off; costs standby
  battery). `POWER_SWITCH_ACTION = "soft_off"` in config.
- **AirPods** are unreliable on this Pi (they drop the A2DP link when idle and
  won't hold a connection) — a known Apple-on-Linux limitation, not fixable in
  software. The **JBL Charge 6** (a normal BT speaker that holds the link) is the
  recommended/reliable sink. AirPods are paired at MAC `30:7A:D2:07:05:AE`.

## Test gates (run before considering work done)

Run with `.venv/bin/python` (uv-created venv). All must stay green:
`.venv/bin/python -m pytest tests/ -q` (75 tests, ~4 min),
`python3 mac/prototype.py --selftest`,
`python -m compileall shared mac pi tools`, `python -c "import pi.device"`.
The full pytest run exceeds the default Bash timeout — run it backgrounded.
