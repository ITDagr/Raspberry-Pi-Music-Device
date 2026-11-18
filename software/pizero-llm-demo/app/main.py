"""pizero-llm-demo — event loop and state machine.

Single-threaded UI at ~20 fps. Generation runs on a worker thread that only
ever pushes into a queue, so a 4 tok/s stream never blocks the encoder read or
the panel write — the screen stays responsive while the model grinds.

States: BOOT -> WHEEL <-> GEN -> DONE, with ERROR reachable from GEN.
Controls: rotate / up / down = move, left / right = switch prompt set,
          press = run (or stop, or regenerate), hold = back.
"""
from __future__ import annotations

import queue
import signal
import sys
import threading
import time

from app import config, prompts
from app.llama import LlamaClient, LlamaError
from app.ui import Renderer, ViewState

_running = True


def _on_signal(signum, _frame):
    # Handling SIGTERM is what makes `systemctl restart` return promptly
    # instead of sitting in stop-sigterm until the timeout expires.
    global _running
    _running = False
    print(f"main: signal {signum} — shutting down")


def read_memory() -> tuple[int, int]:
    """(used_mb, total_mb). Used = Total - Available, which is the number that
    actually predicts whether the mmap'd weights stay resident."""
    try:
        total = avail = 0
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    avail = int(line.split()[1])
                if total and avail:
                    break
        return (total - avail) // 1024, total // 1024
    except Exception:
        return 0, 0


