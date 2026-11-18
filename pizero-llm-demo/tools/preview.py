"""Render the UI off-device, at 4x, into one contact sheet.

Runs on a Mac with only Pillow + numpy installed — no SPI, no I2C, no model.
Use it to iterate on layout without deploying, and to sanity-check the wrap,
scroll and dirty-rect logic.

    uv run --python 3.12 --with pillow --with numpy python tools/preview.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from app import config  # noqa: E402
from app.ui import Renderer, ViewState  # noqa: E402

# install.sh writes runtime.json on the Pi; off-device, stand in for it so the
# strip shows what it will really show.
if config.MODEL_LABEL == "unknown":
    config.MODEL_LABEL, config.MODEL_QUANT = "SmolLM2-360M", "Q4_0"

ANSWER = (
    "A transistor is a tiny electronic switch. A small current at one "
    "terminal controls a much larger current between the other two, which "
    "means it can both amplify a signal and act as a logic gate. Billions "
    "of them etched into silicon are what make a processor work."
)
# Long enough to overflow the 12-line body and exercise the scrollbar.
LONG = ANSWER + (
    " Before transistors, computers used vacuum tubes, which were large, "
    "hot and unreliable. The switch to silicon made everything smaller, "
    "cooler and far cheaper to manufacture at scale."
)

SCENES: list[tuple[str, ViewState]] = [
    ("wheel", ViewState(
        mode="WHEEL", set_name="DEMO", sel=2,
        rows=["Explain what a transistor does, s…",
              "Why is the sky blue?",
              "What is a prime number?",
              "Describe the Moon in two sentenc…",
              "What does a compiler do?",
              "Why do we dream?"],
        tok_s=None, ram_used=331, ram_total=472)),
    ("wheel-quiz", ViewState(
        mode="WHEEL", set_name="QUIZ", sel=0,
        rows=["Ask me one multiple-choice questi…",
              "Ask me one multiple-choice questi…",
              "Ask me a true-or-false question a…",
              "Give me one riddle. Do not give t…"],
        tok_s=4.2, ram_used=338, ram_total=472)),
    ("generating", ViewState(
        mode="GEN", text=ANSWER[:96], scroll=0,
        tok_s=4.2, ram_used=402, ram_total=472)),
    ("done-scrolled", ViewState(
        mode="DONE", text=LONG, scroll=4,
        tok_s=4.4, ram_used=399, ram_total=472)),
    ("ram-pressure", ViewState(
        mode="GEN", text=ANSWER[:150], scroll=0,
        tok_s=1.1, ram_used=455, ram_total=472)),
    ("error", ViewState(
        mode="ERROR", note="inference backend unreachable: "
                           "[Errno 111] Connection refused",
        ram_used=120, ram_total=472)),
]

SCALE = 4
PAD = 10


def main() -> int:
    print(f"font: {config.FONT_PATH}")
    print(f"model label: {config.MODEL_LABEL} {config.MODEL_QUANT}")

    shots: list[tuple[str, Image.Image]] = []
    for name, st in SCENES:
        r = Renderer()                      # fresh: force a full first paint
        dirty = r.render(st)
        assert dirty, f"{name}: renderer reported nothing to draw"
        shots.append((name, r.img.copy()))
        print(f"  {name:<14} dirty={len(dirty)} rect(s)")

    # dirty-rect check: re-rendering an unchanged state must draw nothing
    r = Renderer()
    st = SCENES[0][1]
    r.render(st)
    assert r.render(st) == [], "unchanged state still reported dirty rects"
    print("  dirty-rect suppression ok")

    # wrap check: no rendered line may exceed the text column
    r = Renderer()
    lines = r.wrap(ANSWER, r.f_body, config.SIZE - 18)
    widest = max(r._width(ln, r.f_body) for ln in lines)
    assert widest <= config.SIZE - 18, f"wrap overflow: {widest}px"
    print(f"  wrap ok: {len(lines)} lines, widest {widest:.0f}px "
          f"(limit {config.SIZE - 18})")

    cols = 3
    rows = (len(shots) + cols - 1) // cols
    cell = config.SIZE * SCALE
    sheet = Image.new("RGB",
                      (cols * cell + (cols + 1) * PAD,
                       rows * cell + (rows + 1) * PAD),
                      (24, 24, 28))
    for i, (_, img) in enumerate(shots):
        x = PAD + (i % cols) * (cell + PAD)
        y = PAD + (i // cols) * (cell + PAD)
        sheet.paste(img.resize((cell, cell), Image.NEAREST), (x, y))

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "preview.png")
    out = os.path.normpath(out)
    sheet.save(out)
    print(f"\nwrote {out}  ({sheet.width}x{sheet.height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
