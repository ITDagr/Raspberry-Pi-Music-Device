"""Open the built browser demo in headless Chromium and check that it boots.

    pip install playwright && python -m playwright install --with-deps chromium
    python3 web/smoke_test.py web/build/device/build/web      # a local build
    python3 web/smoke_test.py https://example.github.io/repo/  # a live site

A local build is served under /Raspberry-Pi-Music-Device/, the same sub-path
GitHub Pages uses. The page is clicked (browsers need a click before sound),
then the test waits for main.py to print "demo: running" and presses a few
keys. It prints the browser console and a screenshot (as base64 PNG) and exits
non-zero if the demo never got running or raised a Python error.
"""
from __future__ import annotations

import base64
import functools
import http.server
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

SUBPATH = "/Raspberry-Pi-Music-Device/"
READY = "demo: running"
BOOT_TIMEOUT_S = 120


def _serve(folder: Path) -> str:
    """Serve folder at http://127.0.0.1:<port>/Raspberry-Pi-Music-Device/."""

    class Handler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path: str) -> str:
            if path.startswith(SUBPATH):
                path = "/" + path[len(SUBPATH):]
            elif path.split("?")[0] not in ("", "/"):
                path = "/__outside_subpath__" + path  # 404, as on Pages
            return super().translate_path(path)

        def log_message(self, fmt, *args):
            if args and str(args[1]) != "200":
                sys.stderr.write("http: " + (fmt % args) + "\n")

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Handler, directory=str(folder)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}{SUBPATH}"


def main() -> int:
    target = sys.argv[1]
    url = target if target.startswith("http") else _serve(Path(target).resolve())
    print(f"smoke test: {url}")
    console: list[str] = []
    failed: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page(viewport={"width": 900, "height": 900})
        page.on("console", lambda m: console.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: console.append(f"[pageerror] {e}"))
        page.on("requestfailed", lambda r: failed.append(f"{r.url} ({r.failure})"))
        page.on("response", lambda r: r.status >= 400 and failed.append(f"{r.url} -> {r.status}"))
        page.goto(url, wait_until="load")

        running = False
        deadline = time.monotonic() + BOOT_TIMEOUT_S
        while time.monotonic() < deadline:
            page.mouse.click(450, 450)  # user engagement / "click to start"
            if any(READY in line for line in console):
                running = True
                break
            page.wait_for_timeout(2000)
        if running:
            for key in ["ArrowDown", "Enter", "ArrowDown", "ArrowDown", "ArrowDown",
                        "Enter", "Enter"]:
                page.keyboard.press(key)
                page.wait_for_timeout(400)
            page.wait_for_timeout(2000)
        shot = page.screenshot()
        browser.close()

    print("---- console ----")
    for line in console:
        print(line[:400])
    print("---- failed requests ----")
    for line in failed:
        print(line)
    print("---- screenshot (base64 png) ----")
    print(base64.b64encode(shot).decode())
    errors = [l for l in console if "Traceback" in l or "[pageerror]" in l]
    print(f"running={running} python_errors={len(errors)}")
    return 0 if running and not errors else 1


if __name__ == "__main__":
    sys.exit(main())
