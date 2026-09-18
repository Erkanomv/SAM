import unittest

import httpx

from steam_tracker.steam_api import SteamApi, SteamPrivateDataError


PROFILE_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<profile>
  <steamID64>76561198000000000</steamID64>
  <steamID><![CDATA[Test User]]></steamID>
  <onlineState>online</onlineState>
  <avatarMedium>https://example/avatar_medium.jpg</avatarMedium>
  <avatarFull>https://example/avatar_full.jpg</avatarFull>
</profile>
'''

GAMES_XML = b'''<?xml version="1.0" encoding="UTF-8"?>
<gamesList>
  <steamID64>76561198000000000</steamID64>
  <games>
    <game>
      <appID>730</appID>
      <name><![CDATA[Counter-Strike 2]]></name>
      <logo><![CDATA[https://media.steampowered.com/steamcommunity/public/images/apps/730/abc123.jpg]]></logo>
      <hoursOnRecord>123.4</hoursOnRecord>
    </game>
    <game>
      <appID>252490</appID>
      <name><![CDATA[Rust]]></name>
      <hoursOnRecord>50</hoursOnRecord>
    </game>
  </games>
</gamesList>
'''


class SteamApiTests(unittest.TestCase):
    def make_api(self):
        return SteamApi(lambda: "")

    def test_normalize_key_extracts_key_from_pasted_text(self):
        raw = "Steam key: 0123456789abcdef0123456789ABCDEF"
        self.assertEqual(
            SteamApi.normalize_key(raw),
            "0123456789ABCDEF0123456789ABCDEF",
        )

    def test_public_profile_parser(self):
        api = self.make_api()

        def fake_request(url, *, params=None, timeout=None):
            request = httpx.Request("GET", url, params=params)
            return httpx.Response(200, content=PROFILE_XML, request=request)

        api._request = fake_request
        profile = api.get_public_profile("76561198000000000")
        self.assertEqual(profile["personaname"], "Test User")
        self.assertEqual(profile["personastate"], 1)
        self.assertEqual(profile["avatarfull"], "https://example/avatar_full.jpg")

    def test_public_games_parser(self):
        api = self.make_api()

        def fake_request(url, *, params=None, timeout=None):
            request = httpx.Request("GET", url, params=params)
            return httpx.Response(200, content=GAMES_XML, request=request)

        api._request = fake_request
        games = api.get_public_games("76561198000000000")
        self.assertEqual(len(games), 2)
        self.assertEqual(games[0]["appid"], 730)
        self.assertEqual(games[0]["playtime_forever"], 7404)
        self.assertEqual(games[0]["img_icon_url"], "abc123")

    def test_private_games_redirect_does_not_look_like_empty_library(self):
        api = self.make_api()

        def fake_request(url, *, params=None, timeout=None):
            request = httpx.Request("GET", "https://steamcommunity.com/login/?redir=x")
            return httpx.Response(200, text="<html>login</html>", request=request)

        api._request = fake_request
        with self.assertRaises(SteamPrivateDataError):
            api.get_public_games("76561198000000000")


if __name__ == "__main__":
    unittest.main()
