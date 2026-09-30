# Spotify Playlist Exporter

A Python 3.10+ desktop app for exporting Spotify playlist **metadata** to CSV,
JSON, plain text, Markdown, or a Discord webhook. It does not download audio.
The familiar dark interface, search, sorting, multi-selection and batch export remain.

## Install and run

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
python -m pip install -r requirements.txt
python spotify_exporter.py
# Or, after installation:
spotify-exporter
```

Linux needs a graphical desktop and the system libraries required by Qt; on
Debian/Ubuntu, `libegl1` and `libopengl0` are needed even for offscreen tests.
Runtime dependencies are bounded in `pyproject.toml`; Spotipy 2.26 or newer is
required for the current playlist-items endpoint. The test workflow covers Python
3.10, 3.12 and 3.14 on Windows and Linux. macOS is not covered by CI.

## Connect to Spotify

1. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   and use your app's public **Client ID**.
2. Register this exact redirect URI: `http://127.0.0.1:8888/callback`.
3. Start the exporter, enter the Client ID, and click **Connect**.
4. Complete Spotify's authorization in your own browser. Return to the app when done.

Login uses authorization code with **PKCE** and a random, verified OAuth state.
It requires no client secret. Access and refresh tokens remain in memory and are
forgotten when the application closes; each new session opens browser authorization.
Only the existing read scopes, `playlist-read-private` and
`playlist-read-collaborative`, are requested. Login times out after three minutes;
Cancel stops waiting without closing an active worker unsafely.

The app remembers the public Client ID, output directory and API mode using Qt's
per-user settings (`SpotifyExporter/Settings`): Windows registry, macOS preferences,
or the platform's user configuration directory on Linux. It does not save webhook
URLs or create logs containing tokens.

### Upgrading from 2.0

The old working-directory `config.ini` is used only to prefill its public Client ID.
Its client secret and old `.cache` tokens are never reused or copied. **Delete those
old credential files yourself after upgrading**; this application does not delete
existing files. They are now excluded from Git. No automatic login migration or
permission expansion is performed.

## Export

Select one or more visible playlists, choose an output directory, and select an
export format. Confirm the batch to begin. Hidden search results are not exported.
Sorting preserves selections by playlist ID, including duplicate playlist names.

- **CSV:** UTF-8 with BOM for spreadsheet compatibility; dangerous formula-like
  strings are prefixed with an apostrophe. Use JSON for exact, lossless text.
- **JSON:** Original `playlist`, `tracks` and `exported_at` keys remain, with
  `schema_version: 2`, playlist ID, and richer item fields.
- **TXT / Markdown:** Human-readable metadata, with escaped Markdown content.
- **Discord:** HTTPS Discord webhook only; mentions are disabled, long messages are
  split safely, and requests have timeouts. A timeout is *not* automatically retried
  because it might already have delivered the message. Check the channel before
  retrying. Cancellation cannot recall messages already sent.

All local formats preserve order and duplicates, export empty playlists, and
retain unavailable entries as marked placeholders. Track/episode type, local-file
status, availability, original position, URI and added timestamp are available in
CSV/JSON. Missing metadata stays empty or explicitly unknown; local tracks do not
get fabricated Spotify links. Fields depend on what Spotify returns.

Local files have portable, length-bounded, collision-resistant names. Each playlist
is written to a temporary file and published atomically only after it is complete.
Cancellation or a failed page does not publish a partial playlist. Files from
previous completed playlists in the batch remain available. **To retry, select the
unfinished playlists and export again.** There is no persistent page checkpoint or
automatic Discord resume: this avoids stale mixed snapshots and duplicate posts.

## Spotify API compatibility and limits

The default uses `GET /playlists/{id}/items`, and reads both the current `item` /
`items` and older `track` / `tracks` response shapes. Settings contains an explicit
legacy `/tracks` mode for extended-quota apps. A 403 never triggers an automatic
fallback or bypass.

As of the official 2026 changes, development-mode apps may only read playlist
contents for playlists the user owns or collaborates on. Other playlists can still
appear as metadata without their contents. The app owner's Premium subscription
and the app's allowed-user list also affect access. An exporter cannot remove
these Spotify restrictions.

Pagination validates next-page URLs, rejects repeating/incomplete pages, and checks
playlist snapshots before and after fetching. If a playlist changes, retry rather
than saving a mixed copy. Spotify 429 responses honor `Retry-After`; transient
connection/5xx failures retry at most three times. Quota-exhaustion responses and
waits longer than two minutes stop with a useful error rather than hammering the
API. Refresh and export run off the GUI thread. A running request may take up to
its network timeout to stop; controls remain locked until the worker exits.