class App:
    def __init__(self, display, inp, haptic) -> None:
        self.display = display
        self.inp = inp
        self.haptic = haptic
        self.r = Renderer()
        self.client = LlamaClient()
        self.st = ViewState()

        self.set_idx = 0
        self.sel = 0
        self.prompt_text = ""
        self.follow = True

        self.q: queue.Queue = queue.Queue()
        self.stop_flag = threading.Event()
        self.worker: threading.Thread | None = None
        self.gen_started = 0.0
        self.gen_tokens = 0
        self._last_stats = 0.0

    # --- helpers ------------------------------------------------------------
    @property
    def set_name(self) -> str:
        return prompts.SET_NAMES[self.set_idx]

    @property
    def current_set(self) -> list[str]:
        return prompts.PROMPT_SETS[self.set_name]

    def refresh_wheel(self) -> None:
        self.st.set_name = self.set_name
        self.st.rows = [prompts.short_label(p) for p in self.current_set]
        self.st.sel = self.sel

    def max_scroll(self) -> int:
        lines = self.r.wrap(self.st.text or "", self.r.f_body, config.SIZE - 18)
        return max(0, len(lines) - self.r.body_lines)

    # --- generation ---------------------------------------------------------
    def start_generation(self, prompt: str) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.prompt_text = prompt
        self.stop_flag.clear()
        self.st.text = ""
        self.st.tok_s = None
        self.st.mode = "GEN"
        self.st.scroll = 0
        self.follow = True
        self.gen_started = time.monotonic()
        self.gen_tokens = 0

        def run() -> None:
            try:
                final = self.client.stream(
                    prompt,
                    on_token=lambda t: self.q.put(("tok", t)),
                    should_stop=self.stop_flag.is_set,
                )
                self.q.put(("done", final))
            except LlamaError as exc:
                self.q.put(("err", str(exc)))
            except Exception as exc:  # never let the thread die silently
                self.q.put(("err", f"unexpected: {exc}"))

        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def drain(self) -> None:
        while True:
            try:
                kind, payload = self.q.get_nowait()
            except queue.Empty:
                return
            if kind == "tok":
                self.st.text += payload
                self.gen_tokens += 1
                if self.follow:
                    self.st.scroll = 10 ** 6        # renderer clamps to bottom
                elapsed = time.monotonic() - self.gen_started
                if elapsed > 0.5:
                    self.st.tok_s = self.gen_tokens / elapsed
            elif kind == "done":
                measured = LlamaClient.tokens_per_second(payload)
                if measured:
                    self.st.tok_s = measured
                self.st.mode = "DONE"
                self.st.scroll = min(self.st.scroll, self.max_scroll())
                self.haptic.pulse()
            elif kind == "err":
                self.st.mode = "ERROR"
                self.st.note = payload
                self.haptic.back()

    # --- input --------------------------------------------------------------
    def handle(self, ev: str, ticked: list[bool]) -> None:
        st = self.st

        if ev in ("scroll_up", "up"):
            if st.mode == "WHEEL":
                self.sel = (self.sel - 1) % len(self.current_set)
                self.refresh_wheel()
            else:
                self.follow = False
                st.scroll = max(0, min(st.scroll, self.max_scroll()) - 1)
            if not ticked[0]:
                self.haptic.tick(); ticked[0] = True

        elif ev in ("scroll_down", "down"):
            if st.mode == "WHEEL":
                self.sel = (self.sel + 1) % len(self.current_set)
                self.refresh_wheel()
            else:
                top = self.max_scroll()
                st.scroll = min(top, min(st.scroll, top) + 1)
                self.follow = st.scroll >= top
            if not ticked[0]:
                self.haptic.tick(); ticked[0] = True

        elif ev in ("left", "right"):
            if st.mode == "WHEEL":
                step = -1 if ev == "left" else 1
                self.set_idx = (self.set_idx + step) % len(prompts.SET_NAMES)
                self.sel = 0
                self.refresh_wheel()
                self.haptic.click()

        elif ev == "select":
            if st.mode == "WHEEL":
                self.haptic.click()
                self.start_generation(self.current_set[self.sel])
            elif st.mode == "GEN":
                self.stop_flag.set()        # stop early
                self.haptic.back()
            elif st.mode == "DONE":
                self.haptic.click()
                self.start_generation(self.prompt_text)
            elif st.mode == "ERROR":
                st.mode = "WHEEL"
                self.refresh_wheel()

        elif ev == "back":
            if st.mode == "GEN":
                self.stop_flag.set()
            st.mode = "WHEEL"
            st.note = ""
            self.refresh_wheel()
            self.haptic.back()

    # --- loop ---------------------------------------------------------------
    def run(self) -> None:
        global _running

        # Wait for the backend. The first load pages ~220 MB off the SD card,
        # so this is slow but finite; llamad restarts itself on failure, so
        # polling forever is the right behaviour for an appliance.
        waited = 0.0
        while _running and not self.client.healthy():
            msg = ("loading model…" if waited < 45
                   else f"still loading ({waited:.0f}s)" if waited < 120
                   else "backend not responding")
            self.display.push(self.r.splash(msg))
            time.sleep(2.0)
            waited += 2.0
        if not _running:
            return

        self.st.mode = "WHEEL"
        self.refresh_wheel()
        self.st.ram_used, self.st.ram_total = read_memory()
        self.display.push(self.r.splash("ready"))
        self.r.render(self.st)
        self.display.push(self.r.img)

        frame = 1.0 / config.FPS
        while _running:
            t0 = time.monotonic()

            ticked = [False]
            for ev in self.inp.read():
                self.handle(ev, ticked)

            self.drain()

            if t0 - self._last_stats >= config.STATS_REFRESH_S:
                self.st.ram_used, self.st.ram_total = read_memory()
                self._last_stats = t0

            dirty = self.r.render(self.st)
            if dirty:
                # Measured on the real panel: a full frame costs ~40 ms (the
                # numpy RGB565 conversion dominates, not the SPI wire time),
                # while the stats strip alone is ~5 ms. At 15 fps a full frame
                # every tick would burn most of a core that inference needs, so
                # push only what changed.
                if config.UI_LEAN:
                    for rect in dirty:
                        self.display.push(self.r.img, rect)
                else:
                    self.display.push(self.r.img)

            time.sleep(max(0.0, frame - (time.monotonic() - t0)))


def main() -> int:
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    from app.display import Display
    from app.haptic import make_haptic
    from app.input import ANOInput

    try:
        display = Display()
    except Exception as exc:
        print(f"fatal: display init failed ({exc})", file=sys.stderr)
        return 1

    try:
        inp = ANOInput()
    except Exception as exc:
        # The encoder retries internally for 20s; past that the connection is
        # genuinely bad. Say so on the screen rather than crash-looping.
        print(f"fatal: encoder init failed ({exc})", file=sys.stderr)
        r = Renderer()
        display.push(r.splash("no encoder — check STEMMA QT"))
        time.sleep(10)
        display.close()
        return 1

    haptic = make_haptic()
    app = App(display, inp, haptic)
    try:
        app.run()
    finally:
        display.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
