from .ui_utils import *

register_shared_globals(globals())

class StartScreen(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setSpacing(20)
        
        icon_path = ""
        base_path = Path(__file__).parent
        icon_name = "icon_pre.png" if PREVIEW_VERSION else "icon.png"
        paths_to_check = [
            base_path / icon_name,
            base_path / "sounds" / icon_name,
            base_path / "icon.png",
            base_path / "sounds" / "icon.png"
        ]
        
        for p in paths_to_check:
            if p.exists():
                icon_path = str(p)
                break
            
        lbl_title = QLabel()
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        title_effect = FastDropShadowEffect(lbl_title)
        title_effect.setBlurRadius(8)
        title_effect.setColor(QColor(0, 0, 0, 200))
        title_effect.setOffset(0, 2)
        set_manual_shadow(lbl_title, title_effect)
        
        if icon_path:
            from PyQt6.QtGui import QPixmap
            pixmap = QPixmap(icon_path)
            pixmap = pixmap.scaled(900, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            lbl_title.setPixmap(pixmap)
        else:
            lbl_title.setText("- CBM Editor -")
            lbl_title.setStyleSheet(f"font-size: 64px; font-weight: bold; color: {UI_THEME['accent']};")
            
        layout.addWidget(lbl_title)
        
        ctrl_layout = QHBoxLayout()
        self.lbl_recent = QLabel("Recent Projects")
        self.lbl_recent.setStyleSheet("font-size: 24px; font-weight: bold;")
        
        recent_effect = FastDropShadowEffect(self.lbl_recent)
        recent_effect.setBlurRadius(8)
        recent_effect.setColor(QColor(0, 0, 0, 200))
        recent_effect.setOffset(0, 2)
        set_manual_shadow(self.lbl_recent, recent_effect)
        
        ctrl_layout.addWidget(self.lbl_recent)

        ctrl_layout.addStretch()

        self.lbl_sort_by = QLabel("Sort by:")
        
        sort_effect = FastDropShadowEffect(self.lbl_sort_by)
        sort_effect.setBlurRadius(8)
        sort_effect.setColor(QColor(0, 0, 0, 200))
        sort_effect.setOffset(0, 2)
        set_manual_shadow(self.lbl_sort_by, sort_effect)
        
        ctrl_layout.addWidget(self.lbl_sort_by)
        self.combo_sort = IgnoreWheelComboBox()
        self.combo_sort.setView(SmoothListView(self.combo_sort))
        self.combo_sort.addItems(["Recent", "Name", "Object Amount"])
        self.combo_sort.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_sort.currentIndexChanged.connect(self.populate_list)
        ctrl_layout.addWidget(self.combo_sort)
        
        layout.addLayout(ctrl_layout)
        
        self.list_widget = SmoothListWidget()
        self.list_widget.setStyleSheet(
            f"QListWidget {{ background: transparent; background-color: transparent; border: none; padding: 10px; font-size: 18px; outline: 0; }}"
            f"QListWidget::viewport {{ background: transparent; background-color: transparent; border: none; }}"
            f"QListWidget::item {{ padding: 15px; border-bottom: 1px solid {UI_THEME['border_medium']}; }}"
            f"QListWidget::item:hover {{ background-color: rgba(255, 255, 255, 15); }}"
            f"QListWidget::item:selected {{ background-color: rgba(255, 255, 255, 30); color: white; border: none; }}"
            f"QListWidget::item:selected:!active {{ background-color: rgba(255, 255, 255, 30); color: white; border: none; }}"
            f"QListWidget::item:selected:hover {{ background-color: rgba(255, 255, 255, 45); color: white; border: none; }}"
        )

        self.list_widget.verticalScrollBar().setStyleSheet(
            f"QScrollBar:vertical {{ background: transparent; background-color: transparent; width: 8px; border: none; margin: 0px; }}"
            f"QScrollBar::handle:vertical {{ background-color: {UI_THEME['accent']}; min-height: 30px; border-radius: 4px; margin: 0px; }}"
            f"QScrollBar::handle:vertical:hover {{ background-color: {UI_THEME['accent']}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; border: none; background: transparent; background-color: transparent; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; background-color: transparent; border: none; }}"
        )

        self.list_widget.itemDoubleClicked.connect(self.on_item_double_click)
        self.list_widget.itemClicked.connect(self.on_item_click)
        layout.addWidget(self.list_widget)
        
        self.projects_data = []
        self.project_stats_cache = {}
        self.update_theme()

    def update_theme(self):
        if not hasattr(self, 'editor'): return
        
        text_color = "white"
        item_bg = "rgba(0, 0, 0, 15)"
        hover_bg = "rgba(0, 0, 0, 30)"
        selected_bg = "rgba(0, 0, 0, 45)"
        selected_hover_bg = "rgba(0, 0, 0, 60)"
        outline_color = "rgba(0, 0, 0, 60)"

        self.lbl_recent.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {text_color};")
        self.lbl_sort_by.setStyleSheet(f"color: {text_color};")

        self.list_widget.setStyleSheet(
            f"QListWidget {{ background: transparent; background-color: transparent; border: none; padding: 10px; font-size: 18px; outline: 0; color: {text_color}; }}"
            f"QListWidget::viewport {{ background: transparent; background-color: transparent; border: none; }}"
            f"QListWidget::item {{ background-color: {item_bg}; padding: 15px; border-radius: 6px; margin: 4px 0px; border: 1px solid {outline_color}; color: {text_color}; }}"
            f"QListWidget::item:hover {{ background-color: {hover_bg}; }}"
            f"QListWidget::item:selected {{ background-color: {selected_bg}; color: {text_color}; border: none; }}"
            f"QListWidget::item:selected:!active {{ background-color: {selected_bg}; color: {text_color}; border: none; }}"
            f"QListWidget::item:selected:hover {{ background-color: {selected_hover_bg}; color: {text_color}; border: none; }}"
        )

        self.list_widget.verticalScrollBar().setStyleSheet(
            f"QScrollBar:vertical {{ background: transparent; background-color: transparent; width: 8px; border: none; margin: 0px; }}"
            f"QScrollBar::handle:vertical {{ background-color: {ACCENT_COLOR}; min-height: 30px; border-radius: 4px; margin: 0px; }}"
            f"QScrollBar::handle:vertical:hover {{ background-color: {ACCENT_HOVER}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; border: none; background: transparent; background-color: transparent; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; background-color: transparent; border: none; }}"
        )

    def load_projects(self):
        self.projects_data.clear()
        active_cache_keys = set()

        for idx, path_str in enumerate(self.editor.recent_projects):
            p = Path(path_str)
            if not p.exists() or not p.is_dir():
                continue

            mtime = os.path.getmtime(path_str)
            map_files = []
            signature_parts = []
            try:
                for file in p.iterdir():
                    if file.suffix.lower() in {".osu", ".txt"}:
                        stat = file.stat()
                        map_files.append(file)
                        signature_parts.append((file.name, stat.st_mtime_ns, stat.st_size))
            except OSError:
                pass
            signature = tuple(sorted(signature_parts))
            cache_key = os.path.normcase(os.path.abspath(path_str))
            active_cache_keys.add(cache_key)
            cached = self.project_stats_cache.get(cache_key)
            if cached and cached[0] == signature:
                note_count = cached[1]
            else:
                note_count = 0
                for file in map_files:
                    try:
                        with open(file, "r", encoding="utf-8") as f:
                            in_hitobjects = False
                            is_centered = False
                            for line in f:
                                line = line.strip()
                                if line.startswith("[") and line.endswith("]"):
                                    in_hitobjects = (line == "[HitObjects]")
                                    continue
                                if in_hitobjects and line and not line.startswith("//"):
                                    parts = line.split(",")
                                    if len(parts) >= 5:
                                        x_val = parts[0].strip()
                                        hitsound = parts[4].strip()
                                        if x_val == "384" and hitsound == "2":
                                            is_centered = not is_centered
                                        elif x_val == "384" and hitsound == "8" and is_centered:
                                            continue
                                    note_count += 1
                    except:
                        pass
                self.project_stats_cache[cache_key] = (signature, note_count)

            self.projects_data.append({
                "path": path_str,
                "name": p.name,
                "mtime": mtime,
                "notes": note_count,
                "recent_index": idx
            })

        self.project_stats_cache = {
            key: value
            for key, value in self.project_stats_cache.items()
            if key in active_cache_keys
        }
        self.populate_list()

    def populate_list(self):
        self.list_widget.clear()
        sort_mode = self.combo_sort.currentText()

        if sort_mode == "Recent":
            self.projects_data.sort(key=lambda x: x["recent_index"])
        elif sort_mode == "Name":
            self.projects_data.sort(key=lambda x: x["name"].lower())
        elif sort_mode == "Object Amount":
            self.projects_data.sort(key=lambda x: x["notes"], reverse=True)
            
        for proj in self.projects_data:
            display_text = proj["name"]
            if sort_mode == "Object Amount":
                display_text += f"  ({proj['notes']} objects)"
                
            item = QListWidgetItem(" ")
            item.setData(Qt.ItemDataRole.UserRole, proj["path"])

            lbl = QLabel(display_text)
            lbl.setStyleSheet("background: transparent; color: white; font-size: 18px; font-weight: normal; padding: 2px;")
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, lbl)

            effect = FastDropShadowEffect(lbl)
            effect.setBlurRadius(12)
            effect.setColor(QColor(0, 0, 0, 150))
            effect.setOffset(0, 3)
            set_manual_shadow(lbl, effect)

    def on_item_double_click(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            if hasattr(self.editor, 'play_ui_sound_suppressed'):
                pan = self.editor.get_pan_for_widget(self.list_widget)
                self.editor.play_ui_sound_suppressed('UI Click', pan)
            if not self.editor.confirm_unsaved_changes("load"):
                return
            self.editor.load_project_from_path(Path(path))

    def on_item_click(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            if hasattr(self.editor, 'play_ui_sound_suppressed'):
                pan = self.editor.get_pan_for_widget(self.list_widget)
                self.editor.play_ui_sound_suppressed('UI Click', pan)
            if hasattr(self.editor, 'preview_metadata_for_path'):
                self.editor.preview_metadata_for_path(path)

class SoundSettingWidget(QWidget):
    soundReset = pyqtSignal(str) 
    soundChanged = pyqtSignal(str, str) 

    def __init__(self, friendly_name, filename, game_root):
        super().__init__()
        self.filename = filename
        self.game_root = game_root
        self.preview_sound = None
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        
        lbl_name = QLabel(friendly_name)
        lbl_name.setFixedWidth(120)
        layout.addWidget(lbl_name)
        
        self.btn_play = QPushButton("Play")
        self.btn_play.setFixedWidth(60)
        self.btn_play.setProperty("is_custom_sound_btn", True)
        self.btn_play.clicked.connect(self.play_sound)
        layout.addWidget(self.btn_play)
        
        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setFixedWidth(60)
        self.btn_reset.setProperty("is_custom_sound_btn", True)
        self.btn_reset.clicked.connect(self.reset_sound)
        layout.addWidget(self.btn_reset)
        
        SOUND_TOOLTIPS = {
            "UI Click": "Plays when you click on buttons",
            "UI Tick Off": "Plays when you uncheck a checkbox",
            "UI Tick On": "Plays when you check a checkbox",
            "UI Text": "Plays when clicking on textbox",
            "UI Scroll": "Plays while scrolling on timeline",
            "UI Place": "Plays when placing notes and events",
            "UI Delete": "Plays when deleting notes and events",
            "UI Drag": "Plays while dragging notes and events",
            "UI Change": "Plays when changing modifiers of a note",
            "Boot": "Plays when opening CBM Editor"
        }
        if friendly_name in SOUND_TOOLTIPS:
            tip = SOUND_TOOLTIPS[friendly_name]
            lbl_name.setToolTip(tip)
            self.setToolTip(tip)

        self.drop_label = FileDropLabel("Drag new audio here")
        if friendly_name in SOUND_TOOLTIPS:
            self.drop_label.setToolTip(SOUND_TOOLTIPS[friendly_name])
        self.drop_label.fileDropped.connect(self.handle_drop)
        layout.addWidget(self.drop_label)
        
    def play_sound(self):
        path = self.game_root / "ChartEditorResources" / self.filename
        if path.exists():
            try:
                if self.preview_sound is None:
                    self.preview_sound = get_audio_engine().load_sound(path)
                self.preview_sound.play()
            except:
                pass

    def handle_drop(self, file_path):
        self.soundChanged.emit(self.filename, file_path)
        if self.preview_sound:
            self.preview_sound.free()
            self.preview_sound = None

    def reset_sound(self):
        self.soundReset.emit(self.filename)
        if self.preview_sound:
            self.preview_sound.free()
            self.preview_sound = None

class KeybindButton(QPushButton):
    def __init__(self, key_str="None", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.key_str = key_str
        self.setText(key_str)
        self.listening = False
        self.recorded_keys = []
        self.clicked.connect(self.start_listening)

    def start_listening(self):
        self.listening = True
        self.recorded_keys = []
        self.setText("Press key(s)...")
        self.setFocus()

    def get_key_name(self, e):
        k = e.key()
        if k == Qt.Key.Key_Control: return "Ctrl"
        elif k == Qt.Key.Key_Shift: return "Shift"
        elif k == Qt.Key.Key_Alt: return "Alt"
        elif k == Qt.Key.Key_Meta: return "Meta"
        elif k == Qt.Key.Key_Left: return "Left"
        elif k == Qt.Key.Key_Right: return "Right"
        elif k == Qt.Key.Key_Up: return "Up"
        elif k == Qt.Key.Key_Down: return "Down"
        elif k == Qt.Key.Key_Space: return "Space"
        elif k == Qt.Key.Key_Tab: return "Tab"
        elif k == Qt.Key.Key_Return: return "Return"
        elif k == Qt.Key.Key_Enter: return "Enter"
        elif k == Qt.Key.Key_Backspace: return "Backspace"
        elif k == Qt.Key.Key_Delete: return "Delete"
        else:
            seq = QKeySequence(k)
            s = seq.toString()
            return s.upper() if s else ""

    def keyPressEvent(self, e):
        if self.listening:
            if e.isAutoRepeat():
                e.accept()
                return

            if e.key() == Qt.Key.Key_Escape:
                self.key_str = "None"
                self.setText(self.key_str)
                self.listening = False
                self.clearFocus()
                return

            name = self.get_key_name(e)
            if name:
                mods = [k for k in self.recorded_keys if k in ("Ctrl", "Shift", "Alt", "Meta")]
                others = [k for k in self.recorded_keys if k not in ("Ctrl", "Shift", "Alt", "Meta")]
                if name in ("Ctrl", "Shift", "Alt", "Meta"):
                    if name not in mods: mods.append(name)
                else:
                    if name not in others: others.append(name)
                self.recorded_keys = mods + others
            e.accept()
        else:
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if self.listening:
            if e.isAutoRepeat():
                e.accept()
                return

            if self.recorded_keys:
                self.key_str = "+".join(self.recorded_keys)
                self.setText(self.key_str)
                self.listening = False
                self.clearFocus()
            e.accept()
        else:
            super().keyReleaseEvent(e)

    def focusOutEvent(self, e):
        if self.listening:
            self.listening = False
            if self.recorded_keys:
                self.key_str = "+".join(self.recorded_keys)
            self.setText(self.key_str)
        super().focusOutEvent(e)
        
    def set_key(self, key_str):
        self.key_str = key_str
        self.setText(key_str)


class BlurWorker(QThread):
    finished_blur = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.requests = {}
        self.is_running = True
        self.lock = QMutex()
        self.cond = QWaitCondition()

    def request_blur(self, src, dst, blur):
        self.lock.lock()
        self.requests[dst] = (src, blur)
        self.cond.wakeAll()
        self.lock.unlock()

    def run(self):
        while self.is_running:
            self.lock.lock()
            if not self.requests:
                self.cond.wait(self.lock)
            if not self.is_running:
                self.lock.unlock()
                break
                
            dst, (src, blur) = self.requests.popitem()
            self.lock.unlock()
            
            try:
                apply_bg_image_with_blur(src, dst, blur)
                self.finished_blur.emit(dst)
            except Exception as e:
                pass

    def stop(self):
        self.lock.lock()
        self.is_running = False
        self.cond.wakeAll()
        self.lock.unlock()
        self.wait()


class SettingsDialog(QDialog):
    def showEvent(self, event):
        if hasattr(super(), "showEvent"): super().showEvent(event)

    def get_group_style(self):
         return "QGroupBox { margin-top: 15px; font-weight: bold; border: none; } QGroupBox::title { font-size: 24pt; subcontrol-origin: margin; left: 10px; padding: 0px 5px; border-radius: 4px; }"

    def on_blur_finished(self, dst_path):
        import os
        filename = os.path.basename(dst_path)
        if hasattr(self.parent_window, 'timeline') and self.parent_window.timeline:
            if filename == "bg.png":
                self.parent_window.timeline.load_background_image()
                self.parent_window.timeline.update()
            elif filename == "ui_bg.png":
                if hasattr(self.parent_window, 'load_ui_background_image'):
                    self.parent_window.load_ui_background_image()
                self.parent_window.update()
                for gb in ['gb_proj', 'gb_meta', 'gb_timing']:
                    if hasattr(self.parent_window, gb):
                        getattr(self.parent_window, gb).update()

    def __init__(self, parent, current_scale, current_master_vol, current_music_vol, current_fx_vol, current_ui_vol, current_colors, game_root, event_default_order="Before", enable_3d_sound=True, enable_visualizer=True, enable_beatflash=True, auto_save=False, file_extension=".txt", geometry=None, grid_opacity=50, visualizer_opacity=10, background_opacity=20, grid_thickness=2, current_background="None", preview_bg_opacity=30, lane_opacity=100, background_blur=0, ui_brightness=60, current_keybinds=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(False)
        self.sounds_changed = False
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(540, 750)

        self.original_colors = current_colors.copy()
        self.current_colors = current_colors.copy()
        if current_keybinds is None:
            self.current_keybinds = DEFAULT_KEYBINDS.copy()
        else:
            self.current_keybinds = current_keybinds.copy()
        self.enable_3d_sound = enable_3d_sound
        self.enable_visualizer = enable_visualizer
        self.enable_beatflash = enable_beatflash
        self.auto_save = auto_save
        self.game_root = game_root
        self.original_background = current_background
        self.original_bg_blur = background_blur
        self.original_ui_bg_blur = getattr(parent, 'ui_bg_blur', 0)
        self.original_ui_bg_opacity = getattr(parent, 'ui_bg_opacity', 0)
        self.parent_window = parent
        
        self.blur_worker = BlurWorker()
        self.blur_worker.start()
        self.blur_worker.finished_blur.connect(self.on_blur_finished)

        main_layout = QVBoxLayout(self)
        
        tabs_area = SmoothScrollArea()
        tabs_area.setWidgetResizable(True)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        audio_group = QGroupBox("Audio")
        audio_group.setStyleSheet(self.get_group_style())
        audio_layout = QVBoxLayout()
        audio_layout.setContentsMargins(10, 5, 10, 10)
        
        master_layout = QHBoxLayout()
        master_layout.addWidget(QLabel("Master Volume:"))
        self.master_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.master_slider.setToolTip("Volume of all sounds")
        self.master_slider.setRange(0, 100)
        self.master_slider.setValue(int(current_master_vol * 100))
        self.master_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        master_layout.addWidget(self.master_slider)
        self.master_label = QLabel(f"{int(current_master_vol * 100)}%")
        self.master_label.setFixedWidth(50)
        master_layout.addWidget(self.master_label)
        audio_layout.addLayout(master_layout)

        music_layout = QHBoxLayout()
        music_layout.addWidget(QLabel("Music Volume:"))
        self.music_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.music_slider.setToolTip("Volume of chart audio")
        self.music_slider.setRange(0, 100)
        self.music_slider.setValue(int(current_music_vol * 100))
        self.music_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        music_layout.addWidget(self.music_slider)
        self.music_label = QLabel(f"{int(current_music_vol * 100)}%")
        self.music_label.setFixedWidth(50)
        music_layout.addWidget(self.music_label)
        audio_layout.addLayout(music_layout)
        
        fx_layout = QHBoxLayout()
        fx_layout.addWidget(QLabel("Hit FX Volume:"))
        self.fx_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.fx_slider.setToolTip("Volume of note hit sounds")
        self.fx_slider.setRange(0, 100)
        self.fx_slider.setValue(int(current_fx_vol * 100))
        self.fx_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        fx_layout.addWidget(self.fx_slider)
        self.fx_label = QLabel(f"{int(current_fx_vol * 100)}%")
        self.fx_label.setFixedWidth(50)
        fx_layout.addWidget(self.fx_label)

        audio_layout.addLayout(fx_layout)

        ui_layout = QHBoxLayout()
        ui_layout.addWidget(QLabel("UI SFX Volume:"))
        self.ui_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.ui_slider.setToolTip("Volume of UI sounds")
        self.ui_slider.setRange(0, 100)
        self.ui_slider.setValue(int(current_ui_vol * 100))
        self.ui_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ui_layout.addWidget(self.ui_slider)
        self.ui_label = QLabel(f"{int(current_ui_vol * 100)}%")
        self.ui_label.setFixedWidth(50)
        ui_layout.addWidget(self.ui_label)
        audio_layout.addLayout(ui_layout)
        
        self.chk_mute_events = QCheckBox("Mute Event SFX")
        self.chk_mute_events.setToolTip("Mute Event sounds (Flip, ToggleCenter, InstantFlip)")
        if hasattr(parent, 'mute_event_sfx'):
            self.chk_mute_events.setChecked(parent.mute_event_sfx)
        else:
            self.chk_mute_events.setChecked(False)
        self.chk_mute_events.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        def on_mute_events_changed(state):
            if hasattr(parent, 'mute_event_sfx'):
                parent.mute_event_sfx = bool(state)
        self.chk_mute_events.stateChanged.connect(on_mute_events_changed)
        audio_layout.addWidget(self.chk_mute_events)
 
        audio_group.setLayout(audio_layout)
        content_layout.addWidget(audio_group)

        editor_group = QGroupBox("Editor")
        editor_group.setStyleSheet(self.get_group_style())
        editor_layout = QVBoxLayout()
        editor_layout.setContentsMargins(10, 5, 10, 10)
        
        playback_layout = QHBoxLayout()
        playback_layout.addWidget(QLabel("Playback Bar X:"))
        self.slider_playback_pos = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        
        max_width = 800
        if hasattr(parent, 'timeline') and parent.timeline:
            max_width = parent.timeline.width()
        elif hasattr(parent, 'width'):
            max_width = parent.width()
            
        max_snapped_width = max(25, (max_width // 25) * 25)
        self.slider_playback_pos.setRange(0, max_snapped_width)
        self.slider_playback_pos.setSingleStep(25)
        self.slider_playback_pos.setTickInterval(25)
        self.slider_playback_pos.setTickPosition(QSlider.TickPosition.TicksBelow)
        
        current_x_pos = 150
        if hasattr(parent, 'timeline_visual_start'):
            current_x_pos = parent.timeline_visual_start
            
        self.slider_playback_pos.setValue(current_x_pos)
        self.slider_playback_pos.setToolTip("Change where the playback head is centered on screen")
        self.slider_playback_pos.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        playback_layout.addWidget(self.slider_playback_pos)
        self.lbl_playback_pos = QLabel(str(current_x_pos))
        self.lbl_playback_pos.setFixedWidth(50)
        playback_layout.addWidget(self.lbl_playback_pos)
        
        self.slider_playback_pos.setProperty("skip_global_sound", True)
        
        self.last_sound_time = 0
        self.last_played_val = -1
        
        def play_slider_sound(val):
            if val % 25 != 0: return
            curr = time.time()
            if val != self.last_played_val and (curr - self.last_sound_time > 0.03):
                if hasattr(parent, 'play_ui_sound_suppressed'):
                    val_range = self.slider_playback_pos.maximum() - self.slider_playback_pos.minimum()
                    if val_range > 0:
                        ratio = (val - self.slider_playback_pos.minimum()) / float(val_range)
                    else:
                        ratio = 0.5
                    i = int(round((ratio - 0.5) * 48))
                    i = max(-24, min(24, i))
                    sound_name = f"UI Scroll P{i}" if i != 0 and hasattr(parent, 'sounds') and f"UI Scroll P{i}" in parent.sounds else 'UI Scroll'
                    parent.play_ui_sound_suppressed(sound_name)
                self.last_sound_time = curr
                self.last_played_val = val

        def snap_slider_val(v):
            if self.slider_playback_pos.isSliderDown():
                snapped = round(v / 25) * 25
                if v != snapped:
                    self.slider_playback_pos.blockSignals(True)
                    self.slider_playback_pos.setValue(snapped)
                    self.slider_playback_pos.blockSignals(False)
                    v = snapped
            self.lbl_playback_pos.setText(str(v))
            if parent and hasattr(parent, 'timeline_visual_start'):
                parent.timeline_visual_start = v
                if hasattr(parent, 'timeline'):
                    parent.timeline.update()
            play_slider_sound(v)
            
        self.slider_playback_pos.valueChanged.connect(snap_slider_val)

        editor_layout.addLayout(playback_layout)
        
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Global Scale:"))
        self.scale_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setToolTip("Change the scale of all UI elements (experimental at high levels)")
        self.scale_slider.setRange(50, 150)
        self.scale_slider.setSingleStep(5)
        self.scale_slider.setValue(int(current_scale * 100))
        self.scale_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scale_layout.addWidget(self.scale_slider)
        self.lbl_scale = QLabel(f"{int(current_scale * 100)}%")
        self.lbl_scale.setFixedWidth(50)
        scale_layout.addWidget(self.lbl_scale)
        def update_scale_label(v):
            if self.scale_slider.isSliderDown():
                snapped = round(v / 5) * 5
                if v != snapped:
                    self.scale_slider.blockSignals(True)
                    self.scale_slider.setValue(snapped)
                    self.scale_slider.blockSignals(False)
                    v = snapped
            self.lbl_scale.setText(f"{v}%")
        self.scale_slider.valueChanged.connect(update_scale_label)
        editor_layout.addLayout(scale_layout)
        
        self.chk_3d_sound = QCheckBox("3D Sound")
        self.chk_3d_sound.setToolTip("Makes UI sounds come from a 3D environment when on (aka spatial audio or panning)")
        self.chk_3d_sound.setChecked(self.enable_3d_sound)
        editor_layout.addWidget(self.chk_3d_sound)
        
        self.chk_rpc = QCheckBox("Discord Rich Presence")
        self.chk_rpc.setToolTip("Show CBM Editor on your profile while the program is open")
        self.chk_rpc.setChecked(parent.enable_rpc if hasattr(parent, "enable_rpc") else True)
        editor_layout.addWidget(self.chk_rpc)
        
        self.chk_visualizer = QCheckBox("Visualizer")
        self.chk_visualizer.setToolTip("Music visualizer in the background/bottom left of UI")
        self.chk_visualizer.setChecked(self.enable_visualizer)
        editor_layout.addWidget(self.chk_visualizer)
        
        self.chk_beatflash = QCheckBox("Beat Flashes")
        self.chk_beatflash.setToolTip("Bar lines flash with the beat")
        self.chk_beatflash.setChecked(self.enable_beatflash)
        editor_layout.addWidget(self.chk_beatflash)
        
        self.chk_auto_save = QCheckBox("Auto Save")
        self.chk_auto_save.setToolTip("Automatically save chart every 60s")
        self.chk_auto_save.setChecked(self.auto_save)
        editor_layout.addWidget(self.chk_auto_save)

        self.chk_backups = QCheckBox("Create Backups")
        self.chk_backups.setToolTip("Create a versioned backup whenever a difficulty is saved")
        self.chk_backups.setChecked(getattr(parent, 'enable_backups', True))
        editor_layout.addWidget(self.chk_backups)
        
        self.chk_disable_tooltips = QCheckBox("Disable Tooltips")
        self.chk_disable_tooltips.setToolTip("Disable all hover tooltips globally")
        self.chk_disable_tooltips.setChecked(getattr(parent, 'disable_tooltips', False))
        editor_layout.addWidget(self.chk_disable_tooltips)
        
        self.chk_disable_hold_collisions = QCheckBox("Disable Hold Collisions")
        self.chk_disable_hold_collisions.setToolTip("Allows for the placement of notes within hold notes on the same lane (allows for many 4k patterns, as well as camera tech without blocking note placement)")
        self.chk_disable_hold_collisions.setChecked(getattr(parent, 'disable_hold_collisions', False))
        editor_layout.addWidget(self.chk_disable_hold_collisions)

        self.chk_objects_follow_bpm_grid = QCheckBox("Objects Follow BPM Grid")
        self.chk_objects_follow_bpm_grid.setToolTip("Keep objects on their relative grid positions when BPM tags are moved or changed")
        self.chk_objects_follow_bpm_grid.setChecked(getattr(parent, 'objects_follow_bpm_grid', True))
        editor_layout.addWidget(self.chk_objects_follow_bpm_grid)
        
        editor_layout.addWidget(QLabel("Default Event Execution Order:"))
        self.combo_event_order = IgnoreWheelComboBox()
        self.combo_event_order.setToolTip("Placement priority for new notes placed at the same time as existing notes")
        self.combo_event_order.setView(SmoothListView(self.combo_event_order))
        self.combo_event_order.addItems(["Before", "After"])
        self.combo_event_order.setCurrentText(event_default_order)
        self.combo_event_order.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        editor_layout.addWidget(self.combo_event_order)

        editor_layout.addWidget(QLabel("File Extension:"))
        self.combo_file_ext = IgnoreWheelComboBox()
        self.combo_file_ext.setToolTip("Format of beatmap file (.txt recommended)")
        self.combo_file_ext.setView(SmoothListView(self.combo_file_ext))
        self.combo_file_ext.addItems([".txt", ".osu"])
        self.combo_file_ext.setCurrentText(file_extension)
        self.combo_file_ext.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        editor_layout.addWidget(self.combo_file_ext)
        
        editor_layout.addWidget(QLabel("Background Image:"))

        resources_dir = os.path.join(game_root, "ChartEditorResources")
        bg_path = os.path.join(resources_dir, "bg.png")
        
        self.combo_bg = IgnoreWheelComboBox()
        self.combo_bg.setView(SmoothListView(self.combo_bg))
        
        bg_folder = os.path.join(resources_dir, "backgrounds")
        os.makedirs(bg_folder, exist_ok=True)
        
        bg_files = []
        if os.path.exists(bg_folder):
             for f in os.listdir(bg_folder):
                 if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                     bg_files.append(f)
        
        bg_files.sort()
        self.bg_map = {Path(f).stem: f for f in bg_files}
        self.bg_map["None"] = "None"
        
        self.combo_bg.addItems(["None"] + sorted([Path(f).stem for f in bg_files]))
        
        current_stem = "None"
        if current_background != "None":
             current_stem = Path(current_background).stem
        
        self.combo_bg.setCurrentText(current_stem)
        
        self.bg_drop_label = FileDropLabel("Drag image here to add background")
        
        def on_bg_change(idx):
             stem = self.combo_bg.currentText()
             if stem == "None":
                 if os.path.exists(bg_path):
                     try: os.remove(bg_path)
                     except: pass
                 ui_bg_path = os.path.join(self.game_root, "ChartEditorResources", "ui_bg.png")
                 if os.path.exists(ui_bg_path):
                     try: os.remove(ui_bg_path)
                     except: pass
                     
                 if hasattr(parent, 'timeline') and parent.timeline:
                    parent.timeline.load_background_image()
                    parent.timeline.update()
                 if hasattr(parent, 'load_ui_background_image'):
                    parent.load_ui_background_image()
                    parent.update()
                 return
             
             filename = self.bg_map.get(stem)
             if not filename: return

             src = os.path.join(bg_folder, filename)
             if os.path.exists(src):
                 try:
                     self.blur_worker.request_blur(src, bg_path, self.background_blur_slider.value())
                     ui_bg_path = os.path.join(self.game_root, "ChartEditorResources", "ui_bg.png")
                     self.blur_worker.request_blur(src, ui_bg_path, self.ui_bg_blur_slider.value())
                 except: pass

        self.combo_bg.activated.connect(on_bg_change)
        editor_layout.addWidget(self.combo_bg)
        editor_layout.addWidget(self.bg_drop_label)
        
        def handle_bg_drop(file_path):
            try:
                os.makedirs(bg_folder, exist_ok=True)
                
                fname = Path(file_path).name
                dst = os.path.join(bg_folder, fname)
                shutil.copy2(file_path, dst)
                
                stem = Path(dst).stem
                self.bg_map[stem] = fname

                curr_items = [self.combo_bg.itemText(i) for i in range(self.combo_bg.count())]
                if stem not in curr_items:
                     self.combo_bg.addItem(stem)
                
                self.combo_bg.setCurrentText(stem)
                on_bg_change(0)
                
                if hasattr(parent, 'play_ui_sound'):
                    parent.play_ui_sound('UI Place')
                    
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load image: {e}")
        
        self.bg_drop_label.fileDropped.connect(handle_bg_drop)
        self.bg_drop_label.fileDropped.connect(handle_bg_drop)
        

        
        grid_opacity_layout = QHBoxLayout()
        grid_opacity_layout.addWidget(QLabel("Grid Visibility:"))
        self.grid_opacity_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.grid_opacity_slider.setToolTip("Opacity of the grid snap lines")
        self.grid_opacity_slider.setRange(0, 100)
        self.grid_opacity_slider.setValue(grid_opacity)
        self.grid_opacity_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        grid_opacity_layout.addWidget(self.grid_opacity_slider)
        self.grid_opacity_label = QLabel(f"{grid_opacity}%")
        self.grid_opacity_label.setFixedWidth(50)
        grid_opacity_layout.addWidget(self.grid_opacity_label)
        
        visualizer_opacity_layout = QHBoxLayout()
        visualizer_opacity_layout.addWidget(QLabel("Visualizer Visibility:"))
        self.visualizer_opacity_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.visualizer_opacity_slider.setToolTip("Opacity of the audio visualiser in the background")
        self.visualizer_opacity_slider.setRange(0, 100)
        self.visualizer_opacity_slider.setValue(visualizer_opacity)
        self.visualizer_opacity_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        visualizer_opacity_layout.addWidget(self.visualizer_opacity_slider)
        self.visualizer_opacity_label = QLabel(f"{visualizer_opacity}%")
        self.visualizer_opacity_label.setFixedWidth(50)
        visualizer_opacity_layout.addWidget(self.visualizer_opacity_label)
        
        background_opacity_layout = QHBoxLayout()
        background_opacity_layout.addWidget(QLabel("Background Visibility:"))
        self.background_opacity_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.background_opacity_slider.setToolTip("Opacity of the background image.")
        self.background_opacity_slider.setRange(0, 100)
        self.background_opacity_slider.setValue(background_opacity)
        self.background_opacity_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        background_opacity_layout.addWidget(self.background_opacity_slider)
        self.background_opacity_label = QLabel(f"{background_opacity}%")
        self.background_opacity_label.setFixedWidth(50)
        background_opacity_layout.addWidget(self.background_opacity_label)
        
        preview_bg_layout = QHBoxLayout()
        preview_bg_layout.addWidget(QLabel("Preview Background Visibility:"))
        self.preview_bg_opacity_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.preview_bg_opacity_slider.setToolTip("The opacity of the play area preview background")
        self.preview_bg_opacity_slider.setRange(0, 100)
        self.preview_bg_opacity_slider.setValue(preview_bg_opacity)
        self.preview_bg_opacity_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        preview_bg_layout.addWidget(self.preview_bg_opacity_slider)
        self.preview_bg_opacity_label = QLabel(f"{preview_bg_opacity}%")
        self.preview_bg_opacity_label.setFixedWidth(50)
        preview_bg_layout.addWidget(self.preview_bg_opacity_label)

        ui_bg_opacity_layout = QHBoxLayout()
        ui_bg_opacity_layout.addWidget(QLabel("UI Background Visibility:"))
        self.ui_bg_opacity_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.ui_bg_opacity_slider.setToolTip("Brightness of background image in UI")
        self.ui_bg_opacity_slider.setRange(0, 100)
        self.ui_bg_opacity_slider.setValue(self.original_ui_bg_opacity)
        self.ui_bg_opacity_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ui_bg_opacity_layout.addWidget(self.ui_bg_opacity_slider)
        self.ui_bg_opacity_label = QLabel(f"{self.original_ui_bg_opacity}%")
        self.ui_bg_opacity_label.setFixedWidth(50)
        ui_bg_opacity_layout.addWidget(self.ui_bg_opacity_label)
        
        grid_thickness_layout = QHBoxLayout()
        grid_thickness_layout.addWidget(QLabel("Grid Thickness:"))
        self.grid_thickness_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.grid_thickness_slider.setToolTip("Thickness of the grid snap lines in pixels")
        self.grid_thickness_slider.setRange(1, 5)
        self.grid_thickness_slider.setValue(grid_thickness)
        self.grid_thickness_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        grid_thickness_layout.addWidget(self.grid_thickness_slider)
        self.grid_thickness_label = QLabel(f"{grid_thickness}px")
        self.grid_thickness_label.setFixedWidth(50)
        grid_thickness_layout.addWidget(self.grid_thickness_label)

        ui_brightness_layout = QHBoxLayout()
        ui_brightness_layout.addWidget(QLabel("UI Brightness:"))
        self.ui_brightness_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.ui_brightness_slider.setToolTip("Brightness of UI elements")
        self.ui_brightness_slider.setRange(0, 255)
        self.ui_brightness_slider.setValue(ui_brightness)
        self.ui_brightness_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ui_brightness_layout.addWidget(self.ui_brightness_slider)
        self.ui_brightness_label = QLabel(f"{ui_brightness}")
        self.ui_brightness_label.setFixedWidth(50)
        ui_brightness_layout.addWidget(self.ui_brightness_label)

        lane_opacity_layout = QHBoxLayout()
        lane_opacity_layout.addWidget(QLabel("Lane Opacity:"))
        self.lane_opacity_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.lane_opacity_slider.setToolTip("The opacity of the lanes that the notes are placed on (Changes how much the background shows though them)")
        self.lane_opacity_slider.setRange(0, 100)
        self.lane_opacity_slider.setValue(lane_opacity)
        self.lane_opacity_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lane_opacity_layout.addWidget(self.lane_opacity_slider)
        self.lane_opacity_label = QLabel(f"{lane_opacity}%")
        self.lane_opacity_label.setFixedWidth(50)
        lane_opacity_layout.addWidget(self.lane_opacity_label)

        background_blur_layout = QHBoxLayout()
        background_blur_layout.addWidget(QLabel("Background Blur:"))
        self.background_blur_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.background_blur_slider.setToolTip("How blurred the background image is")
        self.background_blur_slider.setRange(0, 50)
        self.background_blur_slider.setValue(background_blur)
        self.background_blur_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        background_blur_layout.addWidget(self.background_blur_slider)
        self.background_blur_label = QLabel(f"{background_blur}px")
        self.background_blur_label.setFixedWidth(50)
        background_blur_layout.addWidget(self.background_blur_label)

        ui_bg_blur_layout = QHBoxLayout()
        ui_bg_blur_layout.addWidget(QLabel("UI Background Blur:"))
        self.ui_bg_blur_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.ui_bg_blur_slider.setToolTip("Blur amount of background image in UI")
        self.ui_bg_blur_slider.setRange(0, 50)
        self.ui_bg_blur_slider.setValue(self.original_ui_bg_blur)
        self.ui_bg_blur_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ui_bg_blur_layout.addWidget(self.ui_bg_blur_slider)
        self.ui_bg_blur_label = QLabel(f"{self.original_ui_bg_blur}px")
        self.ui_bg_blur_label.setFixedWidth(50)
        ui_bg_blur_layout.addWidget(self.ui_bg_blur_label)
        
        def reset_visibility():
            needs_brightness_update = self.ui_brightness_slider.value() != 60
            self.grid_opacity_slider.setValue(50)
            self.visualizer_opacity_slider.setValue(10)
            self.background_opacity_slider.setValue(20)
            self.preview_bg_opacity_slider.setValue(30)
            self.grid_thickness_slider.setValue(2)
            self.ui_brightness_slider.setValue(60)
            self.lane_opacity_slider.setValue(100)
            self.background_blur_slider.setValue(0)
            self.ui_bg_opacity_slider.setValue(0)
            self.ui_bg_blur_slider.setValue(0)
            self.combo_drop_shadows.setCurrentText("None")
            if needs_brightness_update:
                _apply_brightness(60)
            if hasattr(parent, 'play_ui_sound'):
                parent.play_ui_sound('UI Click')
        
        ds_layout = QHBoxLayout()
        ds_layout.addWidget(QLabel("Drop Shadows:"))
        self.combo_drop_shadows = QComboBox()
        self.combo_drop_shadows.addItems(["None", "Specific", "All"])
        self.combo_drop_shadows.setCurrentText(getattr(parent, "drop_shadow_mode", "None"))
        self.combo_drop_shadows.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ds_layout.addWidget(self.combo_drop_shadows)
        def update_ds(v):
            if hasattr(parent, 'drop_shadow_mode'):
                parent.drop_shadow_mode = v
                schedule_shadow_update(parent)
        self.combo_drop_shadows.currentTextChanged.connect(update_ds)

        def add_cat(title):
            lbl = QLabel(title)
            lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet("font-weight: bold; margin-top: 5px; margin-bottom: 2px;")
            editor_layout.addWidget(lbl)

        add_cat("- Grid -")
        editor_layout.addLayout(grid_thickness_layout)
        editor_layout.addLayout(grid_opacity_layout)

        add_cat("- UI -")
        editor_layout.addLayout(ui_brightness_layout)
        editor_layout.addLayout(ui_bg_opacity_layout)
        editor_layout.addLayout(ui_bg_blur_layout)

        add_cat("- Timeline -")
        editor_layout.addLayout(visualizer_opacity_layout)
        editor_layout.addLayout(lane_opacity_layout)

        add_cat("- Background -")
        editor_layout.addLayout(background_opacity_layout)
        editor_layout.addLayout(preview_bg_layout)
        editor_layout.addLayout(background_blur_layout)

        editor_layout.addLayout(ds_layout)

        btn_reset_visibility = QPushButton("Reset Visibility")
        btn_reset_visibility.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_reset_visibility.clicked.connect(reset_visibility)
        editor_layout.addWidget(btn_reset_visibility)

        
        editor_group.setLayout(editor_layout)
        content_layout.addWidget(editor_group)
        
        def on_master_volume_changed(v):
            self.master_label.setText(f"{v}%")
            if hasattr(parent, 'set_master_volume_live'):
                parent.set_master_volume_live(v / 100.0)
        self.master_slider.valueChanged.connect(on_master_volume_changed)

        def on_music_volume_changed(v):
            self.music_label.setText(f"{v}%")
            if hasattr(parent, 'set_music_volume_live'):
                parent.set_music_volume_live(v / 100.0)
                
        self.music_slider.valueChanged.connect(on_music_volume_changed)

        def on_fx_volume_changed(v):
            self.fx_label.setText(f"{v}%")
            if hasattr(parent, 'set_fx_volume_live'):
                parent.set_fx_volume_live(v / 100.0)

        self.fx_slider.valueChanged.connect(on_fx_volume_changed)
        
        self.last_ui_vol_sound_time = 0
        def on_ui_volume_changed(v):
            self.ui_label.setText(f"{v}%")
            self.update_parent_ui_volume(parent, v)
            curr = time.time()
            if curr - self.last_ui_vol_sound_time > 0.05:
                if hasattr(parent, 'play_ui_sound_suppressed'):
                    parent.play_ui_sound_suppressed('UI Scroll')
                self.last_ui_vol_sound_time = curr
                
        self.ui_slider.valueChanged.connect(on_ui_volume_changed)
        
        def update_grid_opacity(v):
            self.grid_opacity_label.setText(f"{v}%")
            if hasattr(parent, 'grid_opacity'):
                parent.grid_opacity = v
                if hasattr(parent, 'timeline') and parent.timeline:
                    parent.timeline.update()
        
        def update_visualizer_opacity(v):
            self.visualizer_opacity_label.setText(f"{v}%")
            if hasattr(parent, 'visualizer_opacity'):
                parent.visualizer_opacity = v
                if hasattr(parent, 'timeline') and parent.timeline:
                    parent.timeline.update()
        
        def update_background_opacity(v):
            self.background_opacity_label.setText(f"{v}%")
            if hasattr(parent, 'background_opacity'):
                previous = parent.background_opacity
                parent.background_opacity = v
                if hasattr(parent, 'timeline') and parent.timeline:
                    if v <= 0:
                        parent.timeline.release_background_image()
                    elif previous <= 0 or not parent.timeline.bg_image_path:
                        parent.timeline.load_background_image()
                    parent.timeline.update()
        
        def update_grid_thickness(v):
            self.grid_thickness_label.setText(f"{v}px")
            if hasattr(parent, 'grid_thickness'):
                parent.grid_thickness = v
                if hasattr(parent, 'timeline') and parent.timeline:
                    parent.timeline.update()

        def _apply_brightness(v):
            if hasattr(parent, 'ui_brightness'):
                parent.ui_brightness = v
                QApplication.instance().setStyleSheet(get_scaled_stylesheet(BASE_APP_STYLESHEET, parent.global_scale, v))
                parent.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, parent.global_scale, v))
                self.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, parent.global_scale, v))
                if hasattr(parent, 'resources_window') and parent.resources_window:
                    parent.resources_window.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, parent.global_scale, v))
                if hasattr(parent, 'start_screen') and parent.start_screen:
                    parent.start_screen.update_theme()
                if hasattr(parent, 'update_ui_state'):
                    parent.update_ui_state()

        def update_ui_brightness(v):
            self.ui_brightness_label.setText(f"{v}")

        def apply_ui_brightness():
            v = self.ui_brightness_slider.value()
            if hasattr(self, '_brightness_timer'):
                self._brightness_timer.stop()
                self._brightness_timer.deleteLater()
            self._brightness_timer = QTimer()
            self._brightness_timer.setSingleShot(True)
            self._brightness_timer.timeout.connect(lambda: _apply_brightness(v))
            self._brightness_timer.start(50)
        
        def update_preview_bg_opacity(v):
            self.preview_bg_opacity_label.setText(f"{v}%")
            if hasattr(parent, 'preview_bg_opacity'):
                parent.preview_bg_opacity = v
                if hasattr(parent, 'timeline') and parent.timeline:
                    parent.timeline.update()
        self.preview_bg_opacity_slider.valueChanged.connect(update_preview_bg_opacity)

        def update_ui_bg_opacity(v):
            self.ui_bg_opacity_label.setText(f"{v}%")
            if hasattr(parent, 'ui_bg_opacity'):
                previous = parent.ui_bg_opacity
                parent.ui_bg_opacity = v
                if v <= 0:
                    parent.release_ui_background_image()
                elif previous <= 0 or not getattr(parent, 'ui_bg_source_path', None):
                    parent.load_ui_background_image()
                parent.update()
                if hasattr(parent, 'sidebar_vis') and parent.sidebar_vis:
                    parent.sidebar_vis._background_cache = None
                    parent.sidebar_vis._background_cache_signature = None
                    parent.sidebar_vis.update()
        self.ui_bg_opacity_slider.valueChanged.connect(update_ui_bg_opacity)
        self.visualizer_opacity_slider.valueChanged.connect(update_visualizer_opacity)
        self.background_opacity_slider.valueChanged.connect(update_background_opacity)
        self.preview_bg_opacity_slider.valueChanged.connect(update_preview_bg_opacity)
        self.grid_thickness_slider.valueChanged.connect(update_grid_thickness)
        self.ui_brightness_slider.valueChanged.connect(update_ui_brightness)
        self.ui_brightness_slider.sliderReleased.connect(apply_ui_brightness)
        self.grid_opacity_slider.valueChanged.connect(update_grid_opacity)

        def update_lane_opacity(v):
            self.lane_opacity_label.setText(f"{v}%")
            if hasattr(parent, 'lane_opacity'):
                parent.lane_opacity = v
                if hasattr(parent, 'timeline') and parent.timeline:
                    parent.timeline.update()
        self.lane_opacity_slider.valueChanged.connect(update_lane_opacity)

        def update_background_blur(v):
            self.background_blur_label.setText(f"{v}px")
            if hasattr(parent, 'background_blur'):
                parent.background_blur = v

                stem = self.combo_bg.currentText()
                if stem and stem != "None":
                    filename = self.bg_map.get(stem)
                    if filename:
                        bg_folder = os.path.join(self.game_root, "ChartEditorResources", "backgrounds")
                        src = os.path.join(bg_folder, filename)
                        bg_path = os.path.join(self.game_root, "ChartEditorResources", "bg.png")
                        if os.path.exists(src):
                            try:
                                self.blur_worker.request_blur(src, bg_path, v)
                            except Exception as e:
                                print(f"Error applying blur in slider: {e}")

        self.background_blur_slider.valueChanged.connect(update_background_blur)

        def update_ui_bg_blur(v):
            self.ui_bg_blur_label.setText(f"{v}px")
            if hasattr(parent, 'ui_bg_blur'):
                parent.ui_bg_blur = v
                stem = self.combo_bg.currentText()
                if stem and stem != "None":
                    filename = self.bg_map.get(stem)
                    if filename:
                        bg_folder = os.path.join(self.game_root, "ChartEditorResources", "backgrounds")
                        src = os.path.join(bg_folder, filename)
                        ui_bg_path = os.path.join(self.game_root, "ChartEditorResources", "ui_bg.png")
                        if os.path.exists(src):
                            try:
                                self.blur_worker.request_blur(src, ui_bg_path, v)
                            except: pass
        self.ui_bg_blur_slider.valueChanged.connect(update_ui_bg_blur)
        
        color_group = QGroupBox("Object Colors")
        color_group.setStyleSheet(self.get_group_style())
        color_layout = QVBoxLayout()
        color_layout.setContentsMargins(10, 5, 10, 10)

        accent_row = QHBoxLayout()
        accent_row.addWidget(QLabel("Accent Color"))
        curr_accent = getattr(parent, 'custom_accent_color', DEFAULT_ACCENT_COLOR)
        self.btn_accent = ColorPickerButton(curr_accent, default_val=DEFAULT_ACCENT_COLOR, live_preview=False, parent=self)
        self.btn_accent.colorChanged.connect(self.on_accent_color_changed)
        accent_row.addWidget(self.btn_accent)
        color_layout.addLayout(accent_row)

        self.color_combos = {}
        def update_colors_preview():
            if hasattr(parent, 'current_colors'):
                parent.current_colors = self.get_colors()
                if hasattr(parent, 'timeline') and parent.timeline:
                    parent.timeline.set_colors(parent.current_colors)

        ORDERED_COLOR_KEYS = [
            "normal_lane",
            "direction_left",
            "direction_right",
            "direction_left_event",
            "direction_right_event",
            "toggle_center",
            "note",
            "spike",
            "hold",
            "hold_line",
            "double",
            "double_line",
            "spam",
            "spam_line",
            "freestyle",
            "brawl_hold",
            "brawl_hold_line",
            "brawl_spam",
            "brawl_spam_line",
            "brawl_knockout",
            "fly_in_marker",
            "hide_marker"
        ]

        COLOR_LABEL_MAP = {
            "normal_lane": "Normal Lane",
            "direction_left": "Direction Left Lane",
            "direction_right": "Direction Right Lane",
            "direction_left_event": "Direction Left Event",
            "direction_right_event": "Direction Right Event",
            "toggle_center": "Toggle Center",
            "note": "Note",
            "spike": "Spike",
            "hold": "Hold",
            "hold_line": "Hold Line",
            "double": "Double",
            "double_line": "Double Line",
            "spam": "Spam",
            "spam_line": "Spam Line",
            "freestyle": "Freestyle",
            "brawl_hold": "Brawl Hold",
            "brawl_hold_line": "Brawl Hold Line",
            "brawl_spam": "Brawl Spam",
            "brawl_spam_line": "Brawl Spam Line",
            "brawl_knockout": "Brawl Knockout",
            "fly_in_marker": "Fly In Marker",
            "hide_marker": "Hide Marker"
        }
        for key in ORDERED_COLOR_KEYS:
            row = QHBoxLayout()
            label_text = COLOR_LABEL_MAP.get(key, key.replace("_", " ").title())
            row.addWidget(QLabel(label_text))
            
            default_val = DEFAULT_COLORS.get(key, "Cyan (Note)")
            current_val = self.current_colors.get(key, default_val)
            if current_val == "Slate Blue (Direction Left)": current_val = "Slate Blue (Direction Left Lane)"
            if current_val == "Signature Pink (Direction Right)": current_val = "Signature Pink (Direction Right Lane)"
            
            btn = ColorPickerButton(current_val, default_val=default_val, parent=self)
            btn.colorChanged.connect(update_colors_preview)
            if key == "direction_left":
                btn.setToolTip("Color of the left lanes/direction indicators (top and bottom during central gameplay)")
            elif key == "direction_right":
                btn.setToolTip("Color of the right lanes/direction indicators (middle two during central gameplay)")
            self.color_combos[key] = btn
            row.addWidget(btn)
            color_layout.addLayout(row)

        dynamic_combo_width = 264
        self.combo_drop_shadows.setMinimumWidth(dynamic_combo_width)
        self.combo_drop_shadows.setToolTip("Adds shadows to UI elements, Specific is the developers preferred shadows and All is any element that can have shadows")
        
        btn_reset = QPushButton("Reset Colors")
        btn_reset.setToolTip("Reset all colors to default")
        btn_reset.clicked.connect(self.reset_all_colors)
        color_layout.addWidget(btn_reset)
        
        color_group.setLayout(color_layout)
        content_layout.addWidget(color_group)

        sound_group = QGroupBox("Custom Sounds")
        sound_group.setStyleSheet(self.get_group_style())
        sound_layout = QVBoxLayout()
        sound_layout.setContentsMargins(10, 5, 10, 10)

        for name, filename in ORIGINAL_SOUND_FILES_MAP.items():
            w = SoundSettingWidget(name, filename, self.game_root)
            w.soundReset.connect(self.on_sound_reset)
            w.soundChanged.connect(self.on_sound_changed)
            sound_layout.addWidget(w)
            
        btn_reset_all_sounds = QPushButton("Reset All Sounds")
        btn_reset_all_sounds.clicked.connect(self.reset_all_sounds)
        sound_layout.addWidget(btn_reset_all_sounds)
            
        sound_group.setLayout(sound_layout)
        content_layout.addWidget(sound_group)

        keybinds_group = QGroupBox("Keybinds")
        keybinds_group.setStyleSheet(self.get_group_style())
        keybinds_layout = QVBoxLayout()
        keybinds_layout.setContentsMargins(10, 5, 10, 10)

        self.keybind_widgets = {}

        LABEL_MAP = {
            "play_pause": "Play / Pause",
            "jump_start": "Jump To Start",
            "jump_end": "Jump To End",
            "switch_meta_timing": "Metadata / Timing Tab",
            "toggle_metronome": "Toggle Metronome",
            "tab_note": "Note Tab",
            "tab_brawl": "Brawl Tab",
            "tab_event": "Event Tab",
            "faster_modifier": "Faster Scroll",
            "multiselect_modifier": "Multi-Select Modifier",
            "modify_note_modifier": "Modify Note Modifier",
            "range_select_modifier": "Range Select",
            "range_select_type_modifier": "Range Select Same Type"
        }

        KEYBIND_TOOLTIPS = {
            "play_pause": "Why are you looking at this tooltip? You know what this does.",
            "jump_start": "Moves the cursor to the start of the song",
            "jump_end": "Moves the cursor to the end of the song",
            "triplet_toggle": "Notes snap to triplets. This means that there will be 3 notes in the space of 2, only works with even grid values",
            "toggle_metronome": "Toggle Metronome on or off",
            "smooth_placement": "Holding allows for movement of notes off of snap guides",
            "range_select_modifier": "Click one note, then click another note on the same lane to select all notes between them",
            "range_select_type_modifier": "Click one note, then click another note of the same type on the same lane to select all matching notes between them",
            "switch_meta_timing": "Toggles which menu is visible on the left of the screen",
            "timeline_left": "Seek timeline left by one gridline",
            "timeline_right": "Seek timeline right by one gridline",
            "tab_note": "Switch to Notes menu",
            "tab_brawl": "Switch to Brawl notes menu",
            "tab_event": "Switch to Events menu",
            "multiselect_modifier": "Select multiple individual notes by holding this while clicking each note",
            "faster_modifier": "Hold this while scrolling on timeline to scroll faster",
            "modify_note_modifier": "Hold this and left click on a note to change it's modifier when applicable"
        }

        for k in ["play_pause", "jump_start", "jump_end", "switch_meta_timing", "timeline_left", "timeline_right", "smooth_placement", "triplet_toggle", "toggle_metronome", "tab_note", "tab_brawl", "tab_event"]:
            row = QHBoxLayout()
            label = LABEL_MAP.get(k, k.replace("_", " ").title())
            lbl_w = QLabel(label + ":")
            row.addWidget(lbl_w)
            edit = KeybindButton(self.current_keybinds.get(k, DEFAULT_KEYBINDS.get(k, "None")))
            edit.setMinimumWidth(dynamic_combo_width)
            if k in KEYBIND_TOOLTIPS:
                lbl_w.setToolTip(KEYBIND_TOOLTIPS[k])
                edit.setToolTip(KEYBIND_TOOLTIPS[k])
            self.keybind_widgets[k] = edit
            row.addWidget(edit)
            keybinds_layout.addLayout(row)

        for k in ["multiselect_modifier", "faster_modifier", "modify_note_modifier", "range_select_modifier", "range_select_type_modifier"]:
            row = QHBoxLayout()
            label = LABEL_MAP.get(k, k.replace("_", " ").title())
            lbl_w = QLabel(label + ":")
            row.addWidget(lbl_w)
            edit = KeybindButton(self.current_keybinds.get(k, DEFAULT_KEYBINDS.get(k, "None")))
            edit.setMinimumWidth(dynamic_combo_width)
            if k in KEYBIND_TOOLTIPS:
                lbl_w.setToolTip(KEYBIND_TOOLTIPS[k])
                edit.setToolTip(KEYBIND_TOOLTIPS[k])
            self.keybind_widgets[k] = edit
            row.addWidget(edit)
            keybinds_layout.addLayout(row)

        keybinds_layout.addSpacing(10)
        scroll_row = QHBoxLayout()
        lbl_invert = QLabel("Invert Scroll:")
        lbl_invert.setToolTip("Reverses direction of timeline scrolling (inverted=scrolling down moves right)")
        scroll_row.addWidget(lbl_invert)
        self.chk_invert_scroll = QCheckBox()
        self.chk_invert_scroll.setChecked(self.current_keybinds.get("invert_scroll", False))
        self.chk_invert_scroll.setToolTip("Reverses direction of timeline scrolling (inverted=scrolling down moves right)")
        scroll_row.addWidget(self.chk_invert_scroll)
        keybinds_layout.addLayout(scroll_row)
        keybinds_layout.addSpacing(10)

        btn_reset_keybinds = QPushButton("Reset Keybinds")
        btn_reset_keybinds.clicked.connect(self.reset_keybinds)
        keybinds_layout.addWidget(btn_reset_keybinds)
        
        keybinds_group.setLayout(keybinds_layout)
        content_layout.addWidget(keybinds_group)

        info_group = QGroupBox("Information")
        info_group.setStyleSheet(self.get_group_style())
        info_layout = QVBoxLayout()
        
        legal_btn = QPushButton("Legal Information")
        legal_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        legal_btn.clicked.connect(self.show_legal_info)
        info_layout.addWidget(legal_btn)
        
        info_group.setLayout(info_layout)
        content_layout.addWidget(info_group)

        tabs_area.setWidget(content_widget)
        main_layout.addWidget(tabs_area)
        
        self.set_double_click_reset(self.master_slider, 100, master_layout.itemAt(0).widget(), self.master_label)
        self.set_double_click_reset(self.music_slider, 100, music_layout.itemAt(0).widget(), self.music_label)
        self.set_double_click_reset(self.fx_slider, 100, fx_layout.itemAt(0).widget(), self.fx_label)
        self.set_double_click_reset(self.ui_slider, 100, ui_layout.itemAt(0).widget(), self.ui_label)
        self.set_double_click_reset(self.chk_mute_events, False)

        self.set_double_click_reset(self.slider_playback_pos, 150, playback_layout.itemAt(0).widget(), self.lbl_playback_pos)
        self.set_double_click_reset(self.scale_slider, 100, scale_layout.itemAt(0).widget(), self.lbl_scale)
        self.set_double_click_reset(self.chk_3d_sound, True)
        self.set_double_click_reset(self.chk_rpc, True)
        self.set_double_click_reset(self.chk_visualizer, True)
        self.set_double_click_reset(self.chk_beatflash, True)
        self.set_double_click_reset(self.chk_auto_save, False)
        self.set_double_click_reset(self.chk_backups, True)
        self.set_double_click_reset(self.chk_disable_hold_collisions, False)
        self.set_double_click_reset(self.chk_objects_follow_bpm_grid, True)

        self.set_double_click_reset(self.combo_event_order, "Before")
        self.set_double_click_reset(self.combo_file_ext, ".txt")
        self.set_double_click_reset(self.combo_bg, "None")

        self.set_double_click_reset(self.grid_thickness_slider, 2, grid_thickness_layout.itemAt(0).widget(), self.grid_thickness_label)
        self.set_double_click_reset(self.grid_opacity_slider, 50, grid_opacity_layout.itemAt(0).widget(), self.grid_opacity_label)
        self.set_double_click_reset(self.ui_brightness_slider, 60, ui_brightness_layout.itemAt(0).widget(), self.ui_brightness_label)
        self.set_double_click_reset(self.ui_bg_opacity_slider, 0, ui_bg_opacity_layout.itemAt(0).widget(), self.ui_bg_opacity_label)
        self.set_double_click_reset(self.ui_bg_blur_slider, 0, ui_bg_blur_layout.itemAt(0).widget(), self.ui_bg_blur_label)
        self.set_double_click_reset(self.visualizer_opacity_slider, 10, visualizer_opacity_layout.itemAt(0).widget(), self.visualizer_opacity_label)
        self.set_double_click_reset(self.background_opacity_slider, 20, background_opacity_layout.itemAt(0).widget(), self.background_opacity_label)
        self.set_double_click_reset(self.preview_bg_opacity_slider, 30, preview_bg_layout.itemAt(0).widget(), self.preview_bg_opacity_label)
        self.set_double_click_reset(self.lane_opacity_slider, 100, lane_opacity_layout.itemAt(0).widget(), self.lane_opacity_label)
        self.set_double_click_reset(self.background_blur_slider, 0, background_blur_layout.itemAt(0).widget(), self.background_blur_label)
        self.set_double_click_reset(self.combo_drop_shadows, "None")

        for k, btn in getattr(self, 'keybind_widgets', {}).items():
            self.set_double_click_reset(btn, DEFAULT_KEYBINDS.get(k, "None"))

        for k, combo in getattr(self, 'color_combos', {}).items():
            self.set_double_click_reset(combo, DEFAULT_COLORS.get(k, "Cyan (Note)"))

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
        
    def set_double_click_reset(self, widget, default_val, extra_widgets=None, value_label=None):
        if not widget: return
        class ResetFilter(QObject):
            def __init__(self, target_widget, default, parent_dialog):
                super().__init__(target_widget)
                self.target_widget = target_widget
                self.default = default
                self.parent_dialog = parent_dialog

            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.MouseButtonDblClick:
                    if isinstance(self.target_widget, QSlider):
                        self.target_widget.setValue(int(self.default))
                    elif isinstance(self.target_widget, QComboBox):
                        idx = self.target_widget.findText(str(self.default))
                        if idx >= 0:
                            self.target_widget.setCurrentIndex(idx)
                            try: self.target_widget.activated.emit(idx)
                            except: pass
                            try: self.target_widget.currentTextChanged.emit(str(self.default))
                            except: pass
                        else:
                            self.target_widget.setCurrentText(str(self.default))
                            try: self.target_widget.currentTextChanged.emit(str(self.default))
                            except: pass
                    elif isinstance(self.target_widget, QCheckBox):
                        self.target_widget.setChecked(bool(self.default))
                    elif isinstance(self.target_widget, ColorPickerButton):
                        self.target_widget.set_color(str(self.default))
                    elif hasattr(self.target_widget, 'set_key'):
                        self.target_widget.set_key(str(self.default))
                    
                    if hasattr(self.parent_dialog, 'parent_window') and hasattr(self.parent_dialog.parent_window, 'play_ui_sound'):
                        self.parent_dialog.parent_window.play_ui_sound('UI Click')
                    return True
                return super().eventFilter(obj, event)

        filt = ResetFilter(widget, default_val, self)
        widgets_to_install = [widget]
        if extra_widgets:
            if isinstance(extra_widgets, list):
                widgets_to_install.extend([w for w in extra_widgets if w])
            elif extra_widgets:
                widgets_to_install.append(extra_widgets)
        for w in widgets_to_install:
            w.installEventFilter(filt)
            if not hasattr(w, '_reset_filters'):
                w._reset_filters = []
            w._reset_filters.append(filt)

        if value_label:
            class ValueLabelFilter(QObject):
                def __init__(self, slider_widget, parent_dialog):
                    super().__init__(slider_widget)
                    self.slider = slider_widget
                    self.parent_dialog = parent_dialog

                def eventFilter(self, obj, event):
                    if event.type() == QEvent.Type.MouseButtonDblClick:
                        curr_val = self.slider.value()
                        min_val = self.slider.minimum()
                        max_val = self.slider.maximum()
                        step = self.slider.singleStep()
                        if step > 1:
                            min_val = (min_val // step) * step
                            max_val = (max_val // step) * step

                        d = QDialog(self.parent_dialog)
                        d.setWindowTitle("Enter Value")
                        if hasattr(self.parent_dialog, 'styleSheet'):
                            d.setStyleSheet(self.parent_dialog.styleSheet())

                        layout = QVBoxLayout(d)
                        layout.setContentsMargins(15, 15, 15, 15)
                        layout.setSpacing(12)

                        lbl = QLabel(f"Enter value ({min_val} - {max_val}):")
                        layout.addWidget(lbl)

                        edit = QLineEdit(str(curr_val))
                        edit.selectAll()
                        layout.addWidget(edit)

                        btn_layout = QHBoxLayout()
                        btn_layout.setSpacing(10)
                        ok_btn = QPushButton("OK")
                        ok_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                        cancel_btn = QPushButton("Cancel")
                        cancel_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

                        ok_btn.clicked.connect(d.accept)
                        cancel_btn.clicked.connect(d.reject)
                        edit.returnPressed.connect(d.accept)

                        btn_layout.addWidget(ok_btn)
                        btn_layout.addWidget(cancel_btn)
                        layout.addLayout(btn_layout)

                        d.setMinimumWidth(320)

                        if d.exec() == QDialog.DialogCode.Accepted:
                            text = edit.text().strip()
                            clean_text = re.sub(r'[^\d\-]', '', text)
                            try:
                                val = int(clean_text)
                                val = max(min_val, min(max_val, val))
                                self.slider.setValue(val)
                                if hasattr(self.parent_dialog, 'parent_window') and hasattr(self.parent_dialog.parent_window, 'play_ui_sound'):
                                    self.parent_dialog.parent_window.play_ui_sound('UI Click')
                            except ValueError:
                                pass
                        return True
                    return super().eventFilter(obj, event)

            v_filt = ValueLabelFilter(widget, self)
            value_label.installEventFilter(v_filt)
            if not hasattr(value_label, '_reset_filters'):
                value_label._reset_filters = []
            value_label._reset_filters.append(v_filt)

    def show_legal_info(self):
        d = QDialog(self)
        d.setWindowTitle("Legal Information")
        layout = QVBoxLayout()
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        
        preview_text = " -PREVIEW-" if PREVIEW_VERSION else ""
        text = f"CBM Editor {VERSION_NUMBER}{preview_text} made with \u2764 by Splash!\n\n"
        text += "This project is an unofficial, free, open-source level editor for the amazing videogame UNBEATABLE and is not affiliated with or endorsed by D-CELL GAMES.\n"
        text += "Certain visual and audio materials used in this project, including backgrounds and sound effects, originate from UNBEATABLE and remain the property of their respective owners.\n"
        text += "If D-CELL GAMES has any concerns regarding this project or its contents, I am willing to remove or modify the relevant material upon request.\n"
        text += "Audio playback and conversion use BASS by Un4seen Developments. The included BASSenc_MP3 encoder is LGPL-licensed; source: https://www.un4seen.com/files/bassenc_mp3-source.zip\n"
        text += "Contact: Discord @splash029"
        
        lbl = QLabel(text)
        lbl.setFixedWidth(450)
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        
        ok_btn = QPushButton("OK")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ok_btn.clicked.connect(d.accept)
        layout.addWidget(ok_btn)
        
        d.setLayout(layout)
        d.exec()
        
    def get_file_extension(self):
        return self.combo_file_ext.currentText()
        
    def reset_all_sounds(self):
        for name, filename in ORIGINAL_SOUND_FILES_MAP.items():
            self.on_sound_reset(filename)

    def on_sound_reset(self, filename):
        self.sounds_changed = True
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
        self.sounds_changed = True
        target = self.game_root / "ChartEditorResources" / filename
        temp_target = target.with_suffix(".tmp.wav")
        try:
            get_audio_engine().convert_audio(
                new_path,
                temp_target,
                output_format="wav",
                target_sample_rate=44100,
                target_channels=2,
            )
            os.replace(temp_target, target)
        except Exception as e:
            try:
                temp_target.unlink(missing_ok=True)
            except OSError:
                pass
            QMessageBox.critical(self, "Error", f"Could not convert sound: {e}")

    
    def update_parent_ui_volume(self, parent, value):
        if hasattr(parent, 'ui_volume') and hasattr(parent, 'sounds'):
            parent.ui_volume = value / 100.0
            eff_vol = parent.get_effective_ui_volume() if hasattr(parent, 'get_effective_ui_volume') else parent.ui_volume
            for name, sound in parent.sounds.items():
                if name.startswith("UI"):
                    sound.set_volume(eff_vol)
    
    def get_volumes(self):
        return self.master_slider.value() / 100.0, self.music_slider.value() / 100.0, self.fx_slider.value() / 100.0, self.ui_slider.value() / 100.0
    
    def on_accent_color_changed(self, new_hex):
        curr_accent = ACCENT_COLOR
        new_accent = apply_accent_color(new_hex)
        main_ed = self.parent()
        if hasattr(main_ed, 'custom_accent_color'):
            main_ed.custom_accent_color = new_accent
        if hasattr(main_ed, 'save_game_config'):
            main_ed.save_game_config()
        
        if curr_accent == new_accent:
            return

        scale = getattr(main_ed, 'global_scale', 1.0)
        bright = getattr(main_ed, 'ui_brightness', 60)
        
        app_inst = QApplication.instance()
        if app_inst:
            app_inst.setStyleSheet(get_scaled_stylesheet(BASE_APP_STYLESHEET, scale, bright))

        if hasattr(main_ed, 'setStyleSheet'):
            main_ed.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, scale, bright))
        if hasattr(main_ed, 'update_ui_group_styles'):
            main_ed.update_ui_group_styles()
        if hasattr(main_ed, 'start_screen') and main_ed.start_screen:
            main_ed.start_screen.update_theme()
        if hasattr(main_ed, 'timeline') and main_ed.timeline:
            main_ed.timeline.update_color_objects()
            main_ed.timeline.update()

        self.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, scale, bright))
        if hasattr(self, 'btn_accent'):
            self.btn_accent.update_appearance()
        if hasattr(self, 'color_combos'):
            for btn in self.color_combos.values():
                btn.update_appearance()
        for btn in self.findChildren(ColorPickerButton):
            btn.update_appearance()

    def reset_all_colors(self):
        if hasattr(self, 'btn_accent'):
            curr_accent_hex = self.btn_accent.get_hex()
            target_default_hex = QColor(DEFAULT_ACCENT_COLOR).name().upper()
            if curr_accent_hex != target_default_hex:
                self.btn_accent.set_color(DEFAULT_ACCENT_COLOR)
                self.on_accent_color_changed(DEFAULT_ACCENT_COLOR)
        for key, btn in self.color_combos.items():
            default = DEFAULT_COLORS.get(key, "Cyan (Note)")
            btn.set_color(default)
    
    
    def get_colors(self):
        new_colors = {}
        for key, btn in self.color_combos.items():
            new_colors[key] = btn.get_color()
        return new_colors

    def get_keybinds(self):
        kb = {}
        for k, widget in self.keybind_widgets.items():
            kb[k] = widget.key_str
        kb["invert_scroll"] = self.chk_invert_scroll.isChecked()
        return kb

    def reset_keybinds(self):
        for k, widget in self.keybind_widgets.items():
            widget.set_key(DEFAULT_KEYBINDS[k])
        self.chk_invert_scroll.setChecked(DEFAULT_KEYBINDS.get("invert_scroll", False))
    
    def get_background(self):
        txt = self.combo_bg.currentText()
        if txt == "None": return "None"
        return self.bg_map.get(txt, "None")

    def get_auto_save(self):
        return self.chk_auto_save.isChecked()

    def get_backups(self):
        return self.chk_backups.isChecked()
        
    def get_disable_tooltips(self):
        return self.chk_disable_tooltips.isChecked()
        
    def get_disable_hold_collisions(self):
        return self.chk_disable_hold_collisions.isChecked()

    def get_objects_follow_bpm_grid(self):
        return self.chk_objects_follow_bpm_grid.isChecked()
        
    def get_event_default_order(self):
        return self.combo_event_order.currentText()

    def get_ui_brightness(self):
        return self.ui_brightness_slider.value()

    def get_scale(self):
        return self.scale_slider.value() / 100.0
    
    def get_grid_opacity(self):
        return self.grid_opacity_slider.value()
    
    def get_visualizer_opacity(self):
        return self.visualizer_opacity_slider.value()
    
    def get_background_opacity(self):
        return self.background_opacity_slider.value()
    
    def get_grid_thickness(self):
        return self.grid_thickness_slider.value()
    
    def get_preview_bg_opacity(self):
        return self.preview_bg_opacity_slider.value()

    def get_lane_opacity(self):
        return self.lane_opacity_slider.value()

    def get_background_blur(self):
        return self.background_blur_slider.value()

    def release_preview_sounds(self):
        for widget in self.findChildren(SoundSettingWidget):
            if widget.preview_sound:
                widget.preview_sound.free()
                widget.preview_sound = None

    def closeEvent(self, e):
        if hasattr(self, 'blur_worker'):
            self.blur_worker.stop()
        self.release_preview_sounds()
        super().closeEvent(e)

    def accept(self):
        if hasattr(self, 'blur_worker'):
            self.blur_worker.stop()
        self.release_preview_sounds()
        super().accept()

    def reject(self):
        if hasattr(self.parent(), 'current_colors'):
            self.parent().current_colors = self.original_colors
            if hasattr(self.parent(), 'timeline') and self.parent().timeline:
                self.parent().timeline.set_colors(self.original_colors)
                

            
        resources_dir = os.path.join(self.game_root, "ChartEditorResources")
        bg_path = os.path.join(resources_dir, "bg.png")
        bg_folder = os.path.join(resources_dir, "backgrounds")
        
        if hasattr(self, 'blur_worker'):
            self.blur_worker.stop()
        self.release_preview_sounds()
            
        if self.original_background == "None":
            if os.path.exists(bg_path):
                try:
                    os.remove(bg_path)
                except:
                    pass
            ui_bg_path = os.path.join(resources_dir, "ui_bg.png")
            if os.path.exists(ui_bg_path):
                try:
                    os.remove(ui_bg_path)
                except:
                    pass
        else:
            orig_stem = Path(self.original_background).stem
            filename = self.bg_map.get(orig_stem)
            if filename:
                src = os.path.join(bg_folder, filename)
                if os.path.exists(src):
                    try:
                        apply_bg_image_with_blur(src, bg_path, self.original_bg_blur)
                        ui_bg_path = os.path.join(resources_dir, "ui_bg.png")
                        apply_bg_image_with_blur(src, ui_bg_path, self.original_ui_bg_blur)
                    except:
                        pass
        
        if hasattr(self.parent_window, 'timeline') and self.parent_window.timeline:
            self.parent_window.timeline.load_background_image()
            self.parent_window.timeline.update()

        if hasattr(self.parent(), 'ui_bg_opacity'):
            self.parent().ui_bg_opacity = self.original_ui_bg_opacity
            self.parent().ui_bg_blur = self.original_ui_bg_blur
            if hasattr(self.parent(), 'load_ui_background_image'): self.parent().load_ui_background_image()
            self.parent().update()
        
        super().reject()

