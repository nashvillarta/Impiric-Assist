"""Renders the voice pack. Run this offline; the WAVs are what ship.

One producer:
  - speech: Qwen3-TTS (--engine qwen) or the platform's native TTS (--engine native)

--engine native exists so the whole playback pipeline can be built and verified
on a machine without a GPU. Rerun with --engine qwen on the Windows box to swap
in the real voice; the file layout and manifest are identical either way.

Use --voice to pick a voice for either engine (a native OS voice name, or a
Qwen3-TTS preset speaker), and --list-voices to see what's available for the
current --engine without generating anything.
"""

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import voice_lines

SAMPLE_RATE = 44100
IS_WINDOWS = sys.platform == "win32"

QWEN_VOICES = [
    "Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric", "Ryan", "Aiden", "Ono_Anna", "Sohee",
]


def speak_native(text, out_path, voice=None):
    """Renders one line with the platform's built-in TTS."""
    if IS_WINDOWS:
        # Windows voice names (e.g. "Microsoft Zira Desktop") differ from macOS
        # `say` voice names (e.g. "Daniel") -- SelectVoice is wrapped so an
        # unrecognized name warns and falls back to the default voice instead
        # of aborting the whole run.
        select = ""
        if voice:
            select = (
                f"try {{ $s.SelectVoice('{voice}') }} "
                f"catch {{ Write-Warning \"voice '{voice}' not found; using default\" }}; "
            )
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"{select}"
            f"$s.SetOutputToWaveFile('{out_path}'); $s.Speak([Console]::In.ReadToEnd()); $s.Dispose()"
        )
        subprocess.run(["powershell", "-Command", script], input=text, text=True, check=True)
        return
    aiff = out_path + ".aiff"
    say_cmd = ["say"]
    if voice:
        say_cmd += ["-v", voice]
    say_cmd += ["-o", aiff, text]
    subprocess.run(say_cmd, check=True)
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", f"LEI16@{SAMPLE_RATE}", "-c", "1", aiff, out_path],
        check=True,
    )
    os.remove(aiff)


def speak_qwen(text, out_path, model, voice, engine_state={}):
    """Renders one line with Qwen3-TTS. Model is loaded once and reused."""
    if "tts" not in engine_state:
        from qwen_tts import QwenTTS  # imported lazily: never a runtime dependency
        engine_state["tts"] = QwenTTS.from_pretrained(model)
    engine_state["tts"].generate(text=text, speaker=voice, output_path=out_path)


def list_voices_native():
    """Prints installed native TTS voices for the current platform."""
    if IS_WINDOWS:
        script = (
            "Add-Type -AssemblyName System.Speech; "
            "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | "
            "ForEach-Object { $_.VoiceInfo.Name }"
        )
        subprocess.run(["powershell", "-Command", script], check=True)
        return
    result = subprocess.run(["say", "-v", "?"], check=True, capture_output=True, text=True)
    for line in result.stdout.splitlines():
        # Fixed-width columns: name, locale (e.g. en_US), then a "# ..." sample.
        # Names can contain single spaces (e.g. "Bad News"), so split on runs
        # of 2+ spaces rather than on any whitespace.
        columns = re.split(r"\s{2,}", line.strip())
        if len(columns) >= 2 and columns[1].startswith("en_"):
            print(line)


def list_voices_qwen():
    """Prints the documented Qwen3-TTS preset speakers."""
    for name in QWEN_VOICES:
        print(name)


def main():
    parser = argparse.ArgumentParser(description="Render the assistant's voice pack.")
    parser.add_argument("--engine", choices=["native", "qwen"], default="native")
    parser.add_argument("--model", default="Qwen/Qwen3-TTS-12Hz-1.7B-Base")
    parser.add_argument("--voice", default=None, help="Native OS voice name, or Qwen3-TTS preset speaker")
    parser.add_argument("--out", default=None, help="Output dir (default: <repo>/voice)")
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="Print available voices for --engine and exit",
    )
    args = parser.parse_args()

    if args.list_voices:
        if args.engine == "qwen":
            list_voices_qwen()
        else:
            list_voices_native()
        return

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
            speak_qwen(text, path, args.model, args.voice or "default")
        else:
            speak_native(text, path, args.voice)
        manifest_lines[text] = name

    manifest = {
        "engine": args.engine,
        "voice": args.voice or ("default" if args.engine == "qwen" else "system-default"),
        "model": args.model if args.engine == "qwen" else None,
        "sample_rate": SAMPLE_RATE,
        "lines": manifest_lines,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDone. {len(manifest_lines)} speech files in {out_dir}")


if __name__ == "__main__":
    main()
