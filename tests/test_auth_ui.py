from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCloseEvent

from exporter.api import ExportError
from exporter.auth import SCOPE, callback_code
from exporter.models import Playlist
from exporter.workers import ExportWorker, TaskWorker
from spotify_exporter import ConfigManager, ExportFormat, LoginWindow, MainWindow, SettingsDialog


def test_callback_requires_state_and_path():
    assert callback_code("/callback?state=expected&code=example", "expected") == "example"
    for path in [
        "/callback?state=wrong&code=example",
        "/other?state=expected&code=example",
        "/callback?state=expected",
    ]:
        with pytest.raises(ValueError):
            callback_code(path, "expected")
    with pytest.raises(ExportError, match="declined"):
        callback_code("/callback?state=expected&error=access_denied", "expected")
    assert SCOPE == "playlist-read-private playlist-read-collaborative"


def test_configuration_saves_no_client_secret(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = ConfigManager()
    config.save_credentials("public_id")
    assert config.load_credentials() == {"client_id": "public_id"}
    assert not (tmp_path / "config.ini").exists()
    assert not config.settings.contains("client_secret")
    config.settings.clear()


def test_legacy_config_only_imports_public_id(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.ini").write_text(
        "[SPOTIFY]\nclient_id=legacy_id\nclient_secret=do_not_reuse\n"
    )
    config = ConfigManager()
    config.settings.clear()
    assert config.load_credentials() == {"client_id": "legacy_id"}
    assert "do_not_reuse" in (tmp_path / "config.ini").read_text()


def test_dialogs_construct_without_authentication(app):
    login = LoginWindow()
    settings = SettingsDialog(ConfigManager())
    assert not hasattr(login, "secret_input")
    assert settings.api_mode.count() == 2
    login.close()
    settings.close()


@pytest.fixture
def window(app, monkeypatch):
    monkeypatch.setattr(MainWindow, "load_playlists", lambda self: None)
    view = MainWindow(Mock())
    yield view
    view.worker = None
    view.load_worker = None
    view.close()


def test_sort_preserves_identity_for_duplicate_names(window):
    window.playlists = [Playlist("b", "Same", 5, "owner"), Playlist("a", "Same", 1, "owner")]
    window.render_playlists({"b"})
    window.sort_combo.setCurrentIndex(3)
    window.sort_playlists()
    assert [i.data(Qt.ItemDataRole.UserRole) for i in window.playlist_list.selectedItems()] == ["b"]


def test_sort_keeps_filter(window):
    window.playlists = [Playlist("a", "Visible", 1, "owner"), Playlist("b", "Hidden", 2, "owner")]
    window.render_playlists(set())
    window.search_input.setText("Visible")
    window.sort_playlists()
    assert sum(not window.playlist_list.item(i).isHidden() for i in range(2)) == 1


def test_close_cancels_but_does_not_destroy_active_worker(window):
    worker = Mock()
    worker.isRunning.return_value = True
    window.worker = worker
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    worker.cancel.assert_called_once()


def test_task_worker_cancellation_emits_no_success(app):
    operation = Mock()
    worker = TaskWorker(operation)
    success, cancelled = [], []
    worker.succeeded.connect(success.append)
    worker.cancelled.connect(lambda: cancelled.append(True))
    worker.cancel()
    worker.run()
    assert cancelled and not success
    operation.assert_not_called()


def test_empty_export_is_written_and_completed(app, tmp_path, monkeypatch):
    monkeypatch.setattr("exporter.workers.SpotifyReader.tracks", lambda self, _: [])
    worker = ExportWorker(ExportFormat.JSON, [Playlist("p", "empty", 0, "o")], Mock(), tmp_path)
    completed, errors = [], []
    worker.completed.connect(completed.append)
    worker.error.connect(errors.append)
    worker.run()
    assert len(completed[0]) == 1 and not errors


def test_cancelled_export_keeps_completed_files(app, tmp_path, monkeypatch):
    def tracks(reader, _):
        reader.cancel.set()
        return []

    monkeypatch.setattr("exporter.workers.SpotifyReader.tracks", tracks)
    worker = ExportWorker(ExportFormat.JSON, [Playlist("p", "empty", 0, "o")], Mock(), tmp_path)
    completed, cancelled = [], []
    worker.completed.connect(completed.append)
    worker.cancelled.connect(cancelled.append)
    worker.run()
    assert cancelled == [[]] and not completed
    assert not list(tmp_path.iterdir())


def test_repeated_export_is_ignored_while_worker_runs(window, monkeypatch):
    prompt = Mock()
    monkeypatch.setattr("spotify_exporter.QMessageBox.warning", prompt)
    window.worker = Mock()
    window.worker.isRunning.return_value = True
    window.start_export(ExportFormat.JSON)
    prompt.assert_not_called()


def test_cancel_waits_for_finished_before_enabling_controls(window, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.worker = Mock()
    window.worker.isRunning.return_value = True
    window.disable_export_buttons()
    window.cancel_export()
    window.worker.cancel.assert_called_once()
    assert not window.json_btn.isEnabled()
    window.export_stopped()
    assert window.json_btn.isEnabled() and window.cancel_btn.isEnabled()


def test_login_interruption_waits_for_worker(app):
    view = LoginWindow()
    view.login_worker = Mock()
    view.login_worker.isRunning.return_value = True
    view.reject()
    assert view.close_after_cancel
    view.login_worker.cancel.assert_called_once()
    view.login_worker.isRunning.return_value = False
    view.login_stopped()
    view.close()


def test_refresh_guard_avoids_concurrent_calls(window):
    window.load_worker = Mock()
    window.load_worker.isRunning.return_value = True
    # fixture replaces the class method; invoke its saved implementation below.
    ORIGINAL_LOAD_PLAYLISTS(window)
    window.sp.current_user_playlists.assert_not_called()


ORIGINAL_LOAD_PLAYLISTS = MainWindow.load_playlists


def test_queued_login_success_cannot_reopen_after_cancel(app):
    view = LoginWindow()
    view.login_worker = Mock()
    view.login_worker.isRunning.return_value = False
    connected = []
    view.login_successful.connect(connected.append)
    view.reject()
    view.on_connected("dummy-client")
    view.login_stopped()
    assert connected == [] and view.connected_client is None
    view.close()


def test_dependency_debug_logs_cannot_leak_credentials(caplog):
    import logging

    from exporter.logging_utils import protect_transport_logs

    protect_transport_logs()
    with caplog.at_level(logging.DEBUG):
        for name in ["spotipy.oauth2", "spotipy.client", "urllib3.connectionpool"]:
            logging.getLogger(name).debug(
                "Bearer dummy_secret code=dummy_code refresh_token=dummy_refresh"
            )
    assert "dummy_secret" not in caplog.text
    assert "dummy_code" not in caplog.text
    assert "dummy_refresh" not in caplog.text
