from __future__ import annotations

import keyring

SERVICE = "SteamAccountTracker"
API_KEY_USER = "steam_web_api_key"


class SecretStore:
    """Small wrapper around the OS credential backend.

    Failing to read Windows Credential Manager must never prevent the tracker UI
    from starting; the app can still link accounts and use public Steam data.
    Writes intentionally propagate so the controller can show the real error.
    """

    def __init__(self):
        try:
            self._api_key = keyring.get_password(SERVICE, API_KEY_USER) or ""
        except Exception:
            self._api_key = ""

    def get_api_key(self) -> str:
        return self._api_key

    def set_api_key(self, key: str) -> None:
        key = key.strip()
        if key:
            keyring.set_password(SERVICE, API_KEY_USER, key)
            self._api_key = key
        else:
            self.delete_api_key()

    def delete_api_key(self) -> None:
        try:
            keyring.delete_password(SERVICE, API_KEY_USER)
        except keyring.errors.PasswordDeleteError:
            pass
        self._api_key = ""

    @staticmethod
    def _password_user(steam_id: str) -> str:
        return f"steam_password:{steam_id}"

    def get_password(self, steam_id: str) -> str:
        return keyring.get_password(SERVICE, self._password_user(steam_id)) or ""

    def set_password(self, steam_id: str, password: str) -> None:
        if password:
            keyring.set_password(SERVICE, self._password_user(steam_id), password)
        else:
            self.delete_password(steam_id)

    def delete_password(self, steam_id: str) -> None:
        try:
            keyring.delete_password(SERVICE, self._password_user(steam_id))
        except keyring.errors.PasswordDeleteError:
            pass
