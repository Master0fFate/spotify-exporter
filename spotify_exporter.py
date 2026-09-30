"""
An advanced application for exporting Spotify playlists
"""

import argparse
import configparser
import logging
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import spotipy
from PyQt6.QtCore import (
    QSettings,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QCursor,
    QFont,
    QMouseEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    ComboBox,
    LineEdit,
    ListWidget,
    PasswordLineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SimpleCardWidget,
    Theme,
    setTheme,
    setThemeColor,
)

from exporter import __version__
from exporter.api import SpotifyReader
from exporter.auth import REDIRECT_URI, SCOPE
from exporter.logging_utils import protect_transport_logs
from exporter.models import Playlist
from exporter.workers import ExportWorker, LoginWorker, TaskWorker


# ==================== Constants ====================
class Constants:
    """Application constants"""

    APP_NAME = "Spotify Exporter"
    APP_VERSION = __version__
    CONFIG_FILE = "config.ini"
    REDIRECT_URI = REDIRECT_URI
    SPOTIFY_SCOPE = SCOPE

    # Modern Color Palette
    PRIMARY = "#1DB954"
    PRIMARY_HOVER = "#1ed760"
    PRIMARY_DARK = "#169c46"
    PRIMARY_LIGHT = "#22d962"

    BACKGROUND = "#0a0a0a"
    SURFACE = "#181818"
    SURFACE_LIGHT = "#282828"
    CARD = "#1e1e1e"
    CARD_HOVER = "#252525"

    TEXT_PRIMARY = "#FFFFFF"
    TEXT_SECONDARY = "#b3b3b3"
    TEXT_TERTIARY = "#6a6a6a"

    BORDER = "#2a2a2a"
    BORDER_HOVER = "#404040"

    ERROR = "#f03c4b"
    SUCCESS = "#1DB954"
    WARNING = "#ffa726"
    INFO = "#29b6f6"


class ExportFormat(Enum):
    """Export format enumeration"""

    DISCORD = ("discord", "Discord", "#29b6f6")
    CSV = ("csv", "CSV", "#1DB954")
    JSON = ("json", "JSON", "#ffa726")
    TXT = ("txt", "TXT", "#b3b3b3")
    MARKDOWN = ("md", "Markdown", "#1DB954")

    def __init__(self, value, display_name, color):
        self._value_ = value
        self.display_name = display_name
        self.color = color


# ==================== Configuration Manager ====================
class ConfigManager:
    """Manages application configuration"""

    def __init__(self):
        self.config = configparser.ConfigParser()
        self.settings = QSettings("SpotifyExporter", "Settings")

    def load_credentials(self) -> Optional[Dict[str, str]]:
        client_id = self.get_setting("client_id", "")
        if not client_id and Path(Constants.CONFIG_FILE).is_file():
            # Read only the public ID from old installs; never reuse the secret.
            try:
                legacy = configparser.ConfigParser(interpolation=None)
                legacy.read(Constants.CONFIG_FILE, encoding="utf-8")
                client_id = legacy.get("SPOTIFY", "client_id", fallback="")
            except (configparser.Error, OSError):
                pass
        return {"client_id": client_id} if client_id else None

    def save_credentials(self, client_id: str) -> None:
        self.set_setting("client_id", client_id)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.settings.value(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self.settings.setValue(key, value)


# Libraries never write logs or credentials as an import side effect.
logger = logging.getLogger(__name__)


# ==================== Custom Title Bar ====================
class CustomTitleBar(QWidget):
    """Custom title bar with window controls"""

    def __init__(self, parent: QMainWindow):
        super().__init__(parent)
        self.parent_window = parent
        self.start_pos = None
        self.pressing = False

        self.setFixedHeight(50)
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 10, 0)
        layout.setSpacing(15)

        self.title_label = QLabel(Constants.APP_NAME)
        self.title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {Constants.TEXT_PRIMARY};")

        version_badge = QLabel(f"v{Constants.APP_VERSION}")
        version_badge.setFixedSize(45, 22)
        version_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_badge.setStyleSheet(f"""
            background-color: {Constants.PRIMARY};
            color: white;
            border-radius: 11px;
            font-size: 9px;
            font-weight: 600;
            padding: 2px 8px;
        """)

        layout.addWidget(self.title_label)
        layout.addWidget(version_badge)
        layout.addStretch()

        self.minimize_btn = self.create_control_button("−", Constants.INFO)
        self.maximize_btn = self.create_control_button("□", Constants.WARNING)
        self.close_btn = self.create_control_button("×", Constants.ERROR)

        self.minimize_btn.clicked.connect(self.parent_window.showMinimized)
        self.maximize_btn.clicked.connect(self.toggle_maximize)
        self.close_btn.clicked.connect(self.parent_window.close)

        layout.addWidget(self.minimize_btn)
        layout.addWidget(self.maximize_btn)
        layout.addWidget(self.close_btn)

        self.setStyleSheet(f"""
            CustomTitleBar {{
                background-color: {Constants.SURFACE};
                border-bottom: 1px solid {Constants.BORDER};
            }}
        """)

    def create_control_button(self, text: str, color: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedSize(40, 32)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Constants.TEXT_SECONDARY};
                border: none;
                font-size: 18px;
                font-weight: bold;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {color};
                color: white;
            }}
        """)
        return btn

    def toggle_maximize(self):
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
        else:
            self.parent_window.showMaximized()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_pos = event.globalPosition().toPoint()
            self.pressing = True

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.pressing and self.start_pos:
            self.parent_window.move(
                self.parent_window.pos() + event.globalPosition().toPoint() - self.start_pos
            )
            self.start_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.pressing = False

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.toggle_maximize()


# ==================== Modern Widgets ====================
class Card(SimpleCardWidget):
    """Modern card widget using qfluentwidgets"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_style()

    def setup_style(self):
        # Additional custom style if needed, SimpleCardWidget already handles most
        pass


