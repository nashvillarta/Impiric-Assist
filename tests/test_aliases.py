"""Guards alias loading.

Aliases map nicknames to real Discord handles, so the file they live in stays
out of git. That makes "the file is missing" the normal case for a fresh
clone, not an error -- these tests pin that it degrades quietly.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aliases


class TestLoadAliases(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_aliases_tmp.json"
        )
        self.addCleanup(
            lambda: os.path.exists(self.path) and os.remove(self.path)
        )

    def _write(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            if isinstance(data, str):
                f.write(data)
            else:
                json.dump(data, f)

    def test_missing_file_is_not_an_error(self):
        """A fresh clone has no alias file; the assistant must still start."""
        self.assertEqual(aliases.load(self.path), {})

    def test_reads_pairs(self):
        self._write({"nick": "Alice", "rae": "Erin"})
        self.assertEqual(
            aliases.load(self.path), {"nick": "Alice", "rae": "Erin"}
        )

    def test_keys_are_lowercased(self):
        """The lookup lowercases what it heard, so a capitalised key would
        silently never match."""
        self._write({"Nick": "Alice", "RAE": "Erin"})
        self.assertEqual(
            aliases.load(self.path), {"nick": "Alice", "rae": "Erin"}
        )

    def test_malformed_json_does_not_crash_the_assistant(self):
        self._write("{not valid json")
        self.assertEqual(aliases.load(self.path), {})

    def test_non_object_json_is_ignored(self):
        self._write(["nick", "Alice"])
        self.assertEqual(aliases.load(self.path), {})

    def test_non_string_values_are_dropped(self):
        self._write({"nick": "Alice", "bad": 42, "worse": None})
        self.assertEqual(aliases.load(self.path), {"nick": "Alice"})

    def test_blank_entries_are_dropped(self):
        self._write({"nick": "Alice", "": "Nobody", "empty": "   "})
        self.assertEqual(aliases.load(self.path), {"nick": "Alice"})

    def test_underscore_keys_are_settings_not_aliases(self):
        """Without this, "_me" would become a speakable alias."""
        self._write({"_me": "someone", "nick": "Alice"})
        self.assertEqual(aliases.load(self.path), {"nick": "Alice"})


class TestLoadMe(TestLoadAliases):
    def test_reads_the_reserved_me_key(self):
        self._write({"_me": "someone", "nick": "Alice"})
        self.assertEqual(aliases.load_me(self.path), "someone")

    def test_missing_file_returns_empty(self):
        """Empty makes the disconnect command inert, rather than guessing
        which voice channel is yours."""
        self.assertEqual(aliases.load_me(self.path), "")

    def test_absent_key_returns_empty(self):
        self._write({"nick": "Alice"})
        self.assertEqual(aliases.load_me(self.path), "")

    def test_malformed_json_returns_empty(self):
        self._write("{not json")
        self.assertEqual(aliases.load_me(self.path), "")


if __name__ == "__main__":
    unittest.main()
