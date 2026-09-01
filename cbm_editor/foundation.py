#!/usr/bin/env python3
#no more billion line monolith! yay!
import sys
import gc
import urllib.request
import urllib.parse
import os
import json
import shutil
import subprocess
import math
import time
import threading
import _bisect as bisect
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Set
from .bass_audio import BassError, get_audio_engine, shutdown_audio_engine
if sys.platform.startswith("win"):
    import winreg
import re
import webbrowser
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["QT_QPA_UPDATE_IDLE_TIME"] = "0"
os.environ.pop("QT_FFMPEG_DEBUG", None)
_qt_logging_rules = os.environ.get("QT_LOGGING_RULES", "")
_video_logging_rules = "qt.multimedia.ffmpeg.*=false;*.multimedia.ffmpeg.*=false"
os.environ["QT_LOGGING_RULES"] = (
    f"{_qt_logging_rules};{_video_logging_rules}"
    if _qt_logging_rules
    else _video_logging_rules
)
import numpy as np

from PyQt6.QtCore import Qt, QTimer, QPointF, QElapsedTimer, QRectF, pyqtSignal, QThread, QEvent, QPoint, QSize, QByteArray, QMutex, QWaitCondition, QLineF, QObject, QItemSelectionModel
from PyQt6.QtGui import QPainter, QColor, QPen, QKeyEvent, QBrush, QWheelEvent, QMouseEvent, QIcon, QPixmap, QImage, QImageReader, QSurfaceFormat, QRegion, QPainterPath, QPolygonF, QLinearGradient, QFontMetrics, QFont, QFontDatabase
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QSpinBox,
    QDoubleSpinBox, QComboBox, QGroupBox, QFormLayout, QGridLayout,
    QMessageBox, QButtonGroup, QSlider, QDialog, QScrollBar,
    QSizePolicy, QListWidget, QListWidgetItem, QScrollArea, QCheckBox,
    QProgressBar, QAbstractSpinBox,
    QAbstractItemView, QListView, QStackedWidget,
    QStyledItemDelegate, QStyle, QStyleOptionButton, QStyleOptionComboBox
)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

ANIMATED_PUSH_BUTTON_CLASS = None

def get_base_path():
    if os.path.exists('/.flatpak-info') or os.environ.get('FLATPAK_ID'):
        return "/app/share/cbm-editor"
    return str(Path(__file__).resolve().parent)

def is_packaged_application():
    if getattr(sys, "frozen", False):
        return True
    try:
        return bool(__compiled__)
    except NameError:
        return False

def get_application_executable_path():
    candidates = []
    if sys.argv:
        candidates.append(sys.argv[0])
    candidates.append(sys.executable)
    seen = set()
    for candidate in candidates:
        try:
            path = Path(candidate).resolve()
            key = os.path.normcase(str(path))
            if key in seen or not path.is_file():
                continue
            seen.add(key)
            with path.open("rb") as handle:
                header = handle.read(4)
            if sys.platform.startswith("win") and header.startswith(b"MZ"):
                return path
            if sys.platform.startswith("linux") and header == b"\x7fELF":
                return path
        except Exception:
            continue
    return None

def install_application_fonts(app):
    if not sys.platform.startswith("linux"):
        return
    font_directory = Path(get_base_path()) / "fonts"
    loaded_families = []
    for filename in ("selawk.ttf", "selawkb.ttf", "selawkl.ttf", "selawksb.ttf", "selawksl.ttf"):
        font_id = QFontDatabase.addApplicationFont(str(font_directory / filename))
        if font_id >= 0:
            loaded_families.extend(QFontDatabase.applicationFontFamilies(font_id))
    family = next((name for name in loaded_families if name.lower() == "selawik"), None)
    if family:
        font = app.font()
        font.setFamily(family)
        app.setFont(font)

DIFFICULTIES = ["Beginner", "Normal", "Hard", "Expert", "UNBEATABLE", "Star"]
LANE_HEIGHT = 100
TIMELINE_START_X = 150
VERSION_NUMBER = "v2.0-pre1"
TARGET_FPS = 0
PREVIEW_VERSION = os.environ.get("CBM_EDITOR_EDITION", "preview").strip().lower() != "release"
BEATMAP_BACKUP_LIMIT = 200
BEATMAP_BACKUP_EXTENSION = ".backup"
BEATMAP_BACKUP_TIMESTAMP_PATTERN = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})(?:_(\d+))?$"
)

SHARED_GLOBAL_NAMES = (
    "TARGET_FPS",
    "ACCENT_COLOR",
    "ACCENT_HOVER",
    "ACCENT_PRESSED",
    "ACCENT_BORDER",
    "ACCENT_RGBA_15",
    "BASE_APP_STYLESHEET",
    "BASE_WINDOW_STYLESHEET",
)
SHARED_GLOBAL_MODULES = []

def register_shared_globals(namespace):
    if not any(existing is namespace for existing in SHARED_GLOBAL_MODULES):
        SHARED_GLOBAL_MODULES.append(namespace)
    for name in SHARED_GLOBAL_NAMES:
        if name in globals():
            namespace[name] = globals()[name]

def sync_shared_globals():
    for namespace in SHARED_GLOBAL_MODULES:
        for name in SHARED_GLOBAL_NAMES:
            if name in globals():
                namespace[name] = globals()[name]

def set_target_fps(value):
    global TARGET_FPS
    TARGET_FPS = value
    sync_shared_globals()

def format_editor_timestamp(milliseconds, include_milliseconds=False, force_hours=False, pad_minutes=True):
    sign = "-" if milliseconds < 0 else ""
    total_milliseconds = int(abs(milliseconds))
    hours = total_milliseconds // 3600000
    minutes = (total_milliseconds % 3600000) // 60000
    total_minutes = total_milliseconds // 60000
    seconds = (total_milliseconds % 60000) // 1000
    remainder = total_milliseconds % 1000
    if force_hours or hours > 0:
        hour_text = f"{hours:02d}" if pad_minutes else str(hours)
        result = f"{hour_text}:{minutes:02d}:{seconds:02d}"
    else:
        minute_text = f"{total_minutes:02d}" if pad_minutes else str(total_minutes)
        result = f"{minute_text}:{seconds:02d}"
    if include_milliseconds:
        result = f"{result}:{remainder:03d}"
    return f"{sign}{result}"

def get_beatmap_backup_directory(project_folder, difficulty):
    safe_difficulty = re.sub(r'[<>:"/\\|?*]', '_', str(difficulty))
    return Path(project_folder) / "cbm_files" / "beatmap_backups" / safe_difficulty

def list_beatmap_backups(project_folder, difficulty):
    backup_directory = get_beatmap_backup_directory(project_folder, difficulty)
    if not backup_directory.is_dir():
        return []
    backups = []
    for path in backup_directory.iterdir():
        if path.is_file() and path.suffix.lower() == BEATMAP_BACKUP_EXTENSION:
            backups.append(path)
    def sort_key(path):
        match = BEATMAP_BACKUP_TIMESTAMP_PATTERN.search(path.stem)
        if match:
            timestamp_parts = match.groups()
            sequence = int(timestamp_parts[6] or 0)
            return (1, *timestamp_parts[:6], sequence)
        try:
            return (0, path.stat().st_mtime_ns)
        except OSError:
            return (0, 0)
    backups.sort(key=sort_key, reverse=True)
    return backups

