# Impiric Assist

Offline voice control for **SpaceWalker** AR virtual monitors on Windows. Say
`"computer push three"` and your screens move — after it reads the action back to
you and you say yes.

Nothing leaves the machine: speech recognition, intent parsing and the assistant's
own voice all run locally.

## How it works

```
mic -> Vosk (offline STT) -> "computer ..." wake word
     -> keyword fast path        (instant, no model)
     -> phi3 via Ollama          (only for phrases the fast path misses)
     -> spoken confirmation      "Confirm: Push displays away by 3?"  -> you say yes/no
     -> Ctrl+Shift+Alt+<key>     sent to SpaceWalker via pyautogui
```

Every action is gated behind a spoken confirmation. Nothing fires without a yes.

## Requirements

- **Windows 10 or later**
- **Python 3.10+**
- **SpaceWalker running** — it is what receives the hotkeys
- ~2.2 GB disk for the phi3 model, ~70 MB for the Vosk model

## Setup

**1. Install Ollama and pull the model**

Download [Ollama for Windows](https://ollama.com/download/windows), then:

    ollama pull phi3

Ollama must be running when you start the assistant. It listens on
`127.0.0.1:11434`.

**2. Download the Vosk speech model**

Grab a lightweight English model from [alphacephei.com/vosk/models](https://alphacephei.com/vosk/models)
— `vosk-model-small-en-us-0.15` is a good default. Extract it into a folder named
`model` in the project directory, so you end up with `model/am`, `model/conf`,
`model/graph`, `model/ivector`.

**3. Install Python dependencies**

    setup.bat

Or directly: `pip install vosk pyaudio pyautogui requests`

**4. Generate the voice pack**

    python tools/generate_voice_pack.py

This renders every line the assistant can say into `voice/` as WAV files. See
[Customizing the voice](#customizing-the-voice) to pick a different one.

**5. Run it**

    run.bat

You should hear *"Assistant ready."*

## Voice commands

Everything starts with the wake word **"computer"**.

| Say | Does | Hotkey sent |
|---|---|---|
| `computer a one` | Lock/unlock orientation planes | `Ctrl+Shift+Alt+X/Y/Z` |
| `computer b one` | Clear screens | `Win+D` |
| `computer recenter` | Recenter displays | `Ctrl+Shift+Alt+R` |
| `computer push three` | Move screens away by 3 | `Ctrl+Shift+Alt+Down` ×3 |
| `computer pull two` | Bring screens closer by 2 | `Ctrl+Shift+Alt+Up` ×2 |
| `computer open gemini` | Open Gemini in a browser | — |

Anything else goes to phi3, which can also switch layouts — try
*"computer make my screens ultrawide"* or *"computer give me three screens"*.

After each command it speaks the action back and listens **10 seconds** for
`yes` / `no`. Silence cancels.

## Customizing the voice

The assistant never speaks arbitrary text — its vocabulary is a **closed set of 36
lines**. So there is no TTS engine running at runtime: every line is pre-rendered
to a WAV once, and `speak()` just plays the matching file. That keeps speech out of
the confirmation window and leaves your VRAM to phi3.

`voice/` is generated, not committed. Regenerating is how you change voices.

**See what's available on your machine:**

    python tools/generate_voice_pack.py --list-voices

**Windows built-in voices.** On a typical en-US install you will see
`Microsoft David Desktop` and `Microsoft Zira Desktop`. Be aware that
`System.Speech` (SAPI 5) only enumerates the older "Desktop" voices — it does
**not** see the newer voices listed under Windows Settings → Speech. So
`--list-voices` may show fewer than you expect, and it is the authoritative list.
Installing another language pack adds its Desktop voice (e.g.
`Microsoft Hazel Desktop` for en-GB).

    python tools/generate_voice_pack.py --voice "Microsoft David Desktop"

An unrecognized voice name warns and falls back to the default rather than
failing the whole run.

**Qwen3-TTS voices.** For a modern neural voice, install the generator's optional
dependency and pick one of the 9 presets. This needs an NVIDIA GPU (~4 GB VRAM);
it is only used to *generate* the pack, never at runtime.

    pip install qwen-tts
    python tools/generate_voice_pack.py --engine qwen --voice Serena

| Preset | | |
|---|---|---|
| `Vivian` | `Serena` | `Uncle_Fu` |
| `Dylan` | `Eric` | `Ryan` |
| `Aiden` | `Ono_Anna` | `Sohee` |

List them any time with `--engine qwen --list-voices`.

Both engines write identical filenames and a `voice/manifest.json` recording which
engine and voice produced the pack, so switching is one command. If `voice/` is
missing or a line has no file, the assistant falls back to the built-in Windows
voice — it always talks.

## Adding more hotkeys

SpaceWalker actions are `Ctrl+Shift+Alt+<key>`. Two helpers send them:

- `send_shortcut(key)` — one press. Use for toggles and layouts.
- `trigger_action(name, key, amount)` — presses `key` `amount` times, holding the
  modifiers once (avoids Sticky Keys). Use for repeatable nudges like push/pull.

Adding a command takes four steps. Say we want *"computer tile"* →
`Ctrl+Shift+Alt+T`.

**1. Add the spoken confirmation line** in `voice_lines.py`:

```python
FIXED_DESCRIPTIONS = [
    ...
    "Tile windows",
]
```

**2. Add the fast-path rule** in `process_and_execute()` in `assistant.py`:

```python
    # 7. Tile windows
    if any(word in phrase for word in ["tile", "style", "tiles"]):
        if confirm_action("Tile windows", stream, recognizer):
            print("\n[ACTION] Tile -> Ctrl+Shift+Alt+T")
            send_shortcut('t')
        return
```

Include likely mis-hearings in that keyword list — Vosk will not always give you
the word you said. Real examples already in the code: `"pull"` also matches
`poll`, `paul`, `cool`; `"b one"` also matches `be one`.

⚠️ **Rule order matters.** Matching is substring-based and the first rule that
matches wins, so a phrase containing two keywords resolves to whichever rule
appears *earlier* in the function — not to whichever word you said last. Put
narrow rules above broad ones.

**3. (Optional) Teach phi3 about it** so natural phrasing works too. Add the
action to the `system_prompt` list in `query_ollama()`:

```
- 'tile' (if they want to tile, arrange, or grid their windows)
```

then handle it in the LLM fallback chain:

```python
    elif action == "tile":
        if confirm_action("Tile windows", stream, recognizer):
            send_shortcut('t')
```

**4. Regenerate the pack and run the tests**

    python tools/generate_voice_pack.py
    python -m unittest discover -s tests

The new line needs a WAV, which is why step 4 is not optional. If you forget
step 1, the drift test fails with `no voice line for: Tile windows` rather than
letting you discover it as unexplained silence mid-command.

## Tests

    python -m unittest discover -s tests

Standard library `unittest`, no framework to install. The tests stub every
keystroke-sending function, so running them never moves your windows.
