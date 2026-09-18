import unittest

from steam_tracker.steam_client import parse_bulk_credentials, parse_loginusers_vdf


class SteamClientTests(unittest.TestCase):
    def test_bulk_credentials_split_only_first_colon_and_skip_bad_lines(self):
        entries, issues = parse_bulk_credentials(
            "\ufeffalpha:secret\n"
            "# comment\n"
            "beta:p:a:ss\n"
            "missing-separator\n"
            "ALPHA:duplicate\n"
            "empty:\n"
        )
        self.assertEqual([x.username for x in entries], ["alpha", "beta"])
        self.assertEqual(entries[0].password, "secret")
        self.assertEqual(entries[1].password, "p:a:ss")
        self.assertEqual(len(issues), 3)
        self.assertTrue(all("secret" not in issue and "p:a:ss" not in issue for issue in issues))

    def test_loginusers_vdf_parser_reads_local_identity(self):
        text = r'''
"users"
{
    "76561198000000001"
    {
        "AccountName"       "alpha"
        "PersonaName"       "Alpha Display"
        "RememberPassword"  "1"
        "MostRecent"        "1"
        "Timestamp"         "1720000000"
    }
    "76561198000000002"
    {
        "AccountName"       "beta"
        "PersonaName"       "Beta"
        "MostRecent"        "0"
    }
}
'''
        users = parse_loginusers_vdf(text)
        self.assertEqual(len(users), 2)
        self.assertEqual(users[0].steam_id, "76561198000000001")
        self.assertEqual(users[0].account_name, "alpha")
        self.assertEqual(users[0].persona_name, "Alpha Display")
        self.assertTrue(users[0].most_recent)
        self.assertEqual(users[0].timestamp, 1720000000)
        self.assertEqual(users[0].account_id, (76561198000000001 & 0xFFFFFFFF))


if __name__ == "__main__":
    unittest.main()
