from __future__ import annotations

import os
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import webview

from .db import Database
from .secrets import SecretStore
from .steam_api import SteamApi
from .web_controller import WebController


def _data_dir() -> Path:
    """Keep the same Windows data location used by the old Qt build."""
    roaming = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    candidates = [
        roaming / "Local" / "SteamAccountTracker",
        roaming / "SteamAccountTracker",
        Path(os.environ.get("LOCALAPPDATA", roaming)) / "SteamAccountTracker",
    ]
    for candidate in candidates:
        if (candidate / "tracker.sqlite3").exists():
            return candidate
    return candidates[0]


def _resource_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    bundled = base / "steam_tracker" / "web"
    if bundled.exists():
        return bundled
    return Path(__file__).resolve().parent / "web"


class WebApiBridge:
    __slots__ = ("_controller",)

    def __init__(self, controller: WebController):
        self._controller = controller

    def get_state(self): return self._controller.get_state()
    def startup_refresh(self): return self._controller.startup_refresh()
    def add_account(self): return self._controller.add_account()
    def choose_bulk_login_file(self): return self._controller.choose_bulk_login_file()
    def get_bulk_login_status(self): return self._controller.get_bulk_login_status()
    def clear_bulk_login_selection(self): return self._controller.clear_bulk_login_selection()
    def start_bulk_login(self, store_passwords=True): return self._controller.start_bulk_login(store_passwords)
    def cancel_bulk_login(self): return self._controller.cancel_bulk_login()
    def refresh_all(self): return self._controller.refresh_all()
    def refresh_account(self, steam_id): return self._controller.refresh_account(steam_id)
    def set_timer(self, steam_id, days_text): return self._controller.set_timer(steam_id, days_text)
    def clear_timer(self, steam_id): return self._controller.clear_timer(steam_id)
    def toggle_favorite(self, steam_id): return self._controller.toggle_favorite(steam_id)
    def toggle_comp(self, steam_id): return self._controller.toggle_comp(steam_id)
    def save_credentials(self, steam_id, username, password, store_password):
        return self._controller.save_credentials(steam_id, username, password, store_password)
    def forget_password(self, steam_id): return self._controller.forget_password(steam_id)
    def login_account(self, steam_id): return self._controller.login_account(steam_id)
    def save_api_key(self, raw_key): return self._controller.save_api_key(raw_key)
    def clear_api_key(self): return self._controller.clear_api_key()
    def open_api_key_page(self): return self._controller.open_api_key_page()
    def open_profile(self, steam_id): return self._controller.open_profile(steam_id)
    def copy_steam_id(self, steam_id): return self._controller.copy_steam_id(steam_id)
    def delete_account(self, steam_id): return self._controller.delete_account(steam_id)
    def window_action(self, action): return self._controller.window_action(action)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def _start_static_server(root: Path):
    handler = partial(QuietHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    web_root = _resource_dir()
    server = _start_static_server(web_root)

    db = Database(_data_dir() / "tracker.sqlite3")
    secrets = SecretStore()
    api = SteamApi(secrets.get_api_key)
    controller = WebController(db, secrets, api)

    webview.settings["SHOW_DEFAULT_MENUS"] = False
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.settings["DRAG_REGION_SELECTOR"] = ".pywebview-drag-region"
    try:
        webview.settings["JS_API_MAX_DEPTH"] = 2
    except KeyError:
        pass

    url = f"http://127.0.0.1:{server.server_port}/index.html"
    window = webview.create_window(
        "SAM — Steam Account Manager",
        url=url,
        js_api=WebApiBridge(controller),
        width=1480,
        height=900,
        min_size=(1040, 700),
        resizable=True,
        frameless=True,
        easy_drag=True,
        shadow=True,
        background_color="#0b0b0c",
        text_select=False,
    )
    controller.attach_window(window)
    window.events.closed += lambda: server.shutdown()

    try:
        webview.start(
            gui="edgechromium",
            debug=False,
            private_mode=False,
            storage_path=str(_data_dir() / "webview"),
        )
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
    return 0
