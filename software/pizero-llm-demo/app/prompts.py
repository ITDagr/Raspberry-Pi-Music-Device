"""pizero-llm-demo — the prompt wheel contents.

Three sets, switched with the encoder's left/right. Rotating the wheel picks a
prompt within the current set; the centre button runs it.

This is the one file to edit to change what the device *does* — nothing here is
referenced by name anywhere else, so adding a set is a two-line change. A quiz
set is included: a tiny model is poor at open-ended reasoning but fine at
recalling and phrasing a single fact, which is most of what a quiz needs.

Keep prompts short. Every prompt token is prefill, and prefill is the slowest
part of a turn on an A53 — a 60-token prompt costs a couple of seconds before
the first word appears.
"""
from __future__ import annotations

PROMPT_SETS: dict[str, list[str]] = {
    "DEMO": [
        "Explain what a transistor does, simply.",
        "Why is the sky blue?",
        "What is a prime number?",
        "Describe the Moon in two sentences.",
        "What does a compiler do?",
        "Why do we dream?",
        "Explain gravity to a ten year old.",
        "What is the internet, briefly?",
    ],
    "QUIZ": [
        "Ask me one multiple-choice question about space. Give four options, A to D, and do not reveal the answer.",
        "Ask me one multiple-choice question about history. Four options, A to D, no answer.",
        "Ask me a true-or-false question about animals. Do not give the answer.",
        "Give me one riddle. Do not give the answer.",
        "Ask me a multiple-choice question about computers. Four options, no answer.",
        "Name a country and ask me for its capital city.",
    ],
    "ORACLE": [
        "Give me one short piece of unexpected advice.",
        "Invent a proverb that sounds ancient.",
        "Describe my day in one cryptic sentence.",
        "Give me a single creative constraint for a project.",
        "Write a two-line poem about waiting.",
        "Tell me something strange but true.",
    ],
}

SET_NAMES: list[str] = list(PROMPT_SETS)


def short_label(prompt: str, limit: int = 34) -> str:
    """Wheel rows show a trimmed prompt; the full text is what gets sent."""
    one_line = " ".join(prompt.split())
    return one_line if len(one_line) <= limit else one_line[: limit - 1] + "…"
