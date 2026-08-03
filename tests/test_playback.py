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
        path = os.path.join(assistant.VOICE_DIR, "okay.wav")
        if not os.path.exists(path):
            self.skipTest("voice pack not generated; run tools/generate_voice_pack.py")
        stream = FakeStream()
        self.assertTrue(self.real_play_wav(path, stream))
        self.assertEqual(stream.events, ["stop", "start"])

    def test_stream_resumes_even_when_playback_raises(self):
        stream = FakeStream()
        path = os.path.join(assistant.VOICE_DIR, "okay.wav")
        if not os.path.exists(path):
            self.skipTest("voice pack not generated; run tools/generate_voice_pack.py")
        original_run = assistant.subprocess.run
        self.addCleanup(setattr, assistant.subprocess, "run", original_run)
        def boom(*a, **k):
            raise RuntimeError("playback exploded")
        assistant.subprocess.run = boom
        self.assertFalse(self.real_play_wav(path, stream))
        self.assertEqual(stream.events, ["stop", "start"], "mic must resume even on failure")

if __name__ == "__main__":
    unittest.main()
