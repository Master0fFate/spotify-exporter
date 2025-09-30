"""
An advanced application for exporting Spotify playlists
"""

import sys
import json
import csv
import os
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import configparser

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QMessageBox,
    QProgressBar, QFrame, QFileDialog, QStatusBar,
    QCheckBox, QComboBox, QDialog, QTabWidget, QListWidgetItem,
    QSizePolicy, QGroupBox, QGraphicsDropShadowEffect, QScrollArea
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QPoint, QSize, QSettings, QPropertyAnimation,
    QEasingCurve, QRect
)
from PyQt6.QtGui import (
    QFont, QColor, QIcon, QPainter, QPainterPath, QLinearGradient,
    QMouseEvent, QCursor
)


# ==================== Constants ====================
class Constants:
    """Application constants"""
    APP_NAME = "Spotify Exporter"
    APP_VERSION = "2.0"
    CONFIG_FILE = "config.ini"
    REDIRECT_URI = "http://127.0.0.1:8888/callback"
    SPOTIFY_SCOPE = "playlist-read-private playlist-read-collaborative"
    
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


# ==================== Data Classes ====================
@dataclass
class Track:
    """Track data class"""
    name: str
    artist: str
    album: str
    duration_ms: int
    url: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'artist': self.artist,
            'album': self.album,
            'duration_ms': self.duration_ms,
            'url': self.url
        }


@dataclass
class Playlist:
    """Playlist data class"""
    id: str
    name: str
    track_count: int
    owner: str
    description: str = ""


# ==================== Configuration Manager ====================
class ConfigManager:
    """Manages application configuration"""
    
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.settings = QSettings('SpotifyExporter', 'Settings')
        
    def load_credentials(self) -> Optional[Dict[str, str]]:
        if not Path(Constants.CONFIG_FILE).exists():
            return None
            
        self.config.read(Constants.CONFIG_FILE, encoding='utf-8')
        if 'SPOTIFY' not in self.config:
            return None
            
        return {
            'client_id': self.config['SPOTIFY'].get('client_id', ''),
            'client_secret': self.config['SPOTIFY'].get('client_secret', '')
        }
    
    def save_credentials(self, client_id: str, client_secret: str) -> None:
        self.config['SPOTIFY'] = {
            'client_id': client_id,
            'client_secret': client_secret
        }
        with open(Constants.CONFIG_FILE, 'w', encoding='utf-8') as configfile:
            self.config.write(configfile)
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.settings.value(key, default)
    
    def set_setting(self, key: str, value: Any) -> None:
        self.settings.setValue(key, value)


# ==================== Logger Setup ====================
def setup_logging():
    """Setup application logging with UTF-8 encoding"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    file_handler = logging.FileHandler(
        log_dir / f'spotify_exporter_{datetime.now():%Y%m%d}.log',
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    #debug stuff
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


logger = setup_logging()


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
        self.title_label.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
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
class Card(QFrame):
    """Modern card widget with shadow"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_style()
        
    def setup_style(self):
        self.setStyleSheet(f"""
            Card {{
                background-color: {Constants.CARD};
                border: 1px solid {Constants.BORDER};
                border-radius: 12px;
            }}
        """)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)


class ModernButton(QPushButton):
    """Modern button with variants"""
    
    def __init__(self, text: str, variant: str = "primary", parent=None):
        super().__init__(text, parent)
        self.variant = variant
        self.setup_style()
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
    def setup_style(self):
        if self.variant == "primary":
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Constants.PRIMARY};
                    color: white;
                    border: none;
                    padding: 12px 28px;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: {Constants.PRIMARY_HOVER};
                }}
                QPushButton:pressed {{
                    background-color: {Constants.PRIMARY_DARK};
                }}
                QPushButton:disabled {{
                    background-color: {Constants.BORDER};
                    color: {Constants.TEXT_TERTIARY};
                }}
            """)
        elif self.variant == "secondary":
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {Constants.TEXT_PRIMARY};
                    border: 2px solid {Constants.BORDER};
                    padding: 12px 28px;
                    border-radius: 8px;
                    font-weight: 600;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    border-color: {Constants.PRIMARY};
                    color: {Constants.PRIMARY};
                    background-color: {Constants.SURFACE};
                }}
                QPushButton:pressed {{
                    background-color: {Constants.CARD};
                }}
                QPushButton:disabled {{
                    border-color: {Constants.BORDER};
                    color: {Constants.TEXT_TERTIARY};
                }}
            """)
        elif self.variant == "text":
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {Constants.PRIMARY};
                    border: none;
                    padding: 8px 16px;
                    font-weight: 600;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    color: {Constants.PRIMARY_HOVER};
                    background-color: {Constants.SURFACE};
                    border-radius: 6px;
                }}
            """)


class ModernLineEdit(QLineEdit):
    """Modern input field"""
    
    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(45)
        self.setup_style()
        
    def setup_style(self):
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {Constants.SURFACE};
                color: {Constants.TEXT_PRIMARY};
                border: 2px solid {Constants.BORDER};
                padding: 12px 16px;
                border-radius: 8px;
                font-size: 13px;
                min-width: 200px;
            }}
            QLineEdit:focus {{
                border-color: {Constants.PRIMARY};
                background-color: {Constants.CARD};
            }}
            QLineEdit:disabled {{
                background-color: {Constants.SURFACE};
                color: {Constants.TEXT_TERTIARY};
            }}
        """)


