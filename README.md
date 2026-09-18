# SAM (Steam Account Manager)

A Windows desktop Steam account manager focused on fast account switching, clean account cards, playtime/library metadata, manual VCBND timers, and bulk account onboarding.

## Current version

**v0.5.1**

## Features

- Steam OpenID account linking
- Steam profile, avatar, game library and playtime display
- Most-played game artwork and compact account cards
- Manual `VCBND` / `UNBND` countdown status per account
- Per-account `COMP` toggle shown alongside `VCBND` / `UNBND`, with its own filter
- Search, sorting, favorites and status filters
- Favorites use a filled red heart and stay pinned at the top by default
- One-click local Steam account switching
- Optional credential storage through Windows Credential Manager
- Bulk `username:password` import and sequential Steam login
- Background profile/library refresh after successful bulk additions
- SQLite local cache for account metadata and libraries
- HTML/CSS/JS interface hosted in WebView2 via pywebview
- Lightweight SAM startup splash while the native bridge/account cache initializes
- Shared Python runtime for faster launches between updates

## Requirements

- Windows 10 or Windows 11
- Steam desktop client
- Python 3.10+ for source runs
- Microsoft Edge WebView2 Runtime

## Run from source

Double-click:

```text
run.bat
```

For a console with diagnostic output:

```text
run_debug.bat
```

The launcher reuses the shared runtime under `%LOCALAPPDATA%\SteamTracker\runtime` when available so subsequent starts do not reinstall dependencies.

## Bulk login format

Create a text file containing one account per line:

```text
username1:password1
username2:password2
```

Only the first colon separates username from password, so passwords may contain additional colons. The bulk queue closes/switches Steam, verifies the active local Steam account, adds it to SAM, and continues with the next entry.

## Data and credentials

SAM keeps normal application data locally in SQLite. Passwords are not stored in the database; when password storage is enabled they are saved through Windows Credential Manager.

Do **not** commit credential import files, local databases, API keys, or exported account spreadsheets. The repository `.gitignore` excludes common local credential/data files.

## Steam data

SAM can work with public Steam profile/game data without an API key. A Steam Web API key is optional and can improve some metadata requests. Private Steam game details may prevent owned-game/playtime data from being available.

## Project layout

```text
app.py                         Entrypoint
steam_tracker/app.py           Native WebView host
steam_tracker/web_controller.py JS/Python bridge controller
steam_tracker/steam_client.py  Local Steam switching and bulk login
steam_tracker/steam_api.py     Steam metadata requests
steam_tracker/db.py            SQLite persistence/cache
steam_tracker/secrets.py       Credential Manager integration
steam_tracker/openid.py        Steam OpenID flow
steam_tracker/web/             HTML/CSS/JS UI
tests/                         Regression tests
```

## Build

Use:

```text
build_exe.bat
```

to create the packaged Windows build.

## Security note

Steam's command-line login mechanism necessarily exposes credentials to the Steam process at launch time. SAM avoids putting passwords in its SQLite database or logs and uses Windows Credential Manager for persisted passwords.

---

This project is not affiliated with Valve Corporation or Steam.
