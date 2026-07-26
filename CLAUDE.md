# potrakt

PotPlayer -> Trakt.tv scrobbler for Windows. Python + Tkinter GUI, packaged as a
standalone exe via PyInstaller. See README.md for features and usage.

## Git policy - IMPORTANT

**Never run `git commit` or `git push` in this repo unless the user explicitly asks for
it in that specific message.** Do not treat "set up git" or "create a repo" as implicit
permission to commit - stage/prepare files if asked, but leave committing/pushing to the
user unless they explicitly say otherwise.

**When the user does ask for a commit, it must be attributed to them only - never to
Claude.** Do not add a `Co-Authored-By: Claude ...` trailer or a `Claude-Session:` link
to commit messages in this repo (that's the harness's usual default - skip it here).
Git identity is already configured as `hijast <hijas.ht@gmail.com>`; do not touch git
config, just commit plainly under that identity.

## Architecture

- `app.py` - Tkinter GUI: SetupFrame (Trakt app credentials) -> AuthFrame (device-code
  auth) -> DashboardFrame (live status, settings, history). Background thread
  (`scrobble_loop`) polls PotPlayer and talks to Trakt; communicates with the GUI thread
  via a `queue.Queue` consumed by `pump_events` on `after()`.
- `main.py` - headless CLI equivalent of the scrobble loop, no GUI.
- `potplayer_ctl.py` - PotPlayer control/query via `SendMessage`.
- `trakt_client.py` - Trakt OAuth device flow, search, scrobble, ratings.
- `matcher.py` - filename -> movie/episode guess via `guessit`.
- `history.py` - appends JSONL events, `load_summary()` aggregates them per watched item.
- `autorun.py` - HKCU Run-key toggle for "start with Windows".
- `installer.py` - creates Desktop/Start Menu `.lnk` shortcuts via `win32com`.
- `paths.py` - `app_dir()` (beside the exe/script, for user data like config.json) vs
  `resource_dir()` (PyInstaller onefile's temp extraction dir, for bundled read-only
  assets like `icon.ico`). Do not conflate these - a onefile build's `__file__` resolves
  to a throwaway temp dir at runtime, not the exe's real location.
- `config.py` - loads/saves `config.json` (gitignored - holds the user's Trakt client
  id/secret and OAuth tokens). `config.example.json` documents the shape.

## PotPlayer protocol (no official API - reverse-engineered)

PotPlayer responds to `SendMessage(hwnd, 1024, queryCode, 0)`, verified against
[ld3l/PotPlayerControl](https://github.com/ld3l/PotPlayerControl):
`GET_TOTAL_TIME=20482`, `GET_CURRENT_TIME=20484`, `GET_PLAY_STATUS=20486`
(-1 stopped, 1 paused, 2 playing). The filename comes from the window title (title
contains "PotPlayer"; strip the " - PotPlayer..." suffix).

## Build

```
pyinstaller --onefile --windowed --name potrakt --icon icon.ico --add-data "icon.ico;." --collect-all guessit --collect-all babelfish --collect-all rebulk app.py
```

After rebuilding, re-point the Desktop/Start Menu shortcuts at the new `dist/potrakt.exe`
(installer.py's `create_shortcuts()` only self-targets correctly when run *from* the
frozen exe itself, since it reads `sys.frozen`/`sys.executable` of the calling process).
