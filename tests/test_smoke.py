import json

from exporter.smoke import run_smoke_test


def test_offline_package_smoke(app, tmp_path):
    report = tmp_path / "report.json"
    assert run_smoke_test(app, report) == 0
    data = json.loads(report.read_text())
    assert data["status"] == "passed"
    assert data["version"] == "3.0.0"
    assert data["network"] == "blocked"
    assert data["export_formats"] == 4


def test_source_smoke_does_not_need_optional_qt_stacks(tmp_path):
    import subprocess
    import sys

    report = tmp_path / "without-media.json"
    program = """
import importlib.abc
import sys
class BlockOptionalQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        forbidden = ('qfluentwidgets.multimedia', 'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets',
                     'PyQt6.QtPdf', 'PyQt6.QtPdfWidgets', 'win32ui', 'pywin', 'pythonwin')
        if any(fullname == name or fullname.startswith(name + '.') for name in forbidden):
            raise ModuleNotFoundError('Optional media/PDF/Pythonwin stack deliberately unavailable')
sys.meta_path.insert(0, BlockOptionalQt())
import spotify_exporter
spotify_exporter.main(['--smoke-test', '--smoke-report', sys.argv[1]])
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(report)], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(report.read_text())["status"] == "passed"


def test_repeated_gui_and_active_worker_exit_in_subprocess(tmp_path):
    import subprocess
    import sys

    program = """
import sys
from pathlib import Path
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication
from exporter.smoke import OfflineSpotify, run_smoke_test
from exporter.workers import TaskWorker
from spotify_exporter import MainWindow
app = QApplication([])
for index in range(3):
    assert run_smoke_test(app, Path(sys.argv[1]) / f'repeated-{index}.json') == 0
# A genuine running QThread must stop before its window is destroyed.
view = MainWindow(OfflineSpotify())
original = view.load_worker
assert original.wait(2000)
app.processEvents()
worker = TaskWorker(lambda stop: stop.wait(5), view)
view.load_worker = worker
worker.finished.connect(view.load_stopped)
late_success = []
worker.succeeded.connect(late_success.append)
view.show()
worker.start()
view.close()
assert worker.wait(2000)
app.processEvents()
assert late_success == []
assert view.load_worker is None
view.close()
view.deleteLater()
QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
app.processEvents()
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(tmp_path)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert len(list(tmp_path.glob("repeated-*.json"))) == 3
