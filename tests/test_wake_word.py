"""Guards wake-word detection.

"computer" is an ordinary English word, so Vosk transcribes it reliably. These
tests pin that it matches as a whole word only -- the mic picks up the Discord
call, so near-misses must not arm the assistant.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import wake_word


class TestWakeSplit(unittest.TestCase):
    def test_bare_wake_word_returns_empty_command(self):
        """Empty string, not None: it means 'armed, awaiting a command'."""
        self.assertEqual(wake_word.split("computer"), "")

    def test_wake_word_with_command_returns_the_command(self):
        self.assertEqual(wake_word.split("computer kick alice"), "kick alice")

    def test_absent_wake_word_returns_none(self):
        self.assertIsNone(wake_word.split("kick alice"))

    def test_leading_noise_before_the_wake_word_is_ignored(self):
        """Vosk emits a whole utterance, so the wake word is rarely first."""
        self.assertEqual(wake_word.split("um computer kick alice"), "kick alice")

    def test_common_words_must_not_wake_it(self):
        """The mic hears the Discord call. Someone saying any of these in
        conversation must not arm the assistant."""
        for phrase in ("computers", "computing", "compute", "nash"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(wake_word.split(phrase))

    def test_empty_phrase(self):
        self.assertIsNone(wake_word.split(""))


if __name__ == "__main__":
    unittest.main()