class ModernListWidget(QListWidget):
    """Modern list widget"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_style()
        
    def setup_style(self):
        self.setStyleSheet(f"""
            QListWidget {{
                background-color: {Constants.SURFACE};
                color: {Constants.TEXT_PRIMARY};
                border: 1px solid {Constants.BORDER};
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 14px 12px;
                border-radius: 6px;
                margin: 2px 0;
                border: 1px solid transparent;
            }}
            QListWidget::item:hover {{
                background-color: {Constants.CARD_HOVER};
                border-color: {Constants.BORDER_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {Constants.PRIMARY};
                color: white;
                border-color: {Constants.PRIMARY};
            }}
        """)


class FormatButton(QPushButton):
    """Export format button with colored indicator"""
    
    def __init__(self, format_type: ExportFormat, parent=None):
        super().__init__(parent)
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
        name_label.setFont(QFont('Segoe UI', 12, QFont.Weight.Bold))
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        type_label = QLabel(f".{self.format_type.value}")
        type_label.setFont(QFont('Segoe UI', 10))
        type_label.setStyleSheet(f"color: {Constants.TEXT_SECONDARY};")
        type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(indicator, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)
        layout.addWidget(type_label)
        
        self.setLayout(layout)
        self.setFixedSize(140, 100)
        
        self.setStyleSheet(f"""
            FormatButton {{
                background-color: {Constants.CARD};
                border: 2px solid {Constants.BORDER};
                border-radius: 12px;
            }}
            FormatButton:hover {{
                border-color: {self.format_type.color};
                background-color: {Constants.CARD_HOVER};
            }}
            FormatButton:pressed {{
                background-color: {Constants.SURFACE};
            }}
            FormatButton:disabled {{
                opacity: 0.5;
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)


# ==================== Export Worker ====================
class ExportWorker(QThread):
    """Worker thread for exporting playlists"""
    
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    
    def __init__(self, export_format: ExportFormat, playlists: List[Playlist],
                 sp: spotipy.Spotify, output_dir: str, webhook_url: str = ""):
        super().__init__()
        self.export_format = export_format
        self.playlists = playlists
        self.sp = sp
        self.output_dir = Path(output_dir)
        self.webhook_url = webhook_url
        self._is_cancelled = False
        self.exported_files = []
        
    def cancel(self):
        self._is_cancelled = True
        
    def run(self):
        try:
            total = len(self.playlists)
            
            for i, playlist in enumerate(self.playlists):
                if self._is_cancelled:
                    logger.info("Export cancelled by user")
                    return
                    
                self.progress.emit(
                    int((i / total) * 100),
                    f"Exporting: {playlist.name}"
                )
                
                tracks = self.get_playlist_tracks(playlist.id)
                
                if not tracks:
                    logger.warning(f"No tracks found in playlist: {playlist.name}")
                    continue
                
                if self.export_format == ExportFormat.DISCORD:
                    self.export_to_discord(playlist, tracks)
                elif self.export_format == ExportFormat.CSV:
                    filepath = self.export_to_csv(playlist, tracks)
                    self.exported_files.append(filepath)
                elif self.export_format == ExportFormat.JSON:
                    filepath = self.export_to_json(playlist, tracks)
                    self.exported_files.append(filepath)
                elif self.export_format == ExportFormat.TXT:
                    filepath = self.export_to_txt(playlist, tracks)
                    self.exported_files.append(filepath)
                elif self.export_format == ExportFormat.MARKDOWN:
                    filepath = self.export_to_markdown(playlist, tracks)
                    self.exported_files.append(filepath)
                    
            self.progress.emit(100, "Export completed")
            self.finished.emit(self.exported_files)
            
        except Exception as e:
            logger.exception("Export error")
            self.error.emit(str(e))
    
    def get_playlist_tracks(self, playlist_id: str) -> List[Track]:
        """Get all tracks from a playlist with robust error handling"""
        tracks = []
        skipped_count = 0
        
        try:
            results = self.sp.playlist_tracks(playlist_id)
        except Exception as e:
            logger.error(f"Failed to fetch playlist tracks: {e}")
            return tracks
        
        while results:
            for item in results['items']:
                if self._is_cancelled:
                    return tracks
                    
                track = item.get('track')
                if not track:
                    skipped_count += 1
                    continue
                
                try:
                    track_name = track.get('name', 'Unknown Track')
                    
                    artists = track.get('artists', [])
                    if artists:
                        artist_names = ', '.join([artist.get('name', 'Unknown Artist') for artist in artists])
                    else:
                        artist_names = 'Unknown Artist'
                    
                    album = track.get('album', {})
                    album_name = album.get('name', 'Unknown Album') if album else 'Unknown Album'
                    
                    duration_ms = track.get('duration_ms', 0)
                    
                    external_urls = track.get('external_urls', {})
                    if external_urls and 'spotify' in external_urls:
                        track_url = external_urls['spotify']
                    else:
                        track_id = track.get('id', '')
                        if track_id:
                            track_url = f"https://open.spotify.com/track/{track_id}"
                        else:
                            track_url = "https://open.spotify.com"
                            logger.debug(f"No Spotify URL found for track: {track_name}")
                    
                    tracks.append(Track(
                        name=track_name,
                        artist=artist_names,
                        album=album_name,
                        duration_ms=duration_ms,
                        url=track_url
                    ))
                    
                except KeyError as e:
                    skipped_count += 1
                    logger.debug(f"Missing key {e} for track, skipping")
                    continue
                except Exception as e:
                    skipped_count += 1
                    logger.debug(f"Failed to process track: {e}")
                    continue
                    
            if results['next']:
                try:
                    results = self.sp.next(results)
                except Exception as e:
                    logger.error(f"Failed to get next page of tracks: {e}")
                    break
            else:
                break
        
        if skipped_count > 0:
            logger.info(f"Skipped {skipped_count} tracks due to missing data")
            
        return tracks
    
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe file creation"""
        # regex inv char
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
        filename = filename.strip('. ')
        return filename[:200] if filename else "playlist"
    
    def export_to_csv(self, playlist: Playlist, tracks: List[Track]) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self.sanitize_filename(playlist.name)
        filename = self.output_dir / f"{safe_name}_{timestamp}.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldfields=['name', 'artist', 'album', 'duration_ms', 'url'])
            writer.writeheader()
            writer.writerows([track.to_dict() for track in tracks])
            
        logger.info(f"Exported {len(tracks)} tracks to CSV: {filename}")
        return str(filename)
    
    def export_to_json(self, playlist: Playlist, tracks: List[Track]) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self.sanitize_filename(playlist.name)
        filename = self.output_dir / f"{safe_name}_{timestamp}.json"
        
        data = {
            'playlist': {
                'name': playlist.name,
                'owner': playlist.owner,
                'description': playlist.description,
                'track_count': len(tracks)
            },
            'tracks': [track.to_dict() for track in tracks],
            'exported_at': datetime.now().isoformat()
        }
        
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(data, jsonfile, indent=2, ensure_ascii=False)
            
        logger.info(f"Exported {len(tracks)} tracks to JSON: {filename}")
        return str(filename)
    
    def export_to_txt(self, playlist: Playlist, tracks: List[Track]) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self.sanitize_filename(playlist.name)
        filename = self.output_dir / f"{safe_name}_{timestamp}.txt"
        
        with open(filename, 'w', encoding='utf-8') as txtfile:
            txtfile.write(f"Playlist: {playlist.name}\n")
            txtfile.write(f"Owner: {playlist.owner}\n")
            txtfile.write(f"Tracks: {len(tracks)}\n")
            txtfile.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            txtfile.write("=" * 80 + "\n\n")
            
            for i, track in enumerate(tracks, 1):
                txtfile.write(f"{i}. {track.name}\n")
                txtfile.write(f"   Artist: {track.artist}\n")
                txtfile.write(f"   Album: {track.album}\n")
                txtfile.write(f"   URL: {track.url}\n\n")
                
        logger.info(f"Exported {len(tracks)} tracks to TXT: {filename}")
        return str(filename)
    
    def export_to_markdown(self, playlist: Playlist, tracks: List[Track]) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self.sanitize_filename(playlist.name)
        filename = self.output_dir / f"{safe_name}_{timestamp}.md"
        
        with open(filename, 'w', encoding='utf-8') as mdfile:
            mdfile.write(f"# {playlist.name}\n\n")
            mdfile.write(f"**Owner:** {playlist.owner}  \n")
            mdfile.write(f"**Tracks:** {len(tracks)}  \n")
            mdfile.write(f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n\n")
            
            if playlist.description:
                mdfile.write(f"*{playlist.description}*\n\n")
            
            mdfile.write("---\n\n")
            mdfile.write("## Tracks\n\n")
            
            for i, track in enumerate(tracks, 1):
                mdfile.write(f"{i}. **{track.name}** - {track.artist}  \n")
                mdfile.write(f"   *{track.album}*  \n")
                mdfile.write(f"   [Listen on Spotify]({track.url})\n\n")
                
        logger.info(f"Exported {len(tracks)} tracks to Markdown: {filename}")
        return str(filename)
    
    def export_to_discord(self, playlist: Playlist, tracks: List[Track]):
        if not self.webhook_url:
            raise ValueError("Discord webhook URL is required")
            
        header = f"**{playlist.name}**\n"
        header += f"*By {playlist.owner} • {len(tracks)} tracks*\n"
        header += "─" * 40 + "\n\n"
        
        messages = [header]
        current_message = ""
        
        for i, track in enumerate(tracks, 1):
            track_line = f"{i}. **{track.name}** - {track.artist}\n"
            
            if len(current_message) + len(track_line) > 1800:
                messages.append(current_message)
                current_message = track_line
            else:
                current_message += track_line
        
        if current_message:
            messages.append(current_message)
        
        for msg in messages:
            if self._is_cancelled:
                return
            response = requests.post(self.webhook_url, json={'content': msg})
            if response.status_code not in (200, 204):
                raise Exception(f"Failed to send to Discord: {response.status_code}")
                
        logger.info(f"Exported {len(tracks)} tracks to Discord: {playlist.name}")
    
    def get_playlist_tracks(self, playlist_id: str) -> List[Track]:
        """Get all tracks from a playlist with robust error handling"""
        tracks = []
        results = self.sp.playlist_tracks(playlist_id)
        
        while results:
            for item in results['items']:
                if self._is_cancelled:
                    return tracks
                    
                track = item.get('track')
                if not track:
                    logger.warning("Skipping item with no track data")
                    continue
                
                try:
                    track_name = track.get('name', 'Unknown Track')
                    
                    artists = track.get('artists', [])
                    if artists:
                        artist_names = ', '.join([artist.get('name', 'Unknown Artist') for artist in artists])
                    else:
                        artist_names = 'Unknown Artist'
                    
                    album = track.get('album', {})
                    album_name = album.get('name', 'Unknown Album') if album else 'Unknown Album'
                    
                    duration_ms = track.get('duration_ms', 0)
                    
                    external_urls = track.get('external_urls', {})
                    if external_urls and 'spotify' in external_urls:
                        track_url = external_urls['spotify']
                    else:
                        track_id = track.get('id', '')
                        if track_id:
                            track_url = f"https://open.spotify.com/track/{track_id}"
                        else:
                            track_url = "https://open.spotify.com"
                            logger.warning(f"No Spotify URL found for track: {track_name}")
                    
                    tracks.append(Track(
                        name=track_name,
                        artist=artist_names,
                        album=album_name,
                        duration_ms=duration_ms,
                        url=track_url
                    ))
                    
                except KeyError as e:
                    logger.warning(f"Missing key {e} for track, skipping")
                    continue
                except Exception as e:
                    logger.warning(f"Failed to process track: {e}", exc_info=True)
                    continue
                    
            if results['next']:
                results = self.sp.next(results)
            else:
                break
                
        return tracks
    
    def sanitize_filename(self, filename: str) -> str:
        """Regex filename for safe file creation"""
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
        filename = filename.strip('. ')
        return filename[:200] if filename else "playlist"
    
    def export_to_csv(self, playlist: Playlist, tracks: List[Track]) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self.sanitize_filename(playlist.name)
        filename = self.output_dir / f"{safe_name}_{timestamp}.csv"
        
        with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=['name', 'artist', 'album', 'duration_ms', 'url'])
            writer.writeheader()
            writer.writerows([track.to_dict() for track in tracks])
            
        logger.info(f"Exported to CSV: {filename}")
        return str(filename)
    
    def export_to_json(self, playlist: Playlist, tracks: List[Track]) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self.sanitize_filename(playlist.name)
        filename = self.output_dir / f"{safe_name}_{timestamp}.json"
        
        data = {
            'playlist': {
                'name': playlist.name,
                'owner': playlist.owner,
                'description': playlist.description,
                'track_count': len(tracks)
            },
            'tracks': [track.to_dict() for track in tracks],
            'exported_at': datetime.now().isoformat()
        }
        
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(data, jsonfile, indent=2, ensure_ascii=False)
            
        logger.info(f"Exported to JSON: {filename}")
        return str(filename)
    
    def export_to_txt(self, playlist: Playlist, tracks: List[Track]) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self.sanitize_filename(playlist.name)
        filename = self.output_dir / f"{safe_name}_{timestamp}.txt"
        
        with open(filename, 'w', encoding='utf-8') as txtfile:
            txtfile.write(f"Playlist: {playlist.name}\n")
            txtfile.write(f"Owner: {playlist.owner}\n")
            txtfile.write(f"Tracks: {len(tracks)}\n")
            txtfile.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            txtfile.write("=" * 80 + "\n\n")
            
            for i, track in enumerate(tracks, 1):
                txtfile.write(f"{i}. {track.name}\n")
                txtfile.write(f"   Artist: {track.artist}\n")
                txtfile.write(f"   Album: {track.album}\n")
                txtfile.write(f"   URL: {track.url}\n\n")
                
        logger.info(f"Exported to TXT: {filename}")
        return str(filename)
    
    def export_to_markdown(self, playlist: Playlist, tracks: List[Track]) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self.sanitize_filename(playlist.name)
        filename = self.output_dir / f"{safe_name}_{timestamp}.md"
        
        with open(filename, 'w', encoding='utf-8') as mdfile:
            mdfile.write(f"# {playlist.name}\n\n")
            mdfile.write(f"**Owner:** {playlist.owner}  \n")
            mdfile.write(f"**Tracks:** {len(tracks)}  \n")
            mdfile.write(f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n\n")
            
            if playlist.description:
                mdfile.write(f"*{playlist.description}*\n\n")
            
            mdfile.write("---\n\n")
            mdfile.write("## Tracks\n\n")
            
            for i, track in enumerate(tracks, 1):
                mdfile.write(f"{i}. **{track.name}** - {track.artist}  \n")
                mdfile.write(f"   *{track.album}*  \n")
                mdfile.write(f"   [Listen on Spotify]({track.url})\n\n")
                
        logger.info(f"Exported to Markdown: {filename}")
        return str(filename)
    
    def export_to_discord(self, playlist: Playlist, tracks: List[Track]):
        if not self.webhook_url:
            raise ValueError("Discord webhook URL is required")
        
        header = "─" * 40 + "\n\n"
        header += f"##{playlist.name}\n"
        header += f"*By {playlist.owner} • {len(tracks)} tracks*\n"
        header += "─" * 40 + "\n\n"
        
        messages = [header]
        current_message = ""
        
        for i, track in enumerate(tracks, 1):
            track_line = f"{i}. **{track.name}** - {track.artist}\n"
            
            if len(current_message) + len(track_line) > 1800:
                messages.append(current_message)
                current_message = track_line
            else:
                current_message += track_line
        
        if current_message:
            messages.append(current_message)
        
        for msg in messages:
            if self._is_cancelled:
                return
            response = requests.post(self.webhook_url, json={'content': msg})
            if response.status_code not in (200, 204):
                raise Exception(f"Failed to send to Discord: {response.status_code}")
                
        logger.info(f"Exported to Discord: {playlist.name}")


# ==================== Login Window ====================
class LoginWindow(QDialog):
    """Modern login window"""
    
    login_successful = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_manager = ConfigManager()
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle(f'{Constants.APP_NAME} - Login')
        self.setFixedSize(550, 520)
        self.setModal(True)
        
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
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
        dialog_title.setFont(QFont('Segoe UI', 22, QFont.Weight.Bold))
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
        
        subtitle = QLabel('Enter your Spotify Developer credentials to continue')
        subtitle.setFont(QFont('Segoe UI', 11))
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {Constants.TEXT_SECONDARY};")
        
        id_section = QWidget()
        id_layout = QVBoxLayout(id_section)
        id_layout.setSpacing(8)
        id_layout.setContentsMargins(0, 0, 0, 0)
        
        id_label = QLabel('Client ID')
        id_label.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
        id_label.setStyleSheet(f"color: {Constants.TEXT_PRIMARY};")
        
        self.id_input = ModernLineEdit('Enter your Spotify Client ID')
        self.id_input.setMinimumHeight(45)
        self.id_input.setFont(QFont('Segoe UI', 11))
        
        id_layout.addWidget(id_label)
        id_layout.addWidget(self.id_input)
        
        secret_section = QWidget()
        secret_layout = QVBoxLayout(secret_section)
        secret_layout.setSpacing(8)
        secret_layout.setContentsMargins(0, 0, 0, 0)
        
        secret_label = QLabel('Client Secret')
        secret_label.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
        secret_label.setStyleSheet(f"color: {Constants.TEXT_PRIMARY};")
        
        self.secret_input = ModernLineEdit('Enter your Spotify Client Secret')
        self.secret_input.setMinimumHeight(45)
        self.secret_input.setFont(QFont('Segoe UI', 11))
        self.secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        secret_layout.addWidget(secret_label)
        secret_layout.addWidget(self.secret_input)
        
        self.show_secret_cb = QCheckBox('Show Client Secret')
        self.show_secret_cb.setMinimumHeight(28)
        self.show_secret_cb.stateChanged.connect(self.toggle_secret_visibility)
        self.show_secret_cb.setStyleSheet(f"""
            QCheckBox {{
                color: {Constants.TEXT_SECONDARY};
                spacing: 10px;
                font-size: 11px;
            }}
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border-radius: 5px;
                border: 2px solid {Constants.BORDER};
                background-color: {Constants.SURFACE};
            }}
            QCheckBox::indicator:hover {{
                border-color: {Constants.PRIMARY};
            }}
            QCheckBox::indicator:checked {{
                background-color: {Constants.PRIMARY};
                border-color: {Constants.PRIMARY};
                image: none;
            }}
        """)
        
        help_label = QLabel(
            '<a href="https://developer.spotify.com/dashboard" '
            f'style="color: {Constants.PRIMARY}; text-decoration: none; font-size: 11px;">'
            'Need credentials? Get them from Spotify Developer Dashboard →</a>'
        )
        help_label.setOpenExternalLinks(True)
        help_label.setMinimumHeight(30)
        help_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setSpacing(12)
        button_layout.setContentsMargins(0, 10, 0, 0)
        
        self.cancel_btn = ModernButton('Cancel', variant="secondary")
        self.cancel_btn.setMinimumHeight(48)
        self.cancel_btn.setMinimumWidth(120)
        self.cancel_btn.setFont(QFont('Segoe UI', 12, QFont.Weight.Bold))
        self.cancel_btn.clicked.connect(self.reject)
        
        self.login_btn = ModernButton('Connect', variant="primary")
        self.login_btn.setMinimumHeight(48)
        self.login_btn.setMinimumWidth(120)
        self.login_btn.setFont(QFont('Segoe UI', 12, QFont.Weight.Bold))
        self.login_btn.clicked.connect(self.attempt_login)
        self.login_btn.setDefault(True)
        
        button_layout.addWidget(self.cancel_btn, stretch=1)
        button_layout.addWidget(self.login_btn, stretch=1)
        
        main_layout.addWidget(title_bar)
        main_layout.addWidget(subtitle)
        main_layout.addSpacing(10)
        main_layout.addWidget(id_section)
        main_layout.addWidget(secret_section)
        main_layout.addWidget(self.show_secret_cb)
        main_layout.addSpacing(5)
        main_layout.addWidget(help_label)
        main_layout.addStretch()
        main_layout.addWidget(button_container)
        
        outer_layout.addWidget(container)
        
        self.setStyleSheet(f"""
            QDialog {{
                background-color: transparent;
            }}
        """)
    
    def toggle_secret_visibility(self, state):
        if state == Qt.CheckState.Checked.value:
            self.secret_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.secret_input.setEchoMode(QLineEdit.EchoMode.Password)
    
    def attempt_login(self):
        client_id = self.id_input.text().strip()
        client_secret = self.secret_input.text().strip()
        
        if not client_id or not client_secret:
            QMessageBox.warning(
                self,
                'Missing Information',
                'Please provide both Client ID and Client Secret.'
            )
            return
        
        try:
            self.login_btn.setEnabled(False)
            self.login_btn.setText('Connecting...')
            QApplication.processEvents()
            
            auth_manager = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=Constants.REDIRECT_URI,
                scope=Constants.SPOTIFY_SCOPE
            )
            
            self.config_manager.save_credentials(client_id, client_secret)
            
            logger.info("Login successful")
            self.login_successful.emit()
            self.accept()
            
        except Exception as e:
            logger.exception("Login failed")
            self.login_btn.setEnabled(True)
            self.login_btn.setText('Connect')
            QMessageBox.critical(
                self,
                'Login Failed',
                f'Could not connect to Spotify:\n\n{str(e)}\n\n'
                'Please check your credentials and try again.'
            )


# ==================== Settings Dialog ====================
class SettingsDialog(QDialog):
    """Settings dialog"""
    
    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle('Settings')
        self.setFixedSize(550, 400)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(25, 25, 25, 25)
        
        title = QLabel("Settings")
        title.setFont(QFont('Segoe UI', 18, QFont.Weight.Bold))
        
        export_group = Card()
        export_layout = QVBoxLayout(export_group)
        export_layout.setContentsMargins(20, 20, 20, 20)
        export_layout.setSpacing(12)
        
        group_title = QLabel("Export Location")
        group_title.setFont(QFont('Segoe UI', 12, QFont.Weight.Bold))
        
        location_layout = QHBoxLayout()
        self.location_input = ModernLineEdit()
        current_location = self.config_manager.get_setting(
            'export_location',
            str(Path.home() / 'Downloads')
        )
        self.location_input.setText(current_location)
        
        browse_btn = ModernButton("Browse", variant="secondary")
        browse_btn.clicked.connect(self.browse_export_location)
        
        location_layout.addWidget(self.location_input, stretch=1)
        location_layout.addWidget(browse_btn)
        
        export_layout.addWidget(group_title)
        export_layout.addLayout(location_layout)
        
        layout.addWidget(title)
        layout.addWidget(export_group)
        layout.addStretch()
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = ModernButton("Cancel", variant="secondary")
        cancel_btn.clicked.connect(self.reject)
        
        save_btn = ModernButton("Save Changes", variant="primary")
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
            self,
            "Select Export Location",
            self.location_input.text()
        )
        if directory:
            self.location_input.setText(directory)
    
    def save_settings(self):
        self.config_manager.set_setting('export_location', self.location_input.text())
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
        
        main_layout.addWidget(content, stretch=1)
        
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
        self.status_bar.showMessage('Ready')
        
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
        
        title = QLabel('Playlist Library')
        title.setFont(QFont('Segoe UI', 24, QFont.Weight.Bold))
        
        subtitle = QLabel('Manage and export your Spotify playlists')
        subtitle.setFont(QFont('Segoe UI', 12))
        subtitle.setStyleSheet(f"color: {Constants.TEXT_SECONDARY};")
        
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        
        settings_btn = ModernButton('Settings', variant="text")
        settings_btn.clicked.connect(self.show_settings)
        
        refresh_btn = ModernButton('Refresh', variant="secondary")
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
        
        search_label = QLabel('Search')
        search_label.setFont(QFont('Segoe UI', 10, QFont.Weight.Bold))
        
        self.search_input = ModernLineEdit('Search playlists...')
        self.search_input.textChanged.connect(self.filter_playlists)
        
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        
        sort_container = QWidget()
        sort_layout = QVBoxLayout(sort_container)
        sort_layout.setSpacing(8)
        sort_layout.setContentsMargins(0, 0, 0, 0)
        
        sort_label = QLabel('Sort By')
        sort_label.setFont(QFont('Segoe UI', 10, QFont.Weight.Bold))
        
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(['Name (A-Z)', 'Name (Z-A)', 'Most Tracks', 'Least Tracks'])
        self.sort_combo.currentIndexChanged.connect(self.sort_playlists)
        self.sort_combo.setFixedWidth(200)
        self.sort_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {Constants.SURFACE};
                color: {Constants.TEXT_PRIMARY};
                border: 2px solid {Constants.BORDER};
                padding: 12px 16px;
                border-radius: 8px;
            }}
            QComboBox:hover {{
                border-color: {Constants.PRIMARY};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 10px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {Constants.CARD};
                color: {Constants.TEXT_PRIMARY};
                selection-background-color: {Constants.PRIMARY};
                border: 1px solid {Constants.BORDER};
                border-radius: 8px;
                padding: 5px;
            }}
        """)
        
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
        
        section_title = QLabel('Your Playlists')
        section_title.setFont(QFont('Segoe UI', 14, QFont.Weight.Bold))
        
        self.playlist_count_label = QLabel('0 playlists')
        self.playlist_count_label.setStyleSheet(f"color: {Constants.TEXT_SECONDARY};")
        
        select_layout = QHBoxLayout()
        select_layout.setSpacing(5)
        
        select_all_btn = ModernButton('Select All', variant="text")
        select_all_btn.clicked.connect(self.select_all_playlists)
        
        deselect_all_btn = ModernButton('Deselect All', variant="text")
        deselect_all_btn.clicked.connect(self.deselect_all_playlists)
        
        select_layout.addWidget(select_all_btn)
        select_layout.addWidget(deselect_all_btn)
        
        header_layout.addWidget(section_title)
        header_layout.addWidget(self.playlist_count_label)
        header_layout.addStretch()
        header_layout.addLayout(select_layout)
        
        self.playlist_list = ModernListWidget()
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
        
        title = QLabel('Export Options')
        title.setFont(QFont('Segoe UI', 14, QFont.Weight.Bold))
        
        location_container = QWidget()
        location_layout = QVBoxLayout(location_container)
        location_layout.setSpacing(10)
        location_layout.setContentsMargins(0, 0, 0, 0)
        
        location_label = QLabel('Export Location')
        location_label.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
        
        location_input_layout = QHBoxLayout()
        self.location_input = ModernLineEdit()
        default_location = self.config_manager.get_setting(
            'export_location',
            str(Path.home() / 'Downloads')
        )
        self.location_input.setText(default_location)
        
        browse_btn = ModernButton('Browse', variant="secondary")
        browse_btn.clicked.connect(self.browse_export_location)
        
        location_input_layout.addWidget(self.location_input, stretch=1)
        location_input_layout.addWidget(browse_btn)
        
        location_layout.addWidget(location_label)
        location_layout.addLayout(location_input_layout)
        
        webhook_container = QWidget()
        webhook_layout = QVBoxLayout(webhook_container)
        webhook_layout.setSpacing(10)
        webhook_layout.setContentsMargins(0, 0, 0, 0)
        
        webhook_label = QLabel('Discord Webhook (optional)')
        webhook_label.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
        
        self.webhook_input = ModernLineEdit('Paste webhook URL for Discord export')
        
        webhook_layout.addWidget(webhook_label)
        webhook_layout.addWidget(self.webhook_input)
        
        format_label = QLabel('Select Export Format')
        format_label.setFont(QFont('Segoe UI', 11, QFont.Weight.Bold))
        
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
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(38)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 2px solid {Constants.BORDER};
                border-radius: 8px;
                text-align: center;
                color: {Constants.TEXT_PRIMARY};
                background-color: {Constants.SURFACE};
                font-weight: 600;
            }}
            QProgressBar::chunk {{
                background-color: {Constants.PRIMARY};
                border-radius: 6px;
            }}
        """)
        
        controls_layout = QHBoxLayout()
        
        self.progress_label = QLabel('')
        self.progress_label.setStyleSheet(f"color: {Constants.TEXT_SECONDARY};")
        self.progress_label.setVisible(False)
        
        self.cancel_btn = ModernButton('Cancel', variant="secondary")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_export)
        
        controls_layout.addWidget(self.progress_label)
        controls_layout.addStretch()
        controls_layout.addWidget(self.cancel_btn)
        
        layout.addWidget(self.progress_bar)
        layout.addLayout(controls_layout)
        
        return container
    
    def load_playlists(self):
        try:
            self.status_bar.showMessage('Loading playlists...')
            self.playlists.clear()
            self.playlist_list.clear()
            
            results = self.sp.current_user_playlists()
            while results:
                for item in results['items']:
                    playlist = Playlist(
                        id=item['id'],
                        name=item['name'],
                        track_count=item['tracks']['total'],
                        owner=item['owner']['display_name'],
                        description=item.get('description', '')
                    )
                    self.playlists.append(playlist)
                    
                    list_item = QListWidgetItem(f"{playlist.name} • {playlist.track_count} tracks")
                    list_item.setToolTip(
                        f"Owner: {playlist.owner}\n"
                        f"Tracks: {playlist.track_count}\n"
                        f"Description: {playlist.description or 'No description'}"
                    )
                    self.playlist_list.addItem(list_item)
                
                if results['next']:
                    results = self.sp.next(results)
                else:
                    break
            
            self.update_playlist_count()
            self.status_bar.showMessage(f'Loaded {len(self.playlists)} playlists', 3000)
            logger.info(f"Loaded {len(self.playlists)} playlists")
            
        except Exception as e:
            logger.exception("Failed to load playlists")
            QMessageBox.critical(self, 'Error', f'Failed to load playlists:\n\n{str(e)}')
            self.status_bar.showMessage('Failed to load playlists')
    
    def filter_playlists(self):
        search_text = self.search_input.text().lower()
        
        for i in range(self.playlist_list.count()):
            item = self.playlist_list.item(i)
            playlist = self.playlists[i]
            
            visible = (
                search_text in playlist.name.lower() or
                search_text in playlist.owner.lower() or
                search_text in playlist.description.lower()
            )
            
            item.setHidden(not visible)
    
    def sort_playlists(self):
        sort_type = self.sort_combo.currentIndex()
        
        if sort_type == 0:  # Name A-Z
            self.playlists.sort(key=lambda p: p.name.lower())
        elif sort_type == 1:  # Name Z-A
            self.playlists.sort(key=lambda p: p.name.lower(), reverse=True)
        elif sort_type == 2:  # Most tracks
            self.playlists.sort(key=lambda p: p.track_count, reverse=True)
        elif sort_type == 3:  # Least tracks
            self.playlists.sort(key=lambda p: p.track_count)
        
        selected_names = [self.playlists[self.playlist_list.row(item)].name 
                         for item in self.playlist_list.selectedItems()]
        
        self.playlist_list.clear()
        for playlist in self.playlists:
            list_item = QListWidgetItem(f"{playlist.name} • {playlist.track_count} tracks")
            list_item.setToolTip(
                f"Owner: {playlist.owner}\n"
                f"Tracks: {playlist.track_count}\n"
                f"Description: {playlist.description or 'No description'}"
            )
            
            if playlist.name in selected_names:
                list_item.setSelected(True)
            
            self.playlist_list.addItem(list_item)
    
    def select_all_playlists(self):
        for i in range(self.playlist_list.count()):
            item = self.playlist_list.item(i)
            if not item.isHidden():
                item.setSelected(True)
    
    def deselect_all_playlists(self):
        self.playlist_list.clearSelection()
    
    def update_playlist_count(self):
        total = len(self.playlists)
        self.playlist_count_label.setText(f'{total} playlist{"s" if total != 1 else ""}')
    
    def update_selection_count(self):
        selected = len(self.playlist_list.selectedItems())
        if selected > 0:
            self.status_bar.showMessage(f'{selected} playlist{"s" if selected != 1 else ""} selected')
        else:
            self.status_bar.showMessage('Ready')
    
    def browse_export_location(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Export Location",
            self.location_input.text()
        )
        if directory:
            self.location_input.setText(directory)
            self.config_manager.set_setting('export_location', directory)
    
    def start_export(self, export_format: ExportFormat):
        selected_items = self.playlist_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, 'No Selection', 'Please select at least one playlist to export.')
            return
        
        export_location = self.location_input.text()
        if not export_location or not Path(export_location).exists():
            QMessageBox.warning(self, 'Invalid Location', 'Please select a valid export location.')
            return
        
        if export_format == ExportFormat.DISCORD:
            webhook_url = self.webhook_input.text().strip()
            if not webhook_url:
                QMessageBox.warning(self, 'Missing Webhook', 'Please enter a Discord webhook URL.')
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
            'Confirm Export',
            f'Export {len(selected_playlists)} playlist{"s" if len(selected_playlists) != 1 else ""} '
            f'({total_tracks} total tracks) to {export_format.display_name}?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
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
            webhook_url=webhook_url
        )
        
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.export_finished)
        self.worker.error.connect(self.export_error)
        self.worker.start()
        
        logger.info(f"Started export: {len(selected_playlists)} playlists to {export_format.value}")
    
    def show_progress(self, show: bool):
        self.progress_bar.setVisible(show)
        self.progress_label.setVisible(show)
        self.cancel_btn.setVisible(show)
        if not show:
            self.progress_bar.setValue(0)
            self.progress_label.setText('')
    
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
        self.enable_export_buttons()
        
        if exported_files:
            file_list = '\n'.join([f'• {Path(f).name}' for f in exported_files[:10]])
            if len(exported_files) > 10:
                file_list += f'\n... and {len(exported_files) - 10} more'
            
            QMessageBox.information(
                self,
                'Export Complete',
                f'Successfully exported {len(exported_files)} file{"s" if len(exported_files) != 1 else ""}:\n\n{file_list}'
            )
        else:
            QMessageBox.information(self, 'Export Complete', 'Export completed successfully!')
        
        self.status_bar.showMessage('Export completed', 5000)
        logger.info(f"Export completed: {len(exported_files)} files")
    
    def export_error(self, error_message: str):
        self.show_progress(False)
        self.enable_export_buttons()
        
        QMessageBox.critical(self, 'Export Failed', f'An error occurred during export:\n\n{error_message}')
        
        self.status_bar.showMessage('Export failed')
        logger.error(f"Export failed: {error_message}")
    
    def cancel_export(self):
        if self.worker and self.worker.isRunning():
            response = QMessageBox.question(
                self,
                'Cancel Export',
                'Are you sure you want to cancel the export?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if response == QMessageBox.StandardButton.Yes:
                self.worker.cancel()
                self.show_progress(False)
                self.enable_export_buttons()
                self.status_bar.showMessage('Export cancelled')
                logger.info("Export cancelled by user")
    
    def show_settings(self):
        dialog = SettingsDialog(self.config_manager, self)
        if dialog.exec():
            self.location_input.setText(
                self.config_manager.get_setting('export_location', str(Path.home() / 'Downloads'))
            )


# ==================== Main Application ====================
def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName(Constants.APP_NAME)
    app.setApplicationVersion(Constants.APP_VERSION)
    app.setFont(QFont('Segoe UI', 10))
    
    config_manager = ConfigManager()
    
    def create_spotify_client(credentials: Dict[str, str]) -> spotipy.Spotify:
        auth_manager = SpotifyOAuth(
            client_id=credentials['client_id'],
            client_secret=credentials['client_secret'],
            redirect_uri=Constants.REDIRECT_URI,
            scope=Constants.SPOTIFY_SCOPE
        )
        return spotipy.Spotify(auth_manager=auth_manager)
    
    def show_main_window(sp: spotipy.Spotify):
        main_window = MainWindow(sp)
        main_window.show()
    
    credentials = config_manager.load_credentials()
    
    if credentials:
        try:
            sp = create_spotify_client(credentials)
            show_main_window(sp)
        except Exception as e:
            logger.exception("Failed to authenticate with saved credentials")
            if Path(Constants.CONFIG_FILE).exists():
                Path(Constants.CONFIG_FILE).unlink()
            
            login_window = LoginWindow()
            
            def on_login_success():
                credentials = config_manager.load_credentials()
                sp = create_spotify_client(credentials)
                show_main_window(sp)
            
            login_window.login_successful.connect(on_login_success)
            login_window.show()
    else:
        login_window = LoginWindow()
        
        def on_login_success():
            credentials = config_manager.load_credentials()
            sp = create_spotify_client(credentials)
            show_main_window(sp)
        
        login_window.login_successful.connect(on_login_success)
        login_window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()