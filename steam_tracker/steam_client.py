from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import psutil


class SteamClientError(RuntimeError):
    pass


@dataclass(slots=True)
class BulkCredential:
    username: str
    password: str = field(repr=False)
    line_number: int = 0


@dataclass(slots=True)
class LoginUser:
    steam_id: str
    account_name: str
    persona_name: str = ""
    most_recent: bool = False
    timestamp: int = 0

    @property
    def account_id(self) -> int:
        try:
            return int(self.steam_id) & 0xFFFFFFFF
        except (TypeError, ValueError):
            return 0


def parse_bulk_credentials(text: str, *, max_accounts: int = 500) -> tuple[list[BulkCredential], list[str]]:
    credentials: list[BulkCredential] = []
    issues: list[str] = []
    seen: set[str] = []

    for line_number, raw in enumerate((text or "").splitlines(), 1):
        line = raw.lstrip("\ufeff") if line_number == 1 else raw
        if not line.strip() or line.lstrip().startswith(("#", ";")):
            continue
        if ":" not in line:
            issues.append(f"Line {line_number}: missing ':' separator.")
            continue

        username_raw, password = line.split(":", 1)
        username = username_raw.strip()
        password = password.rstrip("\r")
        if not username:
            issues.append(f"Line {line_number}: account name is empty.")
            continue
        if not password:
            issues.append(f"Line {line_number}: password is empty.")
            continue

        key = username.casefold()
        if key in seen:
            issues.append(f"Line {line_number}: duplicate account '{username}' skipped.")
            continue
        seen.add(key)
        credentials.append(BulkCredential(username=username, password=password, line_number=line_number))
        if len(credentials) >= max_accounts:
            issues.append(f"Only the first {max_accounts} valid accounts were loaded.")
            break

    return credentials, issues


def find_steam_exe() -> Path:
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                value, _ = winreg.QueryValueEx(key, "SteamExe")
                p = Path(str(value).replace("/", "\\"))
                if p.exists():
                    return p
        except OSError:
            pass

    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam" / "steam.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam" / "steam.exe",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise SteamClientError("Steam.exe was not found. Install Steam in the normal location or start Steam once.")


def loginusers_path() -> Path:
    return find_steam_exe().parent / "config" / "loginusers.vdf"


def _steam_processes() -> list[psutil.Process]:
    found: list[psutil.Process] = []
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info.get("name") or "").lower() == "steam.exe":
                found.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return found


def steam_is_running() -> bool:
    return bool(_steam_processes())


def _vdf_unescape(value: str) -> str:
    return value.replace(r'\"', '"').replace(r"\\", "\\")


def parse_loginusers_vdf(text: str) -> list[LoginUser]:
    users: list[LoginUser] = []
    block_re = re.compile(r'"(\d{15,20})"\s*\{(.*?)\}', re.DOTALL)
    pair_re = re.compile(r'"((?:\\.|[^"\\])*)"\s*"((?:\\.|[^"\\])*)"')

    for match in block_re.finditer(text or ""):
        steam_id = match.group(1)
        fields = {
            _vdf_unescape(k): _vdf_unescape(v)
            for k, v in pair_re.findall(match.group(2))
        }
        account_name = fields.get("AccountName", "").strip()
        if not account_name:
            continue
        try:
            timestamp = int(fields.get("Timestamp", "0") or 0)
        except ValueError:
            timestamp = 0
        users.append(
            LoginUser(
                steam_id=steam_id,
                account_name=account_name,
                persona_name=fields.get("PersonaName", "").strip(),
                most_recent=fields.get("MostRecent", "0") == "1",
                timestamp=timestamp,
            )
        )
    return users


def read_login_users() -> list[LoginUser]:
    try:
        path = loginusers_path()
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except (OSError, SteamClientError):
        return []
    return parse_loginusers_vdf(text)


def find_login_user(username: str, users: Iterable[LoginUser] | None = None) -> LoginUser | None:
    target = (username or "").strip().casefold()
    if not target:
        return None
    for user in users if users is not None else read_login_users():
        if user.account_name.casefold() == target:
            return user
    return None


def get_active_process_info() -> tuple[int | None, int | None]:
    if os.name != "nt":
        return None, None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess") as key:
            try:
                active_value, _ = winreg.QueryValueEx(key, "ActiveUser")
                active = int(active_value)
            except (OSError, TypeError, ValueError):
                active = 0
            try:
                pid_value, _ = winreg.QueryValueEx(key, "pid")
                pid = int(pid_value)
            except (OSError, TypeError, ValueError):
                pid = 0
            return (active if active > 0 else None, pid if pid > 0 else None)
    except OSError:
        return None, None


def get_active_user_account_id() -> int | None:
    active, _pid = get_active_process_info()
    return active


def shutdown_steam(*, graceful_timeout: float = 15.0, force_timeout: float = 4.0) -> None:
    if os.name != "nt":
        raise SteamClientError("Local Steam switching is supported on Windows only.")

    steam_exe = find_steam_exe()
    if not _steam_processes():
        return

    try:
        subprocess.Popen(
            [str(steam_exe), "-shutdown"],
            cwd=str(steam_exe.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except OSError:
        pass

    deadline = time.monotonic() + max(0.0, graceful_timeout)
    while time.monotonic() < deadline and _steam_processes():
        time.sleep(0.35)

    remaining = _steam_processes()
    for proc in remaining:
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    if remaining:
        _, alive = psutil.wait_procs(remaining, timeout=max(0.0, force_timeout))
        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass


def launch_steam_login(username: str, password: str) -> None:
    if os.name != "nt":
        raise SteamClientError("Local Steam switching is supported on Windows only.")
    if not username or not password:
        raise SteamClientError("Steam login username and password are required.")

    steam_exe = find_steam_exe()
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    subprocess.Popen(
        [str(steam_exe), "-login", username, password],
        cwd=str(steam_exe.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )


def switch_account(username: str, password: str) -> None:
    shutdown_steam()
    launch_steam_login(username, password)


def wait_for_account_login(
    username: str,
    *,
    timeout: float = 55.0,
    cancel_event=None,
    expected_steam_id: str = "",
) -> LoginUser | None:
    started = time.monotonic()
    baseline_path = None
    baseline_mtime = 0
    try:
        baseline_path = loginusers_path()
        baseline_mtime = baseline_path.stat().st_mtime_ns if baseline_path.exists() else 0
    except (OSError, SteamClientError):
        pass

    expected = str(expected_steam_id or "").strip()
    expected_account_id = (int(expected) & 0xFFFFFFFF) if expected.isdigit() else 0

    while time.monotonic() - started < timeout:
        if cancel_event is not None and cancel_event.is_set():
            return None

        users = read_login_users()
        user = find_login_user(username, users)
        active_id, active_pid = get_active_process_info()
        process_ids = {proc.pid for proc in _steam_processes()}
        current_process = active_pid is None or active_pid in process_ids
        elapsed = time.monotonic() - started

        if elapsed >= 1.5 and current_process and process_ids:
            if user and active_id is not None and user.account_id == active_id:
                return user
            if expected_account_id and active_id is not None and expected_account_id == active_id:
                return user or LoginUser(steam_id=expected, account_name=username, persona_name=username, most_recent=True)

        if user and user.most_recent and steam_is_running() and elapsed >= 5.0:
            try:
                current_mtime = baseline_path.stat().st_mtime_ns if baseline_path and baseline_path.exists() else 0
            except OSError:
                current_mtime = 0
            if current_mtime and current_mtime != baseline_mtime:
                return user

        time.sleep(0.5)
    return None
