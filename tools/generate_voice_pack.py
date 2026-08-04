"""Renders the voice pack. Run this offline; the WAVs are what ship.

One producer:
  - speech: Qwen3-TTS (--engine qwen) or Windows' native TTS (--engine native)

--engine native exists so the whole playback pipeline can be built and verified
without a GPU, using the Windows SAPI voice built into System.Speech. Rerun
with --engine qwen to swap in the real voice; the file layout and manifest are
identical either way.

Use --voice to pick a voice for either engine (a native OS voice name, or a
Qwen3-TTS preset speaker), and --list-voices to see what's available for the
current --engine without generating anything.
"""

import argparse
import json
import os
import subprocess
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import voice_lines

# Preset speakers like Serena only exist in the CustomVoice checkpoint. The Base
# checkpoint is the voice-clone model and refuses generate_custom_voice outright.
DEFAULT_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"

QWEN_VOICES = [
    "Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric", "Ryan", "Aiden", "Ono_Anna", "Sohee",
]


def speak_native(text, out_path, voice=None):
    """Renders one line with Windows' built-in TTS."""
    # Windows voice names (e.g. "Microsoft Zira Desktop") -- SelectVoice is
    # wrapped so an unrecognized name warns and falls back to the default
    # voice instead of aborting the whole run.
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


def _write_wav(out_path, samples, sample_rate):
    """Writes float samples as 16-bit mono PCM.

    Qwen returns a float32 waveform in [-1, 1] and writes no file of its own.
    winsound.PlaySound (how assistant.py plays these back) reads plain PCM
    only, so the conversion has to happen here.
    """
    import numpy as np  # part of the qwen path; never imported for --engine native

    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes((clipped * 32767.0).astype("<i2").tobytes())


def _load_kwargs():
    """Puts the checkpoint on the GPU when there is one.

    The pack is meant to be rendered on a CUDA box (see README); left on the
    CPU a 36-line run takes hours. Asking for cuda on a CPU-only torch build
    raises, so this stays empty there and the run just goes slowly.
    """
    import torch

    return {"device_map": "cuda"} if torch.cuda.is_available() else {}


def speak_qwen(text, out_path, model, voice, instruct=None, engine_state={}):
    """Renders one line with Qwen3-TTS. Model is loaded once and reused.

    `instruct` is a free-text style description ("a calm British AI assistant")
    that steers the preset speaker. Returns the sample rate the model produced.
    """
    if "tts" not in engine_state:
        # Imported lazily: never a runtime dependency.
        from qwen_tts import Qwen3TTSModel
        engine_state["tts"] = Qwen3TTSModel.from_pretrained(model, **_load_kwargs())
    wavs, sample_rate = engine_state["tts"].generate_custom_voice(
        text=text, speaker=voice, instruct=instruct
    )
    _write_wav(out_path, wavs[0], sample_rate)
    return sample_rate


def list_voices_native():
    """Prints installed Windows TTS voices."""
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | "
        "ForEach-Object { $_.VoiceInfo.Name }"
    )
    subprocess.run(["powershell", "-Command", script], check=True)


def list_voices_qwen():
    """Prints the documented Qwen3-TTS preset speakers."""
    for name in QWEN_VOICES:
        print(name)


def main_with_args(argv=None):
    parser = argparse.ArgumentParser(description="Render the assistant's voice pack.")
    parser.add_argument("--engine", choices=["native", "qwen"], default="native")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--voice", default=None, help="Native OS voice name, or Qwen3-TTS preset speaker")
    parser.add_argument(
        "--instruct",
        default=None,
        help="Qwen only: free-text style for the voice, e.g. "
        "'a calm British AI assistant, crisp RP, understated'",
    )
    parser.add_argument("--out", default=None, help="Output dir (default: <repo>/voice)")
    parser.add_argument(
        "--list-voices",
        action="store_true",
        help="Print available voices for --engine and exit",
    )
    args = parser.parse_args(argv)

    # Windows SAPI has no style control, so accepting --instruct there would
    # silently produce a pack that sounds nothing like what was asked for.
    if args.instruct and args.engine != "qwen":
        parser.error("--instruct only applies to --engine qwen")

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
    sample_rate = None
    for i, text in enumerate(lines, 1):
        name = voice_lines.slug(text) + ".wav"
        path = os.path.join(out_dir, name)
        # flush: a qwen line takes ~10s, and Python block-buffers stdout when it
        # is redirected to a file, which makes a working run look hung.
        print(f"  [{i}/{len(lines)}] {text}", flush=True)
        if args.engine == "qwen":
            speak_qwen(text, path, args.model, args.voice or "default", args.instruct)
        else:
            speak_native(text, path, args.voice)
        # Read the rate back off the file rather than assuming one: both engines
        # pick it themselves, and a manifest that disagrees with the WAVs is worse
        # than no manifest at all.
        with wave.open(path, "rb") as w:
            sample_rate = w.getframerate()
        manifest_lines[text] = name

    manifest = {
        "engine": args.engine,
        "voice": args.voice or ("default" if args.engine == "qwen" else "system-default"),
        "model": args.model if args.engine == "qwen" else None,
        "instruct": args.instruct,
        "sample_rate": sample_rate,
        "lines": manifest_lines,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDone. {len(manifest_lines)} speech files in {out_dir}")


if __name__ == "__main__":
    main_with_args()
