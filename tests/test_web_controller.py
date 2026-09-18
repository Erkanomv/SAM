import tempfile
import time
import unittest
from pathlib import Path

from steam_tracker.db import Database
from steam_tracker.web_controller import WebController


class DummySecrets:
    def __init__(self):
        self.key = ""
        self.passwords = {}
    def get_api_key(self): return self.key
    def set_api_key(self, value): self.key = value
    def delete_api_key(self): self.key = ""
    def get_password(self, sid): return self.passwords.get(sid, "")
    def set_password(self, sid, value): self.passwords[sid] = value
    def delete_password(self, sid): self.passwords.pop(sid, None)


class DummyApi:
    def has_key(self): return False


class WebControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "tracker.sqlite3")
        self.secrets = DummySecrets()
        self.controller = WebController(self.db, self.secrets, DummyApi())

    def tearDown(self):
        self.temp.cleanup()

    def test_state_serializes_cards_and_expired_timer(self):
        self.db.upsert_account("123", persona_name="Alice", vcbnd_until=int(time.time()) - 5)
        self.db.replace_games("123", [{"appid": 730, "name": "CS2", "playtime_forever": 120, "img_icon_url": "abc"}])
        state = self.controller.get_state()
        self.assertEqual(state["accounts"][0]["personaName"], "Alice")
        self.assertEqual(state["accounts"][0]["topGameName"], "CS2")
        self.assertFalse(state["accounts"][0]["vcbnd"])
        self.assertEqual(self.db.get_account("123")["vcbnd_until"], None)

    def test_custom_day_timer(self):
        self.db.upsert_account("123", persona_name="Alice")
        result = self.controller.set_timer("123", "2.5")
        self.assertTrue(result["ok"])
        self.assertTrue(result["state"]["accounts"][0]["vcbnd"])

    def test_comp_toggle_is_serialized(self):
        self.db.upsert_account("123", persona_name="Alice")
        result = self.controller.toggle_comp("123")
        self.assertTrue(result["ok"])
        self.assertTrue(result["state"]["accounts"][0]["comp"])
        result = self.controller.toggle_comp("123")
        self.assertFalse(result["state"]["accounts"][0]["comp"])


if __name__ == "__main__":
    unittest.main()
