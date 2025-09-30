# <div align="center"> Spotify Playlist Exporter </div>

<div align="center">

![Version](https://img.shields.io/badge/version-2.0-green.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-6.0+-brightgreen.svg)

A modern, professional desktop application for exporting Spotify playlists to multiple formats.

[Features](#features) • [Installation](#installation) • [Usage](#usage) • [Building](#building)

</div>

---

## Features

- > **Modern Dark UI** - Professional interface with custom frameless window design
- > **Multiple Export Formats** - CSV, JSON, TXT, Markdown, and Discord webhook support
- > **Smart Search & Filter** - Quickly find playlists with real-time search
- > **Batch Export** - Export multiple playlists simultaneously
- > **Progress Tracking** - Real-time progress updates with cancel support
- > **Secure Authentication** - OAuth integration with Spotify API
- > **Unicode Support** - Handles international characters and special symbols
- > **Persistent Settings** - Remembers your preferences


## Installation

### Prerequisites

- Python 3.8 or higher
- Spotify Developer Account ([Get one here](https://developer.spotify.com/dashboard))

### Install Dependencies

```bash
pip install -r requirements.txt
```

**requirements.txt:**
```txt
PyQt6
spotipy
requests
```

### Get Spotify API Credentials

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Copy your **Client ID** and **Client Secret**
4. Add `http://127.0.0.1:8888/callback` as a Redirect URI in your app settings

## Usage

### Run from Source

```bash
python spotify_exporter.py
```

### First Time Setup

1. Launch the application
2. Enter your Spotify **Client ID** and **Client Secret**
3. Click **Connect** and authorize in your browser
4. Select playlists to export
5. Choose export format and location
6. Click an export format button

### Export Formats

| Format | Description | Use Case |
|--------|-------------|----------|
| **CSV** | Spreadsheet format | Data analysis, Excel |
| **JSON** | Structured data | API integration, backup |
| **TXT** | Plain text | Simple reading, printing |
| **Markdown** | Formatted text | Documentation, GitHub |
| **Discord** | Webhook export | Share to Discord channels |

## Building

### Build Executable with Nuitka

**Windows:** (alternatively use pyinstaller)
```batch
# Install Nuitka
pip install nuitka

# Build single executable
nuitka --standalone --onefile ^
    --enable-plugin=pyqt6 ^
    --windows-disable-console ^
    --include-package=spotipy ^
    --include-package=requests ^
    --output-filename=SpotifyExporter.exe ^
    spotify_exporter.py
```

**Optional UPX Compression:**
```batch
upx --best --lzma SpotifyExporter.exe
```

## Configuration

Configuration files are stored in:
- **Windows:** `%APPDATA%/SpotifyExporter/`
- **Config File:** `config.ini` (in application directory)
- **Logs:** `logs/` (in application directory)

## Project Structure

```
spotify-exporter/
├── spotify_exporter.py    # Main application
├── requirements.txt       # Python dependencies
├── config.ini            # Generated after first login
├── logs/                 # Application logs
└── README.md
```

## Troubleshooting

**"Invalid credentials" error:**
- Verify your Client ID and Client Secret
- Ensure redirect URI is set to `http://127.0.0.1:8888/callback`

**Unicode errors in logs:**
- Already handled! The app uses UTF-8 encoding for all files

**Empty playlist exports:**
- Check playlist permissions (private playlists require proper scope)
- Ensure you have an active internet connection

## Technology Stack

- **PyQt6** - Modern GUI framework
- **Spotipy** - Spotify Web API wrapper
- **Python 3.8+** - Core language

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Spotify Web API for playlist data
- PyQt6 for the GUI framework
- Spotipy for API integration

---

<div align="center">


[Report Bug](https://github.com/Master0fFate/spotify-exporter/issues) • [Request Feature](https://github.com/Master0fFate/spotify-exporter/issues)

</div>