def create_beatmap_backup(project_folder, difficulty, filename):
    source_path = Path(project_folder) / Path(filename).name
    if not source_path.is_file():
        return None
    try:
        backup_directory = get_beatmap_backup_directory(project_folder, difficulty)
        backup_directory.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        backup_stem = f"{source_path.stem}_{timestamp}"
        backup_name = f"{backup_stem}{BEATMAP_BACKUP_EXTENSION}"
        backup_path = backup_directory / backup_name
        sequence = 2
        while backup_path.exists():
            backup_name = f"{backup_stem}_{sequence}{BEATMAP_BACKUP_EXTENSION}"
            backup_path = backup_directory / backup_name
            sequence += 1
        temporary_path = backup_directory / f".{backup_name}.tmp"
        try:
            shutil.copy2(source_path, temporary_path)
            os.replace(temporary_path, backup_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        backups = list_beatmap_backups(project_folder, difficulty)
        for expired_backup in backups[BEATMAP_BACKUP_LIMIT:]:
            expired_backup.unlink()
        return backup_path
    except Exception as e:
        print(f"Error creating beatmap backup: {e}")
        return None

def get_beatmap_backup_timestamp_parts(backup_path):
    match = BEATMAP_BACKUP_TIMESTAMP_PATTERN.search(Path(backup_path).stem)
    if match:
        return match.groups()[:6]
    fallback = time.localtime(Path(backup_path).stat().st_mtime)
    return (
        time.strftime("%Y", fallback),
        time.strftime("%m", fallback),
        time.strftime("%d", fallback),
        time.strftime("%H", fallback),
        time.strftime("%M", fallback),
        time.strftime("%S", fallback),
    )

def format_beatmap_backup_timestamp(backup_path):
    year, month, day, hour, minute, second = get_beatmap_backup_timestamp_parts(backup_path)
    return f"{day}.{month}.{year} - {hour}:{minute}:{second}"

def load_scaled_display_pixmap(path, widget, target_width, target_height):
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    source_size = reader.size()
    dpr = max(1.0, float(widget.devicePixelRatioF() if widget else 1.0))
    target_width = max(1, int(round(float(target_width) * dpr)))
    target_height = max(1, int(round(float(target_height) * dpr)))
    if source_size.isValid():
        scale = max(
            target_width / max(1, source_size.width()),
            target_height / max(1, source_size.height()),
        )
        if scale > 0.0:
            reader.setScaledSize(QSize(
                max(1, int(math.ceil(source_size.width() * scale))),
                max(1, int(math.ceil(source_size.height() * scale))),
            ))
    image = reader.read()
    if image.isNull():
        return None
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap if not pixmap.isNull() else None

def apply_bg_image_with_blur(src_path, dst_path, blur_val):
    if not os.path.exists(src_path): return
    try:
        if blur_val > 0:
            from PIL import Image, ImageFilter
            img = Image.open(src_path)
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            img = img.filter(ImageFilter.GaussianBlur(radius=blur_val))
            img.save(dst_path)
        else:
            shutil.copy2(src_path, dst_path)
    except Exception as e:
        print(f"Error applying bg image: {e}")

DEFAULT_ACCENT_COLOR = "#DBC93B" if PREVIEW_VERSION else "#DB3B6C"

ACCENT_COLOR = DEFAULT_ACCENT_COLOR
ACCENT_HOVER = "#ebd849" if PREVIEW_VERSION else "#E85080"
ACCENT_PRESSED = "#c2b234" if PREVIEW_VERSION else "#C03060"
ACCENT_BORDER = "#fff291" if PREVIEW_VERSION else "#FF88AA"
ACCENT_RGBA_15 = "rgba(219, 201, 59, 0.15)" if PREVIEW_VERSION else "rgba(219, 59, 108, 0.15)"

def apply_accent_color(accent_hex=None):
    global ACCENT_COLOR, ACCENT_HOVER, ACCENT_PRESSED, ACCENT_BORDER, ACCENT_RGBA_15, UI_THEME, BASE_APP_STYLESHEET, BASE_WINDOW_STYLESHEET
    if not accent_hex or not isinstance(accent_hex, str) or not QColor(accent_hex).isValid():
        accent_hex = DEFAULT_ACCENT_COLOR

    qcol = QColor(accent_hex)
    ACCENT_COLOR = qcol.name().upper()
    ACCENT_HOVER = qcol.lighter(115).name()
    ACCENT_PRESSED = qcol.darker(115).name()
    ACCENT_BORDER = qcol.lighter(130).name()
    ACCENT_RGBA_15 = f"rgba({qcol.red()}, {qcol.green()}, {qcol.blue()}, 0.15)"

    if 'UI_THEME' in globals():
        UI_THEME["accent"] = ACCENT_COLOR
        UI_THEME["accent_hover"] = ACCENT_HOVER
        UI_THEME["accent_pressed"] = ACCENT_PRESSED
        UI_THEME["selection_bg"] = ACCENT_COLOR

    if 'get_base_app_stylesheet' in globals():
        BASE_APP_STYLESHEET = get_base_app_stylesheet()
    if 'get_base_window_stylesheet' in globals():
        BASE_WINDOW_STYLESHEET = get_base_window_stylesheet()

    sync_shared_globals()
    return ACCENT_COLOR

COLOR_PALETTE = {
    "Cyan (Note)": "#64C8FF",
    "Yellow (Spike)": "#e0c61d",
    "Red (Hold)": "#FF3232",
    "Light Red (Hold Line)": "#FF5050",
    "Pale Yellow (Flip)": "#FFFF64",
    "Deep Blue (Toggle/Hit)": "#0064FF",
    "Black (Hide/Final)": "#000000",
    "Green (Double)": "#00FF00",
    "Dark Green (Double Line)": "#00C800",
    "Orange (Spam)": "#FFA500",
    "Dark Orange (Spam Line)": "#FF8C00",
    "White (Fly in marker)": "#FFFFFF",
    "Slate Blue (Direction Left Lane)": "#231E44",
    "Signature Pink (Direction Right Lane)": "#491424",
    "Purple (Toggle Center)": "#400040",
    "Bright Slate Blue": "#6A5ACD",
    "Bright Signature Pink": "#DB3B6C",
    "Bright Purple": "#800080",
    "Dark Gray (Normal Lane)": "#2D2D32",
    "Gray": "#808080",
    "Purple (Freestyle)": "#800080",
    "Royal Blue (Brawl Hold)": "#4169E1",
    "Dark Royal Blue (Brawl Hold Line)": "#2E4A9E",
    "Orange Red (Brawl Spam)": "#FF4500",
    "Dark Orange Red (Brawl Spam Line)": "#CC3700",
    "Pink": "#FFC0CB",
    "Teal": "#008080",
    "Lime": "#00FF00",
    "Brown": "#A52A2A",
    "Navy": "#000080",
    "Gold": "#FFD700",
    "Maroon": "#800000",
    "Coral": "#FF7F50",
    "Indigo": "#4B0082",
    "Turquoise": "#40E0D0",
    "Vibrant Violet": "#8A2BE2",
    "Mint Green": "#98FF98",
    "Deep Rose": "#C71585",
    "Sky Blue": "#87CEEB",
    "Peach": "#FFDAB9",
    "Steel Blue": "#4682B4",
    "Lemon Yellow": "#FFFACD",
    "Magenta": "#FF32FF",
    "Pale Cyan": "#ABE1FF",
    "Yellow": "#FFFF00",
    "Blue": "#0000FF"
}

DEFAULT_COLORS = {
    "normal_lane": "Dark Gray (Normal Lane)",
    "direction_left": "Slate Blue (Direction Left Lane)",
    "direction_right": "Signature Pink (Direction Right Lane)",
    "direction_left_event": "Bright Slate Blue",
    "direction_right_event": "Bright Signature Pink",
    "toggle_center": "Bright Purple",
    "note": "Cyan (Note)",
    "spike": "Yellow (Spike)",
    "hold": "Red (Hold)",
    "hold_line": "Light Red (Hold Line)",
    "double": "Green (Double)",
    "double_line": "Dark Green (Double Line)",
    "spam": "Orange (Spam)",
    "spam_line": "Dark Orange (Spam Line)",
    "freestyle": "Purple (Freestyle)",
    "brawl_hold": "Royal Blue (Brawl Hold)",
    "brawl_hold_line": "Dark Royal Blue (Brawl Hold Line)",
    "brawl_spam": "Orange Red (Brawl Spam)",
    "brawl_spam_line": "Dark Orange Red (Brawl Spam Line)",
    "brawl_knockout": "Black (Hide/Final)",
    "brawl_hit": "Deep Blue (Toggle/Hit)",
    "fly_in_marker": "White (Fly in marker)",
    "hide_marker": "Black (Hide/Final)"
}

DEFAULT_KEYBINDS = {
    "play_pause": "Space",
    "jump_start": "Shift+Space",
    "jump_end": "Ctrl+Space",
    "switch_meta_timing": "Tab",
    "invert_scroll": False,
    "timeline_left": "Left",
    "timeline_right": "Right",
    "multiselect_modifier": "Shift",
    "faster_modifier": "Shift",
    "modify_note_modifier": "Ctrl",
    "range_select_modifier": "Alt",
    "range_select_type_modifier": "Ctrl+Alt",
    "tab_note": "Ctrl+1",
    "tab_brawl": "Ctrl+2",
    "tab_event": "Ctrl+3",
    "smooth_placement": "G",
    "triplet_toggle": "T",
    "grid_half": "E",
    "grid_double": "R",
    "toggle_metronome": "M",
    "toggle_video_preview": "V"
}

def make_hsv_color(h, s, v):
    safe_h = 0 if h < 0 else (int(h) % 360)
    safe_s = max(0, min(255, int(s)))
    safe_v = max(0, min(255, int(v)))
    return QColor.fromHsv(safe_h, safe_s, safe_v)

class ColorSpectrumBox(QWidget):
    colorPicked = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(140)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.hue = 0
        self.sat = 255
        self.val = 255
        self.is_dragging = False

    def set_color_hsv(self, h, s, v):
        self.hue = 0 if h < 0 else (int(h) % 360)
        self.sat = max(0, min(255, int(s)))
        self.val = max(0, min(255, int(v)))
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.update_from_mouse(event.position())

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            self.update_from_mouse(event.position())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False

    def update_from_mouse(self, pos):
        w = max(1, self.width())
        h = max(1, self.height())
        x = max(0, min(w, pos.x()))
        y = max(0, min(h, pos.y()))
        self.sat = int((x / w) * 255)
        self.val = int((1.0 - (y / h)) * 255)
        self.update()
        self.colorPicked.emit(self.sat, self.val)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        pure_hue = make_hsv_color(self.hue, 255, 255)

        horiz_grad = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.top())
        horiz_grad.setColorAt(0.0, QColor("#FFFFFF"))
        horiz_grad.setColorAt(1.0, pure_hue)
        painter.fillRect(rect, horiz_grad)

        vert_grad = QLinearGradient(rect.left(), rect.top(), rect.left(), rect.bottom())
        vert_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        vert_grad.setColorAt(1.0, QColor(0, 0, 0, 255))
        painter.fillRect(rect, vert_grad)

        painter.setPen(QPen(QColor(UI_THEME["border_medium"]), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        sat_ratio = self.sat / 255.0
        val_ratio = (255 - self.val) / 255.0
        hx = rect.left() + sat_ratio * rect.width()
        hy = rect.top() + val_ratio * rect.height()

        painter.setPen(QPen(QColor("#FFFFFF"), 2))
        painter.drawEllipse(QPointF(hx, hy), 6, 6)
        painter.setPen(QPen(QColor("#000000"), 1))
        painter.drawEllipse(QPointF(hx, hy), 7, 7)
        painter.end()


class HueSpectrumBar(QWidget):
    hueChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hue = 0
        self.is_dragging = False

    def set_hue(self, h):
        self.hue = 0 if h < 0 else (int(h) % 360)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.update_from_mouse(event.position())

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            self.update_from_mouse(event.position())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False

    def update_from_mouse(self, pos):
        w = max(1, self.width())
        py = pos.y()
        if py < -50 or py > self.height() + 50:
            return
        px = pos.x()
        x = max(0, min(w, px))
        new_hue = int((x / w) * 359)
        new_hue = max(0, min(359, new_hue))
        if new_hue != self.hue:
            self.hue = new_hue
            self.update()
            self.hueChanged.emit(self.hue)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        grad = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.top())
        for h_step in range(0, 360, 60):
            grad.setColorAt(h_step / 360.0, make_hsv_color(h_step, 255, 255))
        grad.setColorAt(1.0, make_hsv_color(0, 255, 255))

        painter.setPen(QPen(QColor(UI_THEME["border_medium"]), 1))
        painter.setBrush(grad)
        painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 4, 4)

        hx = rect.left() + (self.hue / 359.0) * rect.width()
        hx = max(rect.left() + 2, min(rect.right() - 2, hx))
        painter.setPen(QPen(QColor("#FFFFFF"), 3))
        painter.drawLine(int(hx), rect.top() + 1, int(hx), rect.bottom() - 1)
        painter.end()


