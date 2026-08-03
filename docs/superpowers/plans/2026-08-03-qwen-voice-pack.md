# Qwen3-TTS Voice Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the assistant's two platform-specific speech backends with one pre-rendered voice pack, so it sounds identical on Windows and macOS.

**Architecture:** A dependency-free `voice_lines.py` holds the closed inventory of every speakable string plus the text→filename slug. An offline generator renders 32 speech WAVs (Qwen3-TTS or native TTS) and 4 tone WAVs (sine synthesis) into `voice/`. At runtime `speak()` and the tone functions become a slug lookup and a blocking file play, with native TTS surviving only as a fallback.

**Tech Stack:** Python 3.14, stdlib `wave`/`unittest`/`argparse`, `qwen-tts` (generator only, never at runtime), `winsound.PlaySound` (Windows playback), `afplay` (macOS playback).

## Global Constraints

- Branch is `mac-testing`. NEVER push. NEVER touch `main`. Origin is read-only (`push: false`).
- Runtime dependencies added: **zero**. `qwen-tts` and torch appear only in `tools/generate_voice_pack.py`.
- Tests use stdlib `unittest` only — the repo has no test framework and must not gain one.
- `voice/` is a generated artifact: gitignored, never committed.
- Fail soft everywhere: a missing or broken voice pack degrades to native TTS, never to silence or a crash.
- Never call `send_shortcut`, `trigger_action`, `trigger_clear_screens`, or `trigger_toggle_planes` in a test — they inject real keystrokes into the focused window.
- Match the existing file's style: same comment density, `# --- Section ---` banners, no type annotations.

---

### Task 1: Voice line inventory

**Files:**
- Create: `voice_lines.py`
- Create: `tests/test_voice_lines.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `FIXED_DESCRIPTIONS` (list of str), `STANDALONE_LINES` (list of str), `TONES` (dict of name → list of `(freq_hz, duration_ms)` tuples), `MAX_AMOUNT` (int, 10), `confirm_line(description) -> str`, `all_speech_lines() -> list[str]`, `slug(text) -> str`.

- [ ] **Step 1: Write the failing test**

`tests/test_voice_lines.py`:

```python
import unittest
import voice_lines


class TestVoiceLines(unittest.TestCase):
    def test_speech_line_count_is_32(self):
        self.assertEqual(len(voice_lines.all_speech_lines()), 32)

    def test_no_duplicate_lines(self):
        lines = voice_lines.all_speech_lines()
        self.assertEqual(len(lines), len(set(lines)))

    def test_confirm_line_format(self):
        self.assertEqual(
            voice_lines.confirm_line("Clear screens"),
            "Confirm: Clear screens?",
        )

    def test_slug_is_filesystem_safe(self):
        self.assertEqual(voice_lines.slug("Confirm: Clear screens?"), "confirm-clear-screens")
        self.assertEqual(voice_lines.slug("Timed out. Action cancelled."), "timed-out-action-cancelled")
        self.assertEqual(voice_lines.slug("Confirm: Push displays away by 3?"), "confirm-push-displays-away-by-3")

    def test_slugs_are_unique_across_all_lines(self):
        slugs = [voice_lines.slug(line) for line in voice_lines.all_speech_lines()]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_both_plane_states_present(self):
        lines = voice_lines.all_speech_lines()
        self.assertIn("Confirm: Lock orientation planes?", lines)
        self.assertIn("Confirm: Unlock orientation planes?", lines)

    def test_push_and_pull_cover_one_through_ten(self):
        lines = voice_lines.all_speech_lines()
        for n in range(1, 11):
            self.assertIn(f"Confirm: Push displays away by {n}?", lines)
            self.assertIn(f"Confirm: Pull displays closer by {n}?", lines)

    def test_four_tones_defined(self):
        self.assertEqual(set(voice_lines.TONES), {"startup", "pleasant", "cancel", "error"})
        self.assertEqual(voice_lines.TONES["startup"], [(440, 150), (554, 150), (659, 150), (880, 300)])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/impiric-assist && .venv/bin/python -m unittest tests.test_voice_lines -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'voice_lines'`

- [ ] **Step 3: Write minimal implementation**

`voice_lines.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/impiric-assist && .venv/bin/python -m unittest tests.test_voice_lines -v
```

Expected: PASS, 8 tests. If `tests.test_voice_lines` is not importable, create an empty `tests/__init__.py`.

- [ ] **Step 5: Commit**

```bash
cd ~/impiric-assist && git add voice_lines.py tests/ && git commit -m "Add voice line inventory as single source of truth

