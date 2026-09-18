import tempfile
import unittest
from pathlib import Path

from steam_tracker.db import Database


class DatabaseTests(unittest.TestCase):
    def test_games_are_sorted_and_aggregated(self):
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "tracker.sqlite3")
            sid = "76561198000000000"
            db.upsert_account(sid, persona_name="Example")
            db.replace_games(sid, [
                {"appid": 1, "name": "Low", "playtime_forever": 60, "img_icon_url": "a"},
                {"appid": 2, "name": "High", "playtime_forever": 600, "img_icon_url": "b"},
            ])
            row = db.get_account(sid)
            self.assertEqual(row["game_count"], 2)
            self.assertEqual(row["total_playtime_minutes"], 660)
            self.assertEqual(row["top_games"][0]["name"], "High")

    def test_timer_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "tracker.sqlite3")
            sid = "76561198000000001"
            db.upsert_account(sid)
            db.set_timer(sid, 1234567890)
            self.assertEqual(db.get_account(sid)["vcbnd_until"], 1234567890)
            db.set_timer(sid, None)
            self.assertIsNone(db.get_account(sid)["vcbnd_until"])

    def test_comp_round_trip_and_migration_default(self):
        with tempfile.TemporaryDirectory() as td:
            db = Database(Path(td) / "tracker.sqlite3")
            sid = "76561198000000002"
            db.upsert_account(sid)
            self.assertEqual(db.get_account(sid)["comp"], 0)
            db.set_comp(sid, True)
            self.assertEqual(db.get_account(sid)["comp"], 1)
            db.set_comp(sid, False)
            self.assertEqual(db.get_account(sid)["comp"], 0)


if __name__ == "__main__":
    unittest.main()