class CBMColorPickerDialog(QDialog):
    liveColorPicked = pyqtSignal(str)

    def __init__(self, initial_hex="#FFFFFF", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Object Color")
        self.setFixedWidth(400)
        
        dialog_theme = f"""
            QDialog {{
                background-color: {UI_THEME["bg_dark"]};
                color: {UI_THEME["text_primary"]};
            }}
            QLabel {{
                color: {UI_THEME["text_primary"]};
                font-family: 'Segoe UI', 'Selawik', sans-serif;
            }}
            QLineEdit {{
                background-color: {UI_THEME["button_bg"]};
                border: none;
                border-bottom: 2px solid {UI_THEME["button_depth"]};
                border-radius: 4px;
                color: {UI_THEME["text_primary"]};
                padding: 6px;
                selection-background-color: {UI_THEME["accent"]};
                selection-color: #FFFFFF;
            }}
            QLineEdit:focus {{
                border-bottom: 2px solid {UI_THEME["accent"]};
                background-color: #282828;
            }}
            QPushButton {{
                background-color: {UI_THEME["button_bg"]};
                color: {UI_THEME["text_primary"]};
                border: none;
                border-radius: 6px;
                min-height: 28px;
                font-weight: 600;
                border-bottom: 3px solid {UI_THEME["button_depth"]};
            }}
            QPushButton:hover {{
                background-color: {UI_THEME["button_hover"]};
                border-bottom-color: {UI_THEME["accent"]};
            }}
            QPushButton:pressed {{
                background-color: {UI_THEME["button_pressed"]};
                border-bottom: 0px solid transparent;
                border-top: 3px solid transparent;
            }}
        """
        self.setStyleSheet(dialog_theme)

        self.current_color = QColor(initial_hex)
        if not self.current_color.isValid():
            self.current_color = QColor("#FFFFFF")

        self.is_updating = False

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        self.preview_box = QWidget()
        self.preview_box.setFixedHeight(36)
        self.preview_box.setStyleSheet(f"background-color: {self.current_color.name()}; border: 1px solid {UI_THEME['border_medium']}; border-radius: 6px;")
        main_layout.addWidget(self.preview_box)

        tab_header_style = f"""
            QLabel {{
                background-color: {UI_THEME["bg_medium"]};
                color: {UI_THEME["accent"]};
                font-weight: 600;
                font-size: 13px;
                padding: 5px 12px;
                border: 1px solid {UI_THEME["border_medium"]};
                border-bottom: 2px solid {UI_THEME["accent"]};
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-top: 6px;
            }}
        """

        lbl_visual = QLabel("Color Picker:")
        lbl_visual.setStyleSheet(tab_header_style)
        main_layout.addWidget(lbl_visual)

        self.spectrum_box = ColorSpectrumBox(self)
        self.hue_bar = HueSpectrumBar(self)
        
        main_layout.addWidget(self.spectrum_box)
        main_layout.addWidget(self.hue_bar)

        self.spectrum_box.colorPicked.connect(self.on_spectrum_picked)
        self.hue_bar.hueChanged.connect(self.on_hue_bar_changed)

        hex_layout = QHBoxLayout()
        lbl_hex = QLabel("Hex Code:")
        lbl_hex.setStyleSheet(f"font-size: 13px; font-weight: normal; color: {UI_THEME['text_primary']};")
        self.edit_hex = QLineEdit(self.current_color.name().upper())
        self.edit_hex.setStyleSheet("font-family: monospace; font-size: 13px; font-weight: normal;")
        self.edit_hex.textChanged.connect(self.on_hex_text_changed)
        hex_layout.addWidget(lbl_hex)
        hex_layout.addWidget(self.edit_hex, stretch=1)
        main_layout.addLayout(hex_layout)

        lbl_basic = QLabel("Predefined Colors:")
        lbl_basic.setStyleSheet(tab_header_style)
        main_layout.addWidget(lbl_basic)

        object_colors = [
            ("Note", COLOR_PALETTE["Cyan (Note)"]),
            ("Spike", COLOR_PALETTE["Yellow (Spike)"]),
            ("Hold", COLOR_PALETTE["Red (Hold)"]),
            ("Hold Line", COLOR_PALETTE["Light Red (Hold Line)"]),
            ("Direction Left", COLOR_PALETTE["Slate Blue (Direction Left Lane)"]),
            ("Direction Right", COLOR_PALETTE["Signature Pink (Direction Right Lane)"]),
            ("Normal Lane", COLOR_PALETTE["Dark Gray (Normal Lane)"]),
            ("Toggle Center", COLOR_PALETTE["Purple (Toggle Center)"]),
            ("Double", COLOR_PALETTE["Green (Double)"]),
            ("Double Line", COLOR_PALETTE["Dark Green (Double Line)"]),
            ("Spam", COLOR_PALETTE["Orange (Spam)"]),
            ("Spam Line", COLOR_PALETTE["Dark Orange (Spam Line)"]),
            ("Brawl Hit", COLOR_PALETTE["Deep Blue (Toggle/Hit)"]),
            ("Brawl Knockout / Hide", COLOR_PALETTE["Black (Hide/Final)"]),
            ("Fly-in Marker", COLOR_PALETTE["White (Fly in marker)"]),
            ("Brawl Hold", COLOR_PALETTE["Royal Blue (Brawl Hold)"]),
            ("Brawl Hold Line", COLOR_PALETTE["Dark Royal Blue (Brawl Hold Line)"]),
            ("Brawl Spam", COLOR_PALETTE["Orange Red (Brawl Spam)"]),
            ("Brawl Spam Line", COLOR_PALETTE["Dark Orange Red (Brawl Spam Line)"])
        ]

        palette_grid = QGridLayout()
        palette_grid.setSpacing(6)
        
        cols = 6
        for idx, (elem_name, p_hex) in enumerate(object_colors):
            r, c = divmod(idx, cols)
            btn_swatch = QPushButton()
            btn_swatch.setFixedSize(48, 24)
            btn_swatch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn_swatch.setStyleSheet(f"""
                QPushButton {{
                    background-color: {p_hex};
                    border: 1px solid {UI_THEME["border_medium"]};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border: 2px solid #FFFFFF;
                    border-radius: 4px;
                }}
            """)
            btn_swatch.setToolTip(f"{elem_name} ({p_hex})")
            btn_swatch.clicked.connect(lambda _, hex_val=p_hex: self.set_color_from_hex(hex_val))
            palette_grid.addWidget(btn_swatch, r, c)
        main_layout.addLayout(palette_grid)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        button_class = ANIMATED_PUSH_BUTTON_CLASS or QPushButton
        ok_btn = button_class("OK")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ok_btn.setFixedHeight(32)
        ok_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel_btn = button_class("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cancel_btn.setFixedHeight(32)
        cancel_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        self.edit_hex.returnPressed.connect(self.accept)

        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout)

        self.update_ui_from_color(self.current_color)

    def get_selected_hex(self):
        return self.current_color.name().upper()

    def set_color_from_hex(self, hex_str):
        col = QColor(hex_str)
        if col.isValid():
            self.current_color = col
            self.update_ui_from_color(col)

    def on_spectrum_picked(self, sat, val):
        if self.is_updating: return
        h = self.hue_bar.hue
        col = make_hsv_color(h, sat, val)
        if col.isValid():
            self.current_color = col
            self.update_ui_from_color(col, update_spectrum=False)

    def on_hue_bar_changed(self, hue):
        if self.is_updating: return
        s = self.spectrum_box.sat
        v = self.spectrum_box.val
        self.current_hue = hue % 360
        self.spectrum_box.set_color_hsv(hue, s, v)
        col = make_hsv_color(hue, s, v)
        if col.isValid():
            self.current_color = col
            self.update_ui_from_color(col, update_spectrum=False)

    def on_hex_text_changed(self, text):
        if self.is_updating: return
        t = text.strip()
        if not t.startswith("#"): t = "#" + t
        col = QColor(t)
        if col.isValid():
            self.current_color = col
            self.update_ui_from_color(col, update_hex_text=False)

    def update_ui_from_color(self, col, update_hex_text=True, update_spectrum=True):
        self.is_updating = True
        hex_name = col.name().upper()
        
        self.preview_box.setStyleSheet(f"background-color: {hex_name}; border: 1px solid {UI_THEME['border_medium']}; border-radius: 6px;")
        self.liveColorPicked.emit(hex_name)

        if update_hex_text:
            self.edit_hex.setText(hex_name)

        h, s, v, _ = col.getHsv()
        if h >= 0:
            self.current_hue = h % 360
        else:
            h = getattr(self, 'current_hue', 0)

        if update_spectrum:
            self.hue_bar.set_hue(h)
            self.spectrum_box.set_color_hsv(h, s, v)

        self.is_updating = False


class ColorPickerButton(QPushButton):
    colorChanged = pyqtSignal(str)

    def __init__(self, color_val, default_val=None, live_preview=True, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumWidth(264)
        self.setFixedHeight(34)
        self._color_val = color_val
        self.default_val = default_val if default_val is not None else color_val
        self.live_preview = live_preview
        self.update_appearance()

        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.choose_color)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.click_timer.isActive():
                self.click_timer.start(180)
            else:
                self.click_timer.stop()
                self.reset_to_default()
        super().mouseReleaseEvent(event)

    def reset_to_default(self):
        self.set_color(self.default_val)

    def get_color(self):
        return self._color_val

    def set_color(self, new_val):
        self._color_val = new_val
        self.update_appearance()
        self.colorChanged.emit(self._color_val)

    def get_hex(self):
        if self._color_val in COLOR_PALETTE:
            return COLOR_PALETTE[self._color_val]
        if isinstance(self._color_val, str) and self._color_val.startswith("#"):
            return self._color_val.upper()
        return "#FFFFFF"

    def update_appearance(self):
        hex_code = self.get_hex()
        self.setText(f"  {hex_code}")
        brightness = 60
        current = self
        while current is not None:
            if hasattr(current, "ui_brightness"):
                brightness = max(0, min(255, int(current.ui_brightness)))
                break
            current = current.parentWidget()
        hover = min(255, brightness + 22)
        pressed = max(0, brightness - 18)
        depth = max(0, brightness - int(20 + (brightness / 255.0) * 30))
        background_hex = f"#{brightness:02x}{brightness:02x}{brightness:02x}"
        hover_hex = f"#{hover:02x}{hover:02x}{hover:02x}"
        pressed_hex = f"#{pressed:02x}{pressed:02x}{pressed:02x}"
        depth_hex = UI_THEME["button_depth"] if brightness == 60 else f"#{depth:02x}{depth:02x}{depth:02x}"
        text_hex = "#000000" if brightness > 180 else UI_THEME["text_primary"]

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {background_hex};
                color: {text_hex};
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                font-weight: 600;
                font-size: 12px;
                font-family: monospace, "Segoe UI", "Selawik", sans-serif;
                text-align: left;
                border-bottom: 3px solid {depth_hex};
            }}
            QPushButton:hover {{
                background-color: {hover_hex};
                border-bottom: 3px solid {UI_THEME["accent"]};
            }}
            QPushButton:pressed {{
                background-color: {pressed_hex};
                border-bottom: 0px solid transparent;
                border-top: 3px solid transparent;
                padding: 4px 12px;
                text-align: left;
            }}
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        hex_code = self.get_hex()
        qcol = QColor(hex_code)
        if not qcol.isValid():
            qcol = QColor("#FFFFFF")

        swatch_w, swatch_h = 26, 18
        rect_x = self.width() - swatch_w - 10
        rect_y = (self.height() - swatch_h) // 2
        
        swatch_rect = QRectF(rect_x, rect_y, swatch_w, swatch_h)
        painter.setPen(QPen(QColor(255, 255, 255, 80), 1))
        painter.setBrush(QBrush(qcol))
        painter.drawRoundedRect(swatch_rect, 4, 4)
        painter.end()

    def choose_color(self):
        curr_hex = self.get_hex()
        orig_val = self._color_val
        parent_win = self.window()
        dlg = CBMColorPickerDialog(curr_hex, parent_win)
        if self.live_preview:
            dlg.liveColorPicked.connect(self.set_color)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_hex = dlg.get_selected_hex()
            self.set_color(new_hex)
        else:
            self.set_color(orig_val)