Primary references checked for this retrofit:
- [February 2026 migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide)
- [Current playlist items](https://developer.spotify.com/documentation/web-api/reference/get-playlists-items)
- [July 2026 quota changes](https://developer.spotify.com/documentation/web-api/references/changes/july-2026)
- [Rate limits](https://developer.spotify.com/documentation/web-api/concepts/rate-limits)
- [PKCE authorization](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow)
- [Redirect URI requirements](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri)

## Development and verification

```sh
python -m pip install '.[dev]'
ruff check .
ruff format --check .
python -m pytest -q
python -m build
```

Tests use mocked Spotify, OAuth and Discord calls and offscreen Qt widgets.
They explicitly prohibit real HTTP requests. Coverage includes pagination, 2026
response shapes, snapshots, bounded retries, rate limits, cancellation, atomic
writes, Unicode, CSV formulas, Discord size/mention safety, PKCE state and login
interruption, selection identity and worker lifecycle. Live Spotify authorization,
real account exports and real Discord delivery require manual validation on your
own account; automated tests do not establish that those live flows succeeded.

Project layout:

```text
spotify_exporter.py      Desktop UI and settings
exporter/auth.py          PKCE and loopback callback
exporter/api.py           Read-only API, pagination, retry/cancellation
exporter/models.py        Normalized playlist/item records
exporter/formats.py       Local serializers and Discord delivery
exporter/workers.py       Qt background adapters
tests/                  Offline regression tests
```

### Windows release executable

The release asset remains **`SpotifyExporter.exe`**, now built as a Windows x64
single-file PyInstaller application with Python 3.14. It includes Python and Qt;
no separate Python installation is required. The executable is unsigned. Windows
may display an unknown-publisher or reputation warning; verify the published
SHA-256 and download only from this repository's Releases. No macOS, Linux,
Windows ARM64 or 32-bit executable is included.

`Package Windows executable` builds on pushes to main that affect application or
packaging code (or on manual dispatch). It runs the offline test suite, builds the
EXE, then **runs that exact EXE** in offscreen mode to verify Qt/plugin loading,
login/settings/main rendering, background playlist loading and all four local
export formats. Network and browser access are blocked inside smoke mode.
`SpotifyExporter-windows-x64` contains the EXE, `SHA256SUMS.txt`, the JSON smoke
report and the resolved build dependencies. The workflow does not publish Releases. Optional Qt Multimedia/PDF/FFmpeg components
are excluded from the package; CI inspects the final archive to verify their absence.
A separate ThirdPartyNotices artifact records exact installed license texts and
provenance. It is a review inventory, not a claim of complete GPL/LGPL compliance.

To reproduce on Windows x64:

```powershell
python -m pip install '.[dev]' 'pyinstaller==6.22.3'
./scripts/build_windows.ps1
```

For a credential-free check of the downloaded executable:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
Start-Process .\SpotifyExporter.exe -ArgumentList '--smoke-test --smoke-report smoke-report.json' -Wait
Get-Content smoke-report.json
```

Normal launch still opens the desktop login window. Smoke mode never connects to
Spotify, starts OAuth, or posts to Discord. Live authorization, real account exports
and desktop integration remain manual checks; a passing package smoke is not a
claim that those live flows were tested. The one-file executable extracts bundled
libraries to the user's temporary directory at startup. UPX compression is disabled.

## Troubleshooting

- **Cannot listen on port 8888:** close another login attempt using that port, then
  reconnect. The callback listener binds only to `127.0.0.1`.
- **Login timed out or declined:** click Connect again. The Client ID and exact
  redirect URI must match the dashboard registration.
- **403 / inaccessible playlist:** check the access restrictions above. A public
  playlist is not necessarily readable by a development-mode app.
- **Changed/incomplete playlist:** refresh and retry after edits to the playlist stop.
- **Quota/rate limit:** wait as instructed. As of July 2026, development quota is
  shared across Client IDs belonging to the same developer account.
- **Close while busy:** the first close requests cancellation. Once requests have
  stopped, close again. A live QThread is never destroyed or forcibly terminated.

## License

Project source is MIT; dependencies retain their own licenses. Review dependency
licenses, including Qt and QFluentWidgets, when distributing packaged binaries.