class FormatButton(SimpleCardWidget):
    clicked = pyqtSignal()

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if (
            self.isEnabled()
            and e.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(e.pos())
        ):
            self.clicked.emit()

    def keyPressEvent(self, event):
        if self.isEnabled() and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)

    """Export format button with colored indicator"""

    def __init__(self, format_type: ExportFormat, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"Export {format_type.display_name}")
        self.format_type = format_type
        self.setup_ui()
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(20, 16, 20, 16)

        indicator = QFrame()
        indicator.setFixedSize(40, 4)
        indicator.setStyleSheet(f"""
            background-color: {self.format_type.color};
            border-radius: 2px;
        """)

        name_label = QLabel(self.format_type.display_name)
        name_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        type_label = QLabel(f".{self.format_type.value}")
        type_label.setFont(QFont("Segoe UI", 10))
        type_label.setStyleSheet(f"color: {Constants.TEXT_SECONDARY};")
        type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(indicator, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)
        layout.addWidget(type_label)

        self.setFixedSize(140, 100)


# ==================== Export Worker ====================


# ==================== Login Window ====================
class LoginWindow(QDialog):
    """Modern login window"""

    login_successful = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f"{Constants.APP_NAME} - Login")
        self.setMinimumSize(550, 550)
        self.setModal(True)

        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(15, 15, 15, 15)

        container = Card()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(45, 35, 45, 35)
        main_layout.setSpacing(20)

        title_bar = QWidget()
        title_bar.setFixedHeight(50)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(0, 0, 0, 10)
        title_layout.setSpacing(0)

        dialog_title = QLabel("Connect to Spotify")
        dialog_title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        dialog_title.setStyleSheet(f"color: {Constants.TEXT_PRIMARY};")

        close_btn = QPushButton("×")
        close_btn.setFixedSize(36, 36)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.clicked.connect(self.reject)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {Constants.TEXT_SECONDARY};
                border: none;
                font-size: 28px;
                font-weight: bold;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {Constants.ERROR};
                color: white;
            }}
        """)

        title_layout.addWidget(dialog_title)
        title_layout.addStretch()
        title_layout.addWidget(close_btn)

        subtitle = QLabel(
            "Connect securely in your browser. Only your public Client ID is needed; tokens stay in memory."
        )
        subtitle.setFont(QFont("Segoe UI", 11))
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {Constants.TEXT_SECONDARY};")

        id_section = QWidget()
        id_layout = QVBoxLayout(id_section)
        id_layout.setSpacing(8)
        id_layout.setContentsMargins(0, 0, 0, 0)

        id_label = QLabel("Client ID")
        id_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        id_label.setStyleSheet(f"color: {Constants.TEXT_PRIMARY};")

        self.id_input = LineEdit()
        self.id_input.setPlaceholderText("Enter your Spotify Client ID")
        self.id_input.setMinimumHeight(45)
        self.id_input.setFont(QFont("Segoe UI", 11))

        id_layout.addWidget(id_label)
        id_layout.addWidget(self.id_input)

        saved = self.config_manager.load_credentials()
        if saved:
            self.id_input.setText(saved["client_id"])
        self.login_worker = None
        self.connected_client = None
        self.close_after_cancel = False

        help_label = QLabel(
            '<a href="https://developer.spotify.com/dashboard" '
            f'style="color: {Constants.PRIMARY}; text-decoration: none; font-size: 11px;">'
            "Need credentials? Get them from Spotify Developer Dashboard →</a>"
        )
        help_label.setOpenExternalLinks(True)
        help_label.setMinimumHeight(30)
        help_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setSpacing(12)
        button_layout.setContentsMargins(0, 10, 0, 0)

        self.cancel_btn = PushButton("Cancel")
        self.cancel_btn.setMinimumHeight(48)
        self.cancel_btn.setMinimumWidth(120)
        self.cancel_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.cancel_btn.clicked.connect(self.reject)

        self.login_btn = PrimaryPushButton("Connect")
        self.login_btn.setMinimumHeight(48)
        self.login_btn.setMinimumWidth(120)
        self.login_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.login_btn.clicked.connect(self.attempt_login)
        self.login_btn.setDefault(True)

        button_layout.addWidget(self.cancel_btn, stretch=1)
        button_layout.addWidget(self.login_btn, stretch=1)

        main_layout.addWidget(title_bar)
        main_layout.addWidget(subtitle)
        main_layout.addSpacing(10)
        main_layout.addWidget(id_section)
        notice = QLabel(
            "Redirect URI: http://127.0.0.1:8888/callback\nExisting config.ini and .cache files are not used for secrets.\nRemove old credential files yourself after upgrading."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(f"color: {Constants.TEXT_SECONDARY};")
        main_layout.addWidget(notice)
        main_layout.addSpacing(5)
        main_layout.addWidget(help_label)
        main_layout.addStretch()
        main_layout.addWidget(button_container)

        outer_layout.addWidget(container)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Constants.BACKGROUND};
                border: 1px solid {Constants.BORDER};
                border-radius: 8px;
            }}
        """)

    def attempt_login(self):
        if self.login_worker and self.login_worker.isRunning():
            return
        client_id = self.id_input.text().strip()
        if not re.fullmatch(r"[A-Za-z0-9]{32}", client_id):
            QMessageBox.warning(
                self,
                "Client ID",
                "Enter the 32-character Client ID from Spotify Developer Dashboard.",
            )
            return
        self.login_btn.setEnabled(False)
        self.login_btn.setText("Waiting for browser...")
        self.id_input.setEnabled(False)
        self.connected_client = None
        self.close_after_cancel = False
        self.login_worker = LoginWorker(client_id, self)
        self.login_worker.succeeded.connect(self.on_connected)
        self.login_worker.failed.connect(self.login_failed)
        self.login_worker.finished.connect(self.login_stopped)
        self.login_worker.start()

    def login_failed(self, message):
        if not self.close_after_cancel:
            QMessageBox.critical(self, "Connection failed", message)

    def on_connected(self, client):
        if self.close_after_cancel:
            return
        self.connected_client = client
        self.config_manager.save_credentials(self.id_input.text().strip())

    def login_stopped(self):
        if self.login_worker is not None:
            self.login_worker.deleteLater()
            self.login_worker = None
        self.login_btn.setEnabled(True)
        self.login_btn.setText("Connect")
        self.id_input.setEnabled(True)
        if self.close_after_cancel:
            super().reject()
        elif self.connected_client is not None:
            self.login_successful.emit(self.connected_client)
            self.accept()

    def reject(self):
        self.close_after_cancel = True
        if self.login_worker and self.login_worker.isRunning():
            self.login_worker.cancel()
            self.login_btn.setText("Cancelling...")
            return
        super().reject()

    def closeEvent(self, event):
        if self.login_worker and self.login_worker.isRunning():
            self.reject()
            event.ignore()
        else:
            self.reject()
            event.accept()