from PyQt6.QtGui import QKeySequence

def parse_keybind(keybind_str):
    if not keybind_str or keybind_str == "None" or keybind_str is False:
        return []
    parts = [p.strip() for p in str(keybind_str).split('+') if p.strip()]
    return parts

def check_keybind_match(keybind_str, event_key=None, modifiers=None, pressed_keys=None):
    parts = parse_keybind(keybind_str)
    if not parts:
        return False
        
    pk = set(pressed_keys) if pressed_keys else set()
    if event_key is not None and event_key != Qt.Key.Key_unknown:
        pk.add(event_key)
        
    mods = modifiers if modifiers is not None else Qt.KeyboardModifier.NoModifier

    for part in parts:
        part_u = part.upper()
        if part_u in ("CTRL", "CONTROL"):
            if not (mods & Qt.KeyboardModifier.ControlModifier or Qt.Key.Key_Control in pk):
                return False
        elif part_u == "SHIFT":
            if not (mods & Qt.KeyboardModifier.ShiftModifier or Qt.Key.Key_Shift in pk):
                return False
        elif part_u == "ALT":
            if not (mods & Qt.KeyboardModifier.AltModifier or Qt.Key.Key_Alt in pk):
                return False
        elif part_u == "META":
            if not (mods & Qt.KeyboardModifier.MetaModifier or Qt.Key.Key_Meta in pk):
                return False
        else:
            target_k = get_key(part)
            if target_k != Qt.Key.Key_unknown:
                if target_k not in pk:
                    return False
            else:
                return False
    return True

