"""Qt adapters: one result signal, then QThread.finished releases UI controls."""

from threading import Event

from PyQt6.QtCore import QThread, pyqtSignal

from .api import Cancelled, ExportError, SpotifyReader, check_cancelled
from .auth import authenticate
from .formats import send_discord, write_export


def public_error(exc):
    if isinstance(exc, ExportError):
        return str(exc)
    if isinstance(exc, OSError):
        return "Unable to access the output location. Check free space and permissions."
    return "The operation failed. Check your connection and Spotify app settings, then retry."


class TaskWorker(QThread):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.stop = Event()
        self.operation = operation

    def cancel(self):
        self.stop.set()

    def run(self):
        try:
            check_cancelled(self.stop)
            result = self.operation(self.stop)
            check_cancelled(self.stop)
            self.succeeded.emit(result)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(public_error(exc))


class LoginWorker(TaskWorker):
    def __init__(self, client_id, parent=None):
        super().__init__(lambda cancel: authenticate(client_id, cancel), parent)


class ExportWorker(QThread):
    progress = pyqtSignal(int, str)
    completed = pyqtSignal(list)
    error = pyqtSignal(str)
    cancelled = pyqtSignal(list)

    def __init__(self, export_format, playlists, sp, output_dir, webhook_url="", legacy=False):
        super().__init__()
        self.export_format = export_format
        self.playlists = playlists
        self.sp = sp
        self.output_dir = output_dir
        self.webhook_url = webhook_url
        self.stop = Event()
        self.exported_files = []
        self.legacy = legacy

    def cancel(self):
        self.stop.set()

    def run(self):
        try:
            reader = SpotifyReader(self.sp, self.stop, legacy=self.legacy)
            for i, playlist in enumerate(self.playlists):
                check_cancelled(self.stop)
                self.progress.emit(
                    int(i / len(self.playlists) * 100), f"Exporting: {playlist.name}"
                )
                tracks = reader.tracks(playlist.id)
                if self.export_format.value == "discord":
                    send_discord(playlist, tracks, self.webhook_url, self.stop)
                else:
                    self.exported_files.append(
                        write_export(
                            playlist, tracks, self.export_format.value, self.output_dir, self.stop
                        )
                    )
            self.progress.emit(100, "Export completed")
            self.completed.emit(self.exported_files)
        except Cancelled:
            self.cancelled.emit(self.exported_files)
        except Exception as exc:
            self.error.emit(
                f"{public_error(exc)}\n{len(self.exported_files)} completed files kept. Reselect unfinished playlists to retry."
            )
