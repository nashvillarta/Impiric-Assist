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
#
# The Discord disconnect confirmation ("Confirm: Disconnect Alice from voice?")
# is deliberately absent: it contains a username, which cannot be known ahead
# of time, so it falls through to native TTS. That costs nothing now the pack
# itself is native -- the fallback is the same voice -- and it keeps other
# people's handles out of this repo entirely.
STANDALONE_LINES = [
    "Command cancelled.",
    "Timed out. Action cancelled.",
    "Nobody by that name is in voice.",
    "Discord is not open.",
]

# Spoken feedback lines that replace the old beeps/chimes.
FEEDBACK_LINES = [
    "Assistant ready.",
    "Listening.",
    "Okay.",
    "Sorry, I did not understand that.",
]


def confirm_line(description):
    """The exact string speak() is handed for a given action description."""
    return f"Confirm: {description}?"


def all_speech_lines():
    """Every distinct string the assistant can speak. Closed set, 36 entries."""
    lines = [confirm_line(d) for d in FIXED_DESCRIPTIONS]
    for n in range(1, MAX_AMOUNT + 1):
        lines.append(confirm_line(f"Push displays away by {n}"))
        lines.append(confirm_line(f"Pull displays closer by {n}"))
    lines.extend(STANDALONE_LINES)
    lines.extend(FEEDBACK_LINES)
    return lines


def slug(text):
    """Deterministic filesystem-safe filename stem for a spoken line."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