def check_keybind_match_exact(keybind_str, event_key=None, modifiers=None, pressed_keys=None):
    if not check_keybind_match(keybind_str, event_key, modifiers, pressed_keys):
        return False
    parts = {part.upper() for part in parse_keybind(keybind_str)}
    expected = Qt.KeyboardModifier.NoModifier
    if "CTRL" in parts or "CONTROL" in parts:
        expected |= Qt.KeyboardModifier.ControlModifier
    if "SHIFT" in parts:
        expected |= Qt.KeyboardModifier.ShiftModifier
    if "ALT" in parts:
        expected |= Qt.KeyboardModifier.AltModifier
    if "META" in parts:
        expected |= Qt.KeyboardModifier.MetaModifier
    actual = (modifiers or Qt.KeyboardModifier.NoModifier) & (
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.ShiftModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.MetaModifier
    )
    return actual == expected

def get_key(name):
    if not name or name == "None": return Qt.Key.Key_unknown
    if name.upper() == "CTRL": return Qt.Key.Key_Control
    if name.upper() == "SHIFT": return Qt.Key.Key_Shift
    if name.upper() == "ALT": return Qt.Key.Key_Alt
    if name.upper() == "META": return Qt.Key.Key_Meta
    seq = QKeySequence(name)
    if seq.count() > 0:
        return seq[0].key()
    return Qt.Key.Key_unknown

def check_modifier(modifiers, modifier_name, pressed_keys=None):
    return check_keybind_match(modifier_name, None, modifiers, pressed_keys)

def is_same_lane(obj1, obj2):
    data1 = getattr(obj1, 'custom_data', None)
    data2 = getattr(obj2, 'custom_data', None)
    if (data1 is None) != (data2 is None):
        return False
    if obj1.is_event != obj2.is_event:
        return False
    if obj1.is_event:
        return True
    return getattr(obj1, 'lane', None) == getattr(obj2, 'lane', None)

def get_note_type_category(obj):
    custom_data = getattr(obj, 'custom_data', None)
    if custom_data is not None:
        return ("custom", custom_data.type_id)
    if obj.is_event:
        if getattr(obj, 'is_flip', False): return "flip"
        if getattr(obj, 'is_instant_flip', False): return "instant_flip"
        if getattr(obj, 'is_toggle_center', False): return "toggle_center"
        return "event"
    else:
        if getattr(obj, 'is_spike', False): return "spike"
        if getattr(obj, 'is_hold', False): return "hold"
        if getattr(obj, 'is_screamer', False): return "screamer"
        if getattr(obj, 'is_spam', False): return "spam"
        if getattr(obj, 'is_brawl_hit', False): return "brawl_hit"
        if getattr(obj, 'is_brawl_final', False): return "brawl_final"
        if getattr(obj, 'is_brawl_hold', False): return "brawl_hold"
        if getattr(obj, 'is_brawl_spam', False): return "brawl_spam"
        if getattr(obj, 'is_hide', False): return "hide"
        if getattr(obj, 'is_fly_in', False): return "fly_in"
        return "normal_note"

SOUND_FILES_MAP = {
    'Note': 'note1.wav',
    'Spike': 'spike.wav',
    'Hold Start': 'long.wav',
    'Double Start': 'screamer.wav',
    'Spam': 'spam.wav',
    'Brawl Hit': 'punch1.wav',
    'Brawl Hold Start': 'punch_hold.wav',
    'Brawl Knockout': 'punch2.wav',
    'Hide Note': 'note4.wav',
    'Event Flip': 'event1.wav',
    'Event Instant': 'event2.wav',
    'Event Toggle': 'event3.wav',
    'Metronome': 'metronome.wav',
    'UI Click': 'click.wav',
    'UI Tick On': 'tick.wav',
    'UI Tick Off': 'tick2.wav',
    'UI Text': 'text.wav',
    'UI Scroll': 'roll.wav',
    'UI Place': 'place.wav',
    'UI Delete': 'delete.wav',
    'UI Drag': 'drag.wav',
    'UI Change': 'change.wav',
    'UI Update Exit': 'softclick.wav',
    'UI Toast Exit': 'shortclick.wav',
    'UI Toast Enter': 'toastpop.wav',
    'UI Cover Enter': 'mutedclick.wav',
    'Boot': 'boot.wav'
}

ORIGINAL_SOUND_FILES_MAP = {
    'Note': 'note1.wav',
    'Spike': 'spike.wav',
    'Hold Start': 'long.wav',
    'Double Start': 'screamer.wav',
    'Spam': 'spam.wav',
    'Brawl Hit': 'punch1.wav',
    'Brawl Hold Start': 'punch_hold.wav',
    'Brawl Knockout': 'punch2.wav',
    'Hide Note': 'note4.wav',
    'Event Flip': 'event1.wav',
    'Event Instant': 'event2.wav',
    'Event Toggle': 'event3.wav',
    'Metronome': 'metronome.wav',
    'UI Click': 'click.wav',
    'UI Tick Off': 'tick2.wav',
    'UI Tick On': 'tick.wav',
    'UI Text': 'text.wav',
    'UI Scroll': 'roll.wav',
    'UI Place': 'place.wav',
    'UI Delete': 'delete.wav',
    'UI Drag': 'drag.wav',
    'UI Change': 'change.wav',
    'UI Update Exit': 'softclick.wav',
    'UI Toast Exit': 'shortclick.wav',
    'UI Toast Enter': 'toastpop.wav',
    'UI Cover Enter': 'mutedclick.wav',
    'Boot': 'boot.wav'
}

UI_THEME = {
    "bg_dark": "#1e1e1e",
    "bg_medium": "#2d2d2d",
    "bg_light": "#3c3c3c",
    "bg_lighter": "#4a4a4a",
    "bg_input": "#252525",
    "bg_itemview": "#2e2e2e",
    "bg_success": "#2a3a2a",
    "text_primary": "#e0e0e0",
    "text_secondary": "#a0a0a0",
    "text_disabled": "#606060",
    "border_dark": "#1a1a1a",
    "border_medium": "#3a3a3a",
    "border_light": "#555555",
    "border_success": "#338855",
    "accent": ACCENT_COLOR,
    "accent_hover": ACCENT_HOVER,
    "accent_pressed": ACCENT_PRESSED,
    "button_bg": "#3c3c3c",
    "button_hover": "#525252",
    "button_pressed": "#2a2a2a",
    "button_depth": "#323232",
    "scrollbar_bg": "#2d2d2d",
    "scrollbar_handle": "#555555",
    "scrollbar_handle_hover": "#666666",
    "selection_bg": ACCENT_COLOR,
    "group_bg": "#242424",
    "list_alternate": "#323232"
}

