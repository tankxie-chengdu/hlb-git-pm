import unittest
from types import SimpleNamespace

from web.api.members import _is_outsourced_name, _match_member, _member_last_commits, _member_name_lookup


class MemberMatchingTests(unittest.TestCase):
    def test_outsourced_name_detection_is_case_insensitive_and_trimmed(self):
        self.assertTrue(_is_outsourced_name("  V_alice(艾丽丝)"))
        self.assertFalse(_is_outsourced_name("alice(艾丽丝)"))

    def test_matches_member_by_git_name_when_email_differs(self):
        member = SimpleNamespace(id=1, git_name="cherleyzhu")
        result = _match_member(
            "cherleyzhu@gmail.com",
            "cherleyzhu",
            {},
            {"cherleyzhu": member},
        )
        self.assertIs(result, member)

    def test_matches_member_by_email_local_part(self):
        member = SimpleNamespace(id=2, git_name="pensoyao")
        result = _match_member(
            "pensoyao@yjyhuawei-matebook-air.local",
            "penso",
            {},
            {"pensoyao": member},
        )
        self.assertIs(result, member)

    def test_roster_account_is_kept_as_an_identity_alias(self):
        member = SimpleNamespace(id=3, git_name="tangjiawei", real_name="rookietang(汤加伟)")
        lookup = _member_name_lookup([member])
        self.assertIs(lookup["tangjiawei"], member)
        self.assertIs(lookup["rookietang"], member)

    def test_latest_commit_is_aggregated_across_member_aliases(self):
        member = SimpleNamespace(id=3)
        rows = [
            SimpleNamespace(git_email="1135176001@qq.com", git_name="rookietang", last_commit_at="2026-07-14"),
            SimpleNamespace(git_email="tangjiawei@nnyy.com", git_name="tangjiawei", last_commit_at="2025-04-23"),
        ]
        latest = _member_last_commits(
            rows,
            {"1135176001@qq.com": member},
            {"tangjiawei": member},
        )
        self.assertEqual(latest, {3: "2026-07-14"})


if __name__ == "__main__":
    unittest.main()
