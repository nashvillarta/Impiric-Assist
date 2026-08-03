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