32 speech lines (10 fixed descriptions, push/pull x 1-10, 2 standalone)
plus 4 tone definitions. Dependency-free so the generator can import it
without the runtime deps.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Voice pack generator

**Files:**
- Create: `tools/generate_voice_pack.py`
- Modify: `.gitignore` (append `voice/`)

**Interfaces:**
- Consumes: `voice_lines.all_speech_lines()`, `voice_lines.slug()`, `voice_lines.TONES`.
- Produces: `voice/<slug>.wav` for all 32 speech lines, `voice/tone-<name>.wav` for all 4 tones, and `voice/manifest.json` with keys `engine`, `speaker`, `model`, `sample_rate`, `generated`, `lines` (dict of line text → filename), `tones` (dict of tone name → filename).

- [ ] **Step 1: Write the generator**

`tools/generate_voice_pack.py`:

```python
"""Renders the voice pack. Run this offline; the WAVs are what ship.

Two producers:
  - speech: Qwen3-TTS (--engine qwen) or the platform's native TTS (--engine native)
  - tones:  sine synthesis, always. Qwen does not generate beeps.

--engine native exists so the whole playback pipeline can be built and verified
on a machine without a GPU. Rerun with --engine qwen on the Windows box to swap
in the real voice; the file layout and manifest are identical either way.
"""

import argparse
import json
import math
import os
import struct
import subprocess
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import voice_lines

SAMPLE_RATE = 44100
IS_WINDOWS = sys.platform == "win32"


def write_wav(path, frames, rate=SAMPLE_RATE):
    """Writes 16-bit mono PCM bytes to a WAV file."""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)


def synth_tone(steps):
    """Builds 16-bit mono PCM for a sequence of (freq, ms) beeps, with 5ms fades."""
    frames = bytearray()
    for freq, ms in steps:
        n_samples = int(SAMPLE_RATE * ms / 1000)
        fade_samples = min(int(SAMPLE_RATE * 0.005), n_samples // 2)
        for i in range(n_samples):
            fade = 1.0
            if fade_samples:
                if i < fade_samples:
                    fade = i / fade_samples
                elif i > n_samples - fade_samples:
                    fade = (n_samples - i) / fade_samples
            value = int(32767 * fade * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
            frames += struct.pack("<h", value)
    return bytes(frames)


def speak_native(text, out_path):
    """Renders one line with the platform's built-in TTS."""
    if IS_WINDOWS:
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SetOutputToWaveFile('{out_path}'); $s.Speak([Console]::In.ReadToEnd()); $s.Dispose()"
        )
        subprocess.run(["powershell", "-Command", script], input=text, text=True, check=True)
        return
    aiff = out_path + ".aiff"
    subprocess.run(["say", "-o", aiff, text], check=True)
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", f"LEI16@{SAMPLE_RATE}", "-c", "1", aiff, out_path],
        check=True,
    )
    os.remove(aiff)


def speak_qwen(text, out_path, model, speaker, engine_state={}):
    """Renders one line with Qwen3-TTS. Model is loaded once and reused."""
    if "tts" not in engine_state:
        from qwen_tts import QwenTTS  # imported lazily: never a runtime dependency
        engine_state["tts"] = QwenTTS.from_pretrained(model)
    engine_state["tts"].generate(text=text, speaker=speaker, output_path=out_path)


def main():
    parser = argparse.ArgumentParser(description="Render the assistant's voice pack.")
    parser.add_argument("--engine", choices=["native", "qwen"], default="native")
    parser.add_argument("--model", default="Qwen/Qwen3-TTS-12Hz-1.7B-Base")
    parser.add_argument("--speaker", default="default")
    parser.add_argument("--out", default=None, help="Output dir (default: <repo>/voice)")
    args = parser.parse_args()

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = args.out or os.path.join(repo, "voice")
    os.makedirs(out_dir, exist_ok=True)

    lines = voice_lines.all_speech_lines()
    manifest_lines = {}
    for i, text in enumerate(lines, 1):
        name = voice_lines.slug(text) + ".wav"
        path = os.path.join(out_dir, name)
        print(f"  [{i}/{len(lines)}] {text}")
        if args.engine == "qwen":
            speak_qwen(text, path, args.model, args.speaker)
        else:
            speak_native(text, path)
        manifest_lines[text] = name

    manifest_tones = {}
    for tone_name, steps in voice_lines.TONES.items():
        name = f"tone-{tone_name}.wav"
        print(f"  [tone] {tone_name}")
        write_wav(os.path.join(out_dir, name), synth_tone(steps))
        manifest_tones[tone_name] = name

    manifest = {
        "engine": args.engine,
        "speaker": args.speaker if args.engine == "qwen" else "platform-native",
        "model": args.model if args.engine == "qwen" else None,
        "sample_rate": SAMPLE_RATE,
        "lines": manifest_lines,
        "tones": manifest_tones,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDone. {len(manifest_lines)} speech + {len(manifest_tones)} tone files in {out_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Gitignore the generated pack**

Append to `.gitignore`:

```
# Generated voice pack (see tools/generate_voice_pack.py)
voice/
```

- [ ] **Step 3: Generate the pack with the native engine**

```bash
cd ~/impiric-assist && .venv/bin/python tools/generate_voice_pack.py --engine native
```

Expected: 32 speech lines printed, 4 tones, then `Done. 32 speech + 4 tone files`.

- [ ] **Step 4: Verify every file exists and is a valid WAV**

```bash
cd ~/impiric-assist && .venv/bin/python -c "
import json, os, wave, voice_lines
m = json.load(open('voice/manifest.json'))
assert len(m['lines']) == 32, len(m['lines'])
assert len(m['tones']) == 4, len(m['tones'])
missing = [n for n in list(m['lines'].values()) + list(m['tones'].values()) if not os.path.exists(os.path.join('voice', n))]
assert not missing, missing
for n in list(m['lines'].values()) + list(m['tones'].values()):
    with wave.open(os.path.join('voice', n)) as w:
        assert w.getnframes() > 0, n