class CopyDifficultyDialog(QDialog):
    def showEvent(self, event):
        apply_shadows_to_container(self)
        if hasattr(super(), "showEvent"): super().showEvent(event)

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
        copy_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        copy_btn.setMinimumWidth(120)
        copy_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cancel_btn.setMinimumWidth(120)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(copy_btn, 1)
        button_layout.addWidget(cancel_btn, 1)
        layout.addLayout(button_layout)

    def get_selected_diff(self):
        return self.combo.currentText()

class NewLevelDialog(QDialog):
    def showEvent(self, event):
        apply_shadows_to_container(self)
        if hasattr(super(), "showEvent"): super().showEvent(event)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Level")
        self.setFixedSize(300, 130)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.MSWindowsFixedSizeDialogHint)


        layout = QVBoxLayout(self)

        lbl = QLabel("What Should We Call Your Level?")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet('font-family: "Segoe UI", "Arial", sans-serif; font-size: 14px; font-weight: bold;')
        layout.addWidget(lbl)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Enter Level Name")
        layout.addWidget(self.input_field)

        layout.addSpacing(10)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ok_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(ok_btn, 1)
        btn_layout.addWidget(cancel_btn, 1)
        layout.addLayout(btn_layout)

    def get_text(self):
        return self.input_field.text()

