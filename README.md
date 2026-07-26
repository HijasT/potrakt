# potrakt

Automatic [Trakt.tv](https://trakt.tv) check-ins (scrobbling) for [PotPlayer](https://potplayer.daum.net/) on Windows.

PotPlayer has no public plugin/scripting API, so potrakt runs alongside it as a small
companion app: it polls PotPlayer for what's currently playing and how far into it you
are, identifies the movie/episode from the filename, and calls Trakt's scrobble API to
start/pause/stop check-ins automatically.

![potrakt logo](logo.png)

## Features

- Auto-detects the currently playing file, its position, and play/pause state directly
  from PotPlayer (no PotPlayer configuration needed)
- Identifies movies/episodes from the filename and resolves them against Trakt's search
- Sends `start` / `pause` / `stop` scrobbles to Trakt as you watch
- Guided setup window - paste your Trakt app credentials and authorize via Trakt's
  device-code flow, no manual config file editing
- Persistent activity history with a per-item view, rating (1-10), and a direct link to
  the item's Trakt page
- Optional rating popup when something finishes (≥80% watched)
- Optional "start with Windows" toggle
- Creates its own Desktop / Start Menu shortcuts
- Ships as a single standalone `.exe` - no Python install required to run it

## Requirements

- Windows
- [PotPlayer](https://potplayer.daum.net/)
- A free Trakt.tv account and your own API app (takes ~30 seconds to create, see below)

## Quick start (prebuilt exe)

1. Get `potrakt.exe` (see [Building](#building-the-exe) below, or a release if one has
   been published).
2. Run it.
3. On first launch it'll walk you through:
   - Creating a Trakt API app at
     [app.trakt.tv/settings/apps/api/new](https://app.trakt.tv/settings/apps/api/new)
     (redirect URI: `urn:ietf:wg:oauth:2.0:oob`)
   - Pasting in the Client ID / Client Secret
   - Authorizing via Trakt's device code (a code + link, no password typed into potrakt)
4. Once authorized it opens the dashboard and starts watching PotPlayer automatically.

## Running from source

Requires Python 3.10+ (tested on 3.14) on Windows.

```
pip install -r requirements.txt
python app.py
```

There's also a headless CLI version (no GUI) for scripting/testing:

```
python main.py
```

## Building the exe

```
pip install pyinstaller
pyinstaller --onefile --windowed --name potrakt --icon icon.ico --add-data "icon.ico;." --collect-all guessit --collect-all babelfish --collect-all rebulk app.py
```

The output is `dist/potrakt.exe` - a self-contained single file, safe to copy to another
Windows machine. Each machine/user needs their own Trakt API app credentials (Trakt apps
are free and tied to your account, not something you share).

## How it identifies what's playing

PotPlayer doesn't expose an official API, but it does respond to a private
`SendMessage(hwnd, 1024, queryCode, 0)` protocol for querying playback state (verified
against [ld3l/PotPlayerControl](https://github.com/ld3l/PotPlayerControl)):

| Query code | Meaning |
|---|---|
| `20482` | total duration (ms) |
| `20484` | current position (ms) |
| `20486` | play status (`-1` stopped, `1` paused, `2` playing) |

The filename comes from the PotPlayer window title. Filenames are parsed into
movie/show + season/episode with [`guessit`](https://github.com/guessit-io/guessit), then
resolved against Trakt's `/search` endpoint.

## Project layout

| File | Purpose |
|---|---|
| `app.py` | Tkinter GUI - setup, Trakt auth, dashboard, history window, rating popup |
| `main.py` | Headless CLI runner (no GUI) |
| `potplayer_ctl.py` | Talks to PotPlayer via `SendMessage` |
| `trakt_client.py` | Trakt OAuth device flow, search, scrobble, ratings |
| `matcher.py` | Filename → movie/episode guess |
| `history.py` | Persistent JSONL activity log + per-item aggregation |
| `autorun.py` | Windows "run at startup" registry toggle |
| `installer.py` | Creates Desktop / Start Menu shortcuts |
| `paths.py` | Path helpers that work both as a script and as a frozen exe |
| `config.py` | Loads/saves `config.json` (credentials, tokens, settings) |
| `tools/generate_logo.py` | Regenerates `logo.png` / `icon.ico` |

## Notes

- `config.json` (your Trakt credentials/tokens) and `history.jsonl` (your watch history)
  are personal and gitignored - see `config.example.json` for the expected shape.
- Windows only - it relies on Win32 APIs (`SendMessage`, window enumeration, registry).

## License

[GPL-3.0](LICENSE)