print('all 36 files present and non-empty')
"
```

Expected: `all 36 files present and non-empty`

- [ ] **Step 5: Commit**

```bash
cd ~/impiric-assist && git add tools/generate_voice_pack.py .gitignore && git commit -m "Add voice pack generator

Renders 32 speech WAVs (Qwen3-TTS or native TTS via --engine) and 4 tone
WAVs (sine synthesis) plus a manifest. Qwen/torch are imported lazily so
they are never a runtime dependency. --engine native lets the pipeline be
verified without a GPU.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Runtime playback in assistant.py

**Files:**
- Modify: `assistant.py` — `speak()` at line 22, `_beep()`/tone functions at lines 35-84, imports at lines 1-16
- Create: `tests/test_playback.py`

**Interfaces:**
- Consumes: `voice_lines.slug()`, `voice_lines.TONES`.
- Produces: `VOICE_DIR` (str), `_play_wav(path, stream=None) -> bool`, `speak(text, stream=None)`, `_play_tone(name)`, and the four existing `play_*` functions with unchanged names and signatures.

- [ ] **Step 1: Write the failing test**

`tests/test_playback.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import assistant


class FakeStream:
    """Records stop/start so we can assert the mic is paused during playback."""

    def __init__(self):
        self.events = []

    def stop_stream(self):
        self.events.append("stop")

    def start_stream(self):
        self.events.append("start")


class TestPlayback(unittest.TestCase):
    def setUp(self):
        """Snapshot the real functions and restore them after every test, so
        stubs never leak into other test modules in the same process."""
        self.played = []
        self.native = []
        self.real_play_wav = assistant._play_wav
        self.real_speak_native = assistant._speak_native
        self.addCleanup(setattr, assistant, "_play_wav", self.real_play_wav)
        self.addCleanup(setattr, assistant, "_speak_native", self.real_speak_native)
        assistant._speak_native = lambda text: self.native.append(text)

    def _stub_play(self, result):
        def fake(path, stream=None):
            self.played.append(path)
            return result
        assistant._play_wav = fake

    def test_missing_wav_falls_back_to_native_tts(self):
        self._stub_play(False)
        assistant.speak("Confirm: Clear screens?")
        self.assertEqual(self.native, ["Confirm: Clear screens?"])

    def test_present_wav_skips_native_tts(self):
        self._stub_play(True)
        assistant.speak("Confirm: Clear screens?")
        self.assertEqual(self.native, [])
        self.assertTrue(self.played[0].endswith("confirm-clear-screens.wav"))

    def test_real_play_wav_returns_false_for_missing_file(self):
        stream = FakeStream()
        path = os.path.join(assistant.VOICE_DIR, "does-not-exist-anywhere.wav")
        self.assertFalse(self.real_play_wav(path, stream))
        self.assertEqual(stream.events, [], "must not touch the stream when there is no file")

    def test_real_play_wav_pauses_then_resumes_stream(self):
        """Uses a real generated WAV, so this exercises actual playback."""
        path = os.path.join(assistant.VOICE_DIR, "tone-pleasant.wav")
        if not os.path.exists(path):
            self.skipTest("voice pack not generated; run tools/generate_voice_pack.py")
        stream = FakeStream()
        self.assertTrue(self.real_play_wav(path, stream))
        self.assertEqual(stream.events, ["stop", "start"])

    def test_stream_resumes_even_when_playback_raises(self):
        stream = FakeStream()
        path = os.path.join(assistant.VOICE_DIR, "tone-pleasant.wav")
        if not os.path.exists(path):
            self.skipTest("voice pack not generated; run tools/generate_voice_pack.py")
        original_run = assistant.subprocess.run
        self.addCleanup(setattr, assistant.subprocess, "run", original_run)
        def boom(*a, **k):
            raise RuntimeError("playback exploded")
        assistant.subprocess.run = boom
        self.assertFalse(self.real_play_wav(path, stream))
        self.assertEqual(stream.events, ["stop", "start"], "mic must resume even on failure")

    def test_tone_falls_back_without_crashing(self):
        self._stub_play(False)
        assistant.play_error_tone()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/impiric-assist && .venv/bin/python -m unittest tests.test_playback -v
```

