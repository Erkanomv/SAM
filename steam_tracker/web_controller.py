from __future__ import annotations

import json
import math
import os
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pyperclip

from .openid import SteamOpenId
from .steam_api import SteamApiError, SteamPrivateDataError
from .steam_client import (
    BulkCredential,
    find_steam_exe,
    parse_bulk_credentials,
    switch_account,
    wait_for_account_login,
)


class WebController:
    PROFILE_TTL = 10 * 60
    GAMES_TTL = 12 * 60 * 60

    def __init__(self, db, secrets, api):
        self.db = db
        self.secrets = secrets
        self.api = api
        self._window = None
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._startup_started = False
        self._is_maximized = False
        self._bulk_lock = threading.RLock()
        self._bulk_pending: list[BulkCredential] = []
        self._bulk_selection: dict[str, Any] = {}
        self._bulk_cancel = threading.Event()
        self._bulk_thread: threading.Thread | None = None
        self._bulk_status: dict[str, Any] = {
            "active": False,
            "phase": "idle",
            "total": 0,
            "currentIndex": -1,
            "currentUsername": "",
            "success": 0,
            "failed": 0,
            "cancelled": False,
            "results": [],
        }
        self.openid = SteamOpenId(self._on_openid_authenticated, self._on_openid_failed)

    def attach_window(self, window) -> None:
        self._window = window
        window.events.maximized += self._on_maximized
        window.events.restored += self._on_restored

    def _on_maximized(self):
        self._is_maximized = True
        self._push("window-state", {"maximized": True})

    def _on_restored(self):
        self._is_maximized = False
        self._push("window-state", {"maximized": False})

    # ---------- bridge helpers ----------

    def _push(self, event: str, payload: Any = None) -> None:
        if not self._window:
            return
        try:
            event_json = json.dumps(event, ensure_ascii=False)
            payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            self._window.run_js(f"window.Native?.onEvent({event_json},{payload_json});")
        except Exception:
            pass

    def _toast(self, message: str, kind: str = "info") -> None:
        self._push("toast", {"message": message, "kind": kind})

    @staticmethod
    def _remaining_text(seconds: int) -> str:
        if seconds <= 0:
            return ""
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        if days:
            return f"{days}d {hours}h {minutes}m"
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def _bulk_status_snapshot(self) -> dict[str, Any]:
        with self._bulk_lock:
            status = dict(self._bulk_status)
            status["results"] = [dict(item) for item in self._bulk_status.get("results", [])]
            if self._bulk_selection:
                status["selection"] = {
                    "filename": self._bulk_selection.get("filename", ""),
                    "count": int(self._bulk_selection.get("count", 0) or 0),
                    "usernames": list(self._bulk_selection.get("usernames", [])),
                    "issues": list(self._bulk_selection.get("issues", [])),
                }
            else:
                status["selection"] = None
            return status

    def _push_bulk_status(self) -> None:
        self._push("bulk-status", self._bulk_status_snapshot())

    def _set_bulk_status(self, **changes: Any) -> dict[str, Any]:
        with self._bulk_lock:
            self._bulk_status.update(changes)
        snapshot = self._bulk_status_snapshot()
        self._push("bulk-status", snapshot)
        return snapshot

    def _set_bulk_result(self, index: int, *, status: str, message: str = "", steam_id: str = "") -> None:
        with self._bulk_lock:
            results = self._bulk_status.get("results", [])
            if 0 <= index < len(results):
                results[index].update({"status": status, "message": message, "steamId": steam_id})
        self._push_bulk_status()

    def _serialize_account(self, row: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        until = int(row.get("vcbnd_until") or 0)
        active = until > now
        games = row.get("top_games", []) or []
        top = games[0] if games else {}
        return {
            "steamId": str(row.get("steam_id", "")),
            "personaName": str(row.get("persona_name") or row.get("steam_id") or "Steam account"),
            "avatarUrl": str(row.get("avatar_url") or ""),
            "profileUrl": str(row.get("profile_url") or ""),
            "personaState": int(row.get("persona_state") or 0),
            "steamLevel": row.get("steam_level") if row.get("steam_level") is not None else -1,
            "loginUsername": str(row.get("login_username") or ""),
            "hasPassword": bool(row.get("has_password", 0)),
            "vcbnd": active,
            "vcbndUntil": until if active else 0,
            "remainingText": self._remaining_text(until - now) if active else "",
            "favorite": bool(row.get("favorite", 0)),
            "comp": bool(row.get("comp", 0)),
            "topGames": games,
            "topGameName": str(top.get("name") or "No game data"),
            "topGameHours": float(top.get("hours") or 0),
            "totalHours": round(int(row.get("total_playtime_minutes", 0) or 0) / 60.0, 1),
            "gameCount": int(row.get("game_count", 0) or 0),
            "dateAdded": int(row.get("date_added", 0) or 0),
            "lastProfileSync": int(row.get("last_profile_sync", 0) or 0),
            "lastGamesSync": int(row.get("last_games_sync", 0) or 0),
        }

    def _state(self) -> dict[str, Any]:
        rows = self.db.list_accounts()
        now = int(time.time())
        expired = [r["steam_id"] for r in rows if int(r.get("vcbnd_until") or 0) and int(r.get("vcbnd_until") or 0) <= now]
        if expired:
            for sid in expired:
                self.db.set_timer(sid, None)
            rows = self.db.list_accounts()
        accounts = [self._serialize_account(r) for r in rows]
        try:
            steam_path = str(find_steam_exe())
        except Exception:
            steam_path = ""
        return {
            "version": "0.5.1",
            "accounts": accounts,
            "apiKeyConfigured": bool(self.secrets.get_api_key()),
            "dataModeText": "Web API key configured" if self.api.has_key() else "Public Steam data",
            "steamInstalled": bool(steam_path),
            "steamPath": steam_path,
            "bulkLoginActive": bool(self._bulk_status_snapshot().get("active")),
            "now": now,
        }

    # ---------- public JS API ----------

    def get_state(self):
        with self._lock:
            return self._state()

    def startup_refresh(self):
        with self._lock:
            if self._startup_started:
                return {"ok": True}
            self._startup_started = True
        threading.Thread(target=self._startup_refresh_worker, daemon=True).start()
        return {"ok": True}

    def add_account(self):
        if self.openid.begin():
            return {"ok": True, "message": "Steam sign-in opened in your browser."}
        return {"ok": False, "message": "A Steam sign-in is already in progress."}

    def choose_bulk_login_file(self):
        if not self._window:
            return {"ok": False, "message": "The app window is not ready yet."}
        with self._bulk_lock:
            if self._bulk_status.get("active"):
                return {"ok": False, "message": "A bulk login queue is already running.", "bulk": self._bulk_status_snapshot()}

        try:
            import webview
            dialog_enum = getattr(webview, "FileDialog", None)
            if dialog_enum is not None:
                dialog_type = getattr(dialog_enum, "LOAD", None) or getattr(dialog_enum, "OPEN", None)
            else:
                dialog_type = getattr(webview, "OPEN_DIALOG", None)
            if dialog_type is None:
                raise RuntimeError("This pywebview build does not expose an open-file dialog.")
            selected = self._window.create_file_dialog(
                dialog_type,
                allow_multiple=False,
                file_types=("Text files (*.txt)", "All files (*.*)"),
            )
        except Exception as exc:
            return {"ok": False, "message": f"Could not open the file picker: {exc}"}

        if not selected:
            return {"ok": False, "cancelled": True, "message": "No file selected."}

        selected_path = selected if isinstance(selected, (str, Path)) else selected[0]
        path = Path(selected_path)
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                return {"ok": False, "message": "That file is too large. Use a plain text credential list under 2 MB."}
            raw = path.read_bytes()
            if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                text = raw.decode("utf-16")
            else:
                try:
                    text = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    text = raw.decode("cp1252")
        except OSError as exc:
            return {"ok": False, "message": f"Could not read the selected file: {exc}"}

        credentials, issues = parse_bulk_credentials(text)
        if not credentials:
            return {
                "ok": False,
                "message": "No valid User:Password lines were found.",
                "issues": issues[:30],
            }

        usernames = [entry.username for entry in credentials]
        with self._bulk_lock:
            self._bulk_pending = credentials
            self._bulk_selection = {
                "filename": path.name,
                "count": len(credentials),
                "usernames": usernames,
                "issues": issues[:30],
            }
            if not self._bulk_status.get("active"):
                self._bulk_status = {
                    "active": False,
                    "phase": "ready",
                    "total": len(credentials),
                    "currentIndex": -1,
                    "currentUsername": "",
                    "success": 0,
                    "failed": 0,
                    "cancelled": False,
                    "results": [
                        {"username": name, "status": "pending", "message": "", "steamId": ""}
                        for name in usernames
                    ],
                }
        snapshot = self._bulk_status_snapshot()
        self._push("bulk-status", snapshot)
        return {"ok": True, "message": f"Loaded {len(credentials)} account(s).", "bulk": snapshot}

    def get_bulk_login_status(self):
        return self._bulk_status_snapshot()

    def clear_bulk_login_selection(self):
        with self._bulk_lock:
            if self._bulk_status.get("active"):
                return {"ok": False, "message": "The bulk login queue is currently running."}
            self._bulk_pending = []
            self._bulk_selection = {}
            self._bulk_status = {
                "active": False, "phase": "idle", "total": 0, "currentIndex": -1,
                "currentUsername": "", "success": 0, "failed": 0, "cancelled": False, "results": [],
            }
        self._push_bulk_status()
        return {"ok": True, "bulk": self._bulk_status_snapshot()}

    def start_bulk_login(self, store_passwords: bool = True):
        if os.name != "nt":
            return {"ok": False, "message": "Bulk Steam login is supported on Windows only."}
        try:
            find_steam_exe()
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

        with self._bulk_lock:
            if self._bulk_status.get("active"):
                return {"ok": False, "message": "A bulk login queue is already running.", "bulk": self._bulk_status_snapshot()}
            if not self._bulk_pending:
                return {"ok": False, "message": "Choose a User:Password .txt file first."}
            credentials = list(self._bulk_pending)
            self._bulk_cancel = threading.Event()
            self._bulk_status = {
                "active": True,
                "phase": "starting",
                "total": len(credentials),
                "currentIndex": -1,
                "currentUsername": "",
                "success": 0,
                "failed": 0,
                "cancelled": False,
                "results": [
                    {"username": entry.username, "status": "pending", "message": "", "steamId": ""}
                    for entry in credentials
                ],
            }
            thread = threading.Thread(
                target=self._bulk_login_worker,
                args=(credentials, bool(store_passwords), self._bulk_cancel),
                daemon=True,
                name="steam-bulk-login",
            )
            self._bulk_thread = thread
            thread.start()
        snapshot = self._bulk_status_snapshot()
        self._push("bulk-status", snapshot)
        return {"ok": True, "message": f"Bulk login started for {len(credentials)} account(s).", "bulk": snapshot}

    def cancel_bulk_login(self):
        with self._bulk_lock:
            if not self._bulk_status.get("active"):
                return {"ok": False, "message": "No bulk login queue is running.", "bulk": self._bulk_status_snapshot()}
            self._bulk_cancel.set()
            self._bulk_status["phase"] = "cancelling"
        self._push_bulk_status()
        return {"ok": True, "message": "Stopping after the current Steam attempt…", "bulk": self._bulk_status_snapshot()}

    def refresh_all(self):
        if not self._refresh_lock.acquire(blocking=False):
            return {"ok": False, "message": "A refresh is already running.", "state": self._state()}
        try:
            ids = [x["steam_id"] for x in self.db.list_accounts()]
            if not ids:
                return {"ok": True, "message": "Nothing to refresh.", "state": self._state()}
            self._refresh_profile_batch(ids)
            now = int(time.time())
            stale = [
                row["steam_id"] for row in self.db.list_accounts()
                if now - int(row.get("last_games_sync") or 0) > self.GAMES_TTL
            ]
            if stale:
                with ThreadPoolExecutor(max_workers=6, thread_name_prefix="steam-games") as executor:
                    futures = {executor.submit(self._fetch_details_only, sid): sid for sid in stale}
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception:
                            pass
            return {"ok": True, "message": "Accounts refreshed.", "state": self._state()}
        finally:
            self._refresh_lock.release()

    def refresh_account(self, steam_id: str):
        try:
            result = self._fetch_full_account(str(steam_id))
            notice = result.get("notice") or ""
            message = "Account refreshed." if not notice else f"Account refreshed. {notice} Cached game data was kept."
            return {"ok": True, "message": message, "state": self._state()}
        except Exception as exc:
            return {"ok": False, "message": str(exc), "state": self._state()}

    def set_timer(self, steam_id: str, days_text: str):
        text = (days_text or "").strip().replace(",", ".")
        try:
            days = float(text)
        except ValueError:
            return {"ok": False, "message": "Enter a number of days, e.g. 7 or 2.5."}
        if not math.isfinite(days) or days <= 0 or days > 3650:
            return {"ok": False, "message": "Timer must be greater than 0 and at most 3650 days."}
        self.db.set_timer(str(steam_id), int(time.time() + days * 86400))
        return {"ok": True, "message": f"VCBND set for {days:g} day(s).", "state": self._state()}

    def clear_timer(self, steam_id: str):
        self.db.set_timer(str(steam_id), None)
        return {"ok": True, "message": "Timer cleared — account is UNBND.", "state": self._state()}

    def toggle_favorite(self, steam_id: str):
        row = self.db.get_account(str(steam_id))
        if not row:
            return {"ok": False, "message": "Account not found."}
        self.db.set_favorite(str(steam_id), not bool(row.get("favorite", 0)))
        return {"ok": True, "state": self._state()}

    def toggle_comp(self, steam_id: str):
        row = self.db.get_account(str(steam_id))
        if not row:
            return {"ok": False, "message": "Account not found."}
        enabled = not bool(row.get("comp", 0))
        self.db.set_comp(str(steam_id), enabled)
        return {
            "ok": True,
            "message": "Account marked COMP." if enabled else "COMP cleared.",
            "state": self._state(),
        }

    def save_credentials(self, steam_id: str, username: str, password: str, store_password: bool):
        steam_id = str(steam_id)
        username = (username or "").strip()
        if not username:
            return {"ok": False, "message": "Enter the Steam login/account name."}
        self.db.set_login_username(steam_id, username)
        try:
            if password:
                if store_password:
                    self.secrets.set_password(steam_id, password)
                    self.db.set_has_password(steam_id, True)
                else:
                    self.secrets.delete_password(steam_id)
                    self.db.set_has_password(steam_id, False)
            elif not store_password:
                self.secrets.delete_password(steam_id)
                self.db.set_has_password(steam_id, False)
        except Exception as exc:
            self.db.set_has_password(steam_id, False)
            return {"ok": False, "message": f"Windows Credential Manager error: {exc}"}
        return {"ok": True, "message": "Login details saved.", "state": self._state()}

    def forget_password(self, steam_id: str):
        try:
            self.secrets.delete_password(str(steam_id))
            self.db.set_has_password(str(steam_id), False)
            return {"ok": True, "message": "Stored password removed.", "state": self._state()}
        except Exception as exc:
            return {"ok": False, "message": f"Could not remove stored password: {exc}"}

    def login_account(self, steam_id: str):
        row = self.db.get_account(str(steam_id))
        if not row:
            return {"ok": False, "message": "Account not found."}
        username = str(row.get("login_username") or "")
        try:
            password = self.secrets.get_password(str(steam_id))
        except Exception:
            password = ""
        if not username or not password:
            if bool(row.get("has_password", 0)) and not password:
                self.db.set_has_password(str(steam_id), False)
            return {
                "ok": False,
                "needsCredentials": True,
                "message": "Add the Steam login name and a stored password first.",
                "state": self._state(),
            }
        try:
            switch_account(username, password)
            return {"ok": True, "message": f"Switching Steam to {row.get('persona_name') or username}. Steam Guard may still be required."}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def save_api_key(self, raw_key: str):
        raw_key = (raw_key or "").strip()
        if not raw_key:
            return {"ok": False, "message": "Paste a Steam Web API key first."}
        rows = self.db.list_accounts()
        probe_id = str(rows[0]["steam_id"]) if rows else ""
        try:
            key = self.api.validate_key(raw_key, probe_id)
            self.secrets.set_api_key(key)
            return {"ok": True, "message": "API key validated and saved.", "state": self._state()}
        except Exception as exc:
            return {"ok": False, "message": f"API key not saved: {exc}"}

    def clear_api_key(self):
        try:
            self.secrets.delete_api_key()
            return {"ok": True, "message": "API key removed. Public Steam data remains available.", "state": self._state()}
        except Exception as exc:
            return {"ok": False, "message": f"Could not remove the API key: {exc}"}

    def open_api_key_page(self):
        webbrowser.open("https://steamcommunity.com/dev/apikey")
        return {"ok": True}

    def open_profile(self, steam_id: str):
        row = self.db.get_account(str(steam_id))
        url = (row or {}).get("profile_url") or f"https://steamcommunity.com/profiles/{steam_id}"
        webbrowser.open(str(url))
        return {"ok": True}

    def copy_steam_id(self, steam_id: str):
        try:
            pyperclip.copy(str(steam_id))
            return {"ok": True, "message": "SteamID copied."}
        except Exception as exc:
            return {"ok": False, "message": f"Could not copy SteamID: {exc}"}

    def delete_account(self, steam_id: str):
        steam_id = str(steam_id)
        try:
            self.secrets.delete_password(steam_id)
        except Exception:
            pass
        self.db.delete_account(steam_id)
        return {"ok": True, "message": "Account removed from the tracker.", "state": self._state()}

    def window_action(self, action: str):
        if not self._window:
            return False
        action = str(action or "").lower()
        if action == "minimize":
            self._window.minimize()
        elif action == "maximize":
            if self._is_maximized:
                self._window.restore()
            else:
                self._window.maximize()
        elif action == "close":
            self._window.destroy()
        else:
            return False
        return True

    # ---------- bulk local-login queue ----------

    def _bulk_login_worker(self, credentials: list[BulkCredential], store_passwords: bool, cancel_event: threading.Event) -> None:
        imported_ids: list[str] = []
        success = 0
        failed = 0
        total = len(credentials)

        try:
            for index, credential in enumerate(credentials):
                if cancel_event.is_set():
                    break

                username = credential.username
                existing = self.db.find_account_by_login_username(username)
                expected_sid = str(existing.get("steam_id") or "") if existing else ""
                self._set_bulk_status(
                    active=True, phase="switching", currentIndex=index, currentUsername=username,
                    success=success, failed=failed, cancelled=False,
                )
                self._set_bulk_result(index, status="running", message="Closing Steam and launching this account…")

                try:
                    switch_account(username, credential.password)
                    if cancel_event.is_set():
                        self._set_bulk_result(index, status="cancelled", message="Queue cancelled.")
                        break

                    self._set_bulk_status(phase="waiting")
                    self._set_bulk_result(index, status="running", message="Waiting for Steam to confirm the active account…")
                    local_user = wait_for_account_login(
                        username, timeout=55.0, cancel_event=cancel_event, expected_steam_id=expected_sid
                    )
                    if cancel_event.is_set():
                        self._set_bulk_result(index, status="cancelled", message="Queue cancelled.")
                        break
                    if local_user is None:
                        failed += 1
                        self._set_bulk_result(
                            index,
                            status="failed",
                            message="Steam did not confirm this login within 55 seconds. Check the credentials or Steam client.",
                        )
                        self._set_bulk_status(success=success, failed=failed)
                        continue

                    steam_id = str(local_user.steam_id)
                    persona_name = (local_user.persona_name or username).strip() or username
                    self.db.upsert_account(
                        steam_id,
                        persona_name=persona_name,
                        login_username=username,
                    )

                    password_note = ""
                    if store_passwords:
                        try:
                            self.secrets.set_password(steam_id, credential.password)
                            self.db.set_has_password(steam_id, True)
                        except Exception:
                            self.db.set_has_password(steam_id, False)
                            password_note = " Login succeeded, but Windows Credential Manager could not save the password."

                    imported_ids.append(steam_id)
                    success += 1
                    self._set_bulk_result(
                        index,
                        status="success",
                        steam_id=steam_id,
                        message=f"Signed in and added as SteamID {steam_id}.{password_note}",
                    )
                    self._set_bulk_status(success=success, failed=failed, phase="added")
                    self._push("state", self._state())

                    if index + 1 < total and not cancel_event.wait(1.25):
                        pass
                except Exception as exc:
                    failed += 1
                    self._set_bulk_result(index, status="failed", message=str(exc))
                    self._set_bulk_status(success=success, failed=failed)

            cancelled = cancel_event.is_set()
            if cancelled:
                with self._bulk_lock:
                    for item in self._bulk_status.get("results", []):
                        if item.get("status") == "pending":
                            item.update(status="cancelled", message="Not attempted.")

            self._set_bulk_status(
                active=False,
                phase="cancelled" if cancelled else "complete",
                currentUsername="",
                success=success,
                failed=failed,
                cancelled=cancelled,
            )

            if imported_ids:
                unique_ids = list(dict.fromkeys(imported_ids))
                threading.Thread(
                    target=self._refresh_bulk_imports_worker,
                    args=(unique_ids,),
                    daemon=True,
                    name="steam-bulk-refresh",
                ).start()

            if cancelled:
                self._toast(f"Bulk login stopped: {success} added, {failed} failed.", "info")
            elif failed:
                self._toast(f"Bulk login finished: {success} added, {failed} failed.", "info")
            else:
                self._toast(f"Bulk login finished: {success} account(s) added.", "success")
        finally:
            with self._bulk_lock:
                self._bulk_pending = []
                self._bulk_thread = None

    def _refresh_bulk_imports_worker(self, steam_ids: list[str]) -> None:
        try:
            self._refresh_profile_batch(steam_ids)
            self._push("state", self._state())
            with ThreadPoolExecutor(max_workers=6, thread_name_prefix="steam-bulk-details") as executor:
                futures = [executor.submit(self._fetch_details_only, sid) for sid in steam_ids]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception:
                        pass
            self._push("state", self._state())
        except Exception:
            pass

    # ---------- Steam refresh internals ----------

    def _startup_refresh_worker(self):
        try:
            rows = self.db.list_accounts()
            if not rows:
                return
            now = int(time.time())
            ids = [r["steam_id"] for r in rows if now - int(r.get("last_profile_sync") or 0) > self.PROFILE_TTL]
            if ids:
                self._refresh_profile_batch(ids)
                self._push("state", self._state())
            stale = [r["steam_id"] for r in self.db.list_accounts() if now - int(r.get("last_games_sync") or 0) > self.GAMES_TTL]
            if stale:
                with ThreadPoolExecutor(max_workers=6, thread_name_prefix="steam-startup") as executor:
                    futures = [executor.submit(self._fetch_details_only, sid) for sid in stale]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception:
                            pass
                self._push("state", self._state())
        except Exception:
            pass

    def _on_openid_authenticated(self, steam_id: str):
        try:
            is_new = self.db.get_account(steam_id) is None
            self.db.upsert_account(steam_id)
            self._push("state", self._state())
            self._toast("Steam account linked. Loading profile and most-played games…")
            self._fetch_full_account(steam_id)
            self._push("state", self._state())
            self._toast("Account ready." if is_new else "Account refreshed.", "success")
        except Exception as exc:
            self._toast(str(exc), "error")

    def _on_openid_failed(self, message: str):
        self._toast(message, "error")

    def _save_profile(self, steam_id: str, player: dict[str, Any]):
        self.db.upsert_account(
            steam_id,
            persona_name=str(player.get("personaname", "") or ""),
            avatar_url=str(player.get("avatarfull", "") or player.get("avatarmedium", "") or ""),
            profile_url=str(player.get("profileurl", "") or ""),
            persona_state=int(player.get("personastate", 0) or 0),
            last_profile_sync=int(time.time()),
        )

    def _refresh_profile_batch(self, ids: list[str]):
        players: dict[str, dict] = {}
        if self.api.has_key():
            try:
                players = self.api.get_player_summaries_api(ids)
            except SteamApiError:
                players = {}

        missing = [sid for sid in ids if sid not in players]
        if missing:
            with ThreadPoolExecutor(max_workers=6, thread_name_prefix="steam-profile") as executor:
                futures = {executor.submit(self.api.get_public_profile, sid): sid for sid in missing}
                for future in as_completed(futures):
                    sid = futures[future]
                    try:
                        players[sid] = future.result()
                    except SteamApiError:
                        continue

        for sid in ids:
            player = players.get(sid)
            if player:
                self._save_profile(sid, player)
        return ids

    def _fetch_details_only(self, steam_id: str):
        notice = ""
        try:
            games = self.api.get_owned_games(steam_id)
            self.db.replace_games(steam_id, games)
        except SteamPrivateDataError as exc:
            notice = str(exc)

        try:
            level = self.api.get_steam_level(steam_id)
            if level is not None:
                self.db.upsert_account(steam_id, steam_level=level)
        except SteamApiError:
            pass
        return {"steam_id": steam_id, "notice": notice}

    def _fetch_full_account(self, steam_id: str):
        players = self.api.get_player_summaries([steam_id])
        player = players.get(steam_id)
        if player:
            self._save_profile(steam_id, player)
        return self._fetch_details_only(steam_id)
