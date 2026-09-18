from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS accounts (
    steam_id TEXT PRIMARY KEY,
    persona_name TEXT NOT NULL DEFAULT '',
    avatar_url TEXT NOT NULL DEFAULT '',
    profile_url TEXT NOT NULL DEFAULT '',
    persona_state INTEGER NOT NULL DEFAULT 0,
    steam_level INTEGER,
    total_playtime_minutes INTEGER NOT NULL DEFAULT 0,
    game_count INTEGER NOT NULL DEFAULT 0,
    login_username TEXT NOT NULL DEFAULT '',
    has_password INTEGER NOT NULL DEFAULT 0,
    vcbnd_until INTEGER,
    favorite INTEGER NOT NULL DEFAULT 0,
    comp INTEGER NOT NULL DEFAULT 0,
    date_added INTEGER NOT NULL,
    last_profile_sync INTEGER NOT NULL DEFAULT 0,
    last_games_sync INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS games (
    steam_id TEXT NOT NULL,
    app_id INTEGER NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    playtime_minutes INTEGER NOT NULL DEFAULT 0,
    icon_hash TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (steam_id, app_id),
    FOREIGN KEY (steam_id) REFERENCES accounts(steam_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_games_steam_playtime
ON games(steam_id, playtime_minutes DESC);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.executescript(SCHEMA)
            self._ensure_columns(conn)


    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection) -> None:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()}
        migrations = {
            "total_playtime_minutes": "INTEGER NOT NULL DEFAULT 0",
            "game_count": "INTEGER NOT NULL DEFAULT 0",
            "has_password": "INTEGER NOT NULL DEFAULT 0",
            "comp": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in migrations.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE accounts ADD COLUMN {name} {definition}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=8.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_account(self, steam_id: str, **fields: Any) -> None:
        now = int(time.time())
        allowed = {
            "persona_name", "avatar_url", "profile_url", "persona_state",
            "steam_level", "total_playtime_minutes", "game_count", "login_username", "has_password", "vcbnd_until", "favorite", "comp",
            "last_profile_sync", "last_games_sync",
        }
        clean = {k: v for k, v in fields.items() if k in allowed}
        with self._connection() as conn:
            exists = conn.execute("SELECT 1 FROM accounts WHERE steam_id=?", (steam_id,)).fetchone()
            if exists:
                if clean:
                    pairs = ", ".join(f"{k}=?" for k in clean)
                    conn.execute(
                        f"UPDATE accounts SET {pairs} WHERE steam_id=?",
                        (*clean.values(), steam_id),
                    )
            else:
                cols = ["steam_id", "date_added", *clean.keys()]
                vals = [steam_id, now, *clean.values()]
                q = ",".join("?" for _ in vals)
                conn.execute(
                    f"INSERT INTO accounts ({','.join(cols)}) VALUES ({q})",
                    vals,
                )

    def get_account(self, steam_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE steam_id=?", (steam_id,)).fetchone()
            if not row:
                return None
            result = dict(row)
            result["top_games"] = self._top_games(conn, steam_id)
            return result

    def list_accounts(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM accounts ORDER BY favorite DESC, date_added DESC").fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                d = dict(row)
                d["top_games"] = self._top_games(conn, d["steam_id"])
                out.append(d)
            return out

    def find_account_by_login_username(self, username: str) -> dict[str, Any] | None:
        target = (username or "").strip()
        if not target:
            return None
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE login_username = ? COLLATE NOCASE LIMIT 1",
                (target,),
            ).fetchone()
            if not row:
                return None
            result = dict(row)
            result["top_games"] = self._top_games(conn, result["steam_id"])
            return result

    def _top_games(self, conn: sqlite3.Connection, steam_id: str, limit: int = 8) -> list[dict[str, Any]]:
        rows = conn.execute(
            """SELECT app_id, name, playtime_minutes, icon_hash
               FROM games WHERE steam_id=?
               ORDER BY playtime_minutes DESC LIMIT ?""",
            (steam_id, limit),
        ).fetchall()
        games = []
        for r in rows:
            d = dict(r)
            icon = d.pop("icon_hash", "") or ""
            d["icon_url"] = (
                f"https://media.steampowered.com/steamcommunity/public/images/apps/{d['app_id']}/{icon}.jpg"
                if icon else ""
            )
            # Public store artwork gives the card the same image-led look as Steam
            # marketplace/account cards without needing another metadata request.
            d["header_url"] = (
                f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{d['app_id']}/header.jpg"
            )
            d["hours"] = round((d.get("playtime_minutes") or 0) / 60.0, 1)
            games.append(d)
        return games

    def replace_games(self, steam_id: str, games: Iterable[dict[str, Any]]) -> None:
        now = int(time.time())
        rows = []
        for g in games:
            rows.append((
                steam_id,
                int(g.get("appid", 0)),
                str(g.get("name", "")),
                int(g.get("playtime_forever", 0) or 0),
                str(g.get("img_icon_url", "") or ""),
            ))
        with self._connection() as conn:
            conn.execute("DELETE FROM games WHERE steam_id=?", (steam_id,))
            if rows:
                conn.executemany(
                    "INSERT INTO games(steam_id,app_id,name,playtime_minutes,icon_hash) VALUES (?,?,?,?,?)",
                    rows,
                )
            total_minutes = sum(r[3] for r in rows)
            conn.execute(
                "UPDATE accounts SET last_games_sync=?, total_playtime_minutes=?, game_count=? WHERE steam_id=?",
                (now, total_minutes, len(rows), steam_id),
            )

    def set_timer(self, steam_id: str, until_ts: int | None) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE accounts SET vcbnd_until=? WHERE steam_id=?", (until_ts, steam_id))

    def set_login_username(self, steam_id: str, username: str) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE accounts SET login_username=? WHERE steam_id=?", (username, steam_id))

    def set_has_password(self, steam_id: str, value: bool) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE accounts SET has_password=? WHERE steam_id=?", (1 if value else 0, steam_id))

    def set_favorite(self, steam_id: str, value: bool) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE accounts SET favorite=? WHERE steam_id=?", (1 if value else 0, steam_id))

    def set_comp(self, steam_id: str, value: bool) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE accounts SET comp=? WHERE steam_id=?", (1 if value else 0, steam_id))

    def delete_account(self, steam_id: str) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM accounts WHERE steam_id=?", (steam_id,))
