# Installing the Mac simulator

The Mac build is a pixel-identical simulator of the Pi device: same shared
main loop, same renderer, with keyboard/terminal stand-ins for the wheel,
haptics, battery, and Bluetooth. Use it to develop and to try the device
without hardware.

## Requirements

- macOS (tested on Apple Silicon), Python **3.10 or newer**
- No system Python 3.10+? Install one with [uv](https://docs.astral.sh/uv/):
  `curl -LsSf https://astral.sh/uv/install.sh | sh`, then
  `uv venv --python 3.12 .venv`

## Install + run (one command)

```sh
cd pimusicdevice
bash mac/run.sh
```

That creates `.venv/`, installs `requirements-mac.txt`, and launches —
and is safe to re-run. The manual equivalent:

```sh
python3 -m venv .venv                 # or: uv venv --python 3.12 .venv
source .venv/bin/activate
pip install -r requirements-mac.txt   # pygame (+ pytest for the test suite)
python3 mac/prototype.py
```

First run generates ~54 short synthetic chip-tunes into `mac/_audio/`
(under a second; cached afterwards). A 480×480 window titled
"prototype  —  device simulator" opens, plays the boot animation, and lands
on the home menu. Haptic events print to the terminal.

See [usage.md](usage.md) for the controls and every screen.

## Verify the install

```sh
python3 mac/prototype.py --selftest    # scripted end-to-end run, exit 0 = pass
pytest -q                              # unit + render tests
python -m compileall shared mac pi     # syntax gate
python -c "import pi.device"           # Pi code imports without hardware libs
```

All four must pass on a healthy checkout.

## Uninstall / reset

- Delete `.venv/` to remove the environment.
- Delete `mac/_audio/` to force audio regeneration.
- Delete `.device_state.json` (repo root) to forget playback state,
  volume, and brightness.