Expected: FAIL with `AttributeError: module 'assistant' has no attribute '_play_wav'`

- [ ] **Step 3: Implement playback**

In `assistant.py`, replace the whole `speak()` function and the whole `_beep()` + four `play_*` block. Add `import voice_lines` to the import block, and **remove** the now-unused `import math` and `import struct`.

```python
# --- Voice Pack (pre-rendered audio, see tools/generate_voice_pack.py) ---
VOICE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice")


def _play_wav(path, stream=None):
    """Plays a WAV, pausing the mic so the assistant does not hear itself.

    Returns True if it played. Blocking on purpose: speech must finish before
    confirm_action starts listening.
    """
    if not os.path.exists(path):
        return False
    try:
        if stream is not None:
            stream.stop_stream()
        try:
            if IS_WINDOWS:
                winsound.PlaySound(path, winsound.SND_FILENAME)
            else:
                subprocess.run(["afplay", path])
        finally:
            if stream is not None:
                stream.start_stream()
        return True
    except Exception as e:
        print(f"[Voice Warning] Could not play {os.path.basename(path)}: {e}")
        return False


def _speak_native(text):
    """Platform TTS. Only reached when the voice pack has no line for this text."""
    try:
        if IS_WINDOWS:
            escaped_text = text.replace("'", "")
            os.system(f'powershell -Command "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak(\'{escaped_text}\')"')
        else:
            subprocess.run(["say", text])
    except Exception as e:
        print(f"[TTS Warning] Could not initialize voice engine: {e}")


# --- AI Voice (Text-to-Speech) Setup ---
def speak(text, stream=None):
    """Prints text and speaks it, preferring the pre-rendered voice pack."""
    print(f"\n[AI Voice]: \"{text}\"")
    if _play_wav(os.path.join(VOICE_DIR, voice_lines.slug(text) + ".wav"), stream):
        return
    _speak_native(text)


# --- Custom Tones ---
def _play_tone(name):
    """Plays a pre-rendered tone, falling back to winsound.Beep on Windows."""
    if _play_wav(os.path.join(VOICE_DIR, f"tone-{name}.wav")):
        return
    if IS_WINDOWS:
        for freq, ms in voice_lines.TONES[name]:
            winsound.Beep(freq, ms)


def play_startup_chime():
    _play_tone("startup")


def play_pleasant_tone():
    _play_tone("pleasant")


def play_cancel_tone():
    _play_tone("cancel")


def play_error_tone():
    _play_tone("error")
```

- [ ] **Step 4: Thread `stream` through the three speak() call sites**

All three are inside `confirm_action`, which already has `stream` in scope:

