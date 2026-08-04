"""Guards the parts of the Discord disconnect flow that can go wrong quietly.

parse_member and resolve_name carry the risk and none of the UI, so they are
tested exhaustively here without Discord running. The parse fixtures are real
accessibility strings captured from a live Discord window -- including the
nested-parenthesis channel name that broke the first regex written for it.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord_control


class TestParseMember(unittest.TestCase):
    """Real strings from the accessibility tree, not invented ones."""

    def test_member_in_voice_yields_username_and_channel(self):
        self.assertEqual(
            discord_control.parse_member("AliceIn voiceIn voice (team-room-(work))"),
            ("Alice", "team-room-(work)"),
        )

    def test_channel_name_containing_parentheses_survives(self):
        """The first regex here was non-greedy and returned 'team-room-(work'
        with the paren lopped off."""
        _, channel = discord_control.parse_member(
            "BobIn voiceIn voice (team-room-(work))"
        )
        self.assertEqual(channel, "team-room-(work)")

    def test_plain_member_not_in_voice_is_ignored(self):
        self.assertIsNone(discord_control.parse_member("Dave"))

    def test_member_with_server_tag_not_in_voice_is_ignored(self):
        self.assertIsNone(
            discord_control.parse_member("Carol PrimeServer Tag: WFCD")
        )

    def test_username_with_a_space_is_kept_whole(self):
        username, _ = discord_control.parse_member(
            "in hereIn voice (team-room-(work))"
        )
        self.assertEqual(username, "in here")

    def test_empty_and_junk_input(self):
        self.assertIsNone(discord_control.parse_member(""))
        self.assertIsNone(discord_control.parse_member("   "))


def _members(*names):
    return [discord_control.VoiceMember(n, "chan", object()) for n in names]


class TestResolveName(unittest.TestCase):
    def test_exact_match(self):
        members = _members("Alice", "Dave")
        self.assertEqual(discord_control.resolve_name("Alice", members).username, "Alice")

    def test_match_is_case_insensitive(self):
        members = _members("Alice", "Dave")
        self.assertEqual(discord_control.resolve_name("alice", members).username, "Alice")

    def test_alias_beats_fuzzy_matching(self):
        """Vosk has no vocabulary entry for 'Carol'; it hears 'chicken'."""
        members = _members("Carol", "Dave")
        match = discord_control.resolve_name(
            "chicken", members, aliases={"chicken": "Carol"}
        )
        self.assertEqual(match.username, "Carol")

    def test_close_enough_transcription_still_matches(self):
        members = _members("Alice", "Dave")
        self.assertEqual(discord_control.resolve_name("alise", members).username, "Alice")

    def test_unrelated_word_matches_nothing(self):
        members = _members("Alice", "Dave")
        self.assertIsNone(discord_control.resolve_name("bananas", members))

    def test_two_close_candidates_refuse_rather_than_guess(self):
        """The invariant that keeps this from disconnecting the wrong person:
        neither name is exact and both are plausible, so refuse."""
        members = _members("Chrissy", "Christian")
        self.assertIsNone(discord_control.resolve_name("chris", members))

    def test_an_exact_match_wins_over_a_near_miss(self):
        """Refusing here instead would make the feature useless to anyone with
        a similarly-named person in the channel."""
        members = _members("Adam", "Adan")
        self.assertEqual(discord_control.resolve_name("adam", members).username, "Adam")

    def test_empty_member_list(self):
        self.assertIsNone(discord_control.resolve_name("Alice", []))

    def test_empty_spoken_name(self):
        self.assertIsNone(discord_control.resolve_name("", _members("Alice")))


def _members_in(*pairs):
    return [discord_control.VoiceMember(n, c, object()) for n, c in pairs]


class TestMembersInMyChannel(unittest.TestCase):
    """The member list spans the whole server, so scoping is load-bearing."""

    def setUp(self):
        self.members = _members_in(
            ("Me", "team-room-(work)"),
            ("Alice", "team-room-(work)"),
            ("Dave", "employees-lounge-(games1)"),
            ("Frank", "employees-lounge-(games1)"),
        )

    def test_only_my_channel_is_returned(self):
        got = discord_control.members_in_my_channel(self.members, "Me")
        self.assertEqual([m.username for m in got], ["Alice"])

    def test_i_am_excluded_from_my_own_channel(self):
        got = discord_control.members_in_my_channel(self.members, "Me")
        self.assertNotIn("Me", [m.username for m in got])

    def test_no_username_configured_returns_nothing(self):
        """Falling back to server-wide would silently widen the blast radius."""
        self.assertEqual(discord_control.members_in_my_channel(self.members, ""), [])

    def test_not_in_voice_returns_nothing(self):
        self.assertEqual(
            discord_control.members_in_my_channel(self.members, "Absent"), []
        )


class FakeElement:
    """Stands in for a uiautomation control."""

    def __init__(self, name="", children=None):
        self.Name = name
        self.ControlTypeName = "MenuItemControl"
        self._children = children or []
        self.right_clicked = False
        self.clicked = False

    def RightClick(self, **kwargs):
        self.right_clicked = True

    def Click(self, **kwargs):
        self.clicked = True


class FakeUia:
    """Minimal stand-in for the uiautomation module surface we use."""

    def __init__(self, menu_items):
        self.menu_items = menu_items
        self.keys_sent = []

    def menu_walker(self):
        return list(self.menu_items)

    def SendKeys(self, keys, **kwargs):
        self.keys_sent.append(keys)


class TestDisconnect(unittest.TestCase):
    def setUp(self):
        self.member_el = FakeElement("AliceIn voice")
        self.member = discord_control.VoiceMember("Alice", "chan", self.member_el)

    def test_clicks_the_item_named_disconnect(self):
        disconnect_item = FakeElement("Disconnect")
        uia = FakeUia([FakeElement("Server Deafen"), disconnect_item,
                       FakeElement("Copy User ID")])
        ok = discord_control.disconnect(self.member, uia=uia)
        self.assertTrue(ok)
        self.assertTrue(self.member_el.right_clicked)
        self.assertTrue(disconnect_item.clicked)

    def test_never_clicks_a_neighbouring_item(self):
        """Off-by-one here server-deafens someone instead."""
        deafen = FakeElement("Server Deafen")
        copy_id = FakeElement("Copy User ID")
        uia = FakeUia([deafen, FakeElement("Disconnect"), copy_id])
        discord_control.disconnect(self.member, uia=uia)
        self.assertFalse(deafen.clicked)
        self.assertFalse(copy_id.clicked)

    def test_missing_disconnect_item_clicks_nothing(self):
        deafen = FakeElement("Server Deafen")
        uia = FakeUia([deafen, FakeElement("Copy User ID")])
        ok = discord_control.disconnect(self.member, uia=uia)
        self.assertFalse(ok)
        self.assertFalse(deafen.clicked)

    def test_escapes_even_when_the_item_is_missing(self):
        uia = FakeUia([FakeElement("Copy User ID")])
        discord_control.disconnect(self.member, uia=uia)
        self.assertIn("{Esc}", uia.keys_sent)

    def test_escapes_even_when_the_menu_walk_raises(self):
        """A crash must never leave a context menu open over Discord."""
        uia = FakeUia([])

        def boom():
            raise RuntimeError("tree walk exploded")

        uia.menu_walker = boom
        with self.assertRaises(RuntimeError):
            discord_control.disconnect(self.member, uia=uia)
        self.assertIn("{Esc}", uia.keys_sent)

    def test_dry_run_finds_the_item_but_does_not_click(self):
        disconnect_item = FakeElement("Disconnect")
        uia = FakeUia([disconnect_item])
        ok = discord_control.disconnect(self.member, uia=uia, dry_run=True)
        self.assertTrue(ok, "dry run should still report that it found the item")
        self.assertFalse(disconnect_item.clicked)
        self.assertIn("{Esc}", uia.keys_sent)


if __name__ == "__main__":
    unittest.main()
