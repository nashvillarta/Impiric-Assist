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
