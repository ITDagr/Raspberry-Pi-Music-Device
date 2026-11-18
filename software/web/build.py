"""Build the browser demo: copy what it needs into web/build/device/ and run
pygbag on it. The finished site lands in web/build/device/build/web/.

    pip install pygbag
    python3 web/build.py            # build only
    python3 web/build.py --serve    # build, then serve on http://localhost:8000
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent
SOFTWARE = WEB.parent
STAGE = WEB / "build" / "device"

# only what the demo imports: no Flask web app, no Pi drivers, no tests
SHARED = ["__init__.py", "app.py", "config.py", "encoder.py", "hardware.py",
          "menu_core.py", "netinfo.py", "pisugar.py", "playlists.py",
          "screen.py", "screen_dimmer.py", "startup.py", "state.py"]
MAC = ["__init__.py", "bluetooth_mac.py", "display_mock.py", "haptic_mock.py",
       "input_mock.py", "library_mac.py", "player_mac.py", "power_mock.py",
       "radio_mock.py"]


def stage() -> None:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    for pkg, names in (("shared", SHARED), ("mac", MAC)):
        (STAGE / pkg).mkdir(parents=True)
        for name in names:
            shutil.copy2(SOFTWARE / pkg / name, STAGE / pkg / name)
    shutil.copy2(WEB / "main.py", STAGE / "main.py")


def main() -> int:
    stage()
    args = [sys.executable, "-m", "pygbag", "--title", "Raspberry Pi Music Device",
            "--ume_block", "1"]
    if "--serve" not in sys.argv:
        args.append("--build")
    args.append(str(STAGE))
    return subprocess.call(args)


if __name__ == "__main__":
    sys.exit(main())