# ==================== Settings Dialog ====================
class SettingsDialog(QDialog):
    """Settings dialog"""

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Settings")
        self.setFixedSize(550, 400)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(25, 25, 25, 25)

        title = QLabel("Settings")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))

        export_group = Card()
        export_layout = QVBoxLayout(export_group)
        export_layout.setContentsMargins(20, 20, 20, 20)
        export_layout.setSpacing(12)

        group_title = QLabel("Export Location")
        group_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))

        location_layout = QHBoxLayout()
        self.location_input = LineEdit()
        current_location = self.config_manager.get_setting(
            "export_location", str(Path.home() / "Downloads")
        )
        self.location_input.setText(current_location)

        browse_btn = PushButton("Browse")
        browse_btn.clicked.connect(self.browse_export_location)

        location_layout.addWidget(self.location_input, stretch=1)
        location_layout.addWidget(browse_btn)

        export_layout.addWidget(group_title)
        export_layout.addLayout(location_layout)

        layout.addWidget(title)
        layout.addWidget(export_group)
        layout.addWidget(QLabel("Spotify API mode"))
        self.api_mode = ComboBox()
        self.api_mode.addItems(
            ["Current API (default)", "Legacy /tracks (extended-quota apps only)"]
        )
        self.api_mode.setCurrentIndex(
            1 if self.config_manager.get_setting("api_mode", "current") == "legacy" else 0
        )
        layout.addWidget(self.api_mode)
        layout.addStretch()

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = PushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        save_btn = PrimaryPushButton("Save Changes")
        save_btn.clicked.connect(self.save_settings)

        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Constants.BACKGROUND};
            }}
            QLabel {{
                color: {Constants.TEXT_PRIMARY};
            }}
        """)

    def browse_export_location(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select Export Location", self.location_input.text()
        )
        if directory:
            self.location_input.setText(directory)

    def save_settings(self):
        self.config_manager.set_setting("export_location", self.location_input.text())
        self.config_manager.set_setting(
            "api_mode", "legacy" if self.api_mode.currentIndex() else "current"
        )
        self.accept()


# ==================== Main Window ====================
class MainWindow(QMainWindow):
    """Modern main window with custom title bar"""

    def __init__(self, sp: spotipy.Spotify):
        super().__init__()
        self.sp = sp
        self.config_manager = ConfigManager()
        self.playlists: List[Playlist] = []
        self.worker: Optional[ExportWorker] = None
        self.load_worker = None

        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)

        self.init_ui()
        self.load_playlists()

    def init_ui(self):
        self.setMinimumSize(1100, 750)

        container = QWidget()
        self.setCentralWidget(container)

        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self)
        main_layout.addWidget(self.title_bar)

        content = QWidget()
        content.setObjectName("exportContent")
        content.setStyleSheet(
            f"QWidget#exportContent {{ background-color: {Constants.BACKGROUND}; }}"
        )
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(30, 25, 30, 25)
        content_layout.setSpacing(20)

        header = self.create_header()
        content_layout.addWidget(header)

        search_section = self.create_search_section()
        content_layout.addWidget(search_section)

        playlist_section = self.create_playlist_section()
        content_layout.addWidget(playlist_section, stretch=1)

        export_section = self.create_export_section()
        content_layout.addWidget(export_section)

        progress_section = self.create_progress_section()
        content_layout.addWidget(progress_section)

        content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        main_layout.addWidget(scroll, stretch=1)

        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(f"""
            QStatusBar {{
                background-color: {Constants.SURFACE};
                color: {Constants.TEXT_SECONDARY};
                border-top: 1px solid {Constants.BORDER};
                padding: 8px 30px;
            }}
        """)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {Constants.BACKGROUND};
            }}
            QLabel {{
                color: {Constants.TEXT_PRIMARY};
            }}
        """)

    def create_header(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        title_section = QWidget()
        title_layout = QVBoxLayout(title_section)
        title_layout.setSpacing(8)
        title_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Playlist Library")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))

        subtitle = QLabel("Manage and export your Spotify playlists")
        subtitle.setFont(QFont("Segoe UI", 12))
        subtitle.setStyleSheet(f"color: {Constants.TEXT_SECONDARY};")

        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)

        settings_btn = PushButton("Settings")
        settings_btn.clicked.connect(self.show_settings)

        refresh_btn = PushButton("Refresh")
        refresh_btn.clicked.connect(self.load_playlists)

        action_layout.addWidget(settings_btn)
        action_layout.addWidget(refresh_btn)

        layout.addWidget(title_section)
        layout.addStretch()
        layout.addLayout(action_layout)

        return container

    def create_search_section(self) -> QWidget:
        container = Card()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(20, 20, 20, 20)

        layout = QHBoxLayout()
        layout.setSpacing(15)

        search_container = QWidget()
        search_layout = QVBoxLayout(search_container)
        search_layout.setSpacing(8)
        search_layout.setContentsMargins(0, 0, 0, 0)

        search_label = QLabel("Search")
        search_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

        self.search_input = LineEdit()
        self.search_input.setPlaceholderText("Search playlists...")
        self.search_input.textChanged.connect(self.filter_playlists)

        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)

        sort_container = QWidget()
        sort_layout = QVBoxLayout(sort_container)
        sort_layout.setSpacing(8)
        sort_layout.setContentsMargins(0, 0, 0, 0)

        sort_label = QLabel("Sort By")
        sort_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

        self.sort_combo = ComboBox()
        self.sort_combo.addItems(["Name (A-Z)", "Name (Z-A)", "Most Tracks", "Least Tracks"])
        self.sort_combo.currentIndexChanged.connect(self.sort_playlists)
        self.sort_combo.setFixedWidth(200)

        sort_layout.addWidget(sort_label)
        sort_layout.addWidget(self.sort_combo)

        layout.addWidget(search_container, stretch=1)
        layout.addWidget(sort_container)

        container_layout.addLayout(layout)

        return container

    def create_playlist_section(self) -> QWidget:
        container = Card()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header_layout = QHBoxLayout()

        section_title = QLabel("Your Playlists")
        section_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))

        self.playlist_count_label = QLabel("0 playlists")
        self.playlist_count_label.setStyleSheet(f"color: {Constants.TEXT_SECONDARY};")

        select_layout = QHBoxLayout()
        select_layout.setSpacing(5)

        select_all_btn = PushButton("Select All")
        select_all_btn.clicked.connect(self.select_all_playlists)

        deselect_all_btn = PushButton("Deselect All")
        deselect_all_btn.clicked.connect(self.deselect_all_playlists)

        select_layout.addWidget(select_all_btn)
        select_layout.addWidget(deselect_all_btn)

        header_layout.addWidget(section_title)
        header_layout.addWidget(self.playlist_count_label)
        header_layout.addStretch()
        header_layout.addLayout(select_layout)

        self.playlist_list = ListWidget()
        self.playlist_list.setMinimumHeight(160)
        self.playlist_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.playlist_list.itemSelectionChanged.connect(self.update_selection_count)

        layout.addLayout(header_layout)
        layout.addWidget(self.playlist_list)

        return container

    def create_export_section(self) -> QWidget:
        container = Card()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)

        title = QLabel("Export Options")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))

        location_container = QWidget()
        location_layout = QVBoxLayout(location_container)
        location_layout.setSpacing(10)
        location_layout.setContentsMargins(0, 0, 0, 0)

        location_label = QLabel("Export Location")
        location_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        location_input_layout = QHBoxLayout()
        self.location_input = LineEdit()
        default_location = self.config_manager.get_setting(
            "export_location", str(Path.home() / "Downloads")
        )
        self.location_input.setText(default_location)

        browse_btn = PushButton("Browse")
        browse_btn.clicked.connect(self.browse_export_location)

        location_input_layout.addWidget(self.location_input, stretch=1)
        location_input_layout.addWidget(browse_btn)

        location_layout.addWidget(location_label)
        location_layout.addLayout(location_input_layout)

        webhook_container = QWidget()
        webhook_layout = QVBoxLayout(webhook_container)
        webhook_layout.setSpacing(10)
        webhook_layout.setContentsMargins(0, 0, 0, 0)

        webhook_label = QLabel("Discord Webhook (optional)")
        webhook_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        self.webhook_input = PasswordLineEdit()
        self.webhook_input.setPlaceholderText("Paste webhook URL for Discord export")

        webhook_layout.addWidget(webhook_label)
        webhook_layout.addWidget(self.webhook_input)

        format_label = QLabel("Select Export Format")
        format_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        formats_layout = QHBoxLayout()
        formats_layout.setSpacing(12)

        self.csv_btn = FormatButton(ExportFormat.CSV)
        self.json_btn = FormatButton(ExportFormat.JSON)
        self.txt_btn = FormatButton(ExportFormat.TXT)
        self.md_btn = FormatButton(ExportFormat.MARKDOWN)
        self.discord_btn = FormatButton(ExportFormat.DISCORD)

        for btn in [self.csv_btn, self.json_btn, self.txt_btn, self.md_btn, self.discord_btn]:
            formats_layout.addWidget(btn)

        self.csv_btn.clicked.connect(lambda: self.start_export(ExportFormat.CSV))
        self.json_btn.clicked.connect(lambda: self.start_export(ExportFormat.JSON))
        self.txt_btn.clicked.connect(lambda: self.start_export(ExportFormat.TXT))
        self.md_btn.clicked.connect(lambda: self.start_export(ExportFormat.MARKDOWN))
        self.discord_btn.clicked.connect(lambda: self.start_export(ExportFormat.DISCORD))

        layout.addWidget(title)
        layout.addWidget(location_container)
        layout.addWidget(webhook_container)
        layout.addSpacing(5)
        layout.addWidget(format_label)
        layout.addLayout(formats_layout)

        return container

    def create_progress_section(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        self.progress_bar = ProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(38)

        controls_layout = QHBoxLayout()

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"color: {Constants.TEXT_SECONDARY};")
        self.progress_label.setVisible(False)

        self.cancel_btn = PushButton("Cancel")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_export)

        controls_layout.addWidget(self.progress_label)
        controls_layout.addStretch()
        controls_layout.addWidget(self.cancel_btn)

        layout.addWidget(self.progress_bar)
        layout.addLayout(controls_layout)

        return container

    def load_playlists(self):
        if (self.load_worker and self.load_worker.isRunning()) or (
            self.worker and self.worker.isRunning()
        ):
            return
        self.status_bar.showMessage("Loading playlists...")
        self.disable_export_buttons()
        self.load_worker = TaskWorker(
            lambda cancel: SpotifyReader(self.sp, cancel).playlists(), self
        )
        self.load_worker.succeeded.connect(self.playlists_loaded)
        self.load_worker.failed.connect(self.playlists_failed)
        self.load_worker.finished.connect(self.load_stopped)
        self.load_worker.start()

    def load_stopped(self):
        if self.load_worker is not None:
            self.load_worker.deleteLater()
            self.load_worker = None
        self.enable_export_buttons()

    def playlists_loaded(self, playlists):
        self.playlists = playlists
        self.render_playlists(set())
        self.update_playlist_count()
        self.sort_playlists()
        self.status_bar.showMessage(f"Loaded {len(playlists)} playlists", 3000)

    def playlists_failed(self, message):
        QMessageBox.critical(self, "Unable to load playlists", message)
        self.status_bar.showMessage("Load failed; use Refresh to retry")

    def render_playlists(self, selected_ids):
        self.playlist_list.clear()
        for playlist in self.playlists:
            item = QListWidgetItem(f"{playlist.name} • {playlist.track_count} items")
            item.setData(Qt.ItemDataRole.UserRole, playlist.id)
            item.setToolTip(f"Owner: {playlist.owner}\n{playlist.description}")
            self.playlist_list.addItem(item)
            item.setSelected(playlist.id in selected_ids)
        self.filter_playlists()

    def filter_playlists(self):
        search_text = self.search_input.text().lower()

        for i in range(self.playlist_list.count()):
            item = self.playlist_list.item(i)
            playlist = self.playlists[i]

            visible = (
                search_text in playlist.name.lower()
                or search_text in playlist.owner.lower()
                or search_text in playlist.description.lower()
            )

            item.setHidden(not visible)

    def sort_playlists(self):
        selected_ids = {
            item.data(Qt.ItemDataRole.UserRole) for item in self.playlist_list.selectedItems()
        }
        sort_type = self.sort_combo.currentIndex()
        key = (lambda p: p.name.casefold()) if sort_type < 2 else (lambda p: p.track_count)
        self.playlists.sort(key=key, reverse=sort_type in (1, 2))
        self.render_playlists(selected_ids)

    def select_all_playlists(self):
        for i in range(self.playlist_list.count()):
            item = self.playlist_list.item(i)
            if not item.isHidden():
                item.setSelected(True)

    def deselect_all_playlists(self):
        self.playlist_list.clearSelection()

    def update_playlist_count(self):
        total = len(self.playlists)
        self.playlist_count_label.setText(f"{total} playlist{'s' if total != 1 else ''}")

    def update_selection_count(self):
        selected = len(self.playlist_list.selectedItems())
        if selected > 0:
            self.status_bar.showMessage(
                f"{selected} playlist{'s' if selected != 1 else ''} selected"
            )
        else:
            self.status_bar.showMessage("Ready")

    def browse_export_location(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Select Export Location", self.location_input.text()
        )
        if directory:
            self.location_input.setText(directory)
            self.config_manager.set_setting("export_location", directory)

    def start_export(self, export_format: ExportFormat):
        if (self.worker and self.worker.isRunning()) or (
            self.load_worker and self.load_worker.isRunning()
        ):
            return
        selected_items = [
            item for item in self.playlist_list.selectedItems() if not item.isHidden()
        ]
        if not selected_items:
            QMessageBox.warning(
                self, "No Selection", "Please select at least one playlist to export."
            )
            return

        export_location = self.location_input.text()
        if not export_location or not Path(export_location).is_dir():
            QMessageBox.warning(self, "Invalid Location", "Please select a valid export location.")
            return

        if export_format == ExportFormat.DISCORD:
            webhook_url = self.webhook_input.text().strip()
            if not webhook_url:
                QMessageBox.warning(self, "Missing Webhook", "Please enter a Discord webhook URL.")
                return
        else:
            webhook_url = ""

        selected_playlists = []
        for item in selected_items:
            index = self.playlist_list.row(item)
            selected_playlists.append(self.playlists[index])

        total_tracks = sum(p.track_count for p in selected_playlists)
        response = QMessageBox.question(
            self,
            "Confirm Export",
            f"Export {len(selected_playlists)} playlist{'s' if len(selected_playlists) != 1 else ''} "
            f"({total_tracks} total tracks) to {export_format.display_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if response != QMessageBox.StandardButton.Yes:
            return

        self.show_progress(True)
        self.disable_export_buttons()

        self.worker = ExportWorker(
            export_format=export_format,
            playlists=selected_playlists,
            sp=self.sp,
            output_dir=export_location,
            webhook_url=webhook_url,
            legacy=self.config_manager.get_setting("api_mode", "current") == "legacy",
        )

        self.worker.progress.connect(self.update_progress)
        self.worker.completed.connect(self.export_finished)
        self.worker.cancelled.connect(self.export_cancelled)
        self.worker.finished.connect(self.export_stopped)
        self.worker.error.connect(self.export_error)
        self.worker.start()

        logger.info(f"Started export: {len(selected_playlists)} playlists to {export_format.value}")

    def show_progress(self, show: bool):
        self.progress_bar.setVisible(show)
        self.progress_label.setVisible(show)
        self.cancel_btn.setVisible(show)
        if not show:
            self.progress_bar.setValue(0)
            self.progress_label.setText("")

    def disable_export_buttons(self):
        for btn in [self.csv_btn, self.json_btn, self.txt_btn, self.md_btn, self.discord_btn]:
            btn.setEnabled(False)

    def enable_export_buttons(self):
        for btn in [self.csv_btn, self.json_btn, self.txt_btn, self.md_btn, self.discord_btn]:
            btn.setEnabled(True)

    def update_progress(self, value: int, message: str):
        self.progress_bar.setValue(value)
        self.progress_label.setText(message)
        self.status_bar.showMessage(message)

    def export_finished(self, exported_files: List[str]):
        self.show_progress(False)

        if exported_files:
            file_list = "\n".join([f"• {Path(f).name}" for f in exported_files[:10]])
            if len(exported_files) > 10:
                file_list += f"\n... and {len(exported_files) - 10} more"

            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported {len(exported_files)} file{'s' if len(exported_files) != 1 else ''}:\n\n{file_list}",
            )
        else:
            QMessageBox.information(self, "Export Complete", "Export completed successfully!")

        self.status_bar.showMessage("Export completed", 5000)
        logger.info(f"Export completed: {len(exported_files)} files")

    def export_error(self, error_message: str):
        self.show_progress(False)

        QMessageBox.critical(
            self, "Export Failed", f"An error occurred during export:\n\n{error_message}"
        )

        self.status_bar.showMessage("Export failed")
        logger.error(f"Export failed: {error_message}")

    def cancel_export(self):
        if self.worker and self.worker.isRunning():
            response = QMessageBox.question(
                self,
                "Cancel Export",
                "Are you sure you want to cancel the export?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if response == QMessageBox.StandardButton.Yes:
                self.worker.cancel()
                self.cancel_btn.setEnabled(False)
                self.status_bar.showMessage("Cancelling after the current request...")
                logger.info("Export cancelled by user")

    def export_cancelled(self, files):
        self.status_bar.showMessage(
            f"Cancelled. {len(files)} completed files kept. Discord messages already sent cannot be recalled."
        )

    def export_stopped(self):
        self.show_progress(False)
        self.cancel_btn.setEnabled(True)
        self.enable_export_buttons()

    def closeEvent(self, event):
        active = [
            worker for worker in (self.worker, self.load_worker) if worker and worker.isRunning()
        ]
        if active:
            for worker in active:
                worker.cancel()
            self.status_bar.showMessage(
                "Stopping background requests. Close again once they finish."
            )
            event.ignore()
        else:
            event.accept()

    def show_settings(self):
        dialog = SettingsDialog(self.config_manager, self)
        if dialog.exec():
            self.location_input.setText(
                self.config_manager.get_setting("export_location", str(Path.home() / "Downloads"))
            )


# ==================== Main Application ====================
def main(argv=None):
    """Main application entry point, with a credential-free package smoke mode."""
    parser = argparse.ArgumentParser(
        description="Export Spotify playlist metadata from the desktop."
    )
    parser.add_argument("--version", action="version", version=Constants.APP_VERSION)
    parser.add_argument(
        "--smoke-test", action="store_true", help="Run offline UI/export checks without login"
    )
    parser.add_argument("--smoke-report", help="Write the offline smoke result to this JSON file")
    args = parser.parse_args(argv)
    if args.smoke_test and not args.smoke_report:
        parser.error("--smoke-test requires --smoke-report PATH")
    if args.smoke_report and not args.smoke_test:
        parser.error("--smoke-report requires --smoke-test")
    protect_transport_logs()
    app = QApplication([sys.argv[0]])
    app.setApplicationName(Constants.APP_NAME)
    app.setApplicationVersion(Constants.APP_VERSION)
    app.setFont(QFont("Segoe UI", 10))

    # Set Fluent Theme to Dark and Accent Color to Spotify Green
    setTheme(Theme.DARK)
    setThemeColor(Constants.PRIMARY)

    if args.smoke_test:
        from exporter.smoke import run_smoke_test

        sys.exit(run_smoke_test(app, args.smoke_report))

    # Keep references for the entire application lifetime.
    windows = {}

    def show_main_window(sp):
        windows["main"] = MainWindow(sp)
        windows["main"].show()

    windows["login"] = LoginWindow()
    windows["login"].login_successful.connect(show_main_window)
    windows["login"].show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