def get_base_app_stylesheet():
    return f"""
QWidget#CentralWidget, QWidget#LeftPanel, QWidget#RightPanel, QWidget#ToolTypeContainer, QWidget#NoteTypeContainer, QWidget#BrawlTypeContainer, QWidget#EventTypeContainer, QWidget#CustomTypeContainer, QStackedWidget, QMainWindow {{
    background-color: transparent;
}}

QWidget {{
    background-color: {UI_THEME["bg_dark"]};
    color: {UI_THEME["text_primary"]};
    font-family: "Segoe UI", "Selawik", "Arial", sans-serif;
    font-size: 9pt;
}}

QMainWindow {{
    background-color: {UI_THEME["bg_dark"]};
}}

QDialog {{
    background-color: {UI_THEME["bg_dark"]};
    color: {UI_THEME["text_primary"]};
}}

QLabel {{
    background-color: transparent;
    color: {UI_THEME["text_primary"]};
}}

QPushButton {{
    background-color: {UI_THEME["button_bg"]};
    color: {UI_THEME["text_primary"]};
    border: none;
    border-radius: 6px;
    padding: 6px 15px;
    min-height: 24px;
    font-weight: 600;
    border-bottom: 3px solid {UI_THEME["button_depth"]};
}}

QPushButton:hover {{
    background-color: {UI_THEME["button_hover"]};
    border-bottom-color: {UI_THEME["accent"]}; 
}}

QPushButton:pressed {{
    background-color: {UI_THEME["button_pressed"]};
    border-bottom: 0px solid transparent;
    border-top: 3px solid transparent;
    padding-top: 9px;
    margin-bottom: 0px;
}}

QPushButton:checked {{
    background-color: {UI_THEME["accent"]};
    border-bottom: 3px solid {UI_THEME["accent_pressed"]};
    color: white;
}}

QPushButton:checked:hover {{
    background-color: {UI_THEME["accent_hover"]};
    border-bottom-color: {UI_THEME["accent_pressed"]};
}}

QPushButton:checked:pressed {{
    background-color: {UI_THEME["accent_pressed"]};
    border-bottom: 0px solid transparent;
    padding-top: 9px;
}}

QPushButton:disabled {{
    background-color: {UI_THEME["bg_medium"]};
    color: {UI_THEME["text_disabled"]};
}}

QLineEdit {{
    background-color: {UI_THEME["button_bg"]};
    color: {UI_THEME["text_primary"]};
    border: none;
    border-radius: 4px;
    padding: 6px 8px;
    selection-background-color: {UI_THEME["selection_bg"]};
    border-bottom: 3px solid {UI_THEME["button_depth"]};
}}

QLineEdit:focus {{
    border-bottom: 3px solid {UI_THEME["accent"]};
    background-color: {UI_THEME["bg_medium"]};
}}

QLineEdit:hover {{
    background-color: {UI_THEME["bg_medium"]};
}}

QLineEdit:disabled {{
    background-color: {UI_THEME["bg_medium"]};
    color: {UI_THEME["text_disabled"]};
}}

QSpinBox, QDoubleSpinBox {{
    background-color: {UI_THEME["button_bg"]};
    color: {UI_THEME["text_primary"]};
    border: none;
    border-radius: 4px;
    padding: 6px 8px;
    border-bottom: 3px solid {UI_THEME["button_depth"]};
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border-bottom: 3px solid {UI_THEME["accent"]};
    background-color: {UI_THEME["bg_medium"]};
}}

QSpinBox::up-button, QDoubleSpinBox::up-button {{
    background-color: {UI_THEME["button_bg"]};
    border: none;
    border-left: 1px solid {UI_THEME["border_medium"]};
    width: 16px;
    border-top-right-radius: 3px;
    border-bottom-right-radius: 0px;
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
}}

QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background-color: {UI_THEME["button_bg"]};
    border: none;
    border-left: 1px solid {UI_THEME["border_medium"]};
    width: 16px;
    border-top-right-radius: 0px;
    border-bottom-right-radius: 3px;
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
}}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {UI_THEME["button_hover"]};
}}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {UI_THEME["text_primary"]};
    width: 0;
    height: 0;
}}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {UI_THEME["text_primary"]};
    width: 0;
    height: 0;
}}



QListWidget {{
    background-color: {UI_THEME["bg_input"]};
    color: {UI_THEME["text_primary"]};
    border: 1px solid {UI_THEME["border_medium"]};
    border-radius: 3px;
    outline: none;
}}

QListWidget::item {{
    padding: 5px 10px;
    border-radius: 4px;
    margin: 2px 4px;
    border: 1px solid transparent;
}}

QListWidget::item:selected {{
    background-color: {UI_THEME["selection_bg"]};
    color: {UI_THEME["text_primary"]};
    border: 1px solid {UI_THEME["accent_pressed"]};
}}

QListWidget::item:hover {{
    background-color: {UI_THEME["bg_light"]};
    border: 1px solid {UI_THEME["border_light"]};

}}

QListWidget::item:alternate {{
    background-color: {UI_THEME["list_alternate"]};
}}

QScrollArea {{
    background-color: {UI_THEME["bg_dark"]};
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background-color: {UI_THEME["bg_dark"]};
}}

QGroupBox {{
    background-color: {UI_THEME["group_bg"]};
    border: 1px solid {UI_THEME["border_medium"]};
    border-radius: 5px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 5px;
    color: {UI_THEME["text_primary"]};
    background-color: {UI_THEME["group_bg"]};
}}

QCheckBox {{
    color: {UI_THEME["text_primary"]};
    spacing: 6px;
    background-color: transparent;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {UI_THEME["border_medium"]};
    border-radius: 3px;
    background-color: {UI_THEME["bg_input"]};
}}

QCheckBox::indicator:checked {{
    background-color: {UI_THEME["accent"]};
    border-color: {UI_THEME["accent"]};
}}

QCheckBox::indicator:hover {{
    border-color: {UI_THEME["border_light"]};
}}

QSlider {{
    background-color: transparent;
}}

QSlider::groove:horizontal {{
    background-color: {UI_THEME["bg_light"]};
    height: 6px;
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background-color: {UI_THEME["accent"]};
    width: 14px;
    height: 14px;
    margin: -4px 0;
    border-radius: 0px;
}}

QSlider::handle:horizontal:hover {{
    background-color: {UI_THEME["accent_hover"]};
}}

QSlider::sub-page:horizontal {{
    background-color: {UI_THEME["accent"]};
    border-radius: 3px;
}}
QScrollBar:horizontal {{
    background-color: {UI_THEME["bg_medium"]};
    height: 16px;
    border: none;
    margin: 0px;
    border-radius: 8px;
}}

QScrollBar::handle:horizontal {{
    background-color: {UI_THEME["scrollbar_handle"]};
    min-width: 24px;
    border-radius: 6px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {UI_THEME["scrollbar_handle_hover"]};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QScrollBar:vertical {{
    background-color: {UI_THEME["bg_medium"]};
    width: 16px;
    border: none;
    margin: 0px;
    border-radius: 8px;
}}

QScrollBar::handle:vertical {{
    background-color: {UI_THEME["scrollbar_handle"]};
    min-height: 24px;
    border-radius: 6px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {UI_THEME["scrollbar_handle_hover"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QComboBox {{
    background-color: {UI_THEME["button_bg"]};
    color: {UI_THEME["text_primary"]};
    border: none;
    border-bottom: 3px solid {UI_THEME["accent"]};
    border-radius: 6px;
    padding: 6px 6px;
    padding-left: 10px;
    min-height: 24px;
    font-size: 13px;
    font-weight: 600;
}}

QComboBox:hover {{
    background-color: {UI_THEME["button_hover"]};
    border-bottom-color: {UI_THEME["accent"]};
}}

QComboBox:focus {{
    border-bottom-color: {UI_THEME["accent"]};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px; 
    border-left: none;
}}

QComboBox::down-arrow {{
    image: none;
    border: none;
    width: 0;
    height: 0;
}}

QComboBox QAbstractItemView {{
    background-color: {UI_THEME["bg_itemview"]};
    color: {UI_THEME["text_primary"]};
    border: 2px solid {UI_THEME["bg_itemview"]};
    border-radius: 10px;
    padding: 8px;
    selection-background-color: transparent;
    outline: none;
}}

QComboBox QAbstractItemView QScrollBar:vertical {{
    background-color: transparent;
    border: none;
    width: 8px;
}}

QComboBox QAbstractItemView QScrollBar::groove:vertical {{
    background-color: transparent;
    border: none;
    width: 8px;
}}

QComboBox QAbstractItemView QScrollBar::handle:vertical {{
    background-color: {UI_THEME["accent"]};
    min-height: 24px;
    border-radius: 4px;
    margin: 0px;
    width: 8px;
}}

QComboBox QAbstractItemView QScrollBar::handle:vertical:hover {{
    background-color: {UI_THEME["accent_hover"]};
}}

QComboBox QAbstractItemView QScrollBar::add-line:vertical,
QComboBox QAbstractItemView QScrollBar::sub-line:vertical {{
    height: 0px;
    background: transparent;
}}

QComboBox QAbstractItemView QScrollBar::add-page:vertical,
QComboBox QAbstractItemView QScrollBar::sub-page:vertical {{
    background-color: {UI_THEME["bg_itemview"]};
}}

QComboBox QAbstractItemView::item {{
    padding: 2px 2px;
    min-height: 14px;
    border-radius: 4px;
    margin: 1px 0px;
    background-color: {UI_THEME["bg_lighter"]};
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: {UI_THEME["bg_light"]};
    color: {UI_THEME["text_primary"]};
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: {UI_THEME["accent"]};
    color: white;
}}

QComboBox QAbstractItemView::item:selected:hover {{
     background-color: {UI_THEME["accent_hover"]};
}}

#HeaderGroup::title {{
    font-size: 24px;
    font-weight: bold;
    color: {UI_THEME["text_primary"]};
    padding-bottom: 5px;
}}

#SubHeaderGroup::title {{
    font-size: 16px;
    font-weight: bold;
    color: {UI_THEME["text_primary"]};
    padding-bottom: 5px;
}}

QProgressBar {{
    background-color: {UI_THEME["bg_light"]};
    border: 1px solid {UI_THEME["border_medium"]};
    border-radius: 4px;
    text-align: center;
    color: {UI_THEME["text_primary"]};
}}

QProgressBar::chunk {{
    background-color: {UI_THEME["accent"]};
    border-radius: 3px;
}}

QMessageBox {{
    background-color: {UI_THEME["bg_dark"]};
}}

QMessageBox QLabel {{
    color: {UI_THEME["text_primary"]};
}}

QInputDialog {{
    background-color: {UI_THEME["bg_dark"]};
}}

QFrame {{
    background-color: transparent;
}}

QToolTip {{
    background-color: {UI_THEME["button_bg"]};
    color: {UI_THEME["text_primary"]};
    border: none;
    border-radius: 0px;
    padding: 5px 8px;
    font-size: 12px;
}}
"""

