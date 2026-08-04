"""Disconnects someone from a Discord voice channel by driving the desktop UI.

The only module that knows uiautomation exists; assistant.py talks to it
through list_voice_members / resolve_name / disconnect and never imports UIA.

Why UI automation rather than a bot: the server belongs to someone else and a
bot cannot be invited, but the user holds Move Members there, so this automates
an action they can already perform by hand.

Discord is Electron, so Chromium exposes a UI Automation accessibility tree.
Member rows are named elements that carry voice state in the name itself:

    'AliceIn voiceIn voice (team-room-(work))'

so we match people as text rather than hunting pixels, and act on elements
rather than coordinates.

Safety rules, all load-bearing:
  - the context-menu item is found by exact name, never by position -- its
    neighbours are 'Server Deafen' and 'Copy User ID'
  - an ambiguous name match refuses instead of guessing
  - Escape always runs, so a crash cannot leave a menu open over Discord
  - Discord must be foreground before any click, or the cursor lands elsewhere
"""

import difflib
import re
import time
from dataclasses import dataclass

VOICE_MARKER = "In voice"
MENU_ITEM = "Disconnect"

# A transcription must look at least this much like a name, and beat the
# runner-up by this margin, or we refuse rather than pick a winner.
MATCH_THRESHOLD = 0.7
MATCH_MARGIN = 0.15


@dataclass
class VoiceMember:
    """Someone currently in a voice channel. `element` is opaque to callers."""

    username: str
    channel: str
    element: object


def parse_member(raw_name):
    """Splits an accessibility name into (username, channel), or None.

    Returns None for anyone not in voice -- the member list contains everyone
    in the server, and only voice-connected rows carry the marker.
    """
    if not raw_name:
        return None
    name = raw_name.strip()
    if not name or VOICE_MARKER not in name:
        return None

    username = name.split(VOICE_MARKER)[0].strip()
    if not username:
        return None

    # Greedy to the last ')': channel names contain parentheses themselves,
    # e.g. 'team-room-(work)'. A lazy match truncates them.
    match = re.search(r"In voice \((.*)\)", name)
    channel = match.group(1) if match else ""
    return username, channel


def _normalise(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def resolve_name(spoken, members, aliases=None):
    """Finds the one member a spoken name refers to, or None.

    Returns None when nothing is close enough AND when two candidates are both
    close -- disconnecting the wrong person is worse than not working, so
    ambiguity refuses rather than guessing.
    """
    if not spoken or not members:
        return None

    # Aliases first: Vosk has no vocabulary entry for handles like 'Carol',
    # so fuzzy matching alone never bridges 'chicken' -> 'Carol'.
    if aliases:
        target = aliases.get(spoken.strip().lower())
        if target:
            for member in members:
                if _normalise(member.username) == _normalise(target):
                    return member

    needle = _normalise(spoken)
    if not needle:
        return None

    scored = sorted(
        (
            (difflib.SequenceMatcher(None, needle, _normalise(m.username)).ratio(), m)
            for m in members
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )

    best_score, best = scored[0]
    if best_score < MATCH_THRESHOLD:
        return None
    if len(scored) > 1 and best_score - scored[1][0] < MATCH_MARGIN:
        return None
    return best


def members_in_my_channel(members, my_username):
    """Narrows to the channel `my_username` is sitting in.

    The member list spans every voice channel in the server, so without this
    "kick Dave" could disconnect someone from a call you are not part of.
    With no username configured, or if you are not in voice, this returns
    nothing rather than falling back to server-wide -- silently widening the
    blast radius is the wrong default.
    """
    if not my_username:
        return []
    mine = next(
        (m for m in members if _normalise(m.username) == _normalise(my_username)),
        None,
    )
    if mine is None:
        return []
    return [m for m in members if m.channel == mine.channel and m is not mine]


def _auto():
    """Imported lazily so tests and --engine native never need uiautomation."""
    import uiautomation

    return uiautomation


def find_window(timeout=5):
    """The Discord main window, or None."""
    auto = _auto()
    win = auto.WindowControl(searchDepth=1, RegexName=r".*Discord.*")
    return win if win.Exists(maxSearchSeconds=timeout) else None


def _warm_up(win):
    """Chromium builds the accessibility tree lazily.

    A cold first walk returns zero nodes -- the query itself is what triggers
    construction. Discard one shallow walk, then the real one has a tree.
    """
    auto = _auto()
    for _ in auto.WalkControl(win, includeTop=False, maxDepth=6):
        pass


def list_voice_members(win=None):
    """Everyone currently in a voice channel. Never cached: a stale list is how
    you disconnect whoever replaced the person who left."""
    auto = _auto()
    win = win or find_window()
    if win is None:
        return []
    _warm_up(win)

    members = []
    for control, _ in auto.WalkControl(win, includeTop=False, maxDepth=25):
        if control.ControlTypeName != "ListItemControl":
            continue
        parsed = parse_member(control.Name)
        if parsed:
            username, channel = parsed
            members.append(VoiceMember(username, channel, control))
    return members


def focus_window(win):
    """Brings Discord forward. UIA's right-click drives the real cursor, so a
    click with another window on top lands on that window instead."""
    try:
        win.SetActive()
        time.sleep(0.4)
        return True
    except Exception:
        return False


class Uia:
    """The real menu-walking adapter. Tests pass a fake with this shape."""

    # Discord nests its context menu deeply: 'Disconnect' was measured at depth
    # 17 from the desktop root. A shallower walk finds nothing and the feature
    # silently does nothing, so this has real headroom over the observed depth.
    MENU_DEPTH = 22

    def menu_walker(self):
        auto = _auto()
        root = auto.GetRootControl()
        items = []
        for control, _ in auto.WalkControl(root, includeTop=False, maxDepth=self.MENU_DEPTH):
            if control.ControlTypeName in ("MenuItemControl", "ListItemControl"):
                items.append(control)
        return items

    def SendKeys(self, keys):
        _auto().SendKeys(keys)


def disconnect(member, uia, dry_run=False):
    """Right-clicks a member and clicks the menu item named 'Disconnect'.

    Returns True if the item was found (and clicked, unless dry_run). The
    Escape runs whatever happens: a context menu left open over Discord is one
    stray click away from server-deafening someone.
    """
    try:
        member.element.RightClick(simulateMove=False)
        time.sleep(1.0)

        for item in uia.menu_walker():
            if (item.Name or "").strip().lower() != MENU_ITEM.lower():
                continue
            if not dry_run:
                item.Click(simulateMove=False)
            return True
        return False
    finally:
        uia.SendKeys("{Esc}")
