"""Loads voice-command aliases from a local, gitignored file.

Aliases map a nickname to a real Discord handle, so the file is deliberately
kept out of version control -- other people's handles are not this repo's to
publish. See discord_aliases.example.json for the format.

Because the file is gitignored, a fresh clone will not have one. That is the
normal case, not an error: every failure here returns {} so the assistant
starts regardless, and the disconnect command simply falls back to matching
real usernames.
"""

import json
import os

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "discord_aliases.json"
)


def load(path=None):
    """Returns {spoken_nickname: real_username}, or {} if unusable.

    Keys are lowercased because the lookup lowercases what it heard; a
    capitalised key in the file would otherwise silently never match.
    """
    path = path or DEFAULT_PATH
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Alias Warning] Ignoring {os.path.basename(path)}: {e}")
        return {}

    if not isinstance(raw, dict):
        print(f"[Alias Warning] {os.path.basename(path)} is not a JSON object; ignoring.")
        return {}

    out = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if not key.strip() or not value.strip():
            continue
        # Underscore keys are settings, not aliases -- see load_me().
        if key.startswith("_"):
            continue
        out[key.strip().lower()] = value.strip()
    return out


def load_me(path=None):
    """Your own Discord handle, from the reserved "_me" key.

    Lives in the same gitignored file for the same reason the aliases do: it
    is a real handle, and this repo is not the place for it. Returns "" when
    unset, which makes the disconnect command inert rather than guessing which
    voice channel is yours.
    """
    path = path or DEFAULT_PATH
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return ""
    if not isinstance(raw, dict):
        return ""
    me = raw.get("_me", "")
    return me.strip() if isinstance(me, str) else ""
