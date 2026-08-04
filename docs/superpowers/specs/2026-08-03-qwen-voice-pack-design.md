# Qwen3-TTS Voice Pack — Design

**Date:** 2026-08-03
**Branch:** `mac-testing` (local-only; never pushed — see `.git/hooks/pre-push`)
**Status:** Approved design, not yet implemented

## Goal

Replace the assistant's two platform-specific speech backends with one consistent voice
that sounds identical on Windows and macOS, using a Qwen3-TTS preset speaker.

Today `speak()` uses PowerShell `System.Speech` on Windows and `say` on macOS — two
different-sounding assistants from one codebase. Windows is the real target (SpaceWalker
is Windows-only), but the mac path must keep working so the voice pipeline stays testable.

## Key insight: the vocabulary is closed

`speak()` has exactly three call sites, all inside `confirm_action`:

```
assistant.py:85   speak(f"Confirm: {action_description}?")
assistant.py:117  speak("Command cancelled.")
assistant.py:122  speak("Timed out. Action cancelled.")
```

`action_description` comes from a fixed set of **10** constant strings — `Lock orientation
planes` and `Unlock orientation planes` (two distinct strings, from `state_str`),
`Clear screens`, `Recenter displays`, `Open Gemini`, and five layout names — plus two
parameterized by an amount that `parse_number` caps at ten.

| Group | Count |
|---|---|
| `Confirm: <fixed description>?` | 10 |
| `Confirm: Push displays away by 1-10?` | 10 |
| `Confirm: Pull displays closer by 1-10?` | 10 |
| `Command cancelled.` / `Timed out. Action cancelled.` | 2 |
| **Total speech lines** | **32** |

The assistant never speaks arbitrary text. So it needs no TTS engine at runtime — it needs
32 WAV files (plus 4 tones = 36 files). Generation is a one-time offline batch; playback is
a dictionary lookup.

This removes every objection to using a neural TTS here: no inference inside the
5-second confirmation window, no VRAM held at runtime (relevant — phi3 already occupies
2.2GB on a 4-6GB card), and no torch in the runtime dependency set.

## Architecture

Three components, each with one responsibility.

### `voice_lines.py` (new, zero dependencies)

Single source of truth for every speakable string, plus the deterministic `text -> slug`
filename function. Dependency-free on purpose: the generator imports it without needing
pyaudio, vosk, or pyautogui installed.

Exposes the 32 speech lines and the 4 tone identifiers.

### `tools/generate_voice_pack.py` (new)

The only place `qwen-tts` and torch appear. Two producers, one output directory:

- **Speech (32 files):** Qwen3-TTS, configured preset speaker.
- **Tones (4 files):** sine synthesis — the existing `_beep` math, moved here.
  Qwen does not generate these; they are beeps, not speech.

Writes `voice/*.wav` and `voice/manifest.json` (model, speaker, sample rate, line count,
generation date). Run on the Windows box with the GPU; the WAVs are what ship.

### `assistant.py` (modified)

- `speak(text, stream=None)` — lookup and play, falling back to native TTS.
- `play_startup_chime` / `play_pleasant_tone` / `play_cancel_tone` / `play_error_tone` —
  play their WAV, falling back to `winsound.Beep` on Windows.
- `_beep`'s macOS sine synthesizer is **removed** (moves to the generator).
- `trigger_clear_screens` returns to Windows-only. The `Win+D` -> `F11` macOS mapping is
  **removed**: SpaceWalker is Windows-only, nothing on macOS receives these hotkeys, and
  the mapping's correctness is not verifiable here. It no-ops with a printed note on macOS.

Net effect: `winsound.Beep`, the sine synthesizer, PowerShell `System.Speech`, and `say`
all collapse into one playback function. The platform-specific audio layer disappears.

## Data flow

```
speak(text, stream)
  -> print [AI Voice]: "text"
  -> stream.stop_stream()          # if stream given
  -> play voice/<slug(text)>.wav   # winsound.PlaySound (Win) / afplay (mac), both blocking
  -> stream.start_stream()
  -> on miss or failure: native TTS fallback
```

Blocking playback is correct: speech must finish before the gate listens.

### Why the mic pause

The assistant's own voice feeds back into the always-on microphone and gets transcribed
as the user's reply. This was observed during live testing and is why TTS was suppressed
in the real-confirm harness. A neural voice makes it worse than the current robotic one.

All three `speak()` call sites are inside `confirm_action`, which already has `stream` in
scope — so this needs no module-level global, just a threaded parameter.

## Error handling

Fail soft, always. A fresh clone with no `voice/` directory still talks, in the old voice.

| Failure | Behavior |
|---|---|
| `voice/` missing | Native TTS fallback, warn once |
| Individual WAV missing | Native TTS fallback for that line |
| Playback error | Caught; native TTS fallback |
| Tone WAV missing | `winsound.Beep` on Windows; silent elsewhere |

Known gap, accepted: `parse_number` also accepts raw digits (`word.isdigit()`), so
`"push 47"` has no pre-rendered line and falls back to native TTS. The pack covers 1-10,
which is everything the spoken number words can produce.

## Testing

The real risk is not latency — it is **silent gaps**: the inventory drifting from what the
code actually says, discovered as unexplained silence mid-command.

1. **Drift test (the important one).** Drive `process_and_execute` across every intent
   using the existing stub harness pattern, capture every `confirm_action` description
   produced, and assert each exists in `voice_lines`. Drift becomes a failing test.
2. **Slug determinism.** `slug(text)` is stable and collision-free across all 32 lines.
3. **Fallback.** With an empty `voice/`, `speak()` still reaches native TTS.
4. **Manifest completeness.** Every line in `voice_lines` has a file in the manifest.

Existing harnesses in the session scratchpad (`vosk_test.py`, `live_mic_test.py`,
`verify_fixes.py`) already establish the monkeypatching pattern these reuse — all
actuation stubbed, no real keystrokes.

## Not doing (YAGNI)

- **Live synthesis fallback for unknown text.** Nothing speaks arbitrary text. Revisit
  only if the assistant should ever read out LLM replies.
- **Voice cloning / voice design.** Preset speaker chosen; the speaker is config, so this
  can change without touching the architecture.
- **Committing the WAVs.** `voice/` is gitignored, mirroring how `model/` is already
  untracked — a generated artifact, not source.

## Repo constraints

This is a clone of `nashvillarta/Impiric-Assist` with **read-only** access (`push: false`).
All work stays on `mac-testing`; `main` remains byte-identical to `origin/main`. Two guards
in `.git/` enforce this: `branch.mac-testing.pushRemote` points at a nonexistent remote,
and `pre-push` rejects both the branch itself and any ref containing its commits.