- `speak(f"Confirm: {action_description}?")` → `speak(f"Confirm: {action_description}?", stream)`
- `speak("Command cancelled.")` → `speak("Command cancelled.", stream)`
- `speak("Timed out. Action cancelled.")` → `speak("Timed out. Action cancelled.", stream)`

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd ~/impiric-assist && .venv/bin/python -m unittest tests.test_playback tests.test_voice_lines -v
```

Expected: PASS. Then confirm the module still imports and a real line plays:

```bash
cd ~/impiric-assist && .venv/bin/python -c "
import assistant
assistant.speak('Confirm: Clear screens?')
assistant.play_startup_chime()
print('playback ok')
"
```

Expected: audible speech + chime, then `playback ok`.

- [ ] **Step 6: Commit**

```bash
cd ~/impiric-assist && git add assistant.py tests/test_playback.py && git commit -m "Play pre-rendered voice pack instead of live TTS

speak() and the tone functions now look up a WAV by slug and play it,
pausing the mic during playback so the assistant does not transcribe
itself as the user's reply. Native TTS and winsound.Beep survive only as
fallbacks, so a clone with no voice/ directory still talks.

Removes the macOS sine synthesizer from _beep (moved into the generator)
along with the now-unused math and struct imports.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Remove the unverifiable macOS keybind

**Files:**
- Modify: `assistant.py` — `trigger_clear_screens()`

**Interfaces:**
- Consumes: nothing.
- Produces: `trigger_clear_screens()` with unchanged name and signature.

- [ ] **Step 1: Replace the function**

SpaceWalker is Windows-only, so nothing on macOS receives these hotkeys and the `Win+D` → `F11` mapping cannot be verified here. Make it Windows-only and no-op loudly elsewhere:

```python
def trigger_clear_screens():
    """Triggered by 'B One' to minimize windows and clear screens."""
    if not IS_WINDOWS:
        print("\n[ACTION] B One -> Clear screens is Windows-only (SpaceWalker); skipping.")
        return
    print("\n[ACTION] B One -> Clearing screens (Win+D)...")
    pyautogui.hotkey('win', 'd')
```

- [ ] **Step 2: Verify the module still imports**

```bash
cd ~/impiric-assist && .venv/bin/python -c "import assistant; assistant.trigger_clear_screens(); print('ok')"
```

Expected: the Windows-only skip message, then `ok`. No keystroke is sent.

- [ ] **Step 3: Commit**

```bash
cd ~/impiric-assist && git add assistant.py && git commit -m "Remove unverifiable macOS Win+D -> F11 mapping

SpaceWalker is Windows-only, so nothing on macOS receives these hotkeys
and the mapping's correctness cannot be tested here. Now no-ops with a
printed note off Windows.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Drift test — every spoken line has a voice line

**Files:**
- Create: `tests/test_drift.py`

**Interfaces:**
- Consumes: `assistant.process_and_execute`, `voice_lines.all_speech_lines()`, `voice_lines.confirm_line()`.
- Produces: nothing consumed downstream.

This is the test that matters. The failure mode this guards is a **silent gap**: `voice_lines` drifting from what `process_and_execute` actually says, discovered later as unexplained silence mid-command.

- [ ] **Step 1: Write the test**

`tests/test_drift.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import assistant
import voice_lines

# Every phrase that reaches a fast-path branch, one per branch, plus both plane states.
FAST_PATH_PHRASES = [
    "a one",
    "be one",
    "recenter",
    "push three",
    "poll too",
    "open gemini",
]

# Descriptions only the LLM branches can produce.
LLM_ONLY_DESCRIPTIONS = [
    "Switch to Ultrawide layout",
    "Switch to Single display layout",
    "Switch to Dual display layout",
    "Switch to Triple display layout",
    "Switch to Stacked display layout",
]


