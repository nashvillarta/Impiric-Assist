# Voice-commanded Discord disconnect

**Date:** 2026-08-03
**Status:** Approved, ready for implementation

Say "kick Alice" and the assistant disconnects that person from the Discord
voice channel, after a spoken confirmation naming them.

## Why UI automation and not a bot

A Discord bot would be more reliable, but the target server belongs to someone
else and a bot cannot be invited. The user does hold **Move Members** there, so
this automates an action they are already authorised to perform manually --
the same category as the SpaceWalker hotkeys `assistant.py` already sends.

The rejected alternative was extracting the user's own token from the desktop
client and calling the API as them. That is a ToS violation that gets accounts
terminated, and it is what token-stealer malware does. Not an option.

## Feasibility, established by probe

Discord is Electron, so Chromium exposes a UI Automation accessibility tree.
Probing it on 2026-08-03 established:

- Member rows are named elements. Voice state is embedded in the name:
  `'AliceIn voiceIn voice (team-room-(work))'`
- Every element carries a bounding rectangle, so we act on elements rather
  than guessing coordinates.
- The right-click menu contains an item named exactly `Disconnect`, sitting
  between `Server Deafen` above and `Copy User ID` below.
- **The tree is built lazily.** A cold first walk returns zero nodes; the
  query itself triggers construction. Code must warm up, then walk for real.

## Architecture

`discord_control.py` is the only module that knows UIA exists. `assistant.py`
never imports `uiautomation`.

```
assistant.py     ->  discord_control.py  ->  uiautomation  ->  Discord
(voice, confirm)     (find / act on members)
```

Public surface:

| Function | Returns | Purpose |
|---|---|---|
| `list_voice_members()` | `list[VoiceMember]` | Who is in voice now, with channel |
| `resolve_name(spoken, members)` | `VoiceMember \| None` | Match a garbled transcription |
| `disconnect(member)` | `bool` | Right-click, then click "Disconnect" |

`VoiceMember` holds `username`, `channel`, and the opaque UIA element. Callers
never touch the element.

Two internal pure functions carry most of the logic and all of the risk, so
they are unit-tested exhaustively without Discord running:

- `parse_member(raw_name)` -> `(username, channel) | None`
- `resolve_name(spoken, members)` -> match or `None`

No background thread, no persistent connection, and no caching of members: the
tree walk is cheap and always current, and a stale member list is exactly how
you disconnect whoever replaced the person who left.

## Command flow

```
"kick alice"
  -> fast-path keyword match in process_and_execute
  -> target = text after the verb
list_voice_members()            <- fresh walk, never cached
resolve_name("alice", members)
  |- no match   -> "Nobody by that name is in voice."
  |- ambiguous  -> "Sorry, I did not understand that."
  \- one match  -> confirm_action("Disconnect Alice from voice")
                     -> yes -> RE-RESOLVE -> disconnect() -> "Okay."
```

**Ambiguity refuses rather than guesses.** `difflib.SequenceMatcher` (stdlib),
both sides normalised to lowercase alphanumerics. The top score must clear
~0.7 *and* beat the runner-up by a clear margin. Failing either, we refuse.
Disconnecting the wrong person is the failure mode that matters.

**Re-resolve after confirmation.** The 10-second confirm window is a race:
people leave calls and the list reorders. After a yes, walk again, re-find by
username, and abort if they are gone.

**Aliases**, because Vosk will not transcribe these names. A small Vosk model
has no entry for `Bob` or `Carol`; it emits "the guy seventeen eighty"
and "chicken". An alias map in config is checked before fuzzy matching.
Without it the feature is frustrating for anyone whose handle is not a common
English word.

## Safety invariants

1. **Match the menu item by exact name, never by position.** The neighbours are
   `Server Deafen` and `Copy User ID`; an off-by-one positional guess server-
   deafens someone.
2. **Escape in a `finally`.** Observed live: the probe crashed after right-
   clicking and left a menu open on the user's Discord.
3. **Refuse on ambiguity.**
4. **Re-resolve after the confirm window.**
5. **Discord must be foreground before any click.** UIA's right-click drives
   the real cursor; if another window is on top the click lands there instead.
   Focus, verify it came forward, abort if it did not. Restore cursor after.

Every failure path ends in doing nothing:

| Condition | Response |
|---|---|
| Discord not running | "Discord is not open." |
| Tree empty after warm-up retry | "Discord is not open." |
| Nobody in voice / no match | "Nobody by that name is in voice." |
| Ambiguous match | "Sorry, I did not understand that." |
| Target left during confirm | abort silently, no click |
| Menu absent or no `Disconnect` item | Escape, abort |
| Cannot focus Discord | abort, no click |

**Dry-run flag.** `DISCORD_DRY_RUN` runs the whole flow -- resolve, confirm,
focus, right-click, locate the item -- then Escapes instead of clicking, and
reports what it would have done. Testing this honestly otherwise means
disconnecting real people mid-call.

## Voice pack impact

The pack reverted to the native Windows engine on 2026-08-03, which removes the
reason to pre-render names: the pack voice and the `_speak_native` fallback
voice are now the same voice, so an unknown name sounds identical either way.

The pack therefore gains exactly **two** fixed lines:

- `"Nobody by that name is in voice."`
- `"Discord is not open."`

The per-person confirmation (`"Confirm: Disconnect Alice from voice?"`) has no
pre-rendered WAV and falls through to native TTS, costing about a second of
latency. No handles are stored anywhere, in git or on disk, and the friend
group can change without regenerating anything.

## Testing

Pure functions, no Discord required. `parse_member` fixtures are real strings
captured from the probe, including the nested-parenthesis channel name that
broke the first regex:

```
'AliceIn voiceIn voice (team-room-(work))' -> ('Alice', 'team-room-(work)')
'Dave'                                        -> None (not in voice)
'Erin SmithServer Tag: XYZ'               -> None (not in voice)
```

`resolve_name`: exact, case-insensitive, alias hit, below threshold, **two
close candidates -> None**, empty list.

Faked UIA layer: `disconnect()` asserts right-click -> find item named exactly
`Disconnect` -> click -> Escape. The critical negative case is that when no
such item exists it clicks nothing and still Escapes.

Integration with `discord_control` stubbed: the assistant passes the right
description to `confirm_action`, and answering *no* produces zero clicks.

Drift: the two new standalone lines need WAVs like every other line.
