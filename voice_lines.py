"""Single source of truth for every line the assistant speaks.

Deliberately dependency-free: the voice-pack generator imports this without
needing pyaudio, vosk or pyautogui installed. Keep it that way.
"""

import re

# parse_number() caps spoken number words at ten, so that is the voiced range.
MAX_AMOUNT = 10

# Every fixed action description confirm_action() can be handed.
FIXED_DESCRIPTIONS = [
    "Lock orientation planes",
    "Unlock orientation planes",
    "Clear screens",
    "Recenter displays",
    "Open Gemini",
    "Switch to Ultrawide layout",
    "Switch to Single display layout",
    "Switch to Dual display layout",
    "Switch to Triple display layout",
    "Switch to Stacked display layout",
]

# Lines spoken outside the "Confirm: ...?" pattern.
STANDALONE_LINES = [
    "Command cancelled.",
    "Timed out. Action cancelled.",
]

# Tone name -> list of (frequency Hz, duration ms). These are beeps, not speech.
TONES = {
    "startup": [(440, 150), (554, 150), (659, 150), (880, 300)],
    "pleasant": [(587, 80), (880, 120)],
    "cancel": [(880, 80), (587, 120)],
    "error": [(300, 150), (250, 200)],
}


def confirm_line(description):
    """The exact string speak() is handed for a given action description."""
    return f"Confirm: {description}?"


def all_speech_lines():
    """Every distinct string the assistant can speak. Closed set, 32 entries."""
    lines = [confirm_line(d) for d in FIXED_DESCRIPTIONS]
    for n in range(1, MAX_AMOUNT + 1):
        lines.append(confirm_line(f"Push displays away by {n}"))
        lines.append(confirm_line(f"Pull displays closer by {n}"))
    lines.extend(STANDALONE_LINES)
    return lines


def slug(text):
    """Deterministic filesystem-safe filename stem for a spoken line."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