class DeleteConfirmationDialog(QDialog):
    def showEvent(self, event):
        apply_shadows_to_container(self)
        if hasattr(super(), "showEvent"): super().showEvent(event)

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
        
        brightness = parent.ui_brightness if hasattr(parent, 'ui_brightness') else 0.0
        warn_color = "#333333" if brightness > 0.5 else "#AAAAAA"
        lbl_warn.setStyleSheet(f"font-size: 11px; color: {warn_color};")
        
        layout.addWidget(lbl_warn)
        
        btn_layout = QHBoxLayout()
        yes_btn = QPushButton("Yes, Delete")
        yes_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        yes_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        yes_btn.setStyleSheet("""
            QPushButton {
                background-color: #b5505a;
                font-weight: bold;
                color: white;
                border-bottom: 3px solid #8f3f47;
            }
            QPushButton:hover {
                background-color: #ca6570;
                border-bottom-color: #8f3f47;
            }
            QPushButton:pressed {
                background-color: #8f3f47;
                border-bottom: 0px solid transparent;
                border-top: 3px solid transparent;
                padding-top: 9px;
                margin-bottom: 0px;
            }
        """)
        yes_btn.clicked.connect(self.accept)
        
        no_btn = QPushButton("Cancel")
        no_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        no_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        no_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(yes_btn, 1)
        btn_layout.addWidget(no_btn, 1)
        layout.addLayout(btn_layout)


