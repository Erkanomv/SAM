from __future__ import annotations

import html as html_lib
import re
import secrets
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

OPENID_ENDPOINT = "https://steamcommunity.com/openid/login"
CLAIMED_ID_RE = re.compile(r"/openid/id/(\d+)$")


class SteamOpenId:
    """Small callback-based Steam OpenID helper with no GUI-framework dependency."""

    def __init__(
        self,
        on_authenticated: Callable[[str], None],
        on_failed: Callable[[str], None],
    ):
        self._on_authenticated = on_authenticated
        self._on_failed = on_failed
        self._server: ThreadingHTTPServer | None = None
        self._state = ""
        self._lock = threading.Lock()

    def begin(self) -> bool:
        with self._lock:
            if self._server:
                self._on_failed("A Steam login is already in progress.")
                return False

            self._state = secrets.token_urlsafe(24)
            owner = self

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *_args):
                    pass

                def do_GET(self):
                    parsed = urllib.parse.urlsplit(self.path)
                    if parsed.path != "/callback":
                        self.send_response(404)
                        self.end_headers()
                        return

                    params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
                    ok = False
                    message = "Steam authentication failed."
                    steam_id = ""
                    try:
                        if params.get("state") != owner._state:
                            raise RuntimeError("Login state mismatch.")
                        openid_params = {k: v for k, v in params.items() if k.startswith("openid.")}
                        openid_params["openid.mode"] = "check_authentication"
                        payload = urllib.parse.urlencode(openid_params).encode("utf-8")
                        req = urllib.request.Request(
                            OPENID_ENDPOINT,
                            data=payload,
                            headers={"Content-Type": "application/x-www-form-urlencoded"},
                            method="POST",
                        )
                        with urllib.request.urlopen(req, timeout=12) as resp:
                            body = resp.read().decode("utf-8", errors="replace")
                        if "is_valid:true" not in body:
                            raise RuntimeError("Steam could not verify this login.")
                        claimed = params.get("openid.claimed_id", "")
                        match = CLAIMED_ID_RE.search(claimed)
                        if not match:
                            raise RuntimeError("SteamID was missing from the verified response.")
                        steam_id = match.group(1)
                        ok = True
                        message = "Account linked. You can close this tab and return to Steam Tracker."
                    except Exception as exc:
                        message = str(exc)

                    page = f"""<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Steam Tracker</title>
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0b0c;color:#f4f4f2;font-family:'Segoe UI Variable','Segoe UI',system-ui,sans-serif}}
.card{{width:min(460px,calc(100vw - 40px));padding:30px;border:1px solid #262629;background:#121214;border-radius:14px;box-shadow:0 24px 80px rgba(0,0,0,.45)}}
.mark{{width:36px;height:36px;display:grid;place-items:center;background:#f1f1ef;color:#0b0b0c;border-radius:8px;font-weight:800;font-size:12px;margin-bottom:24px}}
h1{{font-size:22px;letter-spacing:-.5px;margin:0 0 8px}}
p{{margin:0;color:#9b9ba1;line-height:1.6;font-size:14px}}
.ok{{color:#70d99b}} .bad{{color:#ff736d}}
</style>
</head><body><main class='card'><div class='mark'>ST</div><h1 class='{'ok' if ok else 'bad'}'>{'Account linked' if ok else 'Login failed'}</h1><p>{html_lib.escape(message)}</p></main></body></html>"""
                    data = page.encode("utf-8")
                    self.send_response(200 if ok else 400)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)

                    if ok:
                        threading.Thread(target=owner._on_authenticated, args=(steam_id,), daemon=True).start()
                    else:
                        threading.Thread(target=owner._on_failed, args=(message,), daemon=True).start()
                    threading.Thread(target=owner._finish_server, daemon=True).start()

            self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            port = self._server.server_port
            return_to = f"http://127.0.0.1:{port}/callback?state={urllib.parse.quote(self._state)}"
            query = {
                "openid.ns": "http://specs.openid.net/auth/2.0",
                "openid.mode": "checkid_setup",
                "openid.return_to": return_to,
                "openid.realm": f"http://127.0.0.1:{port}/",
                "openid.identity": "http://specs.openid.net/auth/2.0/identifier_select",
                "openid.claimed_id": "http://specs.openid.net/auth/2.0/identifier_select",
            }
            url = OPENID_ENDPOINT + "?" + urllib.parse.urlencode(query)
            threading.Thread(target=self._server.serve_forever, daemon=True).start()
            webbrowser.open(url)
            return True

    def _finish_server(self) -> None:
        with self._lock:
            server, self._server = self._server, None
        if server:
            server.shutdown()
            server.server_close()