BASE_APP_STYLESHEET = get_base_app_stylesheet()

def get_base_window_stylesheet():
    return f"""
            QMainWindow, QDialog {{ background-color: #222; color: #EEE; }}
            QWidget {{ font-family: 'Segoe UI', 'Selawik', sans-serif; font-size: 14px; color: #EEE; }}
            QGroupBox {{ border: 1px solid #555; margin-top: 1.2em; border-radius: 4px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }}
            QLineEdit, QSpinBox, QDoubleSpinBox {{ 
                background-color: {UI_THEME["button_bg"]}; border: 1px solid #555; padding: 4px; border-radius: 4px; 
                color: #EEE;
                border: none; border-bottom: 2px solid {UI_THEME["button_depth"]};
            }}
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
                 border-bottom: 2px solid {ACCENT_COLOR}; background-color: #383838;
            }}
            QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
                 background-color: #383838;
            }}
            QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
                background-color: #222; color: #666;
            }}
            
            QPushButton {{ 
                background-color: {UI_THEME["button_bg"]};
                color: {UI_THEME["text_primary"]};
                border: none;
                border-radius: 6px;
                padding: 6px 5px;
                min-height: 24px;
                font-weight: 600;
                border-bottom: 3px solid {UI_THEME["button_depth"]};
            }}
            QPushButton:hover {{
                background-color: {UI_THEME["button_hover"]};
                border-bottom-color: {UI_THEME["accent"]}; 
            }}
            QPushButton:pressed {{
                background-color: {UI_THEME["button_pressed"]};
                border-bottom: 0px solid transparent;
                border-top: 3px solid transparent;
                padding-top: 9px;
                margin-bottom: 0px;
            }}
            QPushButton:checked {{ 
                background-color: {UI_THEME["accent"]}; 
                border-bottom: 3px solid {UI_THEME["accent_pressed"]}; 
                color: white; 
            }}
            QPushButton:checked:hover {{
                background-color: {UI_THEME["accent_hover"]};
                border-bottom-color: {UI_THEME["accent_pressed"]};
            }}
            QPushButton:checked:pressed {{
                background-color: {UI_THEME["accent_pressed"]};
                border-bottom: 0px solid transparent;
                padding-top: 9px;
            }}
            QPushButton:disabled {{ background-color: {UI_THEME["bg_medium"]}; color: {UI_THEME["text_disabled"]}; border-bottom-color: transparent; }}
            QScrollBar:horizontal {{
                border: none;
                background: #282828;
                height: 16px;
                margin: 0px;
                border-radius: 8px;
            }}
            QScrollBar::handle:horizontal {{
                background: {ACCENT_COLOR};
                min-width: 24px;
                border-radius: 6px;
                margin: 2px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
            QScrollBar:vertical {{
                border: none;
                background: #282828;
                width: 16px;
                margin: 0px;
                border-radius: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: {ACCENT_COLOR};
                min-height: 24px;
                border-radius: 6px;
                margin: 2px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}

            QComboBox {{
                background-color: {UI_THEME["button_bg"]};
                color: {UI_THEME["text_primary"]};
                border: none;
                border-bottom: 3px solid {UI_THEME["accent"]};
                border-radius: 6px;
                padding: 6px 6px;
                padding-left: 10px;
                min-height: 24px;
                font-weight: 600;
            }}
            QComboBox:hover {{
                background-color: {UI_THEME["button_hover"]};
                border-bottom-color: {UI_THEME["accent"]};
            }}
            QComboBox:focus {{
                border-bottom-color: {UI_THEME["accent"]};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border: none;
                background-color: transparent;
            }}
            QComboBox::down-arrow {{
                image: none;
                border: none;
                width: 0;
                height: 0;
            }}
            QComboBox QAbstractItemView {{
                background-color: {UI_THEME["bg_itemview"]};
                color: {UI_THEME["text_primary"]};
                border: 2px solid {UI_THEME["bg_itemview"]};
                border-radius: 10px;
                padding: 8px;
                outline: none;
                selection-background-color: transparent; 
            }}
            
            QComboBox QAbstractItemView QScrollBar:vertical {{
                background-color: transparent;
                border: none;
                width: 8px;
            }}
            
            QComboBox QAbstractItemView QScrollBar::groove:vertical {{
                background-color: transparent;
                border: none;
                width: 8px;
            }}
            
            QComboBox QAbstractItemView QScrollBar::handle:vertical {{
                background-color: {UI_THEME["accent"]};
                min-height: 24px;
                border-radius: 4px;
                margin: 0px;
                width: 8px;
            }}
            
            QComboBox QAbstractItemView QScrollBar::handle:vertical:hover {{
                background-color: {UI_THEME["accent_hover"]};
            }}
            
            QComboBox QAbstractItemView QScrollBar::add-line:vertical,
            QComboBox QAbstractItemView QScrollBar::sub-line:vertical {{
                height: 0px;
                background: transparent;
            }}
            
            QComboBox QAbstractItemView QScrollBar::add-page:vertical,
            QComboBox QAbstractItemView QScrollBar::sub-page:vertical {{
                background-color: {UI_THEME["bg_itemview"]};
            }}
            QComboBox QAbstractItemView::item {{
                padding: 2px 2px;
                min-height: 14px;
                border-radius: 4px;
                margin: 1px 0px;
                background-color: {UI_THEME["bg_lighter"]};
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: #444;
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {ACCENT_COLOR};
                color: white;
            }}
            QProgressBar {{
                border: 1px solid #555;
                border-radius: 4px;
                text-align: center;
                color: #EEE;
                background-color: #333;
            }}
            QProgressBar::chunk {{
                background-color: {ACCENT_COLOR};
            }}
            #HeaderGroup {{ margin-top: 40px; }}
            #HeaderGroup::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
            
            #SubHeaderGroup {{ margin-top: 25px; }}
            #SubHeaderGroup::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
            
        QSlider {{ background-color: transparent; min-height: 32px; }}
            QSlider::groove:horizontal {{ height: 4px; background: #333; border-radius: 2px; }}
            QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -6px 0; border-radius: 0px; background: {ACCENT_COLOR}; }}
            QSlider::sub-page:horizontal {{ background: {ACCENT_COLOR}; border-radius: 2px; }}
            
            QCheckBox {{ spacing: 5px; padding-left: 5px; }}
            
            QListWidget::item:selected:hover {{ background-color: {ACCENT_COLOR}; color: #EEE; }}

            #LargeHeaderGroup {{ margin-top: 50px; }}
            #LargeHeaderGroup::title {{ subcontrol-origin: margin; left: 10px; top: 0px; padding: 0 5px; font-size: 60px; font-weight: bold; color: {UI_THEME["text_primary"]}; }}

            #ProjectTitle, #MetadataTitle {{
                font-size: 40px;
                font-weight: bold;
                color: #E0E0E0;
                margin-bottom: 0px;
                margin-top: -5px;
            }}
            #LeftPanel {{ min-width: 350px; max-width: 350px; }}
            #MetadataGroup {{ min-width: 330px; }}
            #PathLabel {{ color: #AAA; font-size: 11px; }}
            
            #ToolTypeContainer QPushButton, #NoteTypeContainer QPushButton, #BrawlTypeContainer QPushButton, #EventTypeContainer QPushButton, #CustomTypeContainer QPushButton, #NoteTypeContainer QComboBox, #BrawlTypeContainer QComboBox, #CustomTypeContainer QComboBox {{
                margin-right: 2px;
            }}
"""

