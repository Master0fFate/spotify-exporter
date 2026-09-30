"""Offline packaged-app smoke check; never opens login or contacts a service."""

import json
import platform
import tempfile
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from PyQt6.QtCore import QEventLoop, QSettings, QTimer

from . import __version__
from .formats import send_discord, write_export
from .models import Track


class OfflineSpotify:
    def current_user_playlists(self, **kwargs):
        return {
            "items": [
                {
                    "id": "offline",
                    "name": "Offline smoke playlist",
                    "items": {"total": 1},
                    "owner": {"display_name": "Offline"},
                }
            ],
            "total": 1,
            "next": None,
        }


def run_smoke_test(app, report_path):
    # Import lazily to avoid a startup cycle with the desktop entry point.
    from spotify_exporter import ConfigManager, LoginWindow, MainWindow, SettingsDialog

    report = {
        "version": __version__,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "status": "failed",
        "network": "blocked",
    }
    windows = []
    try:
        with tempfile.TemporaryDirectory(prefix="spotify-smoke-") as directory:
            QSettings.setDefaultFormat(QSettings.Format.IniFormat)
            QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, directory)
            with (
                patch(
                    "requests.sessions.Session.request",
                    side_effect=AssertionError("Network is forbidden during smoke testing"),
                ),
                patch(
                    "webbrowser.open",
                    side_effect=AssertionError("Browser login is forbidden during smoke testing"),
                ),
                patch.object(ConfigManager, "load_credentials", return_value=None),
            ):
                login = LoginWindow()
                settings = SettingsDialog(ConfigManager())
                main = MainWindow(OfflineSpotify())
                windows.extend([login, settings, main])
                loop = QEventLoop()
                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(loop.quit)
                if main.load_worker is not None:
                    main.load_worker.finished.connect(loop.quit)
                    timer.start(10000)
                    loop.exec()
                    timer.stop()
                if main.load_worker is not None and main.load_worker.isRunning():
                    raise RuntimeError("Offline playlist loading did not finish")
                if len(main.playlists) != 1 or main.playlists[0].id != "offline":
                    raise RuntimeError("Offline playlist did not render")
                for window in windows:
                    window.show()
                    app.processEvents()
                    if window.grab().isNull():
                        raise RuntimeError("A desktop window could not render")
                track = Track("Offline café 🎵", "Example", "Album", 1000, "", position=1)
                paths = [
                    write_export(main.playlists[0], [track], kind, directory, Event())
                    for kind in ("json", "csv", "txt", "md")
                ]
                if (
                    json.loads(Path(paths[0]).read_text(encoding="utf-8"))["tracks"][0]["name"]
                    != track.name
                ):
                    raise RuntimeError("Unicode export round-trip failed")
                deliveries = []

                def offline_post(url, **kwargs):
                    deliveries.append(kwargs)
                    return SimpleNamespace(status_code=204)

                send_discord(
                    main.playlists[0],
                    [track],
                    "https://discord.com/api/webhooks/123/offline_smoke",
                    Event(),
                    post=offline_post,
                )
                if deliveries[0]["json"]["allowed_mentions"] != {"parse": []}:
                    raise RuntimeError("Offline Discord payload validation failed")
                report.update(
                    status="passed",
                    checks=[
                        "Qt plugin loading",
                        "login/settings/main rendering",
                        "background playlist loading",
                        "CSV/JSON/TXT/Markdown writes",
                        "Unicode JSON round-trip",
                        "offline Discord payload validation",
                    ],
                    export_formats=4,
                )
    except Exception as exc:
        # No external payloads or authentication data enter this report.
        report["error_type"] = type(exc).__name__
    finally:
        for window in windows:
            worker = getattr(window, "load_worker", None)
            if worker is not None and worker.isRunning():
                worker.cancel()
                worker.wait(1000)
            window.close()
        app.processEvents()
        Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["status"] == "passed" else 1
