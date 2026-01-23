# yes its all one python file, do NOT judge me
import sys
import subprocess
import os
import json
import shutil
import string
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Set
import pygame
from pydub import AudioSegment, utils
from PIL import Image
if sys.platform.startswith("win"):
    import winreg
import re

from PyQt6.QtCore import Qt, QTimer, QPointF, QElapsedTimer, QRectF, pyqtSignal, QThread, QEvent, QSize, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QColor, QPen, QKeyEvent, QBrush, QWheelEvent, QMouseEvent, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QSpinBox,
    QDoubleSpinBox, QComboBox, QGroupBox, QFormLayout,
    QMessageBox, QButtonGroup, QSlider, QDialog, QScrollBar, 
    QSizePolicy, QListWidget, QListWidgetItem, QScrollArea, QCheckBox,
    QProgressBar, QAbstractSpinBox, QFrame, QInputDialog, QSplashScreen
)

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def initialize_ffmpeg():
    base_path = get_base_path()

    if base_path and base_path not in os.environ["PATH"]:
        os.environ["PATH"] = base_path + os.pathsep + os.environ["PATH"]

    ffmpeg_exe = os.path.join(base_path, "ffmpeg.exe")
    ffprobe_exe = os.path.join(base_path, "ffprobe.exe")

    if not os.path.exists(ffmpeg_exe):
        ffmpeg_exe = shutil.which("ffmpeg") or "ffmpeg"
    
    if not os.path.exists(ffprobe_exe):
        ffprobe_exe = shutil.which("ffprobe") or "ffprobe"

    if os.path.exists(ffmpeg_exe):
        AudioSegment.converter = ffmpeg_exe
        AudioSegment.ffmpeg = ffmpeg_exe
    
    if os.path.exists(ffprobe_exe):
        AudioSegment.ffprobe = ffprobe_exe
        def get_prober_name_fixed():
            return ffprobe_exe
        utils.get_prober_name = get_prober_name_fixed

DIFFICULTIES = ["Beginner", "Normal", "Hard", "Expert", "UNBEATABLE", "Star"]
LANE_HEIGHT = 100
TIMELINE_START_X = 150
SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
VERSION_NUMBER = "v1.01"

COLOR_PALETTE = {
    "Cyan (Note)": "#64C8FF",
    "Yellow (Spike)": "#FFFF00",
    "Red (Hold)": "#FF3232",
    "Light Red (Hold Line)": "#FF5050",
    "Pale Yellow (Flip)": "#FFFF64",
    "Deep Blue (Toggle/Hit)": "#0064FF",
    "Magenta (Instant)": "#FF32FF",
    "Pale Cyan (Mid)": "#C8F0FF",
    "Black (Hide/Final)": "#000000",
    "Green (Double)": "#00FF00",
    "Dark Green (Double Line)": "#00C800",
    "Orange (Spam)": "#FFA500",
    "Dark Orange (Spam Line)": "#FF8C00",
    "White": "#FFFFFF",
    "Gray": "#808080",
    "Purple (Freestyle)": "#800080",
    "Royal Blue (Brawl Hold)": "#4169E1",
    "Dark Royal Blue (Brawl Hold Line)": "#2E4A9E",
    "Orange Red (Brawl Spam)": "#FF4500",
    "Dark Orange Red (Brawl Spam Line)": "#CC3700"
}

DEFAULT_COLORS = {
    "note": "Cyan (Note)",
    "spike": "Yellow (Spike)",
    "hold": "Red (Hold)",
    "hold_line": "Light Red (Hold Line)",
    "flip": "Pale Yellow (Flip)",
    "toggle": "Deep Blue (Toggle/Hit)",
    "instant": "Magenta (Instant)",
    "mid": "Pale Cyan (Mid)",
    "double": "Green (Double)",
    "double_line": "Dark Green (Double Line)",
    "spam": "Orange (Spam)",
    "spam_line": "Dark Orange (Spam Line)",
    "brawl_hit": "Deep Blue (Toggle/Hit)",
    "brawl_knockout": "Black (Hide/Final)",
    "hide_marker": "Black (Hide/Final)",
    "fly_in_marker": "White",
    "freestyle": "Purple (Freestyle)",
    "brawl_hold": "Royal Blue (Brawl Hold)",
    "brawl_hold_line": "Dark Royal Blue (Brawl Hold Line)",
    "brawl_spam": "Orange Red (Brawl Spam)",
    "brawl_spam_line": "Dark Orange Red (Brawl Spam Line)"
}

SOUND_FILES_MAP = {
    'Lane 1 (Top)': 'note1.wav',
    'Lane 2 (Bottom)': 'note2.wav',
    'Spike': 'spike.wav',
    'Hold Start': 'long.wav',
    'Double Start': 'screamer.wav',
    'Spam': 'spam.wav',
    'Brawl Hit': 'punch1.wav',
    'Brawl Knockout': 'punch2.wav',
    'Mid Note': 'note3.wav',
    'Hide Note': 'note4.wav',
    'Event Flip': 'event1.wav',
    'Event Instant': 'event2.wav',
    'Event Toggle': 'event3.wav',
    'Metronome': 'metronome.wav',
    'UI Click': 'click.wav',
    'UI Tick On': 'tick2.wav',
    'UI Tick Off': 'tick.wav',
    'UI Text': 'text.wav',
    'UI Scroll': 'roll.wav',
    'UI Place': 'place.wav',
    'UI Drag': 'drag.wav'
}

SOUND_DISPLAY_NAMES = {
    'UI Tick On': 'UI Tick Off',
    'UI Tick Off': 'UI Tick On'
}

class OutputSuppressor:
    def __enter__(self):
        self._stdout = sys.stdout
        self._stderr = sys.stderr
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stderr.close()
        sys.stdout = self._stdout
        sys.stderr = self._stderr

class CleanSpinBox(QSpinBox):
    def wheelEvent(self, e: QWheelEvent):
        super().wheelEvent(e)
        self.lineEdit().deselect()

class HoverListWidget(QListWidget):
    itemHovered = pyqtSignal(QListWidgetItem)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
    def mouseMoveEvent(self, e: QMouseEvent):
        item = self.itemAt(e.pos())
        if item:
            self.itemHovered.emit(item)
        super().mouseMoveEvent(e)

class HoverDelegate(QEvent):
     pass

class CleanDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, e: QWheelEvent):
        super().wheelEvent(e)
        self.lineEdit().deselect()

def find_unbeatable_root() -> Optional[Path]:
    possible_roots = []
    
    if sys.platform.startswith("win"):
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam")
            steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)
            
            if steam_path:
                steam_path = Path(steam_path)
                library_vdf = steam_path / "steamapps" / "libraryfolders.vdf"
                
                paths = [steam_path]
                
                if library_vdf.exists():
                    with open(library_vdf, 'r', encoding='utf-8') as f:
                        content = f.read()
                        matches = re.findall(r'"path"\s+"(.+?)"', content)
                        for m in matches:
                            clean_path = m.replace("\\\\", "\\")
                            paths.append(Path(clean_path))
                
                for p in paths:
                    possible_roots.append(p / "steamapps" / "common" / "UNBEATABLE")
                    possible_roots.append(p / "steamapps" / "common" / "UNBEATABLE [white label]")
        except:
            pass
            
        common_paths = [
            "Program Files (x86)/Steam/steamapps/common",
            "Program Files/Steam/steamapps/common",
            "Steam/steamapps/common"
        ]
        available_drives = []
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                available_drives.append(drive)
        
        for drive in available_drives:
            for subpath in common_paths:
                full_path = Path(drive) / subpath
                possible_roots.append(full_path / "UNBEATABLE")
                possible_roots.append(full_path / "UNBEATABLE [white label]")

    else:
        home = Path.home()
        possible_roots.append(home / ".steam" / "steam" / "steamapps" / "common" / "UNBEATABLE")
        possible_roots.append(home / ".local" / "share" / "Steam" / "steamapps" / "common" / "UNBEATABLE")
        possible_roots.append(home / "Library" / "Application Support" / "Steam" / "steamapps" / "common" / "UNBEATABLE")

    for root in possible_roots:
        if root.exists():
            return root
    return None

def get_ffmpeg_path():
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
        return os.path.join(base_path, 'ffmpeg.exe')
    return shutil.which("ffmpeg")

@dataclass
class BeatmapMetadata:
    Title: str = ""
    TitleUnicode: str = ""
    Artist: str = ""
    ArtistUnicode: str = ""
    Creator: str = ""
    Version: str = "Beginner"
    AudioFilename: str = ""
    BPM: float = 120.0
    Offset: int = 0
    PreviewTime: int = -1
    Level: int = 1
    FlavorText: str = ""
    SongLength: float = 0.0
    ActualAudioLength: float = 0.0
    GridSize: int = 4
    Attributes: list = None

    def __post_init__(self):
        if self.Attributes is None:
            self.Attributes = []

@dataclass
class HitObject:
    x: int
    y: int
    time: int
    type: int
    hitSound: int
    objectParams: str = "0"
    hitSample: str = "0:0:0:"

    @property
    def is_event(self):
        return self.x == 384

    @property
    def is_flip(self):
        return self.is_event and self.hitSound == 0

    @property
    def is_toggle_center(self):
        return self.is_event and self.hitSound == 2
    
    @property
    def is_instant_flip(self):
        return self.is_event and self.hitSound == 8

    @property
    def is_spike(self):
        return self.hitSound == 2 and self.type != 128 and not self.is_event
    
    @property
    def is_mid(self):
        return self.hitSample.startswith("1") and not self.is_brawl_hit and not self.is_brawl_final and not self.is_event

    @property
    def is_hide(self):
        return self.hitSound == 8 and not self.is_event

    @property
    def is_fly_in(self):
        return self.objectParams == "1" and not self.is_event

    @property
    def is_hold(self):
        return self.type == 128 and self.hitSound == 0 and not self.is_brawl_hold and not self.is_brawl_spam

    @property
    def is_screamer(self):
        return self.type == 128 and self.hitSound == 2 and not self.is_brawl_hold and not self.is_brawl_spam
    
    @property
    def is_spam(self):
        return self.type == 128 and self.hitSound == 4 and not self.is_brawl_hold and not self.is_brawl_spam
    
    @property
    def is_brawl_hit(self):
        return self.type == 1 and self.hitSound in [0, 2, 8, 10] and self.objectParams == "3" and not self.is_event
    
    @property
    def is_brawl_final(self):
        return self.type == 1 and self.hitSound in [4, 6, 12, 14] and self.objectParams == "3" and not self.is_event

    @property
    def brawl_cop_number(self):
        if self.hitSound in [0, 4]: return 1
        if self.hitSound in [2, 6]: return 2
        if self.hitSound in [8, 12]: return 3
        if self.hitSound in [10, 14]: return 4
        return 1

    @property
    def is_brawl_hold(self):
        return self.type == 128 and self.hitSample.startswith("3:1")

    @property
    def is_brawl_spam(self):
        return self.type == 128 and self.hitSample.startswith("3:0")

    @property
    def is_brawl_hold_knockout(self):
         return self.is_brawl_hold and self.hitSound in [4, 6, 12, 14]

    @property
    def is_brawl_spam_knockout(self):
         return self.is_brawl_spam and self.hitSound in [4, 6, 12, 14]

    @property
    def is_freestyle(self):
        return self.x == 427 and self.type == 1 and self.objectParams != "3" and self.objectParams != "Flip"

    @property
    def lane(self):
        if self.is_event or self.is_freestyle: return -1
        if self.x == 255: return 0
        return 1
    
    @property
    def end_time(self):
        if self.type == 128: 
            try:
                return int(self.objectParams)
            except:
                return self.time
        return self.time

    @end_time.setter
    def end_time(self, value):
        if self.type == 128:
            self.objectParams = str(int(value))

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return self is other

class BeatmapData:
    def __init__(self, difficulty_key: str):
        self.difficulty_key = difficulty_key
        self.metadata = BeatmapMetadata(Version=difficulty_key)
        self.hit_objects: List[HitObject] = []
        self.created = False
        self.unsaved = False
        self.editor_zoom = 1.0
        
    def get_filename(self) -> str:
        return f"{self.difficulty_key}.txt"

    def copy_from(self, other: 'BeatmapData'):
        self.metadata.Title = other.metadata.Title
        self.metadata.TitleUnicode = other.metadata.TitleUnicode
        self.metadata.Artist = other.metadata.Artist
        self.metadata.ArtistUnicode = other.metadata.ArtistUnicode
        self.metadata.Creator = other.metadata.Creator
        self.metadata.AudioFilename = other.metadata.AudioFilename
        self.metadata.BPM = other.metadata.BPM
        self.metadata.Offset = other.metadata.Offset
        self.metadata.Level = other.metadata.Level
        self.metadata.FlavorText = other.metadata.FlavorText
        self.metadata.Attributes = list(other.metadata.Attributes)
        self.metadata.GridSize = other.metadata.GridSize
        
        self.hit_objects = [HitObject(ho.x, ho.y, ho.time, ho.type, ho.hitSound, ho.objectParams, ho.hitSample) 
                           for ho in other.hit_objects]
        self.created = True
        self.unsaved = True
        self.editor_zoom = other.editor_zoom

    def save(self, folder: Path):
        path = folder / self.get_filename()
        self.hit_objects.sort(key=lambda x: x.time)

        length = 0.0
        if self.hit_objects:
            last_obj = max(self.hit_objects, key=lambda o: o.end_time if o.type == 128 else o.time)
            length = (last_obj.end_time if last_obj.type == 128 else last_obj.time) / 1000.0 + 2.0
            
        tags_data = {
            "Level": self.metadata.Level,
            "FlavorText": self.metadata.FlavorText,
            "SongLength": length,
            "Attributes": self.metadata.Attributes
        }
        
        difficulty_name = self.difficulty_key
        version_name = self.difficulty_key
        
        if difficulty_name == "Star":
            if self.metadata.Version and self.metadata.Version != "Star":
                version_name = self.metadata.Version
            else:
                version_name = "Star"
        else:
             version_name = difficulty_name

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"-Made With CBM Editor {VERSION_NUMBER} by Splash!-\n")
                f.write("[General]\n")
                f.write(f"AudioFilename: {self.metadata.AudioFilename}\n")
                f.write(f"AudioLeadIn: {int(self.metadata.Offset)}\n")
                f.write("PreviewTime: -1\n")
                f.write("Countdown: 0\n")
                f.write("SampleSet: Normal\n")
                f.write("StackLeniency: 0.7\n")
                f.write("Mode: 3\n")
                f.write("LetterboxInBreaks: 0\n")
                f.write("SpecialStyle: 0\n")
                f.write("WidescreenStoryboard: 0\n\n")

                f.write("[Metadata]\n")
                f.write(f"Title: {self.metadata.Title}\n")
                f.write(f"TitleUnicode: {self.metadata.TitleUnicode if self.metadata.TitleUnicode else self.metadata.Title}\n")
                f.write(f"Artist: {self.metadata.Artist}\n")
                f.write(f"ArtistUnicode: {self.metadata.ArtistUnicode if self.metadata.ArtistUnicode else self.metadata.Artist}\n")
                f.write(f"Creator: {self.metadata.Creator}\n")
                f.write(f"Difficulty: {difficulty_name}\n")
                f.write(f"Version: {version_name}\n")
                f.write("Source:\n")
                f.write(f"GridSize: {self.metadata.GridSize}\n")
                f.write(f"Tags:{json.dumps(tags_data)}\n\n")

                f.write("[Editor]\n")
                f.write(f"GridSize: {self.metadata.GridSize}\n")
                f.write(f"Zoom: {self.editor_zoom}\n\n")

                f.write("[Events]\n")
                f.write("//Background and Video events\n")
                f.write('0,0,"cover.jpg",0,0\n\n')

                f.write("[TimingPoints]\n")
                beat_len = 60000.0 / self.metadata.BPM if self.metadata.BPM > 0 else 500
                f.write(f"{int(self.metadata.Offset)},{beat_len},4,1,0,100,1,0\n\n")
                
                f.write("[HitObjects]\n")
                for ho in self.hit_objects:
                    param_str = ho.objectParams
                    if ho.is_event and param_str == "Flip":
                        param_str = "0"
                        
                    hit_sample = ho.hitSample if ho.hitSample else "0:0:0:0:"
                    if not hit_sample.endswith(":"):
                        hit_sample += ":"
                        
                    f.write(f"{ho.x},{ho.y},{ho.time},{ho.type},{ho.hitSound},{param_str}:{hit_sample}\n")
                
            self.created = True
            self.unsaved = False
            return True
        except Exception as e:
            print(f"Error saving {path}: {e}")
            return False

    def load(self, folder: Path):
        path = folder / self.get_filename()
        if not path.exists():
            return False
            
        self.created = True
        self.unsaved = False
        self.hit_objects.clear()
        
        current_section = ""
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if not lines:
                return True

            for line in lines:
                line = line.strip()
                if not line or line.startswith("//"):
                    if line.startswith("//"):
                        continue
                
                if line.startswith("[") and line.endswith("]"):
                    current_section = line
                    continue

                if current_section == "[HitObjects]":
                    parts = line.split(",")
                    if len(parts) >= 5:
                        try:
                            x = int(parts[0])
                            y = int(parts[1])
                            time = int(parts[2])
                            type_ = int(parts[3])
                            hitSound = int(parts[4])
                            extras = parts[5] if len(parts) > 5 else ""
                            
                            obj_params = "0"
                            hit_sample = "0:0:0:"
                            if ":" in extras:
                                p_split = extras.split(":", 1)
                                obj_params = p_split[0]
                                hit_sample = p_split[1]
                            else:
                                obj_params = extras
                            
                            if x == 384 and obj_params == "0" and type_ != 128:
                                obj_params = "Flip"
                                
                            self.hit_objects.append(HitObject(x, y, time, type_, hitSound, obj_params, hit_sample))
                        except ValueError:
                            pass
                    continue
                
                if current_section == "[TimingPoints]":
                     parts = line.split(",")
                     if len(parts) >= 2:
                         try:
                             beat_len = float(parts[1])
                             if beat_len > 0:
                                 self.metadata.BPM = 60000.0 / beat_len
                         except:
                             pass

                if ":" in line and (current_section == "[General]" or current_section == "[Metadata]" or current_section == ""):
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == "Title": self.metadata.Title = value
                    elif key == "TitleUnicode": self.metadata.TitleUnicode = value
                    elif key == "Artist": self.metadata.Artist = value
                    elif key == "ArtistUnicode": self.metadata.ArtistUnicode = value
                    elif key == "AudioFilename": self.metadata.AudioFilename = value
                    elif key == "Creator": self.metadata.Creator = value
                    elif key == "BPM": 
                        try: self.metadata.BPM = float(value)
                        except: pass
                    elif key == "Version": self.metadata.Version = value
                    elif key == "Tags":
                        try:
                            tag_data = json.loads(value)
                            self.metadata.Level = tag_data.get("Level", 1)
                            self.metadata.FlavorText = tag_data.get("FlavorText", "")
                            self.metadata.Attributes = tag_data.get("Attributes", [])
                        except:
                            pass
                    elif key == "AudioLeadIn":
                         try: self.metadata.Offset = int(value)
                         except: pass
                    elif key == "GridSize":
                        try: self.metadata.GridSize = int(value)
                        except: pass
                
                if current_section == "[Editor]":
                     if ":" in line:
                         key, value = line.split(":", 1)
                         key = key.strip()
                         value = value.strip()
                         if key == "GridSize":
                             try: self.metadata.GridSize = int(value)
                             except: pass
                         elif key == "Zoom":
                             try: self.editor_zoom = float(value)
                             except: pass
            
            if self.difficulty_key == "Star":
                if self.metadata.Version == "Expert" or self.metadata.Version == "Star":
                    pass
                else:
                    pass

            return True
        except Exception as e:
            print(f"Error loading {path}: {e}")
            return True

class FileDropLabel(QLabel):
    fileDropped = pyqtSignal(str)
    
    def __init__(self, default_text, parent=None):
        super().__init__(default_text, parent)
        self.default_text = default_text
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #555;
                background-color: #2a2a2a;
                color: #888;
                padding: 10px;
                border-radius: 4px;
            }
            QLabel:hover {
                border-color: #777;
                background-color: #333;
            }
        """)
        self.setWordWrap(True)
    
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.accept()
        else:
            e.ignore()
            
    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]
        if files:
            self.fileDropped.emit(files[0])
            
    def set_content_loaded(self, text):
        self.setText(text)
        self.setStyleSheet("""
            QLabel {
                border: 2px solid #385;
                background-color: #2a3a2a;
                color: #EEE;
                padding: 10px;
                border-radius: 4px;
            }
        """)

    def set_empty(self):
        self.setText(self.default_text)
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #555;
                background-color: #2a2a2a;
                color: #888;
                padding: 10px;
                border-radius: 4px;
            }
            QLabel:hover {
                border-color: #777;
                background-color: #333;
            }
        """)

