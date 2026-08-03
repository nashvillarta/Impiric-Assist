"""Renders the voice pack. Run this offline; the WAVs are what ship.

One producer:
  - speech: Qwen3-TTS (--engine qwen) or the platform's native TTS (--engine native)

--engine native exists so the whole playback pipeline can be built and verified
on a machine without a GPU. Rerun with --engine qwen on the Windows box to swap
in the real voice; the file layout and manifest are identical either way.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import voice_lines

SAMPLE_RATE = 44100
IS_WINDOWS = sys.platform == "win32"


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

    manifest = {
        "engine": args.engine,
        "speaker": args.speaker if args.engine == "qwen" else "platform-native",
        "model": args.model if args.engine == "qwen" else None,
        "sample_rate": SAMPLE_RATE,
        "lines": manifest_lines,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDone. {len(manifest_lines)} speech files in {out_dir}")


if __name__ == "__main__":
    main()
