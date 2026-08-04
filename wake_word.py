"""Wake-word detection, kept separate so it can be tested without a microphone.

"computer" is an ordinary English word, so Vosk transcribes it reliably --
unlike the Discord handles, which it mangles badly. The cost is that the
microphone also picks up the Discord call, so anyone saying "computer" in
conversation can arm the assistant. Confirmation is the guard against that,
which is why every action still asks before it acts.

Matched as a whole word so "computers" does not trigger it.
"""

import re

VARIANTS = ["computer"]

_PATTERN = re.compile(r"\b(" + "|".join(VARIANTS) + r")\b")


def split(phrase):
    """Returns the command following the wake word, or None if absent.

    An empty string is meaningful and distinct from None: it means the wake
    word was heard on its own, so the assistant should arm and listen.
    """
    if not phrase:
        return None
    match = _PATTERN.search(phrase)
    if match is None:
        return None
    return phrase[match.end():].strip()
