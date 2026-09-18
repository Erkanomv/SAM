from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Iterable
from urllib.parse import urlparse

import httpx


class SteamApiError(RuntimeError):
    pass


class SteamPrivateDataError(SteamApiError):
    """Raised when Steam intentionally does not expose a user's game details."""


_KEY_RE = re.compile(r"(?i)\b([0-9a-f]{32})\b")


class SteamApi:
    """Steam data access with an API-key fast path and keyless public fallback.

    The app deliberately does *not* require a Web API key. Steam OpenID gives us a
    SteamID, then public profile/game data can be read from Steam Community's XML
    endpoints. Valve marks those XML endpoints as deprecated, so a valid Web API key
    is still useful for faster batched profile refreshes and Steam level data.
    """

    BASE = "https://api.steampowered.com"
    COMMUNITY = "https://steamcommunity.com"

    def __init__(self, key_provider):
        self._key_provider = key_provider
        self._client = httpx.Client(
            timeout=httpx.Timeout(16.0, connect=8.0),
            headers={
                "User-Agent": "SAM/0.5.1 (+Windows desktop app)",
                "Accept-Language": "en-US,en;q=0.8",
            },
            follow_redirects=True,
        )

    @staticmethod
    def normalize_key(value: str) -> str:
        """Extract a normal 32-character Steam Web API key from pasted text."""
        text = (value or "").strip()
        if not text:
            return ""
        match = _KEY_RE.search(text)
        if match:
            return match.group(1).upper()
        return text.replace(" ", "").upper()

    def _key(self, required: bool = True) -> str:
        key = self.normalize_key(self._key_provider() or "")
        if required and not key:
            raise SteamApiError("Steam Web API key is not configured.")
        return key

    def has_key(self) -> bool:
        return bool(self._key(required=False))

    def _request(
        self,
        url: str,
        *,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        try:
            response = self._client.get(url, params=params, timeout=timeout or 16.0)
        except httpx.HTTPError as exc:
            raise SteamApiError(f"Network error: {exc}") from exc
        return response

    @staticmethod
    def _http_error(response: httpx.Response, context: str) -> SteamApiError:
        body = (response.text or "").strip().replace("\n", " ")[:180]
        suffix = f" — {body}" if body else ""
        return SteamApiError(f"{context}: HTTP {response.status_code}{suffix}")

    def _api_get(self, path: str, params: dict, *, key: str | None = None) -> dict:
        request_params = dict(params)
        request_params["key"] = self.normalize_key(key or self._key())
        response = self._request(f"{self.BASE}{path}", params=request_params)
        if response.status_code in (401, 403):
            raise SteamApiError(
                "Steam rejected the Web API key. Remove it or paste a valid 32-character key."
            )
        if response.status_code >= 400:
            raise self._http_error(response, "Steam Web API request failed")
        try:
            return response.json()
        except ValueError as exc:
            raise SteamApiError("Steam Web API returned an invalid response.") from exc

    def validate_key(self, raw_key: str, probe_steam_id: str = "") -> str:
        """Validate and return the normalized key without saving it."""
        key = self.normalize_key(raw_key)
        if not re.fullmatch(r"[0-9A-F]{32}", key):
            raise SteamApiError("Steam Web API keys are 32 hexadecimal characters.")

        if probe_steam_id:
            data = self._api_get(
                "/ISteamUser/GetPlayerSummaries/v2/",
                {"steamids": str(probe_steam_id)},
                key=key,
            )
            if "response" not in data:
                raise SteamApiError("Steam returned an unexpected response while validating the key.")
            return key

        response = self._request(
            f"{self.BASE}/ISteamWebAPIUtil/GetSupportedAPIList/v1/",
            params={"key": key},
        )
        if response.status_code in (401, 403):
            raise SteamApiError("Steam rejected that API key (401/403).")
        if response.status_code >= 400:
            raise self._http_error(response, "Could not validate the Steam API key")
        try:
            response.json()
        except ValueError as exc:
            raise SteamApiError("Steam returned an unexpected response while validating the key.") from exc
        return key

    def get_player_summaries_api(self, steam_ids: list[str]) -> dict[str, dict]:
        if not steam_ids:
            return {}
        result: dict[str, dict] = {}
        for i in range(0, len(steam_ids), 100):
            chunk = steam_ids[i:i + 100]
            data = self._api_get(
                "/ISteamUser/GetPlayerSummaries/v2/",
                {"steamids": ",".join(chunk)},
            )
            for player in data.get("response", {}).get("players", []):
                sid = str(player.get("steamid", ""))
                if sid:
                    result[sid] = player
        return result

    def get_owned_games_api(self, steam_id: str) -> list[dict]:
        data = self._api_get(
            "/IPlayerService/GetOwnedGames/v1/",
            {
                "steamid": steam_id,
                "include_appinfo": 1,
                "include_played_free_games": 1,
                "skip_unvetted_apps": 0,
                "format": "json",
            },
        )
        response = data.get("response", {}) or {}
        if "games" not in response and "game_count" not in response:
            raise SteamPrivateDataError(
                "Steam game details are private or unavailable for this account."
            )
        return response.get("games", []) or []

    def get_steam_level_api(self, steam_id: str) -> int | None:
        data = self._api_get("/IPlayerService/GetSteamLevel/v1/", {"steamid": steam_id})
        level = data.get("response", {}).get("player_level")
        return int(level) if level is not None else None

    @staticmethod
    def _xml_text(root: ET.Element, name: str, default: str = "") -> str:
        node = root.find(name)
        if node is None or node.text is None:
            return default
        return node.text.strip()

    def get_public_profile(self, steam_id: str) -> dict:
        response = self._request(f"{self.COMMUNITY}/profiles/{steam_id}/", params={"xml": 1})
        if response.status_code >= 400:
            raise self._http_error(response, "Steam Community profile request failed")
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise SteamApiError("Steam Community did not return profile XML.") from exc

        if root.tag != "profile":
            raise SteamApiError("Steam Community returned an unexpected profile response.")
        error = self._xml_text(root, "error")
        if error:
            raise SteamApiError(error)

        online = self._xml_text(root, "onlineState", "offline").lower()
        personastate = 0 if online == "offline" else 1
        return {
            "steamid": steam_id,
            "personaname": self._xml_text(root, "steamID", steam_id),
            "avatarfull": self._xml_text(root, "avatarFull"),
            "avatarmedium": self._xml_text(root, "avatarMedium"),
            "profileurl": f"{self.COMMUNITY}/profiles/{steam_id}/",
            "personastate": personastate,
        }

    @staticmethod
    def _icon_hash_from_logo(logo_url: str) -> str:
        try:
            name = urlparse(logo_url).path.rsplit("/", 1)[-1]
            return name.rsplit(".", 1)[0]
        except Exception:
            return ""

    def get_public_games(self, steam_id: str) -> list[dict]:
        response = self._request(
            f"{self.COMMUNITY}/profiles/{steam_id}/games/",
            params={"tab": "all", "xml": 1},
            timeout=35.0,
        )
        if "/login" in str(response.url):
            raise SteamPrivateDataError(
                "Steam game details are private. Set Game details to Public to show playtime."
            )
        if response.status_code >= 400:
            raise self._http_error(response, "Steam Community games request failed")
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise SteamPrivateDataError(
                "Steam did not expose this account's public game list."
            ) from exc

        if root.tag not in {"gamesList", "games"}:
            error = self._xml_text(root, "error")
            if error:
                raise SteamPrivateDataError(error)
            raise SteamApiError("Steam Community returned an unexpected games response.")

        game_nodes: Iterable[ET.Element]
        if root.tag == "gamesList":
            games_parent = root.find("games")
            game_nodes = games_parent.findall("game") if games_parent is not None else []
        else:
            game_nodes = root.findall("game")

        out: list[dict] = []
        for game in game_nodes:
            appid_text = self._xml_text(game, "appID")
            try:
                appid = int(appid_text)
            except (TypeError, ValueError):
                continue
            hours_text = self._xml_text(game, "hoursOnRecord", "0").replace(",", "")
            try:
                hours = float(hours_text or 0)
            except ValueError:
                hours = 0.0
            logo = self._xml_text(game, "logo")
            out.append(
                {
                    "appid": appid,
                    "name": self._xml_text(game, "name", f"App {appid}"),
                    "playtime_forever": max(0, int(round(hours * 60))),
                    "img_icon_url": self._icon_hash_from_logo(logo),
                }
            )
        return out

    def get_player_summaries(self, steam_ids: list[str]) -> dict[str, dict]:
        if not steam_ids:
            return {}
        if self.has_key():
            try:
                return self.get_player_summaries_api(steam_ids)
            except SteamApiError:
                pass

        result: dict[str, dict] = {}
        for sid in steam_ids:
            try:
                result[sid] = self.get_public_profile(sid)
            except SteamApiError:
                continue
        return result

    def get_owned_games(self, steam_id: str) -> list[dict]:
        if self.has_key():
            try:
                return self.get_owned_games_api(steam_id)
            except SteamPrivateDataError:
                raise
            except SteamApiError:
                pass
        return self.get_public_games(steam_id)

    def get_steam_level(self, steam_id: str) -> int | None:
        if not self.has_key():
            return None
        return self.get_steam_level_api(steam_id)
