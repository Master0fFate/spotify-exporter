import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QSettings
from PyQt6.QtWidgets import QApplication

# Keep QApplication alive until interpreter shutdown, after all widget wrappers.
_APP = None


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path_factory.mktemp("settings")),
    )
    global _APP
    _APP = QApplication.instance() or QApplication([])
    yield _APP
    for widget in _APP.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _APP.processEvents()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Tests must not make network requests")

    monkeypatch.setattr("requests.sessions.Session.request", blocked)
    monkeypatch.setattr("webbrowser.open", blocked)