class BPMMatchDialog(QDialog):
    def showEvent(self, event):
        apply_shadows_to_container(self)
        if hasattr(super(), "showEvent"): super().showEvent(event)

    def __init__(self, parent, audio_path, start_pos_ms=0):
        super().__init__(parent)
        self.setWindowTitle("BPM Matcher")
        self.setFixedSize(300, 200)
        self.setModal(True)
        self.audio_path = audio_path
        self.start_pos_ms = start_pos_ms
        self.click_times = []
        self.calculated_bpm = 0
        self.is_running = False
        self.music_stream = None


        layout = QVBoxLayout(self)
        
        self.lbl_bpm = QLabel("Calculated BPM: --")
        self.lbl_bpm.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_bpm.setStyleSheet("font-size: 18px; font-weight: bold;")
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
        self.btn_tap.setStyleSheet("font-size: 14px;")
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
            self.stop_audio()
            self.music_stream = get_audio_engine().load_stream(self.audio_path)
            self.music_stream.play_from_ms(self.start_pos_ms)
            self.is_running = True
            self.btn_start.setEnabled(False)
            self.btn_tap.setEnabled(True)
            self.btn_tap.setStyleSheet("font-size: 14px; font-weight: bold;")
            self.btn_tap.setFocus()
            self.click_times = []
        except Exception as e:
            print(str(e))

    def stop_audio(self):
        if self.music_stream:
            self.music_stream.stop()
            self.music_stream.free()
            self.music_stream = None
        self.is_running = False

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
        self.stop_audio()
        super().closeEvent(event)
    
    def reject(self):
        self.stop_audio()
        super().reject()

    def accept(self):
        self.stop_audio()
        super().accept()