class TestNoVoiceLineDrift(unittest.TestCase):
    # Every assistant attribute this test replaces. unittest discover runs all
    # modules in one process, so these MUST be restored or they leak into
    # tests/test_playback.py (which sorts after this file) and break it.
    STUBBED = (
        "confirm_action",
        "send_shortcut",
        "trigger_action",
        "trigger_clear_screens",
        "trigger_toggle_planes",
        "speak",
        "query_ollama",
        "play_startup_chime",
        "play_pleasant_tone",
        "play_cancel_tone",
        "play_error_tone",
    )

    def setUp(self):
        """Stub every actuation surface. No keystroke may escape a test."""
        self.descriptions = []
        # getattr runs now, so each cleanup captures the ORIGINAL function.
        for name in self.STUBBED:
            self.addCleanup(setattr, assistant, name, getattr(assistant, name))

        def fake_confirm(description, stream, recognizer, timeout_seconds=5):
            self.descriptions.append(description)
            return False  # decline, so no action is even attempted

        assistant.confirm_action = fake_confirm
        for name in ("send_shortcut", "trigger_action", "trigger_clear_screens", "trigger_toggle_planes"):
            setattr(assistant, name, lambda *a, **k: None)
        assistant.speak = lambda *a, **k: None
        assistant.query_ollama = lambda text: {"action": "unknown", "amount": 1}
        for name in ("play_startup_chime", "play_pleasant_tone", "play_cancel_tone", "play_error_tone"):
            setattr(assistant, name, lambda *a, **k: None)

    def test_fast_path_descriptions_all_have_voice_lines(self):
        for phrase in FAST_PATH_PHRASES:
            assistant.process_and_execute(phrase, None, None)
        self.assertTrue(self.descriptions, "no descriptions captured")
        lines = voice_lines.all_speech_lines()
        for description in self.descriptions:
            self.assertIn(voice_lines.confirm_line(description), lines, f"no voice line for: {description}")

    def test_both_plane_states_have_voice_lines(self):
        lines = voice_lines.all_speech_lines()
        for state in ("Lock", "Unlock"):
            self.assertIn(voice_lines.confirm_line(f"{state} orientation planes"), lines)

    def test_llm_only_descriptions_have_voice_lines(self):
        lines = voice_lines.all_speech_lines()
        for description in LLM_ONLY_DESCRIPTIONS:
            self.assertIn(voice_lines.confirm_line(description), lines, f"no voice line for: {description}")

    def test_voiced_amount_range_matches_parse_number(self):
        """parse_number caps spoken number words at ten; the pack must cover that."""
        lines = voice_lines.all_speech_lines()
        for n in range(1, voice_lines.MAX_AMOUNT + 1):
            self.assertIn(voice_lines.confirm_line(f"Push displays away by {n}"), lines)
            self.assertIn(voice_lines.confirm_line(f"Pull displays closer by {n}"), lines)

    def test_standalone_lines_present(self):
        lines = voice_lines.all_speech_lines()
        self.assertIn("Command cancelled.", lines)
        self.assertIn("Timed out. Action cancelled.", lines)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the full suite**

```bash
cd ~/impiric-assist && .venv/bin/python -m unittest discover -s tests -v
```

Expected: PASS, all tests across the three files.

- [ ] **Step 3: Prove the test actually catches drift**

Temporarily remove `"Clear screens"` from `FIXED_DESCRIPTIONS` in `voice_lines.py`, rerun, and confirm `test_fast_path_descriptions_all_have_voice_lines` FAILS with `no voice line for: Clear screens`. Then restore it and confirm the suite passes again. Do not commit the broken state.

- [ ] **Step 4: Commit**

```bash
cd ~/impiric-assist && git add tests/test_drift.py && git commit -m "Add drift test guarding against silent voice gaps

Drives process_and_execute across every fast-path branch with all
actuation stubbed, and asserts each confirm_action description has a
matching voice line. Verified it fails when a description is removed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Document regenerating with the Qwen voice

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing. Produces: nothing.

- [ ] **Step 1: Append to README.md**

```markdown
## Voice pack

The assistant speaks from pre-rendered WAVs in `voice/` (gitignored, generated).
Its vocabulary is a closed set of 32 lines plus 4 tones, so no TTS engine runs at
runtime and nothing competes with phi3 for VRAM.

Generate a pack with the platform's built-in voice (works anywhere, no GPU):

    python tools/generate_voice_pack.py --engine native

Generate the real Qwen3-TTS voice (run this on a machine with an NVIDIA GPU):

    pip install qwen-tts
    python tools/generate_voice_pack.py --engine qwen --speaker <preset-name>

Both write the same filenames and manifest, so swapping voices is one command.
If `voice/` is missing or incomplete the assistant falls back to the platform's
built-in TTS, so it always talks.
```

- [ ] **Step 2: Commit**

```bash
cd ~/impiric-assist && git add README.md && git commit -m "Document voice pack generation

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Verification checklist

- [ ] `.venv/bin/python -m unittest discover -s tests -v` — all pass
- [ ] `.venv/bin/python -c "import assistant"` — clean import
- [ ] `voice/` contains 36 WAVs + `manifest.json`, and is gitignored
- [ ] `git diff main origin/main --stat` — empty (main pristine)
- [ ] `git status` — clean, still on `mac-testing`
- [ ] Nothing pushed