class RecentProjectsDialog(QDialog):
    def __init__(self, parent, recent_paths):
        super().__init__(parent)
        self.setWindowTitle("Recent Projects")
        self.setFixedSize(400, 300)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        self.selected_project = None
        self.parent_window = parent
        
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.setMouseTracking(True)
        self.list_widget.entered.connect(self.on_item_hover)
        self.list_widget.itemClicked.connect(self.on_item_click)
        for path in recent_paths:
            p = Path(path)
            item = QListWidgetItem(p.name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.list_widget.addItem(item)
        
        layout.addWidget(self.list_widget)
        
        btn_layout = QHBoxLayout()
        load_btn = QPushButton("Load")
        load_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        load_btn.clicked.connect(self.on_load)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(load_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
    
    def on_item_hover(self):
        if hasattr(self.parent_window, 'play_ui_sound_suppressed'):
            self.parent_window.play_ui_sound_suppressed('UI Scroll')
    
    def on_item_click(self):
        if hasattr(self.parent_window, 'play_ui_sound_suppressed'):
            self.parent_window.play_ui_sound_suppressed('UI Click')
        
    def on_load(self):
        if self.list_widget.currentItem():
            self.selected_project = self.list_widget.currentItem().data(Qt.ItemDataRole.UserRole)
            self.accept()

class SoundSettingWidget(QWidget):
    soundReset = pyqtSignal(str) 
    soundChanged = pyqtSignal(str, str) 

    def __init__(self, friendly_name, filename, game_root):
        super().__init__()
        self.friendly_name = friendly_name
        self.filename = filename
        self.game_root = game_root
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        
        lbl_name = QLabel(friendly_name)
        lbl_name.setFixedWidth(120)
        layout.addWidget(lbl_name)
        
        self.btn_play = QPushButton("Play")
        self.btn_play.setFixedWidth(50)
        self.btn_play.setProperty("is_custom_sound_btn", True)
        self.btn_play.clicked.connect(self.play_sound)
        layout.addWidget(self.btn_play)
        
        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setFixedWidth(50)
        self.btn_reset.setProperty("is_custom_sound_btn", True)
        self.btn_reset.clicked.connect(lambda: self.soundReset.emit(self.filename))
        layout.addWidget(self.btn_reset)
        
        self.drop_label = FileDropLabel("Drag new wav here")
        self.drop_label.setFixedHeight(40)
        self.drop_label.fileDropped.connect(self.handle_drop)
        layout.addWidget(self.drop_label)
        
    def play_sound(self):
        path = self.game_root / "ChartEditorResources" / self.filename
        if path.exists():
            try:
                s = pygame.mixer.Sound(str(path))
                s.play()
            except:
                pass

    def handle_drop(self, file_path):
        self.soundChanged.emit(self.filename, file_path)

class SettingsDialog(QDialog):
    def __init__(self, parent, current_music_vol, current_fx_vol, current_ui_vol, current_colors, persistent_files, game_root):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setFixedSize(500, 600)
        self.current_colors = current_colors.copy()
        self.persistent_files = persistent_files
        self.game_root = game_root
        
        main_layout = QVBoxLayout(self)
        
        tabs_area = QScrollArea()
        tabs_area.setWidgetResizable(True)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        audio_group = QGroupBox("Audio")
        audio_layout = QVBoxLayout()
        
        music_layout = QHBoxLayout()
        music_layout.addWidget(QLabel("Music Volume:"))
        self.music_slider = QSlider(Qt.Orientation.Horizontal)
        self.music_slider.setRange(0, 100)
        self.music_slider.setValue(int(current_music_vol * 100))
        self.music_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        music_layout.addWidget(self.music_slider)
        self.music_label = QLabel(f"{int(current_music_vol * 100)}%")
        music_layout.addWidget(self.music_label)
        audio_layout.addLayout(music_layout)
        
        fx_layout = QHBoxLayout()
        fx_layout.addWidget(QLabel("Hit FX Volume:"))
        self.fx_slider = QSlider(Qt.Orientation.Horizontal)
        self.fx_slider.setRange(0, 100)
        self.fx_slider.setValue(int(current_fx_vol * 100))
        self.fx_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        fx_layout.addWidget(self.fx_slider)
        self.fx_label = QLabel(f"{int(current_fx_vol * 100)}%")
        fx_layout.addWidget(self.fx_label)

        audio_layout.addLayout(fx_layout)

        ui_layout = QHBoxLayout()
        ui_layout.addWidget(QLabel("UI SFX Volume:"))
        self.ui_slider = QSlider(Qt.Orientation.Horizontal)
        self.ui_slider.setRange(0, 100)
        self.ui_slider.setValue(int(current_ui_vol * 100))
        self.ui_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ui_layout.addWidget(self.ui_slider)
        self.ui_label = QLabel(f"{int(current_ui_vol * 100)}%")
        ui_layout.addWidget(self.ui_label)
        audio_layout.addLayout(ui_layout)
        
        if hasattr(parent, 'installEventFilter'):
            parent.installEventFilter(self.music_slider)
            parent.installEventFilter(self.fx_slider)
            parent.installEventFilter(self.ui_slider)
        
        self.chk_persistent = QCheckBox("Persistent Song Files")
        self.chk_persistent.setChecked(self.persistent_files)
        audio_layout.addWidget(self.chk_persistent)
        
        audio_group.setLayout(audio_layout)
        content_layout.addWidget(audio_group)
        
        self.music_slider.valueChanged.connect(lambda v: self.music_label.setText(f"{v}%"))
        self.fx_slider.valueChanged.connect(lambda v: self.fx_label.setText(f"{v}%"))
        self.ui_slider.valueChanged.connect(lambda v: self.ui_label.setText(f"{v}%"))
        
        if hasattr(parent, 'ui_volume'):
            self.ui_slider.valueChanged.connect(lambda v: self.update_parent_ui_volume(parent, v))

        color_group = QGroupBox("Object Colors")
        color_layout = QVBoxLayout()
        self.color_combos = {}
        sorted_keys = sorted(self.current_colors.keys())
        for key in sorted_keys:
            if key == "hide": continue
            row = QHBoxLayout()
            row.addWidget(QLabel(key.replace("_", " ").title()))
            combo = QComboBox()
            combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            combo.addItems(COLOR_PALETTE.keys())
            current_val = self.current_colors[key]
            if current_val in COLOR_PALETTE:
                combo.setCurrentText(current_val)
            else:
                combo.setCurrentText(DEFAULT_COLORS.get(key, "Cyan (Note)"))
            self.color_combos[key] = combo
            row.addWidget(combo)
            color_layout.addLayout(row)
        
        btn_reset = QPushButton("Reset Colors")
        btn_reset.clicked.connect(self.reset_all_colors)
        color_layout.addWidget(btn_reset)
        
        color_group.setLayout(color_layout)
        content_layout.addWidget(color_group)

        sound_group = QGroupBox("Custom Sounds")
        sound_layout = QVBoxLayout()
        for name, filename in SOUND_FILES_MAP.items():
            display_name = SOUND_DISPLAY_NAMES.get(name, name)
            w = SoundSettingWidget(display_name, filename, self.game_root)
            w.soundReset.connect(self.on_sound_reset)
            w.soundChanged.connect(self.on_sound_changed)
            sound_layout.addWidget(w)
        sound_group.setLayout(sound_layout)
        content_layout.addWidget(sound_group)

        tabs_area.setWidget(content_widget)
        main_layout.addWidget(tabs_area)
        
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        main_layout.addLayout(button_layout)
        
    def on_sound_reset(self, filename):
        target = self.game_root / "ChartEditorResources" / filename
        try:
            if target.exists():
                os.remove(target)
            
            base_sounds = get_base_path()
            if not base_sounds.endswith("sounds"):
                base_sounds = os.path.join(base_sounds, "sounds")
            
            src = os.path.join(base_sounds, filename)
            if os.path.exists(src):
                shutil.copy2(src, target)
        except Exception as e:
            print(e)

    def on_sound_changed(self, filename, new_path):
        target = self.game_root / "ChartEditorResources" / filename
        try:
            audio = AudioSegment.from_file(new_path)
            audio.export(str(target), format="wav")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not convert sound: {e}")

    
    def update_parent_ui_volume(self, parent, value):
        if hasattr(parent, 'ui_volume') and hasattr(parent, 'sounds'):
            parent.ui_volume = value / 100.0
            for name, sound in parent.sounds.items():
                if name.startswith("UI"):
                    sound.set_volume(parent.ui_volume)
    
    def get_volumes(self):
        return self.music_slider.value() / 100.0, self.fx_slider.value() / 100.0, self.ui_slider.value() / 100.0
    
    def reset_all_colors(self):
         for key, combo in self.color_combos.items():
             default = DEFAULT_COLORS.get(key, "Cyan (Note)")
             if default in COLOR_PALETTE:
                 combo.setCurrentText(default)
    
    
    def get_colors(self):
        new_colors = {}
        for key, combo in self.color_combos.items():
            new_colors[key] = combo.currentText()
        return new_colors
    
    def get_persistent(self):
        return self.chk_persistent.isChecked()

class CopyDifficultyDialog(QDialog):
    def __init__(self, parent, available_diffs):
        super().__init__(parent)
        self.setWindowTitle("Copy From Difficulty")
        self.setModal(True)
        self.setFixedSize(300, 150)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Select difficulty to copy from:"))
        
        self.combo = QComboBox()
        self.combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo.addItems(available_diffs)
        layout.addWidget(self.combo)
        
        button_layout = QHBoxLayout()
        copy_btn = QPushButton("Copy From")
        copy_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        copy_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(copy_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
    def get_selected_diff(self):
        return self.combo.currentText()

class DeleteConfirmationDialog(QDialog):
    def __init__(self, parent, diff_name):
        super().__init__(parent)
        self.setWindowTitle("Delete Difficulty")
        self.setFixedSize(300, 150)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        
        layout = QVBoxLayout(self)
        
        lbl = QLabel(f"Are you sure you want to delete the\n'{diff_name}' difficulty?")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #FF6666;")
        layout.addWidget(lbl)
        
        lbl_warn = QLabel("This will delete the file and all metadata permanently.")
        lbl_warn.setWordWrap(True)
        lbl_warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_warn.setStyleSheet("font-size: 11px; color: #AAA;")
        layout.addWidget(lbl_warn)
        
        btn_layout = QHBoxLayout()
        yes_btn = QPushButton("Yes, Delete")
        yes_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        yes_btn.setStyleSheet("background-color: #833; font-weight: bold;")
        yes_btn.clicked.connect(self.accept)
        
        no_btn = QPushButton("Cancel")
        no_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        no_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(yes_btn)
        btn_layout.addWidget(no_btn)
        layout.addLayout(btn_layout)

class BPMMatchDialog(QDialog):
    def __init__(self, parent, audio_path):
        super().__init__(parent)
        self.setWindowTitle("BPM Matcher")
        self.setFixedSize(300, 200)
        self.setModal(True)
        self.audio_path = audio_path
        self.click_times = []
        self.calculated_bpm = 0
        self.is_running = False

        layout = QVBoxLayout(self)
        
        self.lbl_bpm = QLabel("Calculated BPM: --")
        self.lbl_bpm.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_bpm.setStyleSheet("font-size: 18px; font-weight: bold; color: #64C8FF;")
        layout.addWidget(self.lbl_bpm)
        
        self.btn_start = QPushButton("Start Music")
        self.btn_start.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_start.clicked.connect(self.start_matching)
        layout.addWidget(self.btn_start)
        
        self.btn_tap = QPushButton("Tap to Beat")
        self.btn_tap.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tap.setFixedHeight(60)
        self.btn_tap.setEnabled(False)
        self.btn_tap.clicked.connect(self.register_tap)
        self.btn_tap.setStyleSheet("background-color: #444; font-size: 14px;")
        layout.addWidget(self.btn_tap)
        
        btn_box = QHBoxLayout()
        self.btn_done = QPushButton("Done")
        self.btn_done.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_done.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_done)
        btn_box.addWidget(self.btn_cancel)
        layout.addLayout(btn_box)

    def start_matching(self):
        if not self.audio_path or not os.path.exists(self.audio_path):
            return
            
        try:
            pygame.mixer.music.load(str(self.audio_path))
            pygame.mixer.music.play()
            self.is_running = True
            self.btn_start.setEnabled(False)
            self.btn_tap.setEnabled(True)
            self.btn_tap.setStyleSheet("background-color: #285; font-size: 14px; font-weight: bold;")
            self.btn_tap.setFocus()
            self.click_times = []
        except Exception as e:
            print(str(e))

    def register_tap(self):
        if not self.is_running: return
        
        current_time = time.time()
        self.click_times.append(current_time)
        
        if len(self.click_times) > 1:
            intervals = []
            for i in range(1, len(self.click_times)):
                intervals.append(self.click_times[i] - self.click_times[i-1])
            
            avg_interval = sum(intervals) / len(intervals)
            if avg_interval > 0:
                raw_bpm = 60.0 / avg_interval
                self.calculated_bpm = round(raw_bpm)
                self.lbl_bpm.setText(f"Calculated BPM: {self.calculated_bpm}")

    def closeEvent(self, event):
        pygame.mixer.music.stop()
        super().closeEvent(event)
    
    def reject(self):
        pygame.mixer.music.stop()
        super().reject()

    def accept(self):
        pygame.mixer.music.stop()
        super().accept()

class AudioGenerator(QThread):
    progress = pyqtSignal(int, str)
    finished_processing = pyqtSignal(dict) 
    error_occurred = pyqtSignal(str)

    def __init__(self, source_path, output_dir, persistent):
        super().__init__()
        self.source_path = source_path
        self.output_dir = output_dir
        self.persistent = persistent
        
    def run(self):
        try:
            initialize_ffmpeg()
            audio_map = {}
            if not self.output_dir.exists():
                self.output_dir.mkdir(parents=True, exist_ok=True)
            
            self.progress.emit(10, "Loading audio...")
            try:
                audio = AudioSegment.from_file(str(self.source_path))
            except Exception as e:
                self.error_occurred.emit(f"Failed to load audio: {e}")
                return

            audio_map[1.0] = str(self.source_path)
            
            total = len(SPEEDS)
            current = 0
            
            for speed in SPEEDS:
                if speed == 1.0: 
                    current += 1
                    continue
                
                if self.persistent:
                    out_name = f"speed_{speed}x.mp3"
                else:
                    out_name = f"temp_{speed}x.mp3"

                out_path = self.output_dir / out_name

                if self.persistent and out_path.exists():
                    audio_map[speed] = str(out_path)
                    current += 1
                    continue

                self.progress.emit(10 + int((current / total) * 80), f"Generating {speed}x version...")
                
                try:
                    new_rate = int(audio.frame_rate * speed)
                    faster_audio = audio._spawn(audio.raw_data, overrides={'frame_rate': new_rate})
                    faster_audio = faster_audio.set_frame_rate(44100)
                    faster_audio.export(str(out_path), format="mp3")
                    audio_map[speed] = str(out_path)
                except Exception as e:
                    print(f"Error generating {speed}x: {e}")
                
                current += 1
                
            self.progress.emit(100, "Done!")
            self.finished_processing.emit(audio_map)
            
        except Exception as e:
            self.error_occurred.emit(str(e))

class LoadingDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Processing Audio")
        self.setFixedSize(350, 120)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)
        
        layout = QVBoxLayout(self)
        self.lbl_status = QLabel("Initializing...")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

    def update_progress(self, val, msg):
        self.progress_bar.setValue(val)
        self.lbl_status.setText(msg)

class TimelineWidget(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.beatmap: Optional[BeatmapData] = None
        
        self.current_time = 0.0
        self.target_time = 0.0
        self.zoom = 1.0
        self.target_zoom = 1.0
        self.pixels_per_beat = 200
        self.grid_snap_div = 4
        self.saved_grid_div = 4
        self.is_triplet_mode = False
        
        self.current_tool_type = "note"
        self.current_note_type = "normal"
        self.current_brawl_type = "hit"
        self.current_event_type = "flip"
        
        self.selected_objects: Set[HitObject] = set()
        self.clipboard: List[Dict] = []
        
        self.dragging_objects = False
        self.drag_mode = "move" 
        self.drag_offset_x = 0
        self.drag_start_time_map = {}
        self.drag_start_lane_map = {}
        self.drag_original_end_time_map = {}
        self.drag_last_snapped_time = None
        self.drag_last_lane = None
        
        self.last_click_pos = None
        self.last_click_time = 0
        self.click_cycle_index = 0
        
        self.last_mouse_pos = None
        self.selection_start = None
        self.selection_start_y = None
        self.selection_rect = None
        self.selection_last_mouse_y = None
        self.timeline_click_pos = None
        
        self.timeline_scrollbar: Optional[QScrollBar] = None
        
        self.undo_stack = []
        self.redo_stack = []
        self.max_undo_steps = 100
        
        self.elapsed_timer = QElapsedTimer()
        self.elapsed_timer.start()
        self.last_frame_time = 0
        
        self.smooth_timer = QTimer()
        screen = QApplication.primaryScreen()
        refresh_rate = screen.refreshRate() if screen else 60
        if refresh_rate < 1: refresh_rate = 60
        self.smooth_timer.setInterval(int(1000 / refresh_rate))
        self.smooth_timer.timeout.connect(self.smooth_update)
        self.smooth_timer.start()
        
        self.edge_scroll_timer = QTimer()
        self.edge_scroll_timer.setInterval(16)
        self.edge_scroll_timer.timeout.connect(self.on_edge_scroll)
        self.edge_scroll_speed = 0

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(400)

        self.col_bg = QColor(30, 30, 35)
        self.col_lane = QColor(45, 45, 50)
        self.col_line = QColor(60, 60, 65)
        self.col_beat = QColor(100, 100, 100)
        self.col_subbeat = QColor(60, 60, 60)
        self.col_cursor = QColor(255, 255, 255)
        self.col_selection = QColor(100, 150, 255, 100)
        self.col_selection_border = QColor(100, 150, 255, 200)
        self.col_required_zone = QColor(255, 50, 50, 50)
        
        self.color_config = DEFAULT_COLORS.copy()
        self.object_colors = {}
        self.update_color_objects()

    def update_color_objects(self):
        for key, name in self.color_config.items():
            hex_col = COLOR_PALETTE.get(name, "#FFFFFF")
            self.object_colors[key] = QColor(hex_col)

    def set_colors(self, new_colors):
        self.color_config = new_colors
        self.update_color_objects()
        self.update()

    def toggle_triplet(self):
        if not self.is_triplet_mode:
            self.saved_grid_div = self.grid_snap_div
            if self.grid_snap_div > 6:
                self.grid_snap_div = 6
            else:
                self.grid_snap_div = 3
            self.is_triplet_mode = True
        else:
            self.grid_snap_div = self.saved_grid_div
            self.is_triplet_mode = False
        
        if self.editor:
            self.editor.spin_grid.blockSignals(True)
            self.editor.spin_grid.setValue(self.grid_snap_div)
            self.editor.spin_grid.blockSignals(False)
        self.update()

    def set_scrollbar(self, scrollbar):
        self.timeline_scrollbar = scrollbar
    
    def update_scrollbar(self):
        if not self.timeline_scrollbar or not self.beatmap:
            return
        
        song_length_ms = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap.metadata.ActualAudioLength > 0 else 0
        
        if song_length_ms > 0:
            self.timeline_scrollbar.setEnabled(True)
            self.timeline_scrollbar.blockSignals(True)
            self.timeline_scrollbar.setMinimum(0)
            self.timeline_scrollbar.setMaximum(int(song_length_ms))
            
            visible_ms_range = self.x_to_ms(self.width()) - self.x_to_ms(0)
            self.timeline_scrollbar.setPageStep(max(1000, int(visible_ms_range)))
            self.timeline_scrollbar.setSingleStep(500) 
            self.timeline_scrollbar.setValue(int(self.current_time))
            self.timeline_scrollbar.blockSignals(False)
        else:
            self.timeline_scrollbar.setEnabled(False)

    def set_beatmap(self, beatmap: BeatmapData):
        self.beatmap = beatmap
        self.selected_objects.clear()
        self.clipboard.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.current_time = 0
        self.target_time = 0
        self.grid_snap_div = beatmap.metadata.GridSize
        self.target_zoom = beatmap.editor_zoom
        self.zoom = beatmap.editor_zoom
        if self.editor:
            self.editor.spin_grid.blockSignals(True)
            self.editor.spin_grid.setValue(self.grid_snap_div)
            self.editor.spin_grid.blockSignals(False)
        self.update_scrollbar()
        self.update()
    
    def save_undo_state(self):
        if not self.beatmap:
            return
        
        state = {
            'hit_objects': [
                {
                    'x': obj.x,
                    'y': obj.y,
                    'time': obj.time,
                    'type': obj.type,
                    'hitSound': obj.hitSound,
                    'objectParams': obj.objectParams,
                    'hitSample': obj.hitSample
                }
                for obj in self.beatmap.hit_objects
            ]
        }
        
        self.undo_stack.append(state)
        if len(self.undo_stack) > self.max_undo_steps:
            self.undo_stack.pop(0)
        
        self.redo_stack.clear()
    
    def undo(self):
        if not self.undo_stack or not self.beatmap:
            return
        
        current_state = self._get_current_state()
        self.redo_stack.append(current_state)
        
        prev_state = self.undo_stack.pop()
        
        self.beatmap.hit_objects.clear()
        for obj_data in prev_state['hit_objects']:
            self.beatmap.hit_objects.append(HitObject(
                obj_data['x'],
                obj_data['y'],
                obj_data['time'],
                obj_data['type'],
                obj_data['hitSound'],
                obj_data['objectParams'],
                obj_data['hitSample']
            ))
        
        self.selected_objects.clear()
        self.editor.mark_unsaved()
        self.update()
    
    def redo(self):
        if not self.redo_stack or not self.beatmap:
            return
        
        current_state = self._get_current_state()
        self.undo_stack.append(current_state)
        
        next_state = self.redo_stack.pop()
        
        self.beatmap.hit_objects.clear()
        for obj_data in next_state['hit_objects']:
            self.beatmap.hit_objects.append(HitObject(
                obj_data['x'],
                obj_data['y'],
                obj_data['time'],
                obj_data['type'],
                obj_data['hitSound'],
                obj_data['objectParams'],
                obj_data['hitSample']
            ))
        
        self.selected_objects.clear()
        self.editor.mark_unsaved()
        self.update()

    def smooth_update(self):
        current_time = self.elapsed_timer.elapsed()
        dt_ms = current_time - self.last_frame_time
        self.last_frame_time = current_time
        
        if dt_ms <= 0 or dt_ms > 100:
            return
        
        dt_seconds = dt_ms / 1000.0
        smoothness_per_second = 15.0
        
        time_changed = False
        zoom_changed = False
        
        time_diff = self.target_time - self.current_time
        if abs(time_diff) > 0.1:
            lerp_factor = min(1.0, smoothness_per_second * dt_seconds)
            self.current_time += time_diff * lerp_factor
            self.current_time = float(self.current_time) 
            time_changed = True
        else:
            self.current_time = self.target_time
        
        zoom_diff = self.target_zoom - self.zoom
        if abs(zoom_diff) > 0.001:
            lerp_factor = min(1.0, smoothness_per_second * dt_seconds)
            self.zoom += zoom_diff * lerp_factor
            zoom_changed = True
        else:
            self.zoom = self.target_zoom
        
        if time_changed or zoom_changed:
            if time_changed and not self.editor.is_playing:
                if abs(time_diff) > 10:
                    self.editor.sync_audio_to_time()
            
            if self.dragging_objects:
                self.update_dragged_objects()
            
            if self.selection_start is not None:
                self.update_selection_rect()

            self.update_scrollbar()
            self.update()

    def on_edge_scroll(self):
        self.target_time += self.edge_scroll_speed
        self.target_time = max(0, self.target_time)
        song_length_ms = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap and self.beatmap.metadata.ActualAudioLength > 0 else 0
        if song_length_ms > 0:
            self.target_time = min(self.target_time, song_length_ms)
            
        self.update_scrollbar()
        self.update_dragged_objects()
        self.update_selection_rect()
        self.update()

    def update_selection_rect(self):
        if self.selection_start is None or self.selection_last_mouse_y is None:
            return
        
        start_x = self.ms_to_x(self.selection_start)
        current_x = self.last_mouse_pos.x() if self.last_mouse_pos else start_x
        x1 = min(start_x, current_x)
        y1 = min(self.selection_start_y, self.selection_last_mouse_y)
        x2 = max(start_x, current_x)
        y2 = max(self.selection_start_y, self.selection_last_mouse_y)
        
        self.selection_rect = QRectF(x1, y1, x2-x1, y2-y1)
        
        center_y = self.height() / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2
        
        if self.beatmap:
            self.selected_objects.clear()
            for obj in self.beatmap.hit_objects:
                obj_x = self.ms_to_x(obj.time)
                
                if obj.is_event:
                    obj_y = center_y
                else:
                    obj_y = lane_0_y if obj.lane == 0 else lane_1_y
                
                if x1 <= obj_x <= x2 and y1 <= obj_y <= y2:
                    self.selected_objects.add(obj)
                elif obj.is_hold or obj.is_screamer or obj.is_spam:
                    end_x = self.ms_to_x(obj.end_time)
                    if x1 <= end_x <= x2 and y1 <= obj_y <= y2:
                        self.selected_objects.add(obj)

    def ms_to_x(self, ms):
        bpm = self.beatmap.metadata.BPM if self.beatmap else 120
        px_per_ms = (self.pixels_per_beat * (bpm / 60000)) * self.zoom
        return (ms - self.current_time) * px_per_ms + TIMELINE_START_X

    def x_to_ms(self, x):
        bpm = self.beatmap.metadata.BPM if self.beatmap else 120
        px_per_ms = (self.pixels_per_beat * (bpm / 60000)) * self.zoom
        return (x - TIMELINE_START_X) / px_per_ms + self.current_time

    def get_snap_time(self, ms):
        if not self.beatmap: return ms
        bpm = self.beatmap.metadata.BPM
        if bpm <= 0: return ms
        beat_len = 60000 / bpm
        snap_len = beat_len / self.grid_snap_div
        offset = self.beatmap.metadata.Offset
        return round((ms - offset) / snap_len) * snap_len + offset

    def check_start_note_requirement(self):
        return True

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self.col_bg)

        if not self.beatmap:
            p.setPen(Qt.GlobalColor.white)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No Chart Loaded")
            return

        w, h = self.width(), self.height()
        center_y = h / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2

        p.fillRect(0, int(lane_0_y - 30), w, 60, self.col_lane)
        p.fillRect(0, int(lane_1_y - 30), w, 60, self.col_lane)
        
        if not self.check_start_note_requirement():
            pass

        song_length_ms = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap.metadata.ActualAudioLength > 0 else 0
        
        beatmap_end_ms = 0
        if self.beatmap.hit_objects:
            last_obj = max(self.beatmap.hit_objects, key=lambda o: o.end_time if o.type == 128 else o.time)
            beatmap_end_ms = (last_obj.end_time if last_obj.type == 128 else last_obj.time) / 1000.0 * 1000 + 2000

        bpm = self.beatmap.metadata.BPM
        if bpm > 0:
            beat_ms = 60000 / bpm
            start_ms = max(0, self.x_to_ms(0))
            end_ms = min(self.x_to_ms(w), song_length_ms) if song_length_ms > 0 else self.x_to_ms(w)
            
            current_beat = max(0, int((start_ms - self.beatmap.metadata.Offset) / beat_ms))
            t = current_beat * beat_ms + self.beatmap.metadata.Offset
            
            last_x = -1000
            min_line_spacing = 8
            
            visual_grid_div = self.grid_snap_div
            test_div = self.grid_snap_div
            while test_div > 1:
                test_snap_len = beat_ms / test_div
                test_x1 = self.ms_to_x(t)
                test_x2 = self.ms_to_x(t + test_snap_len)
                if abs(test_x2 - test_x1) >= min_line_spacing:
                    visual_grid_div = test_div
                    break
                if test_div % 2 == 0:
                    test_div = test_div // 2
                else:
                    test_div = (test_div // 2) + 1 if test_div > 1 else 1
            else:
                visual_grid_div = max(1, test_div)
            
            while t < end_ms:
                if t >= 0:
                    x = self.ms_to_x(t)
                    if 0 <= x <= w and abs(x - last_x) >= min_line_spacing:
                        p.setPen(QPen(self.col_beat, 1))
                        p.drawLine(int(x), 0, int(x), h)
                        last_x = x
                    
                    for i in range(1, visual_grid_div):
                        sub_t = t + (beat_ms * i / visual_grid_div)
                        if sub_t > end_ms: break
                        if sub_t >= 0:
                            sub_x = self.ms_to_x(sub_t)
                            if 0 <= sub_x <= w and abs(sub_x - last_x) >= min_line_spacing:
                                p.setPen(QPen(self.col_subbeat, 1, Qt.PenStyle.DotLine))
                                p.drawLine(int(sub_x), 0, int(sub_x), h)
                                last_x = sub_x
                t += beat_ms

        if beatmap_end_ms > 0:
            end_x = self.ms_to_x(beatmap_end_ms)
            if 0 <= end_x <= w:
                p.setPen(QPen(QColor(255, 0, 0), 3))
                p.drawLine(int(end_x), 0, int(end_x), h)

        p.setPen(QPen(self.col_cursor, 2))
        p.drawLine(TIMELINE_START_X, 0, TIMELINE_START_X, h)

        strip_h = 20
        strip_y = h - strip_h
        vis_min_ms = self.x_to_ms(0)
        vis_max_ms = self.x_to_ms(w)
        
        flip_objs = sorted([o for o in self.beatmap.hit_objects if o.is_flip or o.is_instant_flip], key=lambda x: x.time)
        flip_times = [0] + [o.time for o in flip_objs]
        cur_flipped = False
        
        for k in range(len(flip_times)):
            st = flip_times[k]
            et = flip_times[k+1] if k+1 < len(flip_times) else song_length_ms + 10000
            
            if et < vis_min_ms:
                cur_flipped = not cur_flipped; continue
            if st > vis_max_ms:
                break
            
            sx = int(self.ms_to_x(st))
            ex = int(self.ms_to_x(et))
            w_rect = ex - sx
            
            if w_rect > 0:
                col = QColor("yellow") if cur_flipped else QColor("blue")
                col.setAlpha(150)
                p.setBrush(col)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(sx, int(strip_y), w_rect, int(strip_h))
                
                p.setPen(QColor("white"))
                arrow_txt = ">>>" if cur_flipped else "<<<"
                spacing = 300
                start_marker = (sx // spacing) * spacing
                if start_marker < sx: start_marker += spacing
                curr_x = start_marker
                while curr_x < ex:
                    if curr_x > 0 and curr_x < w:
                        p.drawText(curr_x, int(strip_y), 50, 20, Qt.AlignmentFlag.AlignCenter, arrow_txt)
                    curr_x += spacing
            cur_flipped = not cur_flipped

        centers = sorted([o for o in self.beatmap.hit_objects if o.is_toggle_center], key=lambda x: x.time)
        center_times = [0] + [o.time for o in centers]
        cur_centered = False
        
        for k in range(len(center_times)):
            st = center_times[k]
            et = center_times[k+1] if k+1 < len(center_times) else song_length_ms + 10000
            if et < vis_min_ms: cur_centered = not cur_centered; continue
            if st > vis_max_ms: break
            
            if cur_centered:
                sx = int(self.ms_to_x(st))
                ex = int(self.ms_to_x(et))
                w_rect = ex - sx
                if w_rect > 0:
                    p.setBrush(QColor("purple"))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawRect(sx, 0, w_rect, 10)
            
            cur_centered = not cur_centered

        
        sorted_flips = sorted([o for o in self.beatmap.hit_objects if o.is_flip or o.is_instant_flip], key=lambda x: x.time)
        obj_flip_color = {}
        is_yellow = False
        for o in sorted_flips:
             is_yellow = not is_yellow
             obj_flip_color[id(o)] = QColor("yellow") if is_yellow else QColor("blue")

        note_radius = 20
        hold_end_radius = 12
        screamer_end_radius = 15
        brawl_size = 30

        non_events = [o for o in self.beatmap.hit_objects if not o.is_event]
        events = [o for o in self.beatmap.hit_objects if o.is_event]
        objects_to_draw = sorted(non_events, key=lambda o: o in self.selected_objects) + sorted(events, key=lambda o: o in self.selected_objects)
        for obj in objects_to_draw:
            x = self.ms_to_x(obj.time)
            
            if obj.is_event:
                if -50 < x < w + 50:
                    is_selected = obj in self.selected_objects
                    color = self.object_colors["flip"]
                    
                    if obj.is_toggle_center:
                        color = QColor("purple")
                    elif obj.is_flip or obj.is_instant_flip:
                        color = obj_flip_color.get(id(obj), color)
                        
                    if is_selected:
                        color = color.lighter(150)
                    p.setPen(QPen(color, 3))
                    p.drawLine(int(x), int(lane_0_y), int(x), int(lane_1_y))
                    
                    if obj.is_instant_flip:
                         p.setBrush(QColor("white"))
                    else:
                         p.setBrush(color)
                    p.drawEllipse(QPointF(x, center_y), 8, 8)
            else:
                y = lane_0_y if obj.lane == 0 else lane_1_y
                is_selected = obj in self.selected_objects
                
                if obj.is_spam:
                    end_x = self.ms_to_x(obj.end_time)
                    if end_x > x or -50 < x < w + 50:
                        p.setPen(QPen(self.object_colors["spam_line"], 4))
                        p.drawLine(int(x), int(lane_0_y), int(end_x), int(lane_0_y))
                        p.drawLine(int(x), int(lane_1_y), int(end_x), int(lane_1_y))
                        
                        col_spam = self.object_colors["spam"]
                        if is_selected: col_spam = col_spam.lighter(150)

                        p.setBrush(QBrush(col_spam))
                        pen_col = Qt.GlobalColor.white if not is_selected else col_spam.lighter(180)
                        p.setPen(QPen(pen_col, 2))
                        
                        p.drawEllipse(QPointF(x, lane_0_y), note_radius, note_radius)
                        p.drawEllipse(QPointF(x, lane_1_y), note_radius, note_radius)
                        p.drawEllipse(QPointF(end_x, lane_0_y), hold_end_radius, hold_end_radius)
                        p.drawEllipse(QPointF(end_x, lane_1_y), hold_end_radius, hold_end_radius)

                elif obj.is_screamer:
                    end_x = self.ms_to_x(obj.end_time)
                    other_y = lane_1_y if obj.lane == 0 else lane_0_y
                    
                    if -50 < x < w + 50 or end_x > -50:
                         p.setPen(QPen(self.object_colors["double_line"], 4))
                         p.drawLine(int(x), int(y), int(end_x), int(other_y))
                         
                         col_screamer = self.object_colors["double"]
                         if is_selected: col_screamer = col_screamer.lighter(150)

                         p.setBrush(QBrush(col_screamer))
                         p.setPen(QPen(Qt.GlobalColor.white if not is_selected else col_screamer.lighter(180), 2))
                         p.drawEllipse(QPointF(x, y), note_radius, note_radius)
                         p.drawEllipse(QPointF(end_x, other_y), screamer_end_radius, screamer_end_radius)

                elif obj.is_hold:
                    end_x = self.ms_to_x(obj.end_time)
                    if end_x > x:
                        p.setPen(QPen(self.object_colors["hold_line"], 4))
                        p.drawLine(int(x), int(y), int(end_x), int(y))
                        
                        col_hold = self.object_colors["hold"]
                        if is_selected: col_hold = col_hold.lighter(150)

                        p.setBrush(QBrush(col_hold))
                        p.setPen(QPen(Qt.GlobalColor.white if not is_selected else col_hold.lighter(180), 2))
                        p.drawEllipse(QPointF(end_x, y), hold_end_radius, hold_end_radius)

                elif obj.is_brawl_hold or obj.is_brawl_spam:
                    end_x = self.ms_to_x(obj.end_time)
                    if end_x > x:
                        col_key = "brawl_hold" if obj.is_brawl_hold else "brawl_spam"
                        line_col_key = "brawl_hold_line" if obj.is_brawl_hold else "brawl_spam_line"
                        line_col = self.object_colors.get(line_col_key, self.object_colors[col_key])
                        
                        draw_lanes = []
                        if obj.is_brawl_spam:
                            draw_lanes = [lane_1_y]
                        else:
                            draw_lanes = [lane_0_y if obj.lane == 0 else lane_1_y]

                        p.setPen(QPen(line_col, 4))
                        for ly in draw_lanes:
                            p.drawLine(int(x), int(ly), int(end_x), int(ly))
                        
                        col = self.object_colors[col_key]
                        if is_selected: col = col.lighter(150)
                        p.setBrush(QBrush(col))
                        p.setPen(QPen(Qt.GlobalColor.white, 2))
                        
                        head_size = brawl_size
                        tail_size = brawl_size * 0.7
                        for ly in draw_lanes:
                            rect = QRectF(x - head_size/2, ly - head_size/2, head_size, head_size)
                            p.drawRect(rect)
                        
                        tail_col = col
                        if obj.is_brawl_hold_knockout or obj.is_brawl_spam_knockout:
                             base_tail = self.object_colors.get("brawl_knockout", Qt.GlobalColor.black)
                             tail_col = QColor(base_tail)
                             if is_selected: tail_col = tail_col.lighter(150)
                        
                        p.setBrush(QBrush(tail_col))
                        for ly in draw_lanes:
                            rect_end = QRectF(end_x - tail_size/2, ly - tail_size/2, tail_size, tail_size)
                            p.drawRect(rect_end)
                        
                        p.setPen(QPen(Qt.GlobalColor.white))
                        font = p.font()
                        font.setBold(True)
                        font.setPointSize(12)
                        p.setFont(font)
                        cop_num = obj.brawl_cop_number if hasattr(obj, 'brawl_cop_number') else 1
                        for ly in draw_lanes:
                            rect = QRectF(x - head_size/2, ly - head_size/2, head_size, head_size)
                            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(cop_num))
                
                if not obj.is_screamer and not obj.is_spam and not obj.is_brawl_hold and not obj.is_brawl_spam:
                    if -50 < x < w + 50 or (obj.is_hold and self.ms_to_x(obj.end_time) > -50):
                        if obj.is_freestyle:
                            color = QColor(self.object_colors["freestyle"])
                            if is_selected: color = color.lighter(150)
                            p.setBrush(QBrush(color))
                            p.setPen(QPen(Qt.GlobalColor.white if not is_selected else color.lighter(180), 2))
                            p.drawEllipse(QPointF(x, center_y), note_radius, note_radius)
                            if obj.is_hide:
                                p.setBrush(QBrush(QColor("black")))
                                p.setPen(Qt.PenStyle.NoPen)
                                p.drawEllipse(QPointF(x, center_y), 6, 6)
                        elif obj.is_brawl_hit:
                            color = self.object_colors["brawl_hit"]
                            if is_selected: color = color.lighter(150)
                            p.setBrush(QBrush(color))
                            p.setPen(QPen(Qt.GlobalColor.white, 2))
                            rect = QRectF(x - brawl_size/2, y - brawl_size/2, brawl_size, brawl_size)
                            p.drawRect(rect)
                            p.setPen(QPen(Qt.GlobalColor.white))
                            font = p.font()
                            font.setBold(True)
                            font.setPointSize(12)
                            p.setFont(font)
                            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(obj.brawl_cop_number))
                        
                        elif obj.is_brawl_final:
                            color = self.object_colors["brawl_knockout"]
                            if is_selected: color = QColor(60, 60, 60)
                            p.setBrush(QBrush(color))
                            p.setPen(QPen(Qt.GlobalColor.white, 2))
                            rect = QRectF(x - brawl_size/2, y - brawl_size/2, brawl_size, brawl_size)
                            p.drawRect(rect)
                            p.setPen(QPen(Qt.GlobalColor.white))
                            font = p.font()
                            font.setBold(True)
                            font.setPointSize(12)
                            p.setFont(font)
                            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(obj.brawl_cop_number))
                        
                        elif obj.is_spike:
                            color = self.object_colors["spike"]
                            if is_selected: color = color.lighter(150)
                            p.setBrush(QBrush(color))
                            p.setPen(QPen(Qt.GlobalColor.white if not is_selected else color.lighter(180), 2))
                            
                            spike_size = note_radius * 1.3
                            if obj.lane == 0: 
                                points = [
                                    QPointF(x, y + spike_size),
                                    QPointF(x + spike_size * 0.7, y - spike_size * 0.4),
                                    QPointF(x - spike_size * 0.7, y - spike_size * 0.4)
                                ]
                            else: 
                                points = [
                                    QPointF(x, y - spike_size),
                                    QPointF(x + spike_size * 0.7, y + spike_size * 0.4),
                                    QPointF(x - spike_size * 0.7, y + spike_size * 0.4)
                                ]
                            p.drawPolygon(points)
                        elif not obj.is_freestyle:
                            color = self.object_colors["note"]
                            if obj.is_hold:
                                color = self.object_colors["hold"]
                            elif obj.is_mid:
                                color = self.object_colors["mid"]
                            
                            if is_selected:
                                color = color.lighter(150)
                                
                            p.setBrush(QBrush(color))
                            p.setPen(QPen(Qt.GlobalColor.white if not is_selected else color.lighter(180), 2))
                            p.drawEllipse(QPointF(x, y), note_radius, note_radius)
                        
                        if obj.is_hide and not obj.is_freestyle and not obj.is_brawl_hit and not obj.is_brawl_final:
                            p.setBrush(QBrush(QColor("black")))
                            p.setPen(Qt.PenStyle.NoPen)
                            p.drawEllipse(QPointF(x, y), 6, 6)
                        
                        if obj.is_fly_in:
                            p.setBrush(QBrush(self.object_colors["fly_in_marker"]))
                            p.setPen(Qt.PenStyle.NoPen)
                            p.drawEllipse(QPointF(x, y), 6, 6)

        if self.selection_rect:
            p.setBrush(QBrush(self.col_selection))
            p.setPen(QPen(self.col_selection_border, 2))
            p.drawRect(self.selection_rect)


    def get_object_at_pos(self, pos, tolerance=30):
        if not self.beatmap:
            return None, None
        
        center_y = self.height() / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2
        
        closest_obj = None
        min_dist = float('inf')
        click_type = None 
        
        for obj in self.beatmap.hit_objects:
            x = self.ms_to_x(obj.time)
            
            if obj.is_event or obj.is_freestyle:
                dy = center_y - pos.y()
                dx = x - pos.x()
                dist = (dx*dx + dy*dy) ** 0.5
                if dist < tolerance and dist < min_dist:
                    min_dist = dist
                    closest_obj = obj
                    click_type = 'head'
            else:
                obj_y = lane_0_y if obj.lane == 0 else lane_1_y
                
                if obj.is_spam:
                    for ly in [lane_0_y, lane_1_y]:
                        dx = x - pos.x()
                        dy = ly - pos.y()
                        dist = (dx*dx + dy*dy) ** 0.5
                        if dist < tolerance and dist < min_dist:
                            min_dist = dist
                            closest_obj = obj
                            click_type = 'head'
                    
                    end_x = self.ms_to_x(obj.end_time)
                    for ly in [lane_0_y, lane_1_y]:
                        dx_end = end_x - pos.x()
                        dy_end = ly - pos.y()
                        dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                        if dist_end < tolerance and dist_end < min_dist:
                            min_dist = dist_end
                            closest_obj = obj
                            click_type = 'tail'

                elif obj.is_brawl_spam:
                    ly = lane_1_y
                    dx = x - pos.x()
                    dy = ly - pos.y()
                    dist = (dx*dx + dy*dy) ** 0.5
                    if dist < tolerance and dist < min_dist:
                        min_dist = dist
                        closest_obj = obj
                        click_type = 'head'
                    
                    end_x = self.ms_to_x(obj.end_time)
                    dx_end = end_x - pos.x()
                    dy_end = ly - pos.y()
                    dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                    if dist_end < tolerance and dist_end < min_dist:
                        min_dist = dist_end
                        closest_obj = obj
                        click_type = 'tail'

                elif obj.is_brawl_hold:
                    dx = x - pos.x()
                    dy = obj_y - pos.y()
                    dist = (dx*dx + dy*dy) ** 0.5
                    if dist < tolerance and dist < min_dist:
                        min_dist = dist
                        closest_obj = obj
                        click_type = 'head'

                    end_x = self.ms_to_x(obj.end_time)
                    dx_end = end_x - pos.x()
                    dy_end = obj_y - pos.y()
                    dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                    if dist_end < tolerance and dist_end < min_dist:
                        min_dist = dist_end
                        closest_obj = obj
                        click_type = 'tail'

                else:
                    dx = x - pos.x()
                    dy = obj_y - pos.y()
                    dist = (dx*dx + dy*dy) ** 0.5
                    
                    if dist < tolerance and dist < min_dist:
                        min_dist = dist
                        closest_obj = obj
                        click_type = 'head'
                    
                    if obj.is_hold:
                        end_x = self.ms_to_x(obj.end_time)
                        dx_end = end_x - pos.x()
                        dist_end = (dx_end*dx_end + dy*dy) ** 0.5
                        if dist_end < tolerance and dist_end < min_dist:
                            min_dist = dist_end
                            closest_obj = obj
                            click_type = 'tail'
                    
                    if obj.is_screamer:
                        end_x = self.ms_to_x(obj.end_time)
                        other_y = lane_1_y if obj.lane == 0 else lane_0_y
                        
                        dx_end = end_x - pos.x()
                        dy_end = other_y - pos.y()
                        dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                        
                        if dist_end < tolerance + 5 and dist_end < min_dist:
                             min_dist = dist_end
                             closest_obj = obj
                             click_type = 'tail'
        
        return closest_obj, click_type

    def get_all_objects_at_pos(self, pos, tolerance=30):
        if not self.beatmap:
            return []
        
        center_y = self.height() / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2
        
        matching_objects = []
        
        for obj in self.beatmap.hit_objects:
            x = self.ms_to_x(obj.time)
            
            if obj.is_event or obj.is_freestyle:
                dy = center_y - pos.y()
                dx = x - pos.x()
                dist = (dx*dx + dy*dy) ** 0.5
                if dist < tolerance:
                    matching_objects.append((obj, 'head', dist))
            else:
                obj_y = lane_0_y if obj.lane == 0 else lane_1_y
                
                if obj.is_spam:
                    for ly in [lane_0_y, lane_1_y]:
                        dx = x - pos.x()
                        dy = ly - pos.y()
                        dist = (dx*dx + dy*dy) ** 0.5
                        if dist < tolerance:
                            matching_objects.append((obj, 'head', dist))
                            break
                    
                    end_x = self.ms_to_x(obj.end_time)
                    for ly in [lane_0_y, lane_1_y]:
                        dx_end = end_x - pos.x()
                        dy_end = ly - pos.y()
                        dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                        if dist_end < tolerance:
                            if not any(o is obj for o, _, _ in matching_objects):
                                matching_objects.append((obj, 'tail', dist_end))
                            break

                elif obj.is_brawl_spam:
                    ly = lane_1_y
                    dx = x - pos.x()
                    dy = ly - pos.y()
                    dist = (dx*dx + dy*dy) ** 0.5
                    if dist < tolerance:
                        matching_objects.append((obj, 'head', dist))
                    
                    end_x = self.ms_to_x(obj.end_time)
                    dx_end = end_x - pos.x()
                    dy_end = ly - pos.y()
                    dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                    if dist_end < tolerance:
                        if not any(o is obj for o, _, _ in matching_objects):
                            matching_objects.append((obj, 'tail', dist_end))

                elif obj.is_brawl_hold:
                    dx = x - pos.x()
                    dy = obj_y - pos.y()
                    dist = (dx*dx + dy*dy) ** 0.5
                    if dist < tolerance:
                        matching_objects.append((obj, 'head', dist))

                    end_x = self.ms_to_x(obj.end_time)
                    dx_end = end_x - pos.x()
                    dy_end = obj_y - pos.y()
                    dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                    if dist_end < tolerance:
                        if not any(o is obj for o, _, _ in matching_objects):
                            matching_objects.append((obj, 'tail', dist_end))

                else:
                    dx = x - pos.x()
                    dy = obj_y - pos.y()
                    dist = (dx*dx + dy*dy) ** 0.5
                    
                    if dist < tolerance:
                        matching_objects.append((obj, 'head', dist))
                    
                    if obj.is_hold:
                        end_x = self.ms_to_x(obj.end_time)
                        dx_end = end_x - pos.x()
                        dist_end = (dx_end*dx_end + dy*dy) ** 0.5
                        if dist_end < tolerance:
                            if not any(o is obj for o, _, _ in matching_objects):
                                matching_objects.append((obj, 'tail', dist_end))
                    
                    if obj.is_screamer:
                        end_x = self.ms_to_x(obj.end_time)
                        other_y = lane_1_y if obj.lane == 0 else lane_0_y
                        
                        dx_end = end_x - pos.x()
                        dy_end = other_y - pos.y()
                        dist_end = (dx_end*dx_end + dy_end*dy_end) ** 0.5
                        
                        if dist_end < tolerance + 5:
                            if not any(o is obj for o, _, _ in matching_objects):
                                matching_objects.append((obj, 'tail', dist_end))
        
        matching_objects.sort(key=lambda x: x[2])
        return matching_objects

    def mousePressEvent(self, e: QMouseEvent):
        if not self.beatmap: return

        center_y = self.height() / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2
        
        in_lane_area = (lane_0_y - 40 < e.pos().y() < lane_1_y + 40)
        
        current_click_time = time.time()

        if e.button() == Qt.MouseButton.LeftButton:
            all_objects = self.get_all_objects_at_pos(e.pos()) if in_lane_area else []
            
            clicked_obj = None
            click_type = None
            
            if all_objects:
                is_same_position = (self.last_click_pos is not None and 
                                   abs(self.last_click_pos.x() - e.pos().x()) < 5 and 
                                   abs(self.last_click_pos.y() - e.pos().y()) < 5)
                
                if is_same_position and len(all_objects) > 1:
                    self.click_cycle_index = (self.click_cycle_index + 1) % len(all_objects)
                else:
                    self.click_cycle_index = 0
                
                clicked_obj, click_type, _ = all_objects[self.click_cycle_index]
                
                self.last_click_pos = e.pos()
                self.last_click_time = current_click_time
            else:
                self.last_click_pos = None
                self.click_cycle_index = 0
            
            if clicked_obj:
                if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    if clicked_obj in self.selected_objects:
                        self.selected_objects.remove(clicked_obj)
                    else:
                        self.selected_objects.add(clicked_obj)
                    self.drag_mode = 'move'
                else:
                    if clicked_obj not in self.selected_objects:
                        self.selected_objects.clear()
                        self.selected_objects.add(clicked_obj)
                    
                    if click_type == 'tail' and len(self.selected_objects) == 1:
                        self.drag_mode = 'resize'
                    else:
                        self.drag_mode = 'move'
                
                self.save_undo_state()
                self.dragging_objects = True
                self.last_mouse_pos = e.pos()
                self.drag_start_time_map.clear()
                self.drag_start_lane_map.clear()
                self.drag_original_end_time_map.clear()
                self.drag_last_snapped_time = None
                self.drag_last_lane = None
                
                for obj in self.selected_objects:
                    self.drag_start_time_map[obj] = obj.time
                    self.drag_start_lane_map[obj] = obj.lane if not obj.is_event else -1
                    if obj.type == 128:
                        self.drag_original_end_time_map[obj] = obj.end_time
                
                self.update()
                return
            
            self.selected_objects.clear()
            
            if not in_lane_area:
                self.timeline_click_pos = e.pos()
                self.selection_start = self.x_to_ms(e.pos().x())
                self.selection_start_y = e.pos().y()
                self.selection_rect = None
                return
            
            if in_lane_area:
                ms = self.x_to_ms(e.pos().x())
                snapped_ms = int(self.get_snap_time(ms))
                
                song_length_ms = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap.metadata.ActualAudioLength > 0 else 0
                
                if snapped_ms < 0 or (song_length_ms > 0 and snapped_ms > song_length_ms):
                    return
                
                if self.current_tool_type == "note" or self.current_tool_type == "brawl":
                    dist_0 = abs(e.pos().y() - lane_0_y)
                    dist_1 = abs(e.pos().y() - lane_1_y)
                    clicked_lane = 0 if dist_0 < dist_1 else 1
                    
                    x_pos = 255 if clicked_lane == 0 else 256
                    y_pos = 0
                    
                    hit_sound = 0
                    note_type = 1
                    params = "0"
                    sample = "0:0:0:"
                    
                    if self.current_tool_type == "brawl":
                        params = "3"
                        cop_offset = 0
                        if hasattr(self.editor, 'brawl_cop_index'):
                            if self.editor.brawl_cop_index == 2: cop_offset = 2
                            elif self.editor.brawl_cop_index == 3: cop_offset = 8
                            elif self.editor.brawl_cop_index == 4: cop_offset = 10
                        
                        if self.current_brawl_type == "hit":
                            hit_sound = 0 + cop_offset
                        elif self.current_brawl_type == "final":
                            hit_sound = 4 + cop_offset
                        elif self.current_brawl_type == "hold":
                            note_type = 128
                            hit_sound = 0 + cop_offset
                            sample = "3:1:0:0:"
                        elif self.current_brawl_type == "hold_knockout":
                            note_type = 128
                            hit_sound = 4 + cop_offset
                            sample = "3:1:0:0:"
                        elif self.current_brawl_type == "spam":
                            note_type = 128
                            hit_sound = 0 + cop_offset
                            sample = "3:0:0:0:"
                            clicked_lane = 1
                            x_pos = 256
                        elif self.current_brawl_type == "spam_knockout":
                            note_type = 128
                            hit_sound = 4 + cop_offset
                            sample = "3:0:0:0:"
                            clicked_lane = 1
                            x_pos = 256
                    else:
                        style = self.editor.combo_note_style.currentText()
                        
                        if self.current_note_type == "freestyle":
                            x_pos = 427
                            if style == "Hide":
                                hit_sound = 8
                        elif self.current_note_type == "spike":
                            hit_sound = 2
                            if style == "Fly In":
                                params = "1"
                        elif self.current_note_type == "hold":
                            note_type = 128
                            hit_sound = 0
                        elif self.current_note_type == "normal":
                             if style == "Hide":
                                 hit_sound = 8
                             elif style == "Fly In":
                                 params = "1"
                        elif self.current_note_type == "screamer":
                             note_type = 128
                             hit_sound = 2 
                        elif self.current_note_type == "spam":
                             note_type = 128
                             hit_sound = 4
                             x_pos = 427
                    
                    if note_type == 128:
                        bpm = self.beatmap.metadata.BPM if self.beatmap.metadata.BPM > 0 else 120
                        beat_ms = 60000 / bpm
                        snap_len = beat_ms / self.editor.timeline.grid_snap_div if hasattr(self.editor, 'timeline') else beat_ms / 4
                        end_ms = snapped_ms + max(10, snap_len)
                        params = str(int(end_ms))

                    is_screamer = (note_type == 128 and hit_sound == 2)
                    is_spam = (note_type == 128 and hit_sound == 4)
                    is_brawl_hold_spam = sample.startswith("3:")
                    is_freestyle = (x_pos == 427 and note_type == 1)
                    is_spike_note = (hit_sound == 2 and note_type != 128)

                    if self.is_space_free(snapped_ms, int(params) if note_type == 128 else snapped_ms, clicked_lane, is_screamer=is_screamer, is_spam=is_spam, is_brawl_hold_spam=is_brawl_hold_spam, is_freestyle=is_freestyle, is_spike=is_spike_note):
                        self.save_undo_state()
                        new_obj = HitObject(x_pos, y_pos, snapped_ms, note_type, hit_sound, params, sample)
                        self.beatmap.hit_objects.append(new_obj)
                        self.beatmap.hit_objects.sort(key=lambda x: x.time)
                        self.editor.mark_unsaved()
                        self.editor.play_ui_sound_suppressed('UI Place')
                
                elif self.current_tool_type == "event":
                    hit_sound = 0
                    if self.current_event_type == "toggle_center":
                        hit_sound = 2
                    elif self.current_event_type == "instant_flip":
                        hit_sound = 8
                    
                    if self.is_space_free(snapped_ms, snapped_ms, -1):
                        self.save_undo_state()
                        self.beatmap.hit_objects.append(HitObject(384, 0, snapped_ms, 1, hit_sound, "Flip", "0:0:0:"))
                        self.beatmap.hit_objects.sort(key=lambda x: x.time)
                        self.editor.mark_unsaved()
                        self.editor.play_ui_sound_suppressed('UI Place')
                
                self.update()

        elif e.button() == Qt.MouseButton.RightButton:
            to_remove, _ = self.get_object_at_pos(e.pos(), tolerance=40)
            
            if to_remove:
                self.save_undo_state()
                self.beatmap.hit_objects.remove(to_remove)
                if to_remove in self.selected_objects:
                    self.selected_objects.remove(to_remove)
                if to_remove in self.drag_start_time_map:
                    del self.drag_start_time_map[to_remove]
                if to_remove in self.drag_start_lane_map:
                    del self.drag_start_lane_map[to_remove]
                if to_remove in self.drag_original_end_time_map:
                    del self.drag_original_end_time_map[to_remove]
                if not self.selected_objects:
                    self.dragging_objects = False
                self.editor.mark_unsaved()
                self.update()

    def is_space_free(self, start_t, end_t, lane, ignore_obj=None, is_screamer=False, is_spam=False, is_brawl_hold_spam=False, is_freestyle=False, tail_lane=None, is_spike=False):
        start_t = int(start_t)
        end_t = int(end_t)
        new_footprints = []
        
        if is_spam or is_brawl_hold_spam:
            h_lane = tail_lane if tail_lane is not None else lane
            new_footprints.append((start_t, start_t, h_lane))

            body_start = start_t + 1
            body_end = max(start_t, end_t - 1)
            if body_end >= body_start:
                new_footprints.append((body_start, body_end, 0))
                new_footprints.append((body_start, body_end, 1))
            
            t_lane = tail_lane if tail_lane is not None else lane
            new_footprints.append((end_t, end_t, t_lane))
        elif is_screamer:
            new_footprints.append((start_t, start_t, lane))
            other_lane = 1 if lane == 0 else 0
            new_footprints.append((end_t, end_t, other_lane))
        elif is_freestyle:
            new_footprints.append((start_t, end_t, 2))
        else:
            new_footprints.append((start_t, end_t, lane))

        for obj in self.beatmap.hit_objects:
            if ignore_obj is not None:
                if isinstance(ignore_obj, (set, list, tuple)):
                    if obj in ignore_obj: continue
                elif obj is ignore_obj:
                     continue
            
            if lane == -1 and not is_freestyle: 
                if obj.is_event:
                    if abs(obj.time - start_t) < 5: 
                        return False
                continue

            if obj.is_event: continue
            
            if is_freestyle:
                if obj.is_freestyle:
                     if max(start_t, obj.time) <= min(end_t, obj.end_time if hasattr(obj, 'end_time') else obj.time):
                         return False
                elif obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam:
                     if max(start_t, obj.time) <= min(end_t, obj.end_time):
                         return False
                continue

            if obj.is_freestyle:
                if is_spam or is_brawl_hold_spam:
                     if max(start_t, obj.time) <= min(end_t, obj.end_time if hasattr(obj, 'end_time') else obj.time):
                         return False
                continue

            obj_footprints = []
            obj_start = int(obj.time)
            obj_end = int(obj.end_time)
            
            if obj.is_spike:
                if is_spam or is_brawl_hold_spam:
                    continue
            
            if obj.is_spam or obj.is_brawl_hold or obj.is_brawl_spam:
                if is_spike:
                    continue
                h_lane = 1 if obj.is_brawl_spam else (0 if obj.lane == 0 else 1)
                obj_footprints.append((obj_start, obj_start, h_lane))
                
                body_start = obj_start + 1
                body_end = max(obj_start, obj_end - 1)
                if body_end >= body_start:
                    obj_footprints.append((body_start, body_end, 0))
                    obj_footprints.append((body_start, body_end, 1))
                
                t_lane = 1 if obj.is_brawl_spam else (0 if obj.lane == 0 else 1)
                obj_footprints.append((obj_end, obj_end, t_lane))
            elif obj.is_screamer:
                s_lane = obj.lane
                e_lane = 1 if s_lane == 0 else 0
                obj_footprints.append((obj_start, obj_start, s_lane))
                obj_footprints.append((obj_end, obj_end, e_lane))
            else:
                obj_footprints.append((obj_start, obj_end, obj.lane))
                
            for nf in new_footprints:
                if nf[2] == 2: continue
                for of in obj_footprints:
                    if nf[2] == of[2]:
                        if max(nf[0], of[0]) <= min(nf[1], of[1]):
                            return False
        return True

    def update_dragged_objects(self):
        if not self.dragging_objects or not self.last_mouse_pos or not self.beatmap:
            return

        current_mouse_time = self.x_to_ms(self.last_mouse_pos.x())
        start_mouse_time = self.x_to_ms(self.timeline_click_pos.x()) if self.timeline_click_pos else current_mouse_time
        
        if not hasattr(self, 'drag_start_mouse_time'):
            self.drag_start_mouse_time = start_mouse_time

        center_y = self.height() / 2
        lane_0_y = center_y - LANE_HEIGHT / 2
        lane_1_y = center_y + LANE_HEIGHT / 2
        
        dist_0 = abs(self.last_mouse_pos.y() - lane_0_y)
        dist_1 = abs(self.last_mouse_pos.y() - lane_1_y)
        target_lane = 0 if dist_0 < dist_1 else 1
        
        valid_selected = [o for o in self.selected_objects if o in self.drag_start_time_map]
        if not valid_selected:
            return
        
        reference_obj = valid_selected[0]
        reference_start_lane = self.drag_start_lane_map.get(reference_obj, 0)

        unique_lanes = set()
        for obj in valid_selected:
            l = self.drag_start_lane_map.get(obj)
            if l != -1:
                unique_lanes.add(l)
        
        if len(unique_lanes) > 1:
            lane_change = 0
        else:
            lane_change = target_lane - reference_start_lane if reference_start_lane >= 0 else 0

        time_delta = current_mouse_time - self.drag_start_mouse_time
        
        collision_detected = False
        potential_moves = []

        if self.drag_mode == 'move':
            ms_diff = self.x_to_ms(self.last_mouse_pos.x()) - self.drag_start_mouse_time
            
            max_duration = float('inf')
            if self.beatmap.metadata.ActualAudioLength > 0:
                max_duration = self.beatmap.metadata.ActualAudioLength * 1000

            sel_min_time = min(self.drag_start_time_map[o] for o in self.selected_objects) if self.selected_objects else 0
            sel_max_end = 0
            for o in self.selected_objects:
                st = self.drag_start_time_map[o]
                et = self.drag_original_end_time_map[o] if o in self.drag_original_end_time_map else st
                if et > sel_max_end: sel_max_end = et
            
            
            
            if ms_diff < -sel_min_time: ms_diff = -sel_min_time
            if ms_diff > max_duration - sel_max_end: ms_diff = max_duration - sel_max_end

            selection_lanes = set()
            has_screamer = False
            for o in self.selected_objects:
                selection_lanes.add(o.lane)
                if o.is_screamer: has_screamer = True
            
            is_vertical_allowed = True
            if len(self.selected_objects) > 1:
                if len(selection_lanes) > 1: is_vertical_allowed = False
                if has_screamer: is_vertical_allowed = False

            for obj in self.selected_objects:
                original_time = self.drag_start_time_map[obj]
                new_time_raw = original_time + ms_diff
                new_time = int(self.get_snap_time(new_time_raw))
                if new_time < 0: new_time = 0

                original_lane = self.drag_start_lane_map[obj]
                new_lane = original_lane
                
                if obj.is_event or obj.is_freestyle:
                     new_lane = original_lane
                elif not obj.is_spam:
                    if is_vertical_allowed:
                        center_y = self.height() / 2
                        if self.last_mouse_pos.y() < center_y:
                            new_lane = 0
                        else:
                            new_lane = 1
                
                duration = 0
                new_end_time = new_time
                if obj.type == 128:
                    duration = self.drag_original_end_time_map[obj] - original_time
                    new_end_time = int(new_time + duration)
                
                is_sc = obj.is_screamer
                is_sp = obj.is_spam
                is_bhs = obj.is_brawl_hold or obj.is_brawl_spam
                is_fs = obj.is_freestyle
                is_spk = obj.is_spike
                
                t_lane = None
                if obj.is_brawl_spam: t_lane = 1
                elif obj.is_brawl_hold: t_lane = 0 if new_lane == 0 else 1
                elif is_sp: t_lane = new_lane

                if not self.is_space_free(new_time, new_end_time, new_lane, ignore_obj=self.selected_objects, is_screamer=is_sc, is_spam=is_sp, is_brawl_hold_spam=is_bhs, is_freestyle=is_fs, tail_lane=t_lane, is_spike=is_spk):
                    collision_detected = True
                    break
                
                potential_moves.append((obj, new_time, new_end_time, new_lane))

        elif self.drag_mode == 'resize':
            obj = reference_obj
            
            max_duration = float('inf')
            if self.beatmap.metadata.ActualAudioLength > 0:
                max_duration = self.beatmap.metadata.ActualAudioLength * 1000

            if obj.type == 128:
                new_end_time_raw = self.drag_original_end_time_map[obj] + time_delta
                new_end_time = int(self.get_snap_time(new_end_time_raw))
                
                if new_end_time > max_duration: new_end_time = int(max_duration)
                
                new_lane = self.drag_start_lane_map[obj]
                
                if new_end_time <= obj.time:
                     new_end_time = int(obj.time + (self.drag_original_end_time_map[obj] - self.drag_start_time_map[obj]))
                     if new_end_time <= obj.time: new_end_time = obj.time + 100 

                is_sc = obj.is_screamer
                is_sp = obj.is_spam
                is_bhs = obj.is_brawl_hold or obj.is_brawl_spam
                is_fs = obj.is_freestyle
                
                t_lane = None
                if obj.is_brawl_spam: t_lane = 1
                elif obj.is_brawl_hold: t_lane = 0 if new_lane == 0 else 1
                elif is_sp: t_lane = new_lane

                if new_end_time > obj.time:
                     if not self.is_space_free(obj.time, new_end_time, new_lane, ignore_obj=obj, is_screamer=is_sc, is_spam=is_sp, is_brawl_hold_spam=is_bhs, is_freestyle=is_fs, tail_lane=t_lane):
                        collision_detected = True
                     else:
                        potential_moves.append((obj, obj.time, new_end_time, new_lane))
        
        if not collision_detected and potential_moves:
            if self.drag_mode == 'resize':
                new_snapped_value = potential_moves[0][2] if potential_moves else None
            else:
                new_snapped_value = potential_moves[0][1] if potential_moves else None
            
            should_play_drag = False
            if new_snapped_value is not None:
                if self.drag_last_snapped_time is None:
                    self.drag_last_snapped_time = new_snapped_value
                elif new_snapped_value != self.drag_last_snapped_time:
                    should_play_drag = True
                    self.drag_last_snapped_time = new_snapped_value
            
            new_lane_value = potential_moves[0][3] if potential_moves else None
            if new_lane_value is not None and new_lane_value != -1:
                if self.drag_last_lane is None:
                    self.drag_last_lane = new_lane_value
                elif new_lane_value != self.drag_last_lane:
                    should_play_drag = True
                    self.drag_last_lane = new_lane_value
            
            for obj, t, et, l in potential_moves:
                obj.time = int(t)
                if obj.type == 128:
                    obj.end_time = int(et)
                if l != -1 and not obj.is_spam and not obj.is_freestyle and not obj.is_event: 
                    obj.x = 255 if l == 0 else 256
            self.editor.mark_unsaved()
            
            if should_play_drag:
                self.editor.play_ui_sound_suppressed('UI Drag')

    def mouseMoveEvent(self, e: QMouseEvent):
        if self.dragging_objects:
            if not self.undo_stack or self.undo_stack[-1] != self._get_current_state():
                pass
            
            self.last_mouse_pos = e.pos()
            if not hasattr(self, 'drag_start_mouse_time'):
                self.drag_start_mouse_time = self.x_to_ms(e.pos().x())

            margin = 50
            w = self.width()
            scroll = 0
            if e.pos().x() < margin: scroll = -1
            elif e.pos().x() > w - margin: scroll = 1
            
            if scroll != 0:
                self.edge_scroll_speed = scroll * 50
                if not self.edge_scroll_timer.isActive():
                    self.edge_scroll_timer.start()
            else:
                self.edge_scroll_timer.stop()
            
            self.update_dragged_objects()
            self.update()
        
        elif self.selection_start is not None:
            self.last_mouse_pos = e.pos()
            self.selection_last_mouse_y = e.pos().y()
            start_x = self.ms_to_x(self.selection_start)
            current_x = e.pos().x()
            x1 = min(start_x, current_x)
            y1 = min(self.selection_start_y, e.pos().y())
            x2 = max(start_x, current_x)
            y2 = max(self.selection_start_y, e.pos().y())
            
            self.selection_rect = QRectF(x1, y1, x2-x1, y2-y1)
            
            margin = 50
            w = self.width()
            scroll = 0
            if e.pos().x() < margin: scroll = -1
            elif e.pos().x() > w - margin: scroll = 1
            
            if scroll != 0:
                self.edge_scroll_speed = scroll * 50
                if not self.edge_scroll_timer.isActive():
                    self.edge_scroll_timer.start()
            else:
                self.edge_scroll_timer.stop()
            
            if not (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self.selected_objects.clear()
            
            center_y = self.height() / 2
            lane_0_y = center_y - LANE_HEIGHT / 2
            lane_1_y = center_y + LANE_HEIGHT / 2
            
            for obj in self.beatmap.hit_objects:
                obj_x = self.ms_to_x(obj.time)
                
                if obj.is_event:
                    obj_y = center_y
                else:
                    obj_y = lane_0_y if obj.lane == 0 else lane_1_y
                
                if x1 <= obj_x <= x2 and y1 <= obj_y <= y2:
                    self.selected_objects.add(obj)
                elif obj.is_hold or obj.is_screamer or obj.is_spam:
                    end_x = self.ms_to_x(obj.end_time)
                    if x1 <= end_x <= x2 and y1 <= obj_y <= y2:
                        self.selected_objects.add(obj)
            
            self.update()
    
    def _get_current_state(self):
        if not self.beatmap:
            return None
        return {
            'hit_objects': [
                {
                    'x': obj.x,
                    'y': obj.y,
                    'time': obj.time,
                    'type': obj.type,
                    'hitSound': obj.hitSound,
                    'objectParams': obj.objectParams,
                    'hitSample': obj.hitSample
                }
                for obj in self.beatmap.hit_objects
            ]
        }

    def mouseReleaseEvent(self, e: QMouseEvent):
        self.edge_scroll_timer.stop()
        if hasattr(self, 'drag_start_mouse_time'):
            del self.drag_start_mouse_time
        
        if e.button() == Qt.MouseButton.LeftButton:
            if self.timeline_click_pos and not self.selection_rect and not self.dragging_objects:
                center_y = self.height() / 2
                lane_0_y = center_y - LANE_HEIGHT / 2
                lane_1_y = center_y + LANE_HEIGHT / 2
                in_lane_area = (lane_0_y - 40 < self.timeline_click_pos.y() < lane_1_y + 40)
                
                if not in_lane_area and not self.selected_objects:
                    ms = self.x_to_ms(self.timeline_click_pos.x())
                    snapped_ms = int(self.get_snap_time(ms))
                    
                    song_length_ms = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap and self.beatmap.metadata.ActualAudioLength > 0 else 0
                    
                    if snapped_ms >= 0 and (song_length_ms == 0 or snapped_ms <= song_length_ms):
                        self.target_time = snapped_ms
                        self.current_time = snapped_ms
                        self.editor.sync_audio_to_time()
            
            if self.dragging_objects:
                if self.undo_stack and self.undo_stack[-1] == self._get_current_state():
                    self.undo_stack.pop()
                self.selected_objects.clear()
                if not (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
                     pass 
            
            self.dragging_objects = False
            self.last_mouse_pos = None
            self.selection_start = None
            self.selection_start_y = None
            self.selection_rect = None
            self.selection_last_mouse_y = None
            self.timeline_click_pos = None
            
            self.update()

    def copy_selected(self):
        if not self.selected_objects:
            return
        
        self.clipboard = []
        min_time = min(obj.time for obj in self.selected_objects)
        
        for obj in sorted(self.selected_objects, key=lambda o: o.time):
            relative_time = obj.time - min_time
            duration = 0
            if obj.type == 128:
                duration = obj.end_time - obj.time
                
            self.clipboard.append({
                'relative_time': relative_time,
                'duration': duration,
                'x': obj.x,
                'y': obj.y,
                'type': obj.type,
                'hitSound': obj.hitSound,
                'objectParams': obj.objectParams,
                'hitSample': obj.hitSample
            })
        
        self.selected_objects.clear()
        self.update()

    def paste_clipboard(self):
        if not self.clipboard or not self.beatmap:
            return
        
        paste_time = int(self.current_time)
        
        possible_objects = []
        for item in self.clipboard:
            new_time = paste_time + item['relative_time']
            if new_time >= 0:
                params = item['objectParams']
                if item['type'] == 128:
                    new_end = new_time + item['duration']
                    params = str(int(new_end))

                new_obj_dummy = HitObject(
                    item['x'],
                    item['y'],
                    new_time,
                    item['type'],
                    item['hitSound'],
                    params, 
                    item['hitSample']
                )
                
                check_lane = new_obj_dummy.lane
                end_t = new_obj_dummy.end_time
                is_sc = new_obj_dummy.is_screamer
                is_sp = new_obj_dummy.is_spam
                
                if not self.is_space_free(new_time, end_t, check_lane, ignore_obj=None, is_screamer=is_sc, is_spam=is_sp):
                    return
                
                possible_objects.append(new_obj_dummy)
        
        self.save_undo_state()
        self.selected_objects.clear()
        
        for obj in possible_objects:
            self.beatmap.hit_objects.append(obj)
            self.selected_objects.add(obj)
        
        self.editor.mark_unsaved()
        self.update()

    def wheelEvent(self, e: QWheelEvent):
        modifiers = QApplication.keyboardModifiers()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            delta = e.angleDelta().y()
            if delta < 0: self.target_zoom /= 1.1
            else: self.target_zoom *= 1.1
            self.target_zoom = max(0.1, min(10.0, self.target_zoom))
        else:
            delta = e.angleDelta().y()
            
            song_length_ms = self.beatmap.metadata.ActualAudioLength * 1000 if self.beatmap and self.beatmap.metadata.ActualAudioLength > 0 else 0
            
            if self.beatmap and self.beatmap.metadata.BPM > 0:
                bpm = self.beatmap.metadata.BPM
                beat_len = 60000 / bpm
                snap_len = beat_len / self.grid_snap_div
                offset = self.beatmap.metadata.Offset
                
                default_boxes = self.grid_snap_div // 2
                if default_boxes < 1:
                    default_boxes = 1
                
                zoom_factor = max(0.1, min(10.0, self.zoom))
                boxes_to_scroll = float(default_boxes)
                
                if zoom_factor > 1.0:
                    zoom_steps = 0
                    temp_zoom = zoom_factor
                    while temp_zoom > 1.5:
                        zoom_steps += 1
                        temp_zoom /= 1.5
                    
                    for _ in range(zoom_steps):
                        if boxes_to_scroll > 1:
                            boxes_to_scroll = boxes_to_scroll / 2
                            if boxes_to_scroll != int(boxes_to_scroll):
                                boxes_to_scroll = int(boxes_to_scroll) + 1
                        else:
                            boxes_to_scroll = boxes_to_scroll / 2
                elif zoom_factor < 1.0:
                    zoom_steps = 0
                    temp_zoom = zoom_factor
                    while temp_zoom < 0.5:
                        zoom_steps += 1
                        temp_zoom *= 2
                    
                    for _ in range(zoom_steps):
                        boxes_to_scroll = boxes_to_scroll * 2
                
                if boxes_to_scroll >= 1:
                    scroll_time = boxes_to_scroll * snap_len
                    sub_snap_len = snap_len
                else:
                    sub_divisions = 1
                    temp_boxes = boxes_to_scroll
                    while temp_boxes < 1:
                        sub_divisions *= 2
                        temp_boxes *= 2
                    sub_snap_len = snap_len / sub_divisions
                    scroll_time = sub_snap_len
                
                scroll_aligned_pos = (self.target_time - offset) / scroll_time
                scroll_aligned_snapped = round(scroll_aligned_pos) * scroll_time + offset
                off_grid_distance = abs(self.target_time - scroll_aligned_snapped)
                
                if off_grid_distance > 0.5:
                    if delta > 0:
                        target_snapped = int(scroll_aligned_pos + 1) * scroll_time + offset
                    else:
                        target_snapped = int(scroll_aligned_pos) * scroll_time + offset
                        if target_snapped >= self.target_time:
                            target_snapped = (int(scroll_aligned_pos) - 1) * scroll_time + offset
                else:
                    if delta > 0:
                        target_snapped = scroll_aligned_snapped + scroll_time
                    else:
                        target_snapped = scroll_aligned_snapped - scroll_time
                
                if target_snapped < 0:
                    target_snapped = 0
                elif song_length_ms > 0:
                    max_grid_time = int((song_length_ms - offset) / scroll_time) * scroll_time + offset
                    if target_snapped > max_grid_time:
                        target_snapped = max_grid_time
                
                self.target_time = target_snapped
            else:
                scroll_amount = 200 * (1/self.zoom)
                if delta > 0:
                    self.target_time += scroll_amount
                else:
                    self.target_time = max(0, self.target_time - scroll_amount)
                
                if song_length_ms > 0:
                    self.target_time = min(self.target_time, song_length_ms)
                else:
                    self.target_time = max(0, self.target_time)
            
            if self.editor.is_playing:
                self.current_time = self.target_time
                self.editor.sync_audio_to_time(force_play=True)
            
            if self.dragging_objects:
                self.update_dragged_objects()
            
            self.update_selection_rect()

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key.Key_A and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.beatmap:
                self.selected_objects.clear()
                for obj in self.beatmap.hit_objects:
                    self.selected_objects.add(obj)
                self.update()
            e.accept()
        elif e.key() == Qt.Key.Key_C and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.copy_selected()
            e.accept()
        elif e.key() == Qt.Key.Key_V and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.paste_clipboard()
            e.accept()
        elif e.key() == Qt.Key.Key_Z and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.undo()
            e.accept()
        elif e.key() == Qt.Key.Key_Y and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.redo()
            e.accept()
        elif e.key() == Qt.Key.Key_Delete or e.key() == Qt.Key.Key_Backspace:
            if self.selected_objects and self.beatmap:
                self.save_undo_state()
                for obj in list(self.selected_objects):
                    if obj in self.beatmap.hit_objects:
                        self.beatmap.hit_objects.remove(obj)
                self.selected_objects.clear()
                self.editor.mark_unsaved()
                self.update()
            e.accept()
        else:
            super().keyPressEvent(e)

class AnimatedSplashScreen(QWidget):
    finished = pyqtSignal()
    
    def __init__(self, icon_path, target_x=None, target_y=None):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.pixmap = QPixmap(icon_path)
        if self.pixmap.isNull():
            self.pixmap = QPixmap(256, 256)
            self.pixmap.fill(Qt.GlobalColor.transparent)
        
        self.pixmap = self.pixmap.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.setFixedSize(400, 400)
        
        if target_x is not None and target_y is not None:
            target_screen = None
            for screen in QApplication.screens():
                geom = screen.geometry()
                if geom.contains(target_x, target_y):
                    target_screen = screen
                    break
            
            if target_screen:
                screen_geom = target_screen.geometry()
                self.move(screen_geom.x() + (screen_geom.width() - self.width()) // 2,
                         screen_geom.y() + (screen_geom.height() - self.height()) // 2)
            else:
                screen = QApplication.primaryScreen().geometry()
                self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)
        else:
            screen = QApplication.primaryScreen().geometry()
            self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)
        
        self.start_time = QElapsedTimer()
        self.start_time.start()
        self.duration = 3000
        self.fade_in_duration = 800
        self.fade_duration = 500
        self.animation_complete = False
        
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start()
        
        if not pygame.mixer.get_init():
             try:
                 with OutputSuppressor():
                     pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
                     pygame.init()
             except: pass
        
        base_path = get_base_path()
        sound_path = None
        
        internal_boot = os.path.join(base_path, "sounds", "boot.wav")
        if not os.path.exists(internal_boot):
             internal_boot = os.path.join(base_path, "boot.wav")
        
        game_root = find_unbeatable_root()
        if not game_root:
             try:
                if sys.platform.startswith("win"):
                    app_data = os.getenv('APPDATA')
                    if app_data: p_file = Path(app_data).parent / "LocalLow" / "CBM_Editor" / "path.json"
                    else: p_file = Path.home() / "AppData" / "LocalLow" / "CBM_Editor" / "path.json"
                else:
                    p_file = Path.home() / ".config" / "CBM_Editor" / "path.json"
                
                if p_file.exists():
                     with open(p_file, 'r') as f:
                         data = json.load(f)
                         if data.get("game_path"):
                             game_root = Path(data.get("game_path"))
             except: pass
        
        target_boot_path = None
        ui_volume = 1.0
        if game_root:
             res_dir = game_root / "ChartEditorResources"
             if res_dir.exists():
                 target_boot_path = res_dir / "boot.wav"
                 if not target_boot_path.exists() and os.path.exists(internal_boot):
                      try: shutil.copy2(internal_boot, target_boot_path)
                      except: pass
                 
                 config_path = res_dir / "editor_config.json"
                 if config_path.exists():
                     try:
                         with open(config_path, 'r') as f:
                             config_data = json.load(f)
                             ui_volume = config_data.get("settings", {}).get("ui_volume", 1.0)
                     except: pass
        
        if target_boot_path and target_boot_path.exists():
             sound_path = str(target_boot_path)
        elif os.path.exists(internal_boot):
             sound_path = internal_boot

        if sound_path:
            try:
                with OutputSuppressor():
                    s = pygame.mixer.Sound(sound_path)
                    s.set_volume(ui_volume)
                    s.play()
            except:
                pass
                
    def update_animation(self):
        elapsed = self.start_time.elapsed()
        if elapsed >= self.duration:
            if not self.animation_complete:
                self.animation_complete = True
                self.timer.stop()
                self.hide()
                QTimer.singleShot(50, self.emit_finished)
            return
        
        if elapsed < self.fade_in_duration:
            opacity = elapsed / self.fade_in_duration
            self.setWindowOpacity(min(1.0, opacity))
        elif elapsed > self.duration - self.fade_duration:
             opacity = 1.0 - ((elapsed - (self.duration - self.fade_duration)) / self.fade_duration)
             self.setWindowOpacity(max(0.0, opacity))
        else:
             self.setWindowOpacity(1.0)
             
        self.update()
    
    def emit_finished(self):
        self.finished.emit()
        self.close()
        
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        elapsed = self.start_time.elapsed()
        progress = min(1.0, elapsed / self.duration)
        scale = 1.0 + (0.3 * progress)
        
        w = self.pixmap.width() * scale
        h = self.pixmap.height() * scale
        
        x = (self.width() - w) / 2
        y = (self.height() - h) / 2
        
        target_rect = QRectF(x, y, w, h)
        p.drawPixmap(target_rect, self.pixmap, QRectF(self.pixmap.rect()))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.last_slider_val = {}
        self.last_hotkey_time = {}
        self.setWindowTitle(f"CBM Editor {VERSION_NUMBER}")
        self.setMinimumHeight(820)
        self.resize(1400, 820)
        
        self.resize(1400, 820)
        
        with OutputSuppressor():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.init()
            pygame.mixer.set_num_channels(32)
        
        self.sounds = {}
        self.metronome_sound = None
        self.music_volume = 1.0
        self.fx_volume = 1.0
        self.playback_speed = 1.0
        self.current_colors = DEFAULT_COLORS.copy()
        self.persistent_files = False
        
        self.project_folder: Optional[Path] = None
        self.beatmaps: Dict[str, BeatmapData] = {}
        self.current_chart: Optional[BeatmapData] = None
        self.game_custom_maps_path: Optional[Path] = None
        self.game_root_path: Optional[Path] = None
        
        self.is_playing = False
        self.play_timer = QTimer()
        refresh_rate = QApplication.primaryScreen().refreshRate()
        if refresh_rate < 30: refresh_rate = 60
        self.play_timer.setInterval(int(1000 / refresh_rate))
        self.play_timer.timeout.connect(self.tick)
        
        self.audio_start_ms = 0.0
        self.system_start_tick = 0
        self.last_played_notes = set()
        
        self.has_unsaved_changes = False
        self.recent_projects = []
        self.recent_projects = []
        self.title_edit_authorized = False
        self.title_warning_active = False
        
        self.metronome_active = False
        self.last_metronome_beat = -1
        
        self.temp_audio_files = {} 
        self.audio_generator = None
        
        self.setup_ui()
        self.ensure_game_path() 
        self.update_ui_state()
        
        self.setStyleSheet("""
            QMainWindow { background-color: #222; color: #EEE; }
            QWidget { font-family: 'Segoe UI', sans-serif; font-size: 14px; color: #EEE; }
            QGroupBox { border: 1px solid #555; margin-top: 1.2em; border-radius: 4px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { 
                background-color: #333; border: 1px solid #555; padding: 4px; border-radius: 4px; 
                color: #EEE;
            }
            QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
                background-color: #222; color: #666;
            }
            QComboBox::drop-down {
                border: none;
                background-color: #444;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #EEE;
                width: 0;
                height: 0;
            }
            QComboBox QAbstractItemView {
                background-color: #333;
                color: #EEE;
                selection-background-color: #555;
                border: 1px solid #555;
            }
            QPushButton { 
                background-color: #444; border: 1px solid #555; padding: 6px; border-radius: 4px; 
            }
            QPushButton:hover { background-color: #555; }
            QPushButton:disabled { background-color: #2a2a2a; color: #555; }
            QPushButton:checked { background-color: #6688AA; border: 1px solid #88AAFF; }
            QSlider::groove:horizontal {
                border: 1px solid #555;
                height: 8px;
                background: #333;
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #6688AA;
                border: 1px solid #88AAFF;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QDialog {
                background-color: #222;
                color: #EEE;
            }
            QScrollBar:horizontal {
                border: 1px solid #555;
                background: #333;
                height: 15px;
                margin: 0px 20px 0 20px;
                border-radius: 7px;
            }
            QScrollBar::handle:horizontal {
                background: #6688AA;
                min-width: 20px;
                border-radius: 7px;
            }
            QScrollBar::add-line:horizontal {
                border: 1px solid #555;
                background: #444;
                width: 20px;
                subcontrol-position: right;
                subcontrol-origin: margin;
                border-top-right-radius: 7px;
                border-bottom-right-radius: 7px;
            }
            QScrollBar::sub-line:horizontal {
                border: 1px solid #555;
                background: #444;
                width: 20px;
                subcontrol-position: left;
                subcontrol-origin: margin;
                border-top-left-radius: 7px;
                border-bottom-left-radius: 7px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
            QScrollBar:vertical {
                border: 1px solid #555;
                background: #333;
                width: 15px;
                margin: 20px 0 20px 0;
                border-radius: 7px;
            }
            QScrollBar::handle:vertical {
                background: #6688AA;
                min-height: 20px;
                border-radius: 7px;
            }
            QScrollBar::add-line:vertical {
                border: 1px solid #555;
                background: #444;
                height: 20px;
                subcontrol-position: bottom;
                subcontrol-origin: margin;
                border-bottom-left-radius: 7px;
                border-bottom-right-radius: 7px;
            }
            QScrollBar::sub-line:vertical {
                border: 1px solid #555;
                background: #444;
                height: 20px;
                subcontrol-position: top;
                subcontrol-origin: margin;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            QProgressBar {
                border: 1px solid #555;
                border-radius: 4px;
                text-align: center;
                color: #EEE;
                background-color: #333;
            }
            QProgressBar::chunk {
                background-color: #385;
            }
        """)

    def resizeEvent(self, event):
        self.save_game_config()
        super().resizeEvent(event)
    
    def closeEvent(self, event):
        has_unsaved = False
        for bm in self.beatmaps.values():
            if bm.created and bm.unsaved:
                has_unsaved = True
                break
        
        if has_unsaved:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Unsaved Changes")
            msg.setText("You have unsaved changes.")
            msg.setInformativeText("Do you want to save before closing?")
            
            btn_cancel = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            btn_save = msg.addButton("Save All && Close", QMessageBox.ButtonRole.AcceptRole)
            btn_discard = msg.addButton("Close Without Saving", QMessageBox.ButtonRole.DestructiveRole)
            
            msg.exec()
            clicked = msg.clickedButton()
            
            if clicked == btn_cancel:
                event.ignore()
                return
            elif clicked == btn_save:
                for diff_key, bm in self.beatmaps.items():
                    if bm.created and bm.unsaved:
                        old_chart = self.current_chart
                        self.current_chart = bm
                        self.save_current()
                        self.current_chart = old_chart
        
        self.save_game_config()
        if self.game_root_path:
            temp_path = self.game_root_path / "ChartEditorResources" / "temp"
            if temp_path.exists():
                try:
                    shutil.rmtree(temp_path)
                except:
                    pass
        super().closeEvent(event)

    def get_appdata_dir(self):
        if sys.platform.startswith("win"):
            app_data = os.getenv('APPDATA')
            if app_data:
                path = Path(app_data).parent / "LocalLow" / "CBM_Editor"
            else:
                path = Path.home() / "AppData" / "LocalLow" / "CBM_Editor"
        else:
            path = Path.home() / ".config" / "CBM_Editor"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def load_game_config(self):
        if not self.game_root_path: return
        path = self.game_root_path / "ChartEditorResources" / "editor_config.json"

        default_config = {
            "window": {"width": 1400, "height": 820, "x": 100, "y": 100},
            "recent_projects": [],
            "settings": {"music_volume": 1.0, "fx_volume": 1.0, "ui_volume": 1.0, "persistent_files": True},
            "colors": DEFAULT_COLORS
        }

        data = default_config.copy()
        if path.exists():
            try:
                with open(path, 'r') as f:
                    loaded_data = json.load(f)
                    for k, v in loaded_data.items():
                        if k == "colors":
                            merged_colors = DEFAULT_COLORS.copy()
                            if isinstance(v, dict):
                                merged_colors.update(v)
                            data[k] = merged_colors
                        else:
                            data[k] = v
            except:
                pass
        
        w_data = data.get("window", {})
        self.resize(w_data.get("width", 1400), w_data.get("height", 820))
        self.move(w_data.get("x", 100), w_data.get("y", 100))
        
        self.recent_projects = data.get("recent_projects", [])
        
        s_data = data.get("settings", {})
        self.music_volume = s_data.get("music_volume", 1.0)
        self.fx_volume = s_data.get("fx_volume", 1.0)
        self.ui_volume = s_data.get("ui_volume", 1.0)
        self.persistent_files = s_data.get("persistent_files", True)
        
        self.current_colors = data.get("colors", DEFAULT_COLORS.copy())
        if hasattr(self, 'timeline'):
            self.timeline.set_colors(self.current_colors)

    def save_game_config(self):
        if not self.game_root_path: return
        res_dir = self.game_root_path / "ChartEditorResources"
        if not res_dir.exists():
            return 
            
        path = res_dir / "editor_config.json"

        data = {
            "window": {"width": self.width(), "height": self.height(), "x": self.x(), "y": self.y()},
            "recent_projects": self.recent_projects,
            "settings": {
                "music_volume": self.music_volume, 
                "fx_volume": self.fx_volume,
                "ui_volume": self.ui_volume,
                "persistent_files": self.persistent_files
            },
            "colors": self.current_colors
        }
        
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
        except:
            pass

    def add_to_recent(self, path):
        str_path = str(path)
        if str_path in self.recent_projects:
            self.recent_projects.remove(str_path)
        self.recent_projects.insert(0, str_path)
        if len(self.recent_projects) > 10:
            self.recent_projects = self.recent_projects[:10]
        self.save_game_config()

    def open_recent_popup(self):
        if not self.recent_projects:
            QMessageBox.information(self, "Recent Projects", "No recent projects found.")
            return

        dialog = RecentProjectsDialog(self, self.recent_projects)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            path = Path(dialog.selected_project)
            if path.exists():
                self.load_project_from_path(path)
            else:
                QMessageBox.warning(self, "Error", "Project path no longer exists.")
                self.recent_projects.remove(dialog.selected_project)
                self.save_game_config()
    
    def open_settings(self):
        dialog = SettingsDialog(self, self.music_volume, self.fx_volume, self.ui_volume, self.current_colors, self.persistent_files, self.game_root_path)
        dialog.setStyleSheet(self.styleSheet())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.music_volume, self.fx_volume, self.ui_volume = dialog.get_volumes()
            self.current_colors = dialog.get_colors()
            self.persistent_files = dialog.get_persistent()
            
            pygame.mixer.music.set_volume(self.music_volume)
            for name, sound in self.sounds.items():
                if name.startswith("UI"):
                    sound.set_volume(self.ui_volume)
                else:
                    sound.set_volume(self.fx_volume)
            
            self.timeline.set_colors(self.current_colors)
            self.save_game_config()
            self.load_sounds()

            if self.current_chart and self.current_chart.metadata.AudioFilename:
                self.prepare_audio_versions(self.current_chart.metadata.AudioFilename)

    def update_window_title(self):
        title = f"CBM Editor {VERSION_NUMBER}"
        if self.project_folder:
            title += f" [{self.project_folder.name}]"
        if self.current_chart and self.current_chart.unsaved:
            title += " *"
        self.setWindowTitle(title)

    def mark_unsaved(self):
        if self.current_chart:
            self.current_chart.unsaved = True
            self.update_window_title()

    def mark_saved(self):
        if self.current_chart:
            self.current_chart.unsaved = False
            self.update_window_title()

    def update_ui_state(self):
        has_chart = self.current_chart is not None
        
        self.combo_diff.setEnabled(has_chart)
        self.btn_play.setEnabled(has_chart)
        self.btn_tool_note.setEnabled(has_chart)
        self.btn_tool_brawl.setEnabled(has_chart)
        self.btn_tool_event.setEnabled(has_chart)
        
        self.btn_note_normal.setEnabled(has_chart)
        self.btn_note_spike.setEnabled(has_chart)
        self.btn_note_hold.setEnabled(has_chart)
        self.btn_note_screamer.setEnabled(has_chart)
        self.btn_note_spam.setEnabled(has_chart)
        self.btn_note_freestyle.setEnabled(has_chart)
        self.combo_note_style.setEnabled(has_chart)
        
        self.btn_brawl_hit.setEnabled(has_chart)
        self.btn_brawl_final.setEnabled(has_chart)
        self.btn_brawl_hold.setEnabled(has_chart)
        self.btn_brawl_spam.setEnabled(has_chart)
        self.combo_brawl_cop.setEnabled(has_chart)
        
        self.btn_event_flip.setEnabled(has_chart)
        self.btn_event_toggle.setEnabled(has_chart)
        self.btn_event_instant.setEnabled(has_chart)
        self.spin_grid.setEnabled(has_chart)
        self.btn_save.setEnabled(has_chart)
        self.btn_delete.setEnabled(has_chart and self.current_chart.created)
        self.btn_settings.setEnabled(True)
        self.combo_speed.setEnabled(has_chart)
        self.btn_bpm_match.setEnabled(has_chart)
        self.chk_metronome.setEnabled(has_chart)
        
        for name, widget in self.meta_widgets.items():
            if name == "AudioFilename":
                widget.setEnabled(has_chart)
            else:
                widget.setEnabled(has_chart)
        self.cover_label.setEnabled(has_chart)
        self.txt_star_name.setEnabled(has_chart)
        
        for i in range(self.combo_diff.count()):
            diff_name = self.combo_diff.itemText(i)
            if diff_name in self.beatmaps and self.beatmaps[diff_name].created:
                self.combo_diff.setItemData(i, QColor("#EEE"), Qt.ItemDataRole.ForegroundRole)
            else:
                self.combo_diff.setItemData(i, QColor("#777"), Qt.ItemDataRole.ForegroundRole)

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setFixedWidth(350)
        
        gb_proj = QGroupBox("Project")
        l_proj = QVBoxLayout()
        btn_open = QPushButton("Open / Create Project")
        btn_open.clicked.connect(self.open_project)
        btn_open.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        l_proj.addWidget(btn_open)
        
        btn_recent = QPushButton("Open Recent Projects")
        btn_recent.clicked.connect(self.open_recent_popup)
        btn_recent.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        l_proj.addWidget(btn_recent)

        self.lbl_path = QLabel("No Folder Selected")
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet("color: #AAA; font-size: 11px;")
        l_proj.addWidget(self.lbl_path)
        self.combo_diff = QComboBox()
        self.combo_diff.addItems(DIFFICULTIES)
        self.combo_diff.currentTextChanged.connect(self.change_difficulty)
        self.combo_diff.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        l_proj.addWidget(QLabel("Select Difficulty:"))
        l_proj.addWidget(self.combo_diff)
        gb_proj.setLayout(l_proj)
        left_layout.addWidget(gb_proj)
        
        gb_meta = QGroupBox("Metadata")
        self.form_meta = QFormLayout()
        self.meta_widgets = {}
        
        fields = [
            ("Title", "text"), ("Artist", "text"), ("Charted By", "text"),
            ("BPM", "bpm_row"), ("Level", "int"),
            ("FlavorText", "text"), ("Attributes", "text")
        ]
        
        for name, ftype in fields:
            if ftype == "text":
                w = QLineEdit()
                w.textChanged.connect(self.update_metadata_from_ui)
                w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
                w.returnPressed.connect(lambda: self.focusNextChild())
                self.meta_widgets[name] = w
                self.form_meta.addRow(name, w)
            elif ftype == "int":
                w = CleanSpinBox()
                w.setRange(1, 100)
                w.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
                w.valueChanged.connect(self.update_metadata_from_ui)
                w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
                self.meta_widgets[name] = w
                self.form_meta.addRow(name, w)
            elif ftype == "bpm_row":
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                
                w = CleanDoubleSpinBox()
                w.setRange(1, 1000)
                w.setSingleStep(1)
                w.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
                w.valueChanged.connect(self.update_metadata_from_ui)
                w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
                w.setFixedWidth(80)
                
                self.btn_bpm_match = QPushButton("Match")
                self.btn_bpm_match.setFixedWidth(50)
                self.btn_bpm_match.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                self.btn_bpm_match.clicked.connect(self.open_bpm_matcher)
                
                self.chk_metronome = QCheckBox("Metro")
                self.chk_metronome.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                self.chk_metronome.stateChanged.connect(self.toggle_metronome)
                
                row_layout.addWidget(w)
                row_layout.addWidget(self.btn_bpm_match)
                row_layout.addWidget(self.chk_metronome)
                
                self.meta_widgets[name] = w
                self.form_meta.addRow(name, row_widget)

        self.audio_label = FileDropLabel("Drag song here")
        self.audio_label.fileDropped.connect(self.handle_audio_drop)
        self.meta_widgets["AudioFilename"] = self.audio_label
        self.form_meta.addRow("Audio", self.audio_label) 

        self.cover_label = FileDropLabel("Drag cover here")
        self.cover_label.fileDropped.connect(self.handle_cover_drop)
        self.form_meta.addRow("Cover", self.cover_label)
            
        self.txt_star_name = QLineEdit()
        self.txt_star_name.setPlaceholderText("Enter Custom Difficulty Name")
        self.txt_star_name.setStyleSheet("border: 1px solid #FFD700; background-color: #333; color: #EEE;")
        self.txt_star_name.textChanged.connect(self.update_metadata_from_ui)
        self.txt_star_name.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.txt_star_name.returnPressed.connect(lambda: self.focusNextChild())
        self.form_meta.addRow("Star Name", self.txt_star_name)
        
        gb_meta.setLayout(self.form_meta)
        left_layout.addWidget(gb_meta)
        
        self.btn_save = QPushButton("Save Current Difficulty")
        self.btn_save.clicked.connect(self.save_current)
        self.btn_save.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_save.setStyleSheet("background-color: #385; font-weight: bold;")
        left_layout.addWidget(self.btn_save)
        
        self.btn_delete = QPushButton("Delete Current Difficulty")
        self.btn_delete.clicked.connect(self.delete_current_difficulty)
        self.btn_delete.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_delete.setStyleSheet("background-color: #833; font-weight: bold;")
        left_layout.addWidget(self.btn_delete)
        
        self.btn_delete.setStyleSheet("background-color: #833; font-weight: bold;")
        left_layout.addWidget(self.btn_delete)
        
        QApplication.instance().installEventFilter(self)
        
        self.btn_settings = QPushButton("Settings")
        self.btn_settings.clicked.connect(self.open_settings)
        self.btn_settings.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        left_layout.addWidget(self.btn_settings)
        
        left_layout.addStretch()
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        toolbar = QHBoxLayout()
        self.btn_play = QPushButton("Play / Pause (Space)")
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        toolbar.addWidget(self.btn_play)
        toolbar.addSpacing(20)
        
        tool_group_widget = QWidget()
        tool_group_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tool_group_layout = QVBoxLayout(tool_group_widget)
        tool_group_layout.setContentsMargins(0, 0, 0, 0)
        tool_group_layout.setSpacing(0)
        
        tool_type_layout = QHBoxLayout()
        tool_type_layout.setSpacing(5)
        tool_type_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_tool_note = QPushButton("Note")
        self.btn_tool_note.setCheckable(True)
        self.btn_tool_note.setChecked(True)
        self.btn_tool_note.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tool_note.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_tool_note.clicked.connect(lambda: self.change_tool_type("note"))
        
        self.btn_tool_brawl = QPushButton("Brawl")
        self.btn_tool_brawl.setCheckable(True)
        self.btn_tool_brawl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tool_brawl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_tool_brawl.clicked.connect(lambda: self.change_tool_type("brawl"))
        
        self.btn_tool_event = QPushButton("Event")
        self.btn_tool_event.setCheckable(True)
        self.btn_tool_event.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tool_event.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_tool_event.clicked.connect(lambda: self.change_tool_type("event"))
        
        tool_type_layout.addWidget(self.btn_tool_note)
        tool_type_layout.addWidget(self.btn_tool_brawl)
        tool_type_layout.addWidget(self.btn_tool_event)
        tool_group_layout.addLayout(tool_type_layout)
        
        self.note_type_container = QWidget()
        self.note_type_container.setFixedHeight(35)
        note_type_layout = QHBoxLayout(self.note_type_container)
        note_type_layout.setContentsMargins(0, 0, 0, 0)
        note_type_layout.setSpacing(5)
        
        self.btn_note_normal = QPushButton("Normal")
        self.btn_note_normal.setCheckable(True)
        self.btn_note_normal.setChecked(True)
        self.btn_note_normal.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_note_normal.clicked.connect(lambda: self.change_note_type("normal"))
        
        self.btn_note_spike = QPushButton("Spike")
        self.btn_note_spike.setCheckable(True)
        self.btn_note_spike.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_note_spike.clicked.connect(lambda: self.change_note_type("spike"))
        
        self.btn_note_hold = QPushButton("Hold")
        self.btn_note_hold.setCheckable(True)
        self.btn_note_hold.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_note_hold.clicked.connect(lambda: self.change_note_type("hold"))
        
        self.btn_note_screamer = QPushButton("Double")
        self.btn_note_screamer.setCheckable(True)
        self.btn_note_screamer.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_note_screamer.clicked.connect(lambda: self.change_note_type("screamer"))
        
        self.btn_note_spam = QPushButton("Spam")
        self.btn_note_spam.setCheckable(True)
        self.btn_note_spam.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_note_spam.clicked.connect(lambda: self.change_note_type("spam"))

        self.btn_note_freestyle = QPushButton("Freestyle")
        self.btn_note_freestyle.setCheckable(True)
        self.btn_note_freestyle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_note_freestyle.clicked.connect(lambda: self.change_note_type("freestyle"))
        
        self.combo_note_style = QComboBox()
        self.combo_note_style.addItems(["Normal", "Hide", "Fly In"])
        self.combo_note_style.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        note_button_group = QButtonGroup(self.note_type_container)
        note_button_group.addButton(self.btn_note_normal)
        note_button_group.addButton(self.btn_note_spike)
        note_button_group.addButton(self.btn_note_hold)
        note_button_group.addButton(self.btn_note_screamer)
        note_button_group.addButton(self.btn_note_spam)
        note_button_group.addButton(self.btn_note_freestyle)
        note_button_group.setExclusive(True)
        
        note_type_layout.addWidget(self.btn_note_normal)
        note_type_layout.addWidget(self.btn_note_spike)
        note_type_layout.addWidget(self.btn_note_hold)
        note_type_layout.addWidget(self.btn_note_screamer)
        note_type_layout.addWidget(self.btn_note_spam)
        note_type_layout.addWidget(self.btn_note_freestyle)
        note_type_layout.addWidget(self.combo_note_style)
        
        tool_group_layout.addWidget(self.note_type_container)
        
        self.brawl_type_container = QWidget()
        self.brawl_type_container.setFixedHeight(35)
        brawl_type_layout = QHBoxLayout(self.brawl_type_container)
        brawl_type_layout.setContentsMargins(0, 0, 0, 0)
        brawl_type_layout.setSpacing(5)
        
        self.btn_brawl_hit = QPushButton("Cop Hit")
        self.btn_brawl_hit.setCheckable(True)
        self.btn_brawl_hit.setChecked(True)
        self.btn_brawl_hit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_brawl_hit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_brawl_hit.clicked.connect(lambda: self.change_brawl_type("hit"))
        
        self.btn_brawl_final = QPushButton("Cop Knockout")
        self.btn_brawl_final.setCheckable(True)
        self.btn_brawl_final.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_brawl_final.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_brawl_final.clicked.connect(lambda: self.change_brawl_type("final"))

        self.btn_brawl_hold = QPushButton("Cop Hold")
        self.btn_brawl_hold.setCheckable(True)
        self.btn_brawl_hold.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_brawl_hold.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_brawl_hold.clicked.connect(lambda: self.change_brawl_type("hold"))

        self.btn_brawl_hold_ko = QPushButton("Cop Hold Knockout")
        self.btn_brawl_hold_ko.setCheckable(True)
        self.btn_brawl_hold_ko.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_brawl_hold_ko.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_brawl_hold_ko.clicked.connect(lambda: self.change_brawl_type("hold_knockout"))

        self.btn_brawl_spam = QPushButton("Cop Spam")
        self.btn_brawl_spam.setCheckable(True)
        self.btn_brawl_spam.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_brawl_spam.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_brawl_spam.clicked.connect(lambda: self.change_brawl_type("spam"))

        self.btn_brawl_spam_ko = QPushButton("Cop Spam Knockout")
        self.btn_brawl_spam_ko.setCheckable(True)
        self.btn_brawl_spam_ko.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_brawl_spam_ko.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_brawl_spam_ko.clicked.connect(lambda: self.change_brawl_type("spam_knockout"))

        self.combo_brawl_cop = QComboBox()
        self.combo_brawl_cop.addItems(["Cop 1", "Cop 2", "Cop 3", "Cop 4"])
        self.combo_brawl_cop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_brawl_cop.currentIndexChanged.connect(self.change_brawl_cop)
        self.brawl_cop_index = 1
        
        brawl_button_group = QButtonGroup(self.brawl_type_container)
        brawl_button_group.addButton(self.btn_brawl_hit)
        brawl_button_group.addButton(self.btn_brawl_final)
        brawl_button_group.addButton(self.btn_brawl_hold)
        brawl_button_group.addButton(self.btn_brawl_hold_ko)
        brawl_button_group.addButton(self.btn_brawl_spam)
        brawl_button_group.addButton(self.btn_brawl_spam_ko)
        brawl_button_group.setExclusive(True)
        
        brawl_type_layout.addWidget(self.btn_brawl_hit)
        brawl_type_layout.addWidget(self.btn_brawl_final)
        brawl_type_layout.addWidget(self.btn_brawl_hold)
        brawl_type_layout.addWidget(self.btn_brawl_hold_ko)
        brawl_type_layout.addWidget(self.btn_brawl_spam)
        brawl_type_layout.addWidget(self.btn_brawl_spam_ko)
        brawl_type_layout.addWidget(self.combo_brawl_cop)
        
        tool_group_layout.addWidget(self.brawl_type_container)
        self.brawl_type_container.setVisible(False)

        self.event_type_container = QWidget()
        self.event_type_container.setFixedHeight(35)
        event_type_layout = QHBoxLayout(self.event_type_container)
        event_type_layout.setContentsMargins(0, 0, 0, 0)
        event_type_layout.setSpacing(5)
        
        self.btn_event_flip = QPushButton("Flip")
        self.btn_event_flip.setCheckable(True)
        self.btn_event_flip.setChecked(True)
        self.btn_event_flip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_event_flip.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_event_flip.clicked.connect(lambda: self.change_event_type("flip"))
        
        self.btn_event_toggle = QPushButton("ToggleCenter")
        self.btn_event_toggle.setCheckable(True)
        self.btn_event_toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_event_toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_event_toggle.clicked.connect(lambda: self.change_event_type("toggle_center"))

        self.btn_event_instant = QPushButton("InstantFlip")
        self.btn_event_instant.setCheckable(True)
        self.btn_event_instant.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_event_instant.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_event_instant.clicked.connect(lambda: self.change_event_type("instant_flip"))

        event_button_group = QButtonGroup(self.event_type_container)
        event_button_group.addButton(self.btn_event_flip)
        event_button_group.addButton(self.btn_event_toggle)
        event_button_group.addButton(self.btn_event_instant)
        event_button_group.setExclusive(True)
        
        event_type_layout.addWidget(self.btn_event_flip)
        event_type_layout.addWidget(self.btn_event_toggle)
        event_type_layout.addWidget(self.btn_event_instant)
        tool_group_layout.addWidget(self.event_type_container)
        self.event_type_container.setVisible(False)
        
        toolbar.addWidget(tool_group_widget, 1) 
        toolbar.addStretch() 
        
        toolbar.addWidget(QLabel("Speed:"))
        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["0.25x", "0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
        self.combo_speed.setCurrentText("1.0x")
        self.combo_speed.currentTextChanged.connect(self.change_speed)
        self.combo_speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_speed.setFixedWidth(70)
        toolbar.addWidget(self.combo_speed)

        toolbar.addWidget(QLabel("Grid:"))
        self.spin_grid = CleanSpinBox()
        self.spin_grid.setRange(1, 64)
        self.spin_grid.setValue(4)
        self.spin_grid.setFixedWidth(60)
        self.spin_grid.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_grid.valueChanged.connect(self.change_grid)
        self.spin_grid.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        toolbar.addWidget(self.spin_grid)
        
        right_layout.addLayout(toolbar)
        
        self.timeline_scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self.timeline_scrollbar.setEnabled(False)
        self.timeline_scrollbar.valueChanged.connect(self.on_scrollbar_changed)
        right_layout.addWidget(self.timeline_scrollbar)
        
        self.timeline = TimelineWidget(self)
        self.timeline.set_scrollbar(self.timeline_scrollbar)
        right_layout.addWidget(self.timeline)
        
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
        self.update_star_visibility()
        
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if isinstance(obj, QPushButton):
                if obj is self.btn_play or obj.property("is_custom_sound_btn"):
                    pass 
                else:
                    with OutputSuppressor():
                        self.play_ui_sound('UI Click')
            elif isinstance(obj, QComboBox):
                 was_open = obj.view().isVisible() if obj.view() else False
                 if not was_open:
                      with OutputSuppressor():
                          self.play_ui_sound('UI Click')
            elif isinstance(obj, QSlider):
                  self.last_slider_val[id(obj)] = obj.value()
                     
        elif event.type() == QEvent.Type.Enter:
             if isinstance(obj, QComboBox):
                  v = obj.view()
                  if v and not v.property("hover_connected"):
                       v.setProperty("hover_connected", True)
                       v.setMouseTracking(True)
                       v.entered.connect(lambda: self.play_ui_sound_suppressed('UI Scroll'))

        elif event.type() == QEvent.Type.MouseButtonRelease:
            if isinstance(obj, QCheckBox) and obj.isEnabled():
                if obj.isChecked():
                     with OutputSuppressor():
                         self.play_ui_sound('UI Tick On')
                else:
                     with OutputSuppressor():
                         self.play_ui_sound('UI Tick Off')
            elif isinstance(obj, QSlider):
                  self.last_slider_val.pop(id(obj), None)
            elif isinstance(obj, QComboBox):
                 is_open = obj.view().isVisible() if obj.view() else False
                 if not is_open:
                      with OutputSuppressor():
                          self.play_ui_sound('UI Click')
                     
        elif event.type() == QEvent.Type.FocusIn:
            if isinstance(obj, QLineEdit) or isinstance(obj, QSpinBox) or isinstance(obj, QDoubleSpinBox):
                 with OutputSuppressor():
                     self.play_ui_sound('UI Text')
                 
        elif event.type() == QEvent.Type.Wheel:
            if isinstance(obj, (QComboBox, QSpinBox, QDoubleSpinBox, CleanSpinBox, CleanDoubleSpinBox)):
                 with OutputSuppressor():
                     self.play_ui_sound('UI Scroll')
        
        elif event.type() == QEvent.Type.MouseMove:
             if isinstance(obj, QSlider) and obj.isSliderDown():
                  last = self.last_slider_val.get(id(obj), obj.value())
                  curr = obj.value()
                  if abs(curr - last) >= 5:
                       with OutputSuppressor():
                           self.play_ui_sound('UI Scroll')
                       self.last_slider_val[id(obj)] = curr
        
        elif event.type() == QEvent.Type.KeyPress:
             if isinstance(obj, QLineEdit):
                  ke = event
                  if ke.key() == Qt.Key.Key_Return or ke.key() == Qt.Key.Key_Enter:
                       with OutputSuppressor():
                           self.play_ui_sound('UI Tick On')
                 
        return super().eventFilter(obj, event)

    def play_ui_sound_suppressed(self, name):
         with OutputSuppressor():
             self.play_ui_sound(name)

    def play_ui_sound(self, name):
         key = SOUND_FILES_MAP.get(name)
         if key and key in self.sounds:
             try:
                 with OutputSuppressor():
                    self.sounds[key].set_volume(self.ui_volume)
                    self.sounds[key].play()
             except: pass

    def ensure_game_path(self):
        found_path = None
        
        if sys.platform.startswith("win"):
            found_path = find_unbeatable_root()
            
            if not found_path:
                try:
                    p_file = self.get_appdata_dir() / "path.json"
                    if p_file.exists():
                        with open(p_file, 'r') as f:
                            data = json.load(f)
                            saved = data.get("game_path")
                            if saved:
                                p = Path(saved)
                                if p.exists():
                                    found_path = p
                except:
                    pass
        
        if not found_path:
            while True:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setText("UNBEATABLE Path not found.")
                msg.setInformativeText("Please select the UNBEATABLE installation folder.")
                msg.setWindowTitle("Game Path Not Found")
                msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                ret = msg.exec()
                
                if ret == QMessageBox.StandardButton.Ok:
                    folder = QFileDialog.getExistingDirectory(self, "Select UNBEATABLE Folder")
                    if folder:
                        p = Path(folder)
                        if p.exists():
                            found_path = p
                            break
                else:
                    sys.exit()

        self.game_root_path = found_path
        
        try:
            p_file = self.get_appdata_dir() / "path.json"
            with open(p_file, 'w') as f:
                json.dump({"game_path": str(self.game_root_path)}, f)
        except:
            pass
            
        if self.game_root_path:
            self.lbl_path.setText(f"Game detected at: {self.game_root_path}")
            self.setup_custom_maps_path()
            self.load_game_config() 
            self.load_sounds()
            
            base_sounds = get_base_path()
            if not base_sounds.endswith("sounds"):
                base_sounds = os.path.join(base_sounds, "sounds")
            
            i_src = os.path.join(base_sounds, "icon.png")
            i_dst = self.game_root_path / "ChartEditorResources" / "icon.png"
            
            if not i_dst.exists() and os.path.exists(i_src):
                try:
                    shutil.copy2(i_src, i_dst)
                except:
                    pass

            icon_path = self.game_root_path / "ChartEditorResources" / "icon.png"
            if icon_path.exists():
                app_icon = QIcon(str(icon_path))
                self.setWindowIcon(app_icon)
                QApplication.setWindowIcon(app_icon)

            log_dir = self.game_root_path / "ChartEditorResources"
            log_dir.mkdir(parents=True, exist_ok=True)
            possible_log = log_dir / "log.txt"
            if possible_log.exists():
                try:
                    os.remove(possible_log)
                except:
                    pass

        else:
            self.lbl_path.setText("Game path not set")

    def setup_custom_maps_path(self):
        if self.game_root_path:
            self.game_custom_maps_path = self.game_root_path / "USER_PACKAGES"
            if not self.game_custom_maps_path.exists():
                try:
                    self.game_custom_maps_path.mkdir(parents=True, exist_ok=True)
                except:
                    pass
            
            res_dir = self.game_root_path / "ChartEditorResources"
            if not res_dir.exists():
                try:
                    res_dir.mkdir(parents=True, exist_ok=True)
                except:
                    pass

    def load_sounds(self):
        if not self.game_root_path:
            return
            
        base_sounds = get_base_path()
        if not base_sounds.endswith("sounds"):
            base_sounds = os.path.join(base_sounds, "sounds")

        for key, filename in SOUND_FILES_MAP.items():
            target_path = self.game_root_path / "ChartEditorResources" / filename
            
            if not target_path.exists():
                source_path = os.path.join(base_sounds, filename)
                if os.path.exists(source_path):
                    try:
                        shutil.copy2(source_path, target_path)
                    except:
                        pass
            
            if target_path.exists():
                try:
                    if key == 'Metronome':
                        self.metronome_sound = pygame.mixer.Sound(str(target_path))
                    else:
                        self.sounds[filename] = pygame.mixer.Sound(str(target_path))
                        if key.startswith("UI"):
                             self.sounds[filename].set_volume(self.ui_volume)
                        else:
                             self.sounds[filename].set_volume(self.fx_volume)
                except Exception as e:
                    pass

    def open_project(self):
        start_dir = str(self.game_custom_maps_path) if self.game_custom_maps_path else ""
        folder = QFileDialog.getExistingDirectory(self, "Select Project Folder", start_dir)
        if not folder: return
        self.load_project_from_path(Path(folder))

    def load_project_from_path(self, folder_path: Path):
        self.project_folder = folder_path
        self.lbl_path.setText(str(self.project_folder))
        self.add_to_recent(folder_path)
        self.beatmaps.clear()
        
        if not self.persistent_files:
            persist_dir = self.project_folder / "cbm_files"
            if persist_dir.exists():
                try:
                    shutil.rmtree(persist_dir)
                except:
                    pass
        
        has_beatmaps = any(self.project_folder.glob("*.txt"))
        initial_level_name = "New Level"
        
        if not has_beatmaps:
            text, ok = QInputDialog.getText(self, "New Level", "What Should We Call Your Level?")
            if ok and text:
                initial_level_name = text

        found_audio = next(self.project_folder.glob("*.mp3"), None)
        if not found_audio:
            found_audio = next(self.project_folder.glob("*.wav"), None)
        if not found_audio:
            found_audio = next(self.project_folder.glob("*.ogg"), None)
        
        common_audio = found_audio.name if found_audio else ""

        try:
            for diff_name in DIFFICULTIES:
                bm = BeatmapData(diff_name)
                try:
                    bm.load(self.project_folder)
                except Exception as e:
                    pass
                
                
                if common_audio:
                     bm.metadata.AudioFilename = common_audio

                if not bm.created:
                     bm.metadata.Title = initial_level_name
                     if self.beatmaps:
                         first_valid = next((b for b in self.beatmaps.values() if b.created), None)
                         if first_valid:
                             bm.metadata.Title = first_valid.metadata.Title
                             bm.metadata.Artist = first_valid.metadata.Artist
                             bm.metadata.BPM = first_valid.metadata.BPM
                             bm.metadata.AudioFilename = first_valid.metadata.AudioFilename

                self.beatmaps[diff_name] = bm
        except Exception as e:
             QMessageBox.warning(self, "Load Warning", f"Some files could not be loaded fully: {e}")

        existing_diffs = [d for d in DIFFICULTIES if self.beatmaps[d].created]
        if existing_diffs:
            self.change_difficulty(existing_diffs[0])
            self.combo_diff.setCurrentText(existing_diffs[0])
        else:
            self.change_difficulty("Beginner")
            self.combo_diff.setCurrentText("Beginner")
            self.current_chart.created = True 
            self.current_chart.metadata.Title = initial_level_name
            self.mark_unsaved()
        
        self.update_window_title()
        
        if self.current_chart and self.current_chart.metadata.AudioFilename:
            self.prepare_audio_versions(self.current_chart.metadata.AudioFilename)

    def prepare_audio_versions(self, filename):
        if not self.project_folder or not self.game_root_path: return
        
        source = self.project_folder / filename
        if not source.exists():
            return
            
        if self.persistent_files:
            output_dir = self.project_folder / "cbm_files"
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            persist_dir = self.project_folder / "cbm_files"
            if persist_dir.exists():
                try:
                    shutil.rmtree(persist_dir)
                except:
                    pass
            
            output_dir = self.game_root_path / "ChartEditorResources" / "temp"
            if output_dir.exists():
                try:
                    shutil.rmtree(output_dir)
                except:
                    pass
            output_dir.mkdir(parents=True, exist_ok=True)
        
        self.temp_audio_files = {}
        
        was_playing = self.is_playing
        if was_playing: self.toggle_play()
        
        try:
            pygame.mixer.music.unload()
        except:
            pygame.mixer.music.stop()
        
        self.loading_dialog = LoadingDialog(self)
        self.loading_dialog.show()
        
        self.audio_generator = AudioGenerator(source, output_dir, self.persistent_files)
        self.audio_generator.progress.connect(self.loading_dialog.update_progress)
        self.audio_generator.finished_processing.connect(self.on_audio_processed)
        self.audio_generator.error_occurred.connect(lambda e: print(f"Audio Error: {e}"))
        self.audio_generator.finished.connect(self.loading_dialog.accept)
        
        self.audio_generator.start()

    def on_audio_processed(self, audio_map):
        self.temp_audio_files = audio_map
        self.load_audio(self.current_chart.metadata.AudioFilename)

    def handle_audio_drop(self, file_path):
        if not self.project_folder: return
        
        src_path = Path(file_path)
        
        try:
            if self.current_chart.metadata.AudioFilename:
                old_file = self.project_folder / self.current_chart.metadata.AudioFilename
                try:
                    pygame.mixer.music.unload()
                except AttributeError:
                    pygame.mixer.music.stop()

                if old_file.exists():
                    pass
            
            final_filename = src_path.stem + ".mp3"
            dest_path = self.project_folder / final_filename
            
            if src_path.suffix.lower() != '.mp3':
                try:
                    audio = AudioSegment.from_file(str(src_path))
                    audio.export(str(dest_path), format="mp3")
                except Exception as e:
                    QMessageBox.critical(self, "Conversion Error", f"Could not convert to MP3: {e}\nIs ffmpeg installed?")
                    return
            else:
                if src_path != dest_path:
                    shutil.copy2(src_path, dest_path)
                
            if self.persistent_files:
                persist_dir = self.project_folder / "cbm_files"
                if persist_dir.exists():
                    try:
                        shutil.rmtree(persist_dir)
                    except:
                        pass
                
            self.current_chart.metadata.AudioFilename = final_filename
            self.audio_label.set_content_loaded(final_filename)
            
            for bm in self.beatmaps.values():
                bm.metadata.AudioFilename = final_filename
            
            self.mark_unsaved()
            
            self.prepare_audio_versions(final_filename)
            
        except Exception as e:
            print(f"Failed to import audio: {e}")
            QMessageBox.critical(self, "Error", f"Failed to import audio: {e}")

    def handle_cover_drop(self, file_path):
        if not self.project_folder: return
        
        src_path = Path(file_path)
        
        try:
            for existing in self.project_folder.glob("cover.*"):
                try:
                    os.remove(existing)
                except:
                    pass
            
            dest_path = self.project_folder / "cover.jpg"
            
            with Image.open(src_path) as img:
                img = img.convert('RGB')
                img.save(dest_path, "JPEG")
            
            self.cover_label.set_content_loaded("Cover Loaded")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import cover: {e}\n(Is Pillow installed?)")

    def change_difficulty(self, diff_name):
        if not self.project_folder: return
        
        was_playing = self.is_playing
        current_playback_time = self.timeline.current_time

        if diff_name not in self.beatmaps: 
            self.beatmaps[diff_name] = BeatmapData(diff_name)
        
        target_beatmap = self.beatmaps[diff_name]
        
        if not target_beatmap.created:
            existing_diffs = [d for d in DIFFICULTIES if d in self.beatmaps and self.beatmaps[d].created]
            
            if existing_diffs:
                reply = QMessageBox.question(
                    self, 
                    "Copy Beatmap?", 
                    "Copy Beatmap From Other Difficulty?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    dialog = CopyDifficultyDialog(self, existing_diffs)
                    if dialog.exec() == QDialog.DialogCode.Accepted:
                        source_diff = dialog.get_selected_diff()
                        if source_diff in self.beatmaps:
                            target_beatmap.copy_from(self.beatmaps[source_diff])
                            target_beatmap.metadata.Version = diff_name
                            if diff_name == "Star":
                                target_beatmap.metadata.Version = ""
                else:
                    if existing_diffs:
                        src_name = existing_diffs[0]
                        src = self.beatmaps[src_name]
                        target_beatmap.metadata.Title = src.metadata.Title
                        target_beatmap.metadata.TitleUnicode = src.metadata.TitleUnicode
                        target_beatmap.metadata.Artist = src.metadata.Artist
                        target_beatmap.metadata.BPM = src.metadata.BPM
                        target_beatmap.metadata.AudioFilename = src.metadata.AudioFilename
        
        self.current_chart = target_beatmap
        
        self.block_meta_signals(True)
        m = self.current_chart.metadata
        self.meta_widgets["Title"].setText(m.Title)
        self.meta_widgets["Artist"].setText(m.Artist)
        self.meta_widgets["Charted By"].setText(m.Creator)
        self.meta_widgets["BPM"].setValue(m.BPM)
        self.meta_widgets["Level"].setValue(m.Level)
        self.meta_widgets["FlavorText"].setText(m.FlavorText)
        self.meta_widgets["Attributes"].setText(m.Attributes[0] if m.Attributes else "")
        
        if m.AudioFilename:
            self.audio_label.set_content_loaded(m.AudioFilename)
        else:
            self.audio_label.set_empty()
            
        has_cover = any(self.project_folder.glob("cover.*"))
        if has_cover:
            self.cover_label.set_content_loaded("Cover Loaded")
        else:
            self.cover_label.set_empty()
        
        if diff_name == "Star": self.txt_star_name.setText(m.Version)
        else: self.txt_star_name.clear()
        self.block_meta_signals(False)
        
        self.update_star_visibility()
        self.timeline.set_beatmap(self.current_chart)
        self.load_audio(m.AudioFilename)
        
        self.timeline.current_time = current_playback_time
        self.timeline.target_time = current_playback_time
        
        song_len_ms = self.current_chart.metadata.ActualAudioLength * 1000
        if song_len_ms > 0 and self.timeline.current_time > song_len_ms:
            self.timeline.current_time = 0
            self.timeline.target_time = 0

        self.timeline.update_scrollbar()
        
        if was_playing:
            self.sync_audio_to_time(force_play=True)
        else:
            self.sync_audio_to_time(force_play=False)

        self.update_ui_state()
        self.update_window_title()

    def update_star_visibility(self):
        is_star = self.combo_diff.currentText() == "Star"
        self.txt_star_name.setVisible(is_star)
        self.form_meta.labelForField(self.txt_star_name).setVisible(is_star)

    def block_meta_signals(self, block: bool):
        for w in self.meta_widgets.values(): 
            if isinstance(w, QWidget):
                w.blockSignals(block)
        self.txt_star_name.blockSignals(block)


    def update_metadata_from_ui(self):
        if not self.current_chart: return
        m = self.current_chart.metadata
        
        new_title = self.meta_widgets["Title"].text()
        if m.Title != new_title:
             m.Title = new_title
             for bm in self.beatmaps.values():
                 bm.metadata.Title = new_title
                 bm.metadata.TitleUnicode = new_title

        m.TitleUnicode = m.Title
        m.Artist = self.meta_widgets["Artist"].text()
        m.ArtistUnicode = m.Artist
        m.Creator = self.meta_widgets["Charted By"].text()
        m.BPM = self.meta_widgets["BPM"].value()
        m.Level = self.meta_widgets["Level"].value()
        m.FlavorText = self.meta_widgets["FlavorText"].text()
        attr_text = self.meta_widgets["Attributes"].text()
        m.Attributes = [attr_text] if attr_text else []
        
        if self.current_chart.difficulty_key == "Star":
            m.Version = self.txt_star_name.text()
        else:
            m.Version = self.current_chart.difficulty_key
        
        self.mark_unsaved()

    def update_bmap_file(self):
        if not self.project_folder: return
        bmap_files = list(self.project_folder.glob("*.bmap"))
        if bmap_files:
            bmap_path = bmap_files[0]
            try:
                with open(bmap_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                song_files = {}
                for diff_key in DIFFICULTIES:
                     if diff_key in self.beatmaps and self.beatmaps[diff_key].created:
                         song_files[diff_key] = self.beatmaps[diff_key].get_filename()
                
                data["Songs"] = [song_files]
                
                with open(bmap_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            except:
                pass

    def save_current(self):
        if not self.current_chart or not self.project_folder: return


        
        self.current_chart.editor_zoom = self.timeline.target_zoom
        
        saved = self.current_chart.save(self.project_folder)
        if saved:
            self.mark_saved()
            self.update_bmap_file()
            self.update_ui_state()
        else:
            QMessageBox.critical(self, "Error", "Failed to save file.")

    def delete_current_difficulty(self):
        if not self.current_chart or not self.project_folder or not self.current_chart.created:
            return

        diff_name = self.current_chart.difficulty_key
        dialog = DeleteConfirmationDialog(self, diff_name)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            filename = self.current_chart.get_filename()
            path = self.project_folder / filename
            try:
                if path.exists():
                    os.remove(path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not delete file: {e}")
                return

            self.current_chart.hit_objects = []
            self.current_chart.created = False
            self.current_chart.unsaved = False
            
            next_diff = None
            for d in DIFFICULTIES:
                if d != diff_name and d in self.beatmaps and self.beatmaps[d].created:
                    next_diff = d
                    break
            
            if next_diff:
                self.combo_diff.setCurrentText(next_diff)
            else:
                self.change_difficulty(diff_name)
            
            self.update_bmap_file()
            self.update_ui_state()

    def change_tool_type(self, tool_type):
        self.timeline.current_tool_type = tool_type
        self.btn_tool_note.setChecked(tool_type == "note")
        self.btn_tool_brawl.setChecked(tool_type == "brawl")
        self.btn_tool_event.setChecked(tool_type == "event")
        
        self.note_type_container.setVisible(tool_type == "note")
        self.brawl_type_container.setVisible(tool_type == "brawl")
        self.event_type_container.setVisible(tool_type == "event")
        
        self.btn_event_flip.setVisible(tool_type == "event")
        self.btn_event_toggle.setVisible(tool_type == "event")
        self.btn_event_instant.setVisible(tool_type == "event")
    
    def on_scrollbar_changed(self, value):
        self.timeline.target_time = value
        self.timeline.current_time = value
        self.timeline.update()
        
        if self.is_playing:
            self.sync_audio_to_time(force_play=True)
        else:
            self.sync_audio_to_time()

    def change_note_type(self, note_type):
        self.timeline.current_note_type = note_type
        self.btn_note_normal.setChecked(note_type == "normal")
        self.btn_note_spike.setChecked(note_type == "spike")
        self.btn_note_hold.setChecked(note_type == "hold")
        self.btn_note_screamer.setChecked(note_type == "screamer")
        self.btn_note_spam.setChecked(note_type == "spam")
        self.btn_note_freestyle.setChecked(note_type == "freestyle")
        
        self.combo_note_style.blockSignals(True)
        self.combo_note_style.clear()
        
        if note_type == "normal":
            self.combo_note_style.setEnabled(True)
            self.combo_note_style.addItems(["Normal", "Hide", "Fly In"])
        elif note_type == "spike":
            self.combo_note_style.setEnabled(True)
            self.combo_note_style.addItems(["Normal", "Fly In"])
        elif note_type == "freestyle":
            self.combo_note_style.setEnabled(True)
            self.combo_note_style.addItems(["Normal", "Hide"])
        else:
            self.combo_note_style.setEnabled(False)
            self.combo_note_style.addItem("Normal")
            
        self.combo_note_style.blockSignals(False)

    def change_brawl_type(self, brawl_type):
        self.timeline.current_brawl_type = brawl_type
        self.btn_brawl_hit.setChecked(brawl_type == "hit")
        self.btn_brawl_final.setChecked(brawl_type == "final")
        self.btn_brawl_hold.setChecked(brawl_type == "hold")
        self.btn_brawl_hold_ko.setChecked(brawl_type == "hold_knockout")
        self.btn_brawl_spam.setChecked(brawl_type == "spam")
        self.btn_brawl_spam_ko.setChecked(brawl_type == "spam_knockout")

    def change_brawl_cop(self, index):
        self.brawl_cop_index = index + 1

    def change_event_type(self, event_type):
        self.timeline.current_event_type = event_type
        self.btn_event_flip.setChecked(event_type == "flip")
        self.btn_event_toggle.setChecked(event_type == "toggle_center")
        self.btn_event_instant.setChecked(event_type == "instant_flip")

    def change_grid(self):
        self.timeline.grid_snap_div = self.spin_grid.value()
        if self.current_chart:
            self.current_chart.metadata.GridSize = self.spin_grid.value()
            self.mark_unsaved()
        self.timeline.update()

    def change_speed(self, text):
        val_str = text.replace('x', '')
        try:
            self.playback_speed = float(val_str)
            was_playing = self.is_playing
            
            if self.current_chart and self.current_chart.metadata.AudioFilename:
                self.load_audio(self.current_chart.metadata.AudioFilename)
            
            self.sync_audio_to_time(force_play=was_playing)

        except ValueError:
            pass
            
    def open_bpm_matcher(self):
        if not self.project_folder or not self.current_chart:
            return
            
        audio_file = self.project_folder / self.current_chart.metadata.AudioFilename
        if not audio_file.exists():
            QMessageBox.warning(self, "Error", "Audio file not found")
            return
            
        was_playing = self.is_playing
        if was_playing:
            self.toggle_play()
            
        dialog = BPMMatchDialog(self, audio_file)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.calculated_bpm > 0:
                self.meta_widgets["BPM"].setValue(float(dialog.calculated_bpm))
        
        self.load_audio(self.current_chart.metadata.AudioFilename)

    def toggle_metronome(self, state):
        self.metronome_active = (state == Qt.CheckState.Checked.value)

    def load_audio(self, filename):
        if not self.project_folder or not filename: return
        
        audio_file = None
        if self.playback_speed in self.temp_audio_files:
            audio_file = self.temp_audio_files[self.playback_speed]
        else:
            audio_file = str(self.project_folder / filename)

        if os.path.exists(audio_file):
            try:
                if pygame.mixer.music.get_busy(): 
                    pygame.mixer.music.stop()
                try:
                    pygame.mixer.music.unload()
                except AttributeError:
                    pass
                
                pygame.mixer.music.load(audio_file)
                pygame.mixer.music.set_volume(self.music_volume)
                
                sound = pygame.mixer.Sound(audio_file)
                
                real_len = sound.get_length()
                if self.current_chart:
                    if self.playback_speed != 1.0 and self.playback_speed in self.temp_audio_files:
                         self.current_chart.metadata.ActualAudioLength = real_len * self.playback_speed
                    else:
                         self.current_chart.metadata.ActualAudioLength = real_len
                         
                    self.timeline.update_scrollbar()
                    
            except Exception as e: 
                print(f"Audio error loading {audio_file}: {e}")
        else:
            print(f"Audio file not found: {audio_file}")

    def toggle_play(self):
        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.play_timer.stop()
        else:
            if not self.current_chart: return
            
            self.sync_audio_to_time(force_play=True)
            
            self.is_playing = True
            self.play_timer.start()

    def stop_and_reset(self):
        self.is_playing = False
        self.play_timer.stop()
        pygame.mixer.music.stop()
        self.timeline.target_time = 0.0
        self.timeline.current_time = 0.0
        self.audio_start_ms = 0.0
        self.system_start_tick = 0
        self.last_played_notes.clear()
        self.last_metronome_beat = -1
        self.timeline.update_scrollbar()
        self.timeline.update()

    def sync_audio_to_time(self, force_play=False):
        new_pos_seconds = max(0.0, self.timeline.current_time / 1000.0)
        
        if not self.current_chart: return
        
        playback_pos = new_pos_seconds
        
        if self.playback_speed != 1.0:
             playback_pos = playback_pos / self.playback_speed

        if self.is_playing or force_play:
            try:
                audio_file = None
                if self.playback_speed in self.temp_audio_files:
                    audio_file = self.temp_audio_files[self.playback_speed]
                else:
                    audio_file = str(self.project_folder / self.current_chart.metadata.AudioFilename)

                pygame.mixer.music.stop()
                pygame.mixer.music.load(audio_file)
                pygame.mixer.music.set_volume(self.music_volume)
                pygame.mixer.music.play(start=playback_pos)
                
                if not self.is_playing and not force_play:
                    pygame.mixer.music.pause()
                
                self.audio_start_ms = self.timeline.current_time
                self.system_start_tick = pygame.time.get_ticks()
                self.is_playing = force_play or self.is_playing
                
                if self.is_playing:
                    self.play_timer.start()

            except pygame.error as e:
                print(e)
        
        bpm = self.current_chart.metadata.BPM
        if bpm > 0:
             beat_interval = 60000.0 / bpm
             current_beat_index = math.floor((self.timeline.current_time - self.current_chart.metadata.Offset) / beat_interval)
             self.last_metronome_beat = current_beat_index

    def tick(self):
        if self.is_playing:
            if self.system_start_tick > 0:
                elapsed_real_ticks = pygame.time.get_ticks() - self.system_start_tick
                
                elapsed_song_ticks = elapsed_real_ticks * self.playback_speed
                
                self.timeline.current_time = self.audio_start_ms + elapsed_song_ticks
                self.timeline.target_time = self.timeline.current_time
                
                self.timeline_scrollbar.blockSignals(True)
                self.timeline_scrollbar.setValue(int(self.timeline.current_time))
                self.timeline_scrollbar.blockSignals(False)

                if self.current_chart and self.current_chart.metadata.ActualAudioLength > 0:
                    song_length_ms = self.current_chart.metadata.ActualAudioLength * 1000
                    if self.timeline.current_time >= song_length_ms:
                        self.timeline.current_time = song_length_ms
                        self.timeline.target_time = song_length_ms
                        self.is_playing = False
                        self.play_timer.stop()
                        pygame.mixer.music.stop()
            
            if self.metronome_active and self.current_chart and self.current_chart.metadata.BPM > 0:
                 bpm = self.current_chart.metadata.BPM
                 offset = self.current_chart.metadata.Offset
                 beat_interval = 60000.0 / bpm
                 
                 current_beat_index = math.floor((self.timeline.current_time - offset) / beat_interval)
                 
                 if current_beat_index > self.last_metronome_beat:
                     if self.metronome_sound:
                         self.metronome_sound.set_volume(1.0)
                         self.metronome_sound.play()
                     self.last_metronome_beat = current_beat_index

            if self.timeline.selection_start is not None:
                self.timeline.update_selection_rect()
            
            if self.timeline.dragging_objects:
                self.timeline.update_dragged_objects()
            
            self.check_and_play_notes()
            self.timeline.update()

    def check_and_play_notes(self):
        if not self.current_chart:
            return
        
        current_time = self.timeline.current_time
        hit_window = 40 * self.playback_speed
        
        for obj in self.current_chart.hit_objects:
            obj_id = id(obj)
            head_diff = abs(obj.time - current_time)
            
            if head_diff <= hit_window and (obj_id, 'head') not in self.last_played_notes:
                sound_key = None
                
                if obj.is_event:
                    if obj.is_flip: sound_key = SOUND_FILES_MAP['Event Flip']
                    elif obj.is_instant_flip: sound_key = SOUND_FILES_MAP['Event Instant']
                    elif obj.is_toggle_center: sound_key = SOUND_FILES_MAP['Event Toggle']
                else:
                    if obj.is_spike: sound_key = SOUND_FILES_MAP['Spike']
                    elif obj.is_hold: sound_key = SOUND_FILES_MAP['Hold Start']
                    elif obj.is_screamer: sound_key = SOUND_FILES_MAP['Double Start']
                    elif obj.is_spam: sound_key = SOUND_FILES_MAP['Spam']
                    elif obj.is_brawl_hit: sound_key = SOUND_FILES_MAP['Brawl Hit']
                    elif obj.is_brawl_final: sound_key = SOUND_FILES_MAP['Brawl Final']
                    elif obj.is_mid: sound_key = SOUND_FILES_MAP['Mid Note']
                    elif obj.is_hide: sound_key = SOUND_FILES_MAP['Hide Note']
                    else:
                        sound_key = SOUND_FILES_MAP['Lane 1 (Top)'] if obj.lane == 0 else SOUND_FILES_MAP['Lane 2 (Bottom)']
                
                if sound_key and sound_key in self.sounds:
                    self.sounds[sound_key].play()
                
                self.last_played_notes.add((obj_id, 'head'))

            if obj.is_hold:
                 pass 

            if obj.is_screamer:
                tail_diff = abs(obj.end_time - current_time)
                if tail_diff <= hit_window and (obj_id, 'tail') not in self.last_played_notes:
                    if SOUND_FILES_MAP['Double Start'] in self.sounds:
                        self.sounds[SOUND_FILES_MAP['Double Start']].play()
                    self.last_played_notes.add((obj_id, 'tail'))
            
            if head_diff > hit_window * 3:
                 if (obj_id, 'head') in self.last_played_notes:
                     self.last_played_notes.remove((obj_id, 'head'))
            
            if obj.is_screamer:
                tail_diff_check = abs(obj.end_time - current_time)
                if tail_diff_check > hit_window * 3:
                     if (obj_id, 'tail') in self.last_played_notes:
                         self.last_played_notes.remove((obj_id, 'tail'))

    def keyPressEvent(self, e: QKeyEvent):
        if e.isAutoRepeat():
            e.accept()
            return
            
        if e.key() == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
            return

        modifiers = e.modifiers()
        key = e.key()
        
        handled = False
        
        current_time = time.time()
        key_id = (modifiers, key)
        last_time = self.last_hotkey_time.get(key_id, 0)
        
        if current_time - last_time < 0.1:
            e.accept()
            return
        
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_1: self.change_tool_type("note"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
            elif key == Qt.Key.Key_2: self.change_tool_type("brawl"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
            elif key == Qt.Key.Key_3: self.change_tool_type("event"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True

        else:
            if self.timeline.current_tool_type == "note":
                if key == Qt.Key.Key_1: self.change_note_type("normal"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_2: self.change_note_type("spike"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_3: self.change_note_type("hold"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_4: self.change_note_type("screamer"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_5: self.change_note_type("spam"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_6: self.change_note_type("freestyle"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
            elif self.timeline.current_tool_type == "brawl":
                if key == Qt.Key.Key_1: self.change_brawl_type("hit"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_2: self.change_brawl_type("final"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_3: self.change_brawl_type("hold"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_4: self.change_brawl_type("hold_knockout"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_5: self.change_brawl_type("spam"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_6: self.change_brawl_type("spam_knockout"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
            elif self.timeline.current_tool_type == "event":
                if key == Qt.Key.Key_1: self.change_event_type("flip"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_2: self.change_event_type("toggle_center"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_3: self.change_event_type("instant_flip"); self.play_ui_sound_suppressed('UI Click'); self.last_hotkey_time[key_id] = current_time; handled = True

        if handled:
            e.accept()
            return

        if e.key() == Qt.Key.Key_Space:
            if e.isAutoRepeat():
                e.accept()
                return
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.stop_and_reset()
            else:
                self.toggle_play()
            e.accept()
        elif e.key() == Qt.Key.Key_Shift:
            if e.isAutoRepeat():
                e.accept()
                return
            self.stop_and_reset()
            e.accept()
        elif e.key() == Qt.Key.Key_S and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.save_current()
            e.accept()
        elif e.key() == Qt.Key.Key_T:
            if not e.isAutoRepeat():
                self.timeline.toggle_triplet()
            e.accept()

if __name__ == "__main__":
    if sys.platform.startswith('win'):
        import subprocess
        subprocess.CREATE_NO_WINDOW = 0x08000000
        _old_popen = subprocess.Popen.__init__
        
        def _new_popen(self, *args, **kwargs):
            kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
            _old_popen(self, *args, **kwargs)
        
        subprocess.Popen.__init__ = _new_popen
    try:
        initialize_ffmpeg()
    except Exception as e:
        print(f"Init Error: {e}")
    app = QApplication(sys.argv)
    
    icon_path = None
    base_path = get_base_path()
    
    paths_to_check = [
        os.path.join(base_path, "icon.png"),
        os.path.join(base_path, "sounds", "icon.png")
    ]
    
    for p in paths_to_check:
        if os.path.exists(p):
            icon_path = p
            break
    
    saved_x = 100
    saved_y = 100
    
    try:
        if sys.platform.startswith("win"):
            app_data = os.getenv('APPDATA')
            if app_data:
                p_file = Path(app_data).parent / "LocalLow" / "CBM_Editor" / "path.json"
            else:
                p_file = Path.home() / "AppData" / "LocalLow" / "CBM_Editor" / "path.json"
        else:
            p_file = Path.home() / ".config" / "CBM_Editor" / "path.json"
        
        if p_file.exists():
            with open(p_file, 'r') as f:
                data = json.load(f)
                game_path = data.get("game_path")
                if game_path:
                    config_path = Path(game_path) / "ChartEditorResources" / "editor_config.json"
                    if config_path.exists():
                        with open(config_path, 'r') as cf:
                            config = json.load(cf)
                            w_data = config.get("window", {})
                            saved_x = w_data.get("x", 100)
                            saved_y = w_data.get("y", 100)
    except:
        pass
         
    launch_window = None 
    
    def show_main_window():
        global launch_window
        launch_window = MainWindow()
        launch_window.show()
        launch_window.installEventFilter(launch_window)

    if icon_path:
        splash = AnimatedSplashScreen(icon_path, saved_x, saved_y)
        splash.finished.connect(show_main_window)
        splash.show()
    else:
        show_main_window()


    sys.exit(app.exec())