class AudioConversionWorker(QThread):
    progress_changed = pyqtSignal(int)
    conversion_ready = pyqtSignal(str, object)
    conversion_failed = pyqtSignal(str)

    def __init__(
        self,
        source_path,
        output_path,
        output_format="mp3",
        leading_silence_ms=0,
        trim_start_ms=0,
        target_sample_rate=None,
        target_channels=None,
        parent=None,
    ):
        super().__init__(parent)
        self.source_path = str(source_path)
        self.output_path = str(output_path)
        self.output_format = str(output_format)
        self.leading_silence_ms = float(leading_silence_ms)
        self.trim_start_ms = float(trim_start_ms)
        self.target_sample_rate = target_sample_rate
        self.target_channels = target_channels

    def run(self):
        try:
            result = get_audio_engine().convert_audio(
                self.source_path,
                self.output_path,
                output_format=self.output_format,
                progress_callback=self.progress_changed.emit,
                cancel_callback=self.isInterruptionRequested,
                leading_silence_ms=self.leading_silence_ms,
                trim_start_ms=self.trim_start_ms,
                target_sample_rate=self.target_sample_rate,
                target_channels=self.target_channels,
            )
            if not self.isInterruptionRequested():
                self.conversion_ready.emit(self.output_path, result)
        except InterruptedError:
            pass
        except Exception as e:
            self.conversion_failed.emit(str(e))