BASE_WINDOW_STYLESHEET = get_base_window_stylesheet()

def get_scaled_stylesheet(style, scale, ui_brightness=60):
    b = ui_brightness
    b_h = min(255, b + 22)
    b_p = max(0, b - 18)
    b_d = max(0, b - int(20 + (b / 255.0) * 30))
    b_i = max(0, b - 9)
    b_disabled = max(0, b - 15)
    
    b_w = max(0, b - 30)
    b_panel = max(0, b - 26)
    
    bg_hex = f"#{b:02x}{b:02x}{b:02x}"
    hover_hex = f"#{b_h:02x}{b_h:02x}{b_h:02x}"
    pressed_hex = f"#{b_p:02x}{b_p:02x}{b_p:02x}"
    depth_hex = UI_THEME["button_depth"] if b == 60 else f"#{b_d:02x}{b_d:02x}{b_d:02x}"
    input_hex = f"#{b_i:02x}{b_i:02x}{b_i:02x}"
    disabled_hex = f"#{b_disabled:02x}{b_disabled:02x}{b_disabled:02x}"
    window_hex = f"#{b_w:02x}{b_w:02x}{b_w:02x}"
    panel_hex = f"#{b_panel:02x}{b_panel:02x}{b_panel:02x}"
    
    if b != 60:
        style = style.replace("#3c3c3c", bg_hex)
        style = style.replace("#525252", hover_hex)
        style = style.replace("#4a4a4a", hover_hex)
        style = style.replace("#2a2a2a", pressed_hex)
        style = style.replace("#323232", depth_hex)
        style = style.replace("#1e1e1e", window_hex)
        style = style.replace("#222222", panel_hex)
        style = style.replace("#222", panel_hex)
        
    style += f"\nQLineEdit, QSpinBox, QDoubleSpinBox {{ background-color: {bg_hex}; border-bottom: 2px solid {depth_hex}; }}"
    style += f"\nQLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ background-color: {bg_hex}; }}"
    style += f"\nQLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ background-color: {bg_hex}; }}"
    
    style += f"\nQScrollArea, QScrollArea > QWidget > QWidget {{ background-color: {window_hex}; }}"
    style += f"\nQGroupBox {{ background-color: {panel_hex}; }}"
    style += f"\nQGroupBox::title {{ background-color: {panel_hex}; border-radius: 4px; padding: 2px 5px; }}"
    style += f"\nQSlider::groove:horizontal {{ background: {input_hex}; height: 6px; border-radius: 3px; }}"
    style += f"\nQSlider::handle:horizontal {{ background-color: {ACCENT_COLOR}; width: 14px; height: 14px; margin: -4px 0; border-radius: 0px; }}"
    style += f"\nQSlider::handle:horizontal:hover {{ background-color: {ACCENT_HOVER}; }}"
    style += f"\nQSlider::sub-page:horizontal {{ background-color: {ACCENT_COLOR}; border-radius: 3px; }}"
    style += f"\nQProgressBar {{ background-color: {input_hex}; border: 1px solid {depth_hex}; }}"
    
    b_scroll = max(0, b - 20)
    scroll_hex = f"#{b_scroll:02x}{b_scroll:02x}{b_scroll:02x}"
    style += f"\nQScrollBar:vertical, QScrollBar:horizontal {{ background: {scroll_hex}; border-radius: 8px; }}"
    style += f"\nQComboBox QAbstractItemView QScrollBar:vertical {{ background-color: {scroll_hex}; border-radius: 4px; }}"
    style += f"\nQComboBox QAbstractItemView QScrollBar::add-page:vertical, QComboBox QAbstractItemView QScrollBar::sub-page:vertical {{ background-color: transparent; }}"
    
    style += f"\nQComboBox QAbstractItemView {{ background-color: {input_hex}; border: 2px solid {depth_hex}; }}"
    style += f"\nQComboBox QAbstractItemView::item {{ background-color: {input_hex}; }}"
    style += f"\nQComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected {{ background-color: {ACCENT_COLOR}; color: white; }}"
    
    style += f"\nQCheckBox::indicator {{ background-color: {input_hex}; border: 1px solid {depth_hex}; }}"
    style += f"\nQCheckBox::indicator:hover {{ background-color: {bg_hex}; border-color: {depth_hex}; }}"
    style += f"\nQCheckBox::indicator:checked {{ background-color: {ACCENT_COLOR}; border-color: {ACCENT_COLOR}; }}"
    
    style += f"\n#FileDropLabel[state=\"empty\"] {{ background-color: {input_hex}; border: 2px dashed {depth_hex}; padding: 0px; margin: 0px; border-radius: 4px; }}"
    style += f"\n#FileDropLabel[state=\"empty\"]:hover {{ background-color: {bg_hex}; border-color: {ACCENT_COLOR}; }}"
    style += f"\n#FileDropLabel[state=\"loaded\"] {{ background-color: {ACCENT_RGBA_15}; border: 2px solid {ACCENT_COLOR}; padding: 0px; margin: 0px; border-radius: 4px; }}"
    
    style += f"\nQPushButton:disabled, QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{ background-color: {disabled_hex}; border-bottom-color: transparent; }}"
    style += f"\nQCheckBox::indicator:disabled {{ background-color: {disabled_hex}; border-color: {disabled_hex}; }}"
    
    style += "\nQDoubleSpinBox#BPMDoubleSpinBox { background-color: transparent; border: 1px solid #444; color: #fff; }"
    
    if b > 180:
        style += "\nQPushButton { color: black; }\nQPushButton:disabled { color: #555; }"
        style += "\nQComboBox { color: black; }\nQComboBox:disabled { color: #555; }"
        style += "\nQLineEdit { color: black; }\nQLineEdit:disabled { color: #555; }"
        style += "\nQSpinBox { color: black; }\nQSpinBox:disabled { color: #555; }"
        style += "\nQDoubleSpinBox { color: black; }\nQDoubleSpinBox:disabled { color: #555; }"
        style += "\nQComboBox QAbstractItemView { color: black; }"
        style += "\nQComboBox QAbstractItemView::item:disabled { color: #888; }"
        style += "\nQMainWindow, QDialog, QWidget, QLabel, QGroupBox, QCheckBox, QPushButton, QProgressBar { color: black; }"
        style += "\nQGroupBox::title { color: black; }"
        style += "\n#FileDropLabel { color: black; }"
        style += "\nQLabel#WhiteLabel, QLabel#ProjectTitle, QLabel#MetadataTitle, QCheckBox#WhiteLabel, QListWidget, QListWidget::item { color: white; }"
        style += "\nQDoubleSpinBox#BPMDoubleSpinBox { border-color: white; }"
        
    style += f"\n#CurrentTimeLabel {{ color: {ACCENT_COLOR}; }}"

    if scale == 1.0: return style
    import re
    def repl(m):
        val = int(m.group(1))
        new_val = round(val * scale)
        if val > 0 and new_val <= 0: new_val = 1
        return f"{int(new_val)}{m.group(2)}"
    return re.sub(r'(-?\d+)(px|pt)', repl, style)


