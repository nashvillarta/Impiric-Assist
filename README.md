WIP

Basic setup:
- You can download Ollama for Windows (requires Windows 10 or later) directly from this link: https://ollama.com/download/windows.
- Download a lightweight Vosk model. https://alphacephei.com/vosk/models (e.g., vosk-model-small-en-us-0.15).
- Extract the contents into a folder named model inside the project directory.

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