class AudioConversionProgressDialog(QDialog):
    def __init__(self, title, progress_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.progress_text = progress_text
        self.setModal(True)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowCloseButtonHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        layout = QVBoxLayout(self)
        self.label = QLabel(f"{self.progress_text} 0%")
        self.label.setMinimumWidth(380)
        layout.addWidget(self.label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.setFixedSize(self.sizeHint())

    def set_progress(self, value):
        value = max(0, min(100, int(value)))
        self.progress.setValue(value)
        self.label.setText(f"{self.progress_text} {value}%")

class AudioAnalysisWorker(QThread):
    analysis_started = pyqtSignal(str, float, int, float, object)
    analysis_progress = pyqtSignal(str, float, int)
    analysis_ready = pyqtSignal(str, float, object)

    def __init__(self, source_path, waveform_resolution_ms, parent=None):
        super().__init__(parent)
        self.source_path = str(source_path)
        self.waveform_resolution_ms = float(waveform_resolution_ms)

    def run(self):
        stream = None
        try:
            source_mtime = os.path.getmtime(self.source_path)
            stream = get_audio_engine().load_decode_stream(self.source_path)
            frames_per_point = max(1, int(round(stream.sample_rate * self.waveform_resolution_ms / 1000.0)))
            waveform_ratio = frames_per_point * 1000.0 / stream.sample_rate
            total_points = max(1, int(math.ceil(stream.get_length_ms() / waveform_ratio)))
            waveform = np.zeros(total_points, dtype=np.float32)
            self.analysis_started.emit(self.source_path, source_mtime, total_points, waveform_ratio, waveform)
            pending = np.empty(0, dtype=np.float32)
            emitted_points = 0
            last_emission = 0.0

            while not self.isInterruptionRequested():
                buffer, sample_count = stream.read_float_frames(262144)
                if sample_count <= 0:
                    break
                samples = np.ctypeslib.as_array(buffer)[:sample_count]
                frame_count = sample_count // stream.channels
                if frame_count <= 0:
                    continue
                frames = samples[:frame_count * stream.channels].reshape(frame_count, stream.channels)
                amplitudes = np.mean(frames, axis=1, dtype=np.float32)
                np.abs(amplitudes, out=amplitudes)
                if pending.size:
                    amplitudes = np.concatenate((pending, amplitudes))
                point_count = amplitudes.size // frames_per_point
                if point_count:
                    used = point_count * frames_per_point
                    peaks = amplitudes[:used].reshape(point_count, frames_per_point).max(axis=1)
                    write_count = min(int(peaks.size), total_points - emitted_points)
                    if write_count > 0:
                        waveform[emitted_points:emitted_points + write_count] = peaks[:write_count]
                        emitted_points += write_count
                    pending = amplitudes[used:].copy()
                    now = time.perf_counter()
                    if emitted_points == 0 or now - last_emission >= 0.04:
                        self.analysis_progress.emit(self.source_path, source_mtime, emitted_points)
                        last_emission = now
                else:
                    pending = amplitudes.copy()

            if self.isInterruptionRequested():
                return
            if pending.size:
                if emitted_points < total_points:
                    waveform[emitted_points] = float(np.max(pending))
                    emitted_points += 1
            self.analysis_progress.emit(self.source_path, source_mtime, emitted_points)
            self.analysis_ready.emit(
                self.source_path,
                source_mtime,
                {
                    'waveform_ratio': waveform_ratio,
                    'waveform_length': emitted_points,
                    'duration': stream.get_length_ms() / 1000.0,
                }
            )
        except Exception:
            pass
        finally:
            if stream:
                stream.free()

class BeatmapSaveWorker(QThread):
    save_finished = pyqtSignal(object, int, bool, str, str)

    def __init__(self, chart, revision, folder, extension, snapshot, save_lock, backup_enabled, parent=None):
        super().__init__(parent)
        self.chart = chart
        self.revision = revision
        self.folder = Path(folder)
        self.extension = extension
        self.snapshot = snapshot
        self.save_lock = save_lock
        self.backup_enabled = bool(backup_enabled)

    def run(self):
        success = False
        filename = ""
        self.save_lock.acquire()
        try:
            beatmap = BeatmapData(self.snapshot['difficulty_key'])
            beatmap.metadata = BeatmapMetadata(**self.snapshot['metadata'])
            beatmap.hit_objects = [
                HitObject(
                    obj[0],
                    obj[1],
                    obj[2],
                    obj[3],
                    obj[4],
                    obj[5],
                    obj[6],
                    obj[7],
                    obj[8],
                    obj[9],
                    obj[10],
                    uid=obj[11]
                )
                for obj in self.snapshot['hit_objects']
            ]
            beatmap.timing_points = [
                {'time': tp[0], 'bpm': tp[1]}
                for tp in self.snapshot['timing_points']
            ]
            beatmap.filename = self.snapshot['filename']
            beatmap.editor_zoom = self.snapshot['editor_zoom']
            beatmap.created = True
            beatmap.unsaved = True
            success = beatmap.save(self.folder, self.extension)
            filename = beatmap.filename or ""
            if success and self.backup_enabled:
                create_beatmap_backup(self.folder, beatmap.difficulty_key, filename)
        except Exception:
            success = False
        finally:
            self.save_lock.release()
        self.save_finished.emit(self.chart, self.revision, success, filename, str(self.folder))

