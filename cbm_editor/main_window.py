from .services import *
from .windows_install import *
import random

register_shared_globals(globals())

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._is_initialized = False
        self.pressed_keys = set()
        QApplication.instance().applicationStateChanged.connect(self.on_application_state_changed)
        self.last_slider_val = {}
        self.last_hotkey_time = {}
        self.last_global_slider_sound_time = 0
        self.global_scale = 1.0
        self.update_window_title()
        self.resize(1460, 878)
        
        self.audio_engine = get_audio_engine()
        self.sounds = {}
        self.toast_enter_sound_variants = []
        self.toast_exit_sound_variants = []
        self.project_cover_enter_sound_variants = []
        self.metronome_sound = None
        self.master_volume = 1.0
        self.music_volume = 1.0
        self.fx_volume = 1.0
        self.ui_volume = 1.0
        self.playback_speed = 1.0
        self.current_background = "None"
        self.current_colors = DEFAULT_COLORS.copy()
        
        self.current_playback_channel = None
        self.event_default_order = "Before"
        self.enable_3d_sound = True
        self.enable_visualizer = True
        self.enable_beatflash = True
        self.auto_save = False
        self.enable_backups = True
        self.disable_hold_collisions = False
        self.objects_follow_bpm_grid = True
        self.update_channel = "Preview" if PREVIEW_VERSION else "Stable"
        self.video_preview_enabled = True
        self.custom_notes_enabled = True
        self.custom_notes = []
        self.custom_note_tombstones = []
        self.enable_rpc = True
        self.file_extension_setting = ".txt"
        self.project_view_mode = "Cover View"
        
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self.do_auto_save)
        self.auto_save_timer.start(10000)

        self.config_save_timer = QTimer(self)
        self.config_save_timer.setSingleShot(True)
        self.config_save_timer.setInterval(300)
        self.config_save_timer.timeout.connect(self.save_game_config)
        
        self.project_folder: Optional[Path] = None
        self.beatmaps: Dict[str, BeatmapData] = {}
        self.current_chart: Optional[BeatmapData] = None
        self.game_custom_maps_path: Optional[Path] = None
        self.game_root_path: Optional[Path] = None
        
        self.is_playing = False
        self.next_note_index = 0
        self.last_scrollbar_update = 0.0
        self.last_visualizer_submit = 0.0
        self.last_visualizer_level_update = time.perf_counter()
        
        self.audio_start_ms = 0.0
        self.system_start_tick = 0
        self._audio_waiting_for_zero = False
        self.last_played_notes = set()
        self.active_tails = []
        
        self.recent_projects = []
        
        self.metronome_active = False
        self.last_metronome_beat = -1
        
        self.visualizer_level = 0.0
        self.audio_analysis_worker = None
        self.audio_analysis_workers = []
        self._audio_analysis_key = None
        self._audio_analysis_completed_key = None
        self.audio_import_worker = None
        self.audio_import_dialog = None
        self.audio_import_context = None
        self.video_job_worker = None
        self.video_progress_dialog = None
        self.video_configuration_window = None
        self.auto_save_worker = None
        self.save_io_lock = threading.Lock()
        
        self.settings_geometry = None
        
        self.setup_ui()
        self.save_toast = SaveToast(self)
        self.video_controller = VideoPreviewController(self)
        self.start_screen.setVisible(True)
        self.ensure_game_path() 
        self.start_screen.load_projects()
        self.update_ui_state()
        
        self.current_audio_filename = None
        self._current_audio_path = None
        
        self.rpc_timer = QTimer()

        self.rpc_timer.setInterval(15000)
        self.rpc_timer.timeout.connect(self.update_discord_presence)
        if self.enable_rpc:
            self.rpc_timer.start()
        
        
        self.app_start_time = time.time()
        self.rpc = None
        self.rpc_worker = None

        self.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, self.global_scale, self.ui_brightness))
        self._update_checks_disabled_for_session = False
        self._manual_update_check_available_at = 0.0
        self._update_last_checked_at = 0.0
        self.update_check_timer = QTimer(self)
        self.update_check_timer.setInterval(10 * 60 * 1000)
        self.update_check_timer.timeout.connect(self.check_updates)
        self.update_check_timer.start()
        self.check_updates()
        
        self.vis_worker = None
        self.update_visualizer_worker_state()
        
        QTimer.singleShot(100, self.init_discord_rpc)
        self._is_initialized = True

    def resizeEvent(self, event):
        if getattr(self, '_is_initialized', False):
            self.config_save_timer.start()
        if hasattr(self, 'sidebar_vis'):
            self.sidebar_vis.set_visible_based_on_height(self.height())
        super().resizeEvent(event)

    def clear_pressed_input_state(self):
        self.pressed_keys.clear()
        if hasattr(self, 'undo_redo_timer') and self.undo_redo_timer.isActive():
            self.undo_redo_timer.stop()
        timeline = getattr(self, 'timeline', None)
        if timeline:
            timeline.pressed_keys.clear()
            timeline.range_select_anchor = None
            timeline.is_g_pressed = False
            timeline.edge_scroll_speed = 0
            timeline.edge_scroll_timer.stop()

    def on_application_state_changed(self, state):
        if state != Qt.ApplicationState.ApplicationActive:
            self.clear_pressed_input_state()
    
    def confirm_unsaved_changes(self, method="close"):
        has_unsaved = False
        for bm in self.beatmaps.values():
            if bm.created and bm.unsaved:
                has_unsaved = True
                break
        
        if not has_unsaved: return True
        
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Unsaved Changes")

        if method == "load":
            msg.setText("Load project without saving?")
            msg.setInformativeText("Do you want to save current changes before loading?")
            btn_save = QPushButton("Save All && Load")
            btn_discard = QPushButton("Load Without Saving")
        elif method == "update":
            msg.setText("You have unsaved changes.")
            msg.setInformativeText("Do you want to save before updating?")
            btn_save = QPushButton("Save")
            btn_discard = QPushButton("Don't Save")
            msg.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        else:
            msg.setText("You have unsaved changes.")
            msg.setInformativeText("Do you want to save before closing?")
            btn_save = QPushButton("Save All && Close")
            btn_discard = QPushButton("Close Without Saving")

        msg.addButton(btn_save, QMessageBox.ButtonRole.AcceptRole)
        msg.addButton(btn_discard, QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = None
        if method != "update":
            btn_cancel = QPushButton("Cancel")
            msg.addButton(btn_cancel, QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_save)
        apply_shadows_to_container(msg)
        msg.exec()
        clicked = msg.clickedButton()

        if btn_cancel is not None and clicked == btn_cancel:
            return False
        if clicked == btn_save:
            for diff_key, bm in self.beatmaps.items():
                if bm.created and bm.unsaved:
                    old_chart = self.current_chart
                    self.current_chart = bm
                    self.save_current()
                    self.current_chart = old_chart
            return True
        return True

    def closeEvent(self, event):
        if not getattr(self, "_update_shutdown_approved", False) and not self.confirm_unsaved_changes("close"):
            event.ignore()
            return

        pending = getattr(self, "_pending_update", None)
        if pending and pending.get("ready") and not pending.get("helper_launched"):
            integration_prepared = False
            try:
                if pending.get("installed") and sys.platform.startswith("win"):
                    register_windows_installation(
                        pending["current"],
                        preview=pending["channel"].casefold() == "preview",
                        version=pending["version"],
                    )
                    integration_prepared = True
                self.launch_update_helper(pending)
                pending["helper_launched"] = True
            except Exception as error:
                if integration_prepared:
                    try:
                        register_windows_installation(pending["current"])
                    except Exception:
                        pass
                self.show_update_error(error)
                event.ignore()
                return
        
        self.save_game_config()
        if self.game_root_path:
            temp_path = self.game_root_path / "ChartEditorResources" / "temp"
            if temp_path.exists():
                try:
                    shutil.rmtree(temp_path)
                except:
                    pass
        if self.vis_worker:
            self.vis_worker.stop()
        for worker in list(self.audio_analysis_workers):
            if worker.isRunning():
                worker.requestInterruption()
                worker.wait(5000)
        if self.audio_import_worker and self.audio_import_worker.isRunning():
            self.audio_import_worker.requestInterruption()
            self.audio_import_worker.wait()
        if self.video_job_worker and self.video_job_worker.isRunning():
            self.video_job_worker.cancel()
            self.video_job_worker.wait()
        if self.video_configuration_window:
            worker = getattr(self.video_configuration_window, "worker", None)
            if worker and worker.isRunning():
                worker.cancel()
                worker.wait()
        if hasattr(self, "video_controller"):
            self.video_controller.release()
        if self.auto_save_worker and self.auto_save_worker.isRunning():
            self.auto_save_worker.wait()
        if self.rpc_worker:
            self.rpc_worker.stop()
        self.stop_music_playback(release=True)
        self.stop_all_hold_sounds()
        for sound in list(self.sounds.values()):
            sound.free()
        self.sounds.clear()
        if self.metronome_sound:
            self.metronome_sound.free()
            self.metronome_sound = None
        super().closeEvent(event)
        
    def update_ui_group_styles(self):
        style = "QGroupBox { margin-top: 0px; border: 1px solid #555; background-color: rgba(255,255,255,8); border-radius: 4px; }"
        if hasattr(self, 'gb_proj'): self.gb_proj.setStyleSheet(style)
        if hasattr(self, 'gb_meta'): self.gb_meta.setStyleSheet(style)
        if hasattr(self, 'gb_timing'): self.gb_timing.setStyleSheet(style)
        if hasattr(self, 'txt_star_name'):
            self.txt_star_name.setStyleSheet(f"border-bottom: 3px solid {ACCENT_COLOR};")
        if hasattr(self, 'resources_window') and self.resources_window:
            scale = getattr(self, 'global_scale', 1.0)
            bright = getattr(self, 'ui_brightness', 60)
            self.resources_window.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, scale, bright))
        if hasattr(self, 'start_screen') and self.start_screen:
            self.start_screen.update_theme()

    def update_bpm_match_button_height(self):
        bpm_field = getattr(self, 'meta_widgets', {}).get('BPM')
        match_button = getattr(self, 'btn_bpm_match', None)
        if bpm_field is not None and match_button is not None:
            match_button.setFixedHeight(max(1, bpm_field.sizeHint().height()))

    def load_ui_background_image(self):
        try:
            self.release_ui_background_image()
            if getattr(self, 'ui_bg_opacity', 0) <= 0:
                return
            if hasattr(self, 'game_root_path') and self.game_root_path:
                ui_bg_path = self.game_root_path / "ChartEditorResources" / "ui_bg.png"
                if not ui_bg_path.exists():
                    bg_path = self.game_root_path / "ChartEditorResources" / "bg.png"
                    if bg_path.exists():
                        shutil.copy2(str(bg_path), str(ui_bg_path))
                if ui_bg_path.exists():
                    self.ui_bg_source_path = str(ui_bg_path)
        except Exception as e:
            print(f"LOAD UI BG ERROR: {e}")
            import traceback
            traceback.print_exc()

    def release_ui_background_image(self):
        self.ui_bg_source_path = None
        self._cached_main_bg = None
        self._cached_main_bg_size = None
        self._cached_main_bg_path = None
        if hasattr(self, "sidebar_vis"):
            self.sidebar_vis._background_cache = None
            self.sidebar_vis._background_cache_signature = None
            self.sidebar_vis.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(UI_THEME["bg_dark"]))

        ui_bg_opacity = getattr(self, 'ui_bg_opacity', 0)
        if ui_bg_opacity > 0 and getattr(self, 'ui_bg_source_path', None):
            p.setOpacity(ui_bg_opacity / 100.0)
            dpr = max(1.0, float(self.devicePixelRatioF()))
            scaled_size = (
                max(1, int(round(self.width() * dpr))),
                max(1, int(round(self.height() * dpr))),
            )
            
            if self._cached_main_bg_size != scaled_size or self._cached_main_bg_path != self.ui_bg_source_path:
                self._cached_main_bg_size = scaled_size
                self._cached_main_bg_path = self.ui_bg_source_path
                self._cached_main_bg = load_scaled_display_pixmap(
                    self.ui_bg_source_path,
                    self,
                    self.width(),
                    self.height(),
                )
            
            if self._cached_main_bg:
                pixmap_dpr = self._cached_main_bg.devicePixelRatio()
                x = (self.width() - self._cached_main_bg.width() / pixmap_dpr) / 2
                y = (self.height() - self._cached_main_bg.height() / pixmap_dpr) / 2
                p.drawPixmap(int(x), int(y), self._cached_main_bg)
        
        super().paintEvent(e)

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

    def init_discord_rpc(self):
        if not self.enable_rpc:
            return
        if self.rpc_worker and self.rpc_worker.isRunning():
            return
        self.rpc_worker = DiscordRPCWorker("1466206307085455579", self)
        self.rpc_worker.connected.connect(self.on_discord_rpc_connected)
        self.rpc_worker.start()

    def update_rpc_state(self):
        if self.enable_rpc:
            if not self.rpc_timer.isActive():
                self.rpc_timer.start()
            self.init_discord_rpc()
            return
        self.rpc_timer.stop()
        if self.rpc_worker:
            self.rpc_worker.stop()
            self.rpc_worker.deleteLater()
            self.rpc_worker = None
        self.rpc = False

    def on_discord_rpc_connected(self):
        self.rpc = True
        self.update_discord_presence()

    def update_discord_presence(self):
        if not self.rpc_worker or not self.rpc:
            return
        if not self.enable_rpc:
            self.rpc_worker.set_presence(None)
            return
        
        try:
            details = "Idle"
            state = None
            if hasattr(self, 'timeline') and self.timeline and self.timeline.beatmap:
                t = self.timeline.beatmap.metadata.Title
                if not t: t = "Untitled"
                details = f"Working on {t}"
                
                v = self.timeline.beatmap.metadata.Version
                if not v: v = "Normal"
                
                obj_count = 0
                if self.timeline.beatmap.hit_objects:
                    obj_count = len(self.timeline.beatmap.hit_objects)
                state = f"Difficulty: {v} | Objects: {obj_count}"
            
            rpc_icon = "icon_pre" if PREVIEW_VERSION else "icon"
            self.rpc_worker.set_presence({
                'details': details,
                'state': state,
                'large_image': rpc_icon,
                'start': self.app_start_time
            })
        except Exception:
            pass

    def load_game_config(self):
        if not self.game_root_path: return
        path = self.game_root_path / "ChartEditorResources" / "editor_config.json"

        default_config = {
            "window": {"width": 1400, "height": 820, "x": 100, "y": 100},
            "recent_projects": [],
            "settings": {"music_volume": 1.0, "fx_volume": 1.0, "ui_volume": 1.0, "event_default_order": "Before", "file_extension": ".txt", "update_channel": "Preview" if PREVIEW_VERSION else "Stable"},
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
                                for ck, cv in v.items():
                                    if ck in merged_colors:
                                        merged_colors[ck] = cv
                            data[k] = merged_colors
                        else:
                            data[k] = v
            except:
                pass
        
        w_data = data.get("window", {})
        self.resize(w_data.get("width", 1400), w_data.get("height", 820))
        self.move(w_data.get("x", 100), w_data.get("y", 100))
        
        if w_data.get("is_maximized", False):
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        
        if "settings_geometry" in w_data:
             self.settings_geometry = QByteArray.fromBase64(w_data["settings_geometry"].encode())

        
        self.recent_projects = [p for p in data.get("recent_projects", []) if Path(p).exists()]
        
        s_data = data.get("settings", {})
        self.master_volume = s_data.get("master_volume", 1.0)
        self.music_volume = s_data.get("music_volume", 1.0)
        self.fx_volume = s_data.get("fx_volume", 1.0)
        self.ui_volume = s_data.get("ui_volume", 1.0)
        self.mute_event_sfx = s_data.get("mute_event_sfx", False)
        self.event_default_order = s_data.get("event_default_order", "Before")
        self.enable_3d_sound = s_data.get("enable_3d_sound", True)
        self.enable_visualizer = s_data.get("enable_visualizer", True)
        self.enable_beatflash = s_data.get("enable_beatflash", True)
        self.auto_save = s_data.get("auto_save", False)
        self.enable_backups = s_data.get("enable_backups", True)
        self.disable_tooltips = s_data.get("disable_tooltips", False)
        QApplication.instance().setProperty("disable_tooltips", self.disable_tooltips)
        self.disable_hold_collisions = s_data.get("disable_hold_collisions", False)
        self.objects_follow_bpm_grid = s_data.get("objects_follow_bpm_grid", True)
        self.update_channel = s_data.get("update_channel", "Preview" if PREVIEW_VERSION else "Stable")
        if self.update_channel not in ("Stable", "Preview"):
            self.update_channel = "Preview" if PREVIEW_VERSION else "Stable"
        self.video_preview_enabled = s_data.get("video_preview_enabled", True)
        self.custom_notes_enabled = s_data.get("custom_notes_enabled", True)
        self.custom_notes, self.custom_note_tombstones = set_custom_note_registry(
            data.get("custom_notes", []),
            data.get("custom_note_tombstones", []),
        )
        self.project_view_mode = s_data.get("project_view_mode", "Cover View")
        if self.project_view_mode not in ("List View", "Cover View"):
            self.project_view_mode = "Cover View"
        if hasattr(self, "video_controller"):
            self.video_controller.enabled = self.video_preview_enabled
        self.enable_rpc = s_data.get("enable_rpc", True)
        self.file_extension_setting = s_data.get("file_extension", ".txt")
        self.timeline_visual_start = s_data.get("timeline_visual_start", 150)
        self.global_scale = s_data.get("global_scale", 1.0)
        self.grid_opacity = s_data.get("grid_opacity", 50)
        self.visualizer_opacity = s_data.get("visualizer_opacity", 10)
        self.background_opacity = s_data.get("background_opacity", 20)
        self.preview_bg_opacity = s_data.get("preview_bg_opacity", 30)
        self.grid_thickness = s_data.get("grid_thickness", 2)
        self.lane_opacity = s_data.get("lane_opacity", 100)
        self.drop_shadow_mode = s_data.get("drop_shadow_mode", "None")
        self.background_blur = s_data.get("background_blur", 0)
        self.ui_bg_opacity = s_data.get("ui_bg_opacity", 0)
        self.ui_brightness = s_data.get("ui_brightness", 60)
        self.ui_bg_blur = s_data.get("ui_bg_blur", 0)
        self.current_background = s_data.get("current_background", "None")
        self.custom_accent_color = s_data.get("accent_color", DEFAULT_ACCENT_COLOR)
        apply_accent_color(self.custom_accent_color)
        
        QApplication.instance().setStyleSheet(get_scaled_stylesheet(BASE_APP_STYLESHEET, self.global_scale, self.ui_brightness))
        self.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, self.global_scale, self.ui_brightness))
        if hasattr(self, "save_toast"):
            self.save_toast.update_scale()
        if hasattr(self, 'resources_window') and self.resources_window:
            self.resources_window.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, self.global_scale, self.ui_brightness))
        
        loaded_colors = data.get("colors", {})
        self.current_colors = DEFAULT_COLORS.copy()
        for k, v in loaded_colors.items():
            if k in self.current_colors:
                if v in COLOR_PALETTE:
                    self.current_colors[k] = v
                elif isinstance(v, str) and v.startswith("#") and QColor(v).isValid():
                    self.current_colors[k] = QColor(v).name().upper()
                else:
                    self.current_colors[k] = DEFAULT_COLORS[k]

        loaded_keybinds = data.get("keybinds", {})
        self.current_keybinds = DEFAULT_KEYBINDS.copy()
        for k, v in loaded_keybinds.items():
            if k in self.current_keybinds:
                self.current_keybinds[k] = v

        if hasattr(self, 'timeline'):
            self.timeline.set_colors(self.current_colors)
            if hasattr(self.timeline, 'set_keybinds'):
                self.timeline.set_keybinds(self.current_keybinds)
        if hasattr(self, "refresh_custom_note_tools"):
            self.refresh_custom_note_tools()
        self.load_ui_background_image()

        self.update_ui_group_styles()
        if hasattr(self, 'start_screen') and self.start_screen:
            self.start_screen.update_theme()
        update_all_shadows(self)
    def save_game_config(self):
        if not getattr(self, '_is_initialized', False):
            return
            
        if not self.game_root_path: return
        res_dir = self.game_root_path / "ChartEditorResources"
        if not res_dir.exists():
            return 
            
        path = res_dir / "editor_config.json"

        w_geo = {
            "width": self.normalGeometry().width() if self.isMaximized() else self.width(),
            "height": self.normalGeometry().height() if self.isMaximized() else self.height(),
            "x": self.normalGeometry().x() if self.isMaximized() else self.x(),
            "y": self.normalGeometry().y() if self.isMaximized() else self.y(),
            "is_maximized": self.isMaximized()
        }
        if self.settings_geometry is not None:
             w_geo["settings_geometry"] = self.settings_geometry.toBase64().data().decode()

        data = {
            "window": w_geo,
            "recent_projects": self.recent_projects,
            "settings": {
                "master_volume": getattr(self, 'master_volume', 1.0),
                "music_volume": self.music_volume, 
                "fx_volume": self.fx_volume,
                "ui_volume": self.ui_volume,
                "mute_event_sfx": getattr(self, 'mute_event_sfx', False),
                "event_default_order": self.event_default_order,
                "enable_3d_sound": self.enable_3d_sound,
                "enable_visualizer": self.enable_visualizer,
                "enable_beatflash": self.enable_beatflash,
                "auto_save": getattr(self, 'auto_save', False),
                "enable_backups": getattr(self, 'enable_backups', True),
                "disable_tooltips": getattr(self, 'disable_tooltips', False),
                "disable_hold_collisions": getattr(self, 'disable_hold_collisions', False),
                "objects_follow_bpm_grid": getattr(self, 'objects_follow_bpm_grid', True),
                "update_channel": getattr(self, "update_channel", "Preview" if PREVIEW_VERSION else "Stable"),
                "video_preview_enabled": getattr(self, "video_preview_enabled", True),
                "custom_notes_enabled": getattr(self, "custom_notes_enabled", True),
                "project_view_mode": getattr(self, "project_view_mode", "Cover View"),
                "enable_rpc": self.enable_rpc,
                "file_extension": self.file_extension_setting,
                "timeline_visual_start": self.timeline_visual_start,
                "global_scale": self.global_scale,
                "grid_opacity": self.grid_opacity,
                "visualizer_opacity": self.visualizer_opacity,
                "background_opacity": self.background_opacity,
                "preview_bg_opacity": self.preview_bg_opacity,
                "grid_thickness": self.grid_thickness,
                "lane_opacity": getattr(self, "lane_opacity", 100),
                "drop_shadow_mode": getattr(self, "drop_shadow_mode", "None"),
                "background_blur": getattr(self, "background_blur", 0),
                "ui_bg_opacity": getattr(self, "ui_bg_opacity", 0),
                "ui_bg_blur": getattr(self, "ui_bg_blur", 0),
                "ui_brightness": getattr(self, "ui_brightness", 60),
                "current_background": self.current_background,
                "accent_color": getattr(self, "custom_accent_color", DEFAULT_ACCENT_COLOR)
            },
            "colors": self.current_colors,
            "keybinds": getattr(self, "current_keybinds", DEFAULT_KEYBINDS.copy()),
            "custom_notes": getattr(self, "custom_notes", []),
            "custom_note_tombstones": getattr(self, "custom_note_tombstones", []),
        }
        
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"LOAD UI BG ERROR: {e}")
            import traceback
            traceback.print_exc()

    def add_to_recent(self, path):
        str_path = str(path)
        if str_path in self.recent_projects:
            self.recent_projects.remove(str_path)
        self.recent_projects.insert(0, str_path)
        self.save_game_config()

    def open_recent_popup(self):
        if self.start_screen.isVisible():
            if not getattr(self, 'current_chart', None):
                return
            self.start_screen.setVisible(False)
            if hasattr(self, 'update_ui_from_metadata'):
                self.update_ui_from_metadata()
            if hasattr(self, "timeline"):
                self.timeline.update()
            self.update_ui_state()
        else:
            if getattr(self, 'is_playing', False):
                self.toggle_play()
            self.start_screen.load_projects()
            self.start_screen.setVisible(True)
            self.start_screen.raise_()
            if hasattr(self, 'stack_meta_timing'):
                self.stack_meta_timing.setCurrentWidget(self.gb_meta)
                self.btn_tab_meta.setChecked(True)
                self.btn_tab_timing.setChecked(False)
            if hasattr(self, "timeline"):
                self.timeline.update()
            self.update_ui_state()
    def get_effective_music_volume(self):
        return getattr(self, 'music_volume', 1.0) * getattr(self, 'master_volume', 1.0)

    def get_effective_fx_volume(self):
        return getattr(self, 'fx_volume', 1.0) * getattr(self, 'master_volume', 1.0)

    def get_effective_ui_volume(self):
        return getattr(self, 'ui_volume', 1.0) * getattr(self, 'master_volume', 1.0)

    def stop_music_playback(self, release=False):
        stream = getattr(self, 'current_playback_channel', None)
        if not stream:
            return
        stream.stop()
        if release:
            stream.free()
            self.current_playback_channel = None

    def update_live_music_volume(self):
        eff_music = self.get_effective_music_volume()
        if getattr(self, 'current_playback_channel', None):
            try: self.current_playback_channel.set_volume(eff_music)
            except: pass

    def set_master_volume_live(self, vol):
        self.master_volume = vol
        self.update_live_music_volume()
        eff_ui = self.get_effective_ui_volume()
        eff_fx = self.get_effective_fx_volume()
        for name, sound in self.sounds.items():
            if name.startswith("UI"):
                try: sound.set_volume(eff_ui)
                except: pass
            else:
                try: sound.set_volume(eff_fx)
                except: pass
        for channel in getattr(self, 'active_hold_sounds', {}).values():
            try: channel.set_volume(eff_fx, eff_fx)
            except: pass

    def set_music_volume_live(self, vol):
        self.music_volume = vol
        self.update_live_music_volume()

    def set_fx_volume_live(self, vol):
        self.fx_volume = vol
        eff_fx = self.get_effective_fx_volume()
        for name, sound in self.sounds.items():
            if not name.startswith("UI"):
                try: sound.set_volume(eff_fx)
                except: pass
        for channel in getattr(self, 'active_hold_sounds', {}).values():
            try: channel.set_volume(eff_fx, eff_fx)
            except: pass

    def open_resources_window(self):
        if self.resources_window is None:
            self.resources_window = ResourcesWindow(
                self,
                self.audio_label,
                self.cover_label,
                self.video_label,
            )
        self.resources_window.update_video_state()
        self.resources_window.exec()

    def open_video_configuration(self):
        if not self.project_folder or not find_project_video(self.project_folder):
            return
        existing = self.video_configuration_window
        if existing:
            try:
                if existing.isVisible():
                    existing.raise_()
                    existing.activateWindow()
                    return
            except RuntimeError:
                self.video_configuration_window = None
        self.video_configuration_window = VideoConfigurationWindow(self)
        self.video_configuration_window.show()

    def set_video_preview_enabled(self, enabled):
        self.video_preview_enabled = bool(enabled)
        if hasattr(self, "video_controller"):
            self.video_controller.set_enabled(self.video_preview_enabled)
    def toggle_video_preview(self):
        self.set_video_preview_enabled(not getattr(self, "video_preview_enabled", True))

    def restore_beatmap_backup(self, difficulty, backup_path):
        if not self.project_folder:
            return False, "No project is currently open."
        chart = self.beatmaps.get(difficulty)
        if not chart or not chart.created:
            return False, f"The {difficulty} difficulty no longer exists."

        try:
            backup_path = Path(backup_path).resolve()
            backup_directory = get_beatmap_backup_directory(self.project_folder, difficulty).resolve()
            if backup_path.parent != backup_directory or not backup_path.is_file():
                return False, "The selected backup is invalid or no longer exists."

            validation = BeatmapData(difficulty)
            if not validation.load(backup_path.parent, backup_path.name):
                return False, "The selected backup could not be read."

            if self.auto_save_worker and self.auto_save_worker.isRunning():
                self.auto_save_worker.wait()

            destination = self.project_folder / Path(chart.get_filename()).name
            temporary = destination.with_name(f".{destination.name}.restore-{time.time_ns()}.tmp")
            with self.save_io_lock:
                try:
                    shutil.copy2(backup_path, temporary)
                    os.replace(temporary, destination)
                finally:
                    if temporary.exists():
                        temporary.unlink()

            restored_chart = BeatmapData(difficulty)
            if not restored_chart.load(self.project_folder, destination.name):
                return False, "The restored beatmap could not be reloaded."

            is_current = (
                self.current_chart is not None
                and self.current_chart.difficulty_key == difficulty
            )
            self.beatmaps[difficulty] = restored_chart
            if is_current:
                self.change_difficulty(difficulty)
            else:
                self.update_ui_state()
                self.update_window_title()
            self.update_bmap_file()
            return True, ""
        except Exception as e:
            return False, f"Failed to restore the backup:\n{e}"

    def open_settings(self):
        existing_dialog = getattr(self, 'settings_dialog', None)
        if existing_dialog is not None:
            try:
                if existing_dialog.isVisible():
                    existing_dialog.raise_()
                    existing_dialog.activateWindow()
                    return
            except RuntimeError:
                self.settings_dialog = None

        self._old_settings_master_vol = getattr(self, 'master_volume', 1.0)
        self._old_settings_music_vol = self.music_volume
        self._old_settings_fx_vol = self.fx_volume
        self._old_settings_ui_vol = self.ui_volume
        self._old_settings_grid_opacity = self.grid_opacity
        self._old_settings_vis_opacity = self.visualizer_opacity
        self._old_settings_bg_opacity = self.background_opacity
        self._old_settings_preview_bg_opacity = getattr(self, 'preview_bg_opacity', 30)
        self._old_settings_grid_thick = self.grid_thickness
        self._old_settings_lane_opacity = getattr(self, 'lane_opacity', 100)
        self._old_settings_background_blur = getattr(self, 'background_blur', 0)
        self._old_settings_timeline_start = getattr(self, 'timeline_visual_start', 150)
        self._old_settings_shadow_mode = getattr(self, 'drop_shadow_mode', "None")
        
        self.settings_dialog = SettingsDialog(
            self,
            self.global_scale, getattr(self, 'master_volume', 1.0), self.music_volume, self.fx_volume, self.ui_volume, self.current_colors, self.game_root_path,
            self.event_default_order, self.enable_3d_sound,
            self.enable_visualizer, self.enable_beatflash, getattr(self, 'auto_save', False), self.file_extension_setting, getattr(self, 'settings_geometry', None),
            self.grid_opacity, self.visualizer_opacity, self.background_opacity,
            self.grid_thickness, self.current_background, self.preview_bg_opacity,
            getattr(self, 'lane_opacity', 100), getattr(self, 'background_blur', 0),
            getattr(self, 'ui_brightness', 60),
            getattr(self, 'current_keybinds', None),
            getattr(self, "custom_notes_enabled", True),
            getattr(self, "custom_notes", []),
            getattr(self, "custom_note_tombstones", [])
        )
        self.settings_dialog.setStyleSheet(self.styleSheet())
        self.settings_dialog.finished.connect(self.on_settings_finished)
        self.settings_dialog.show()

    def on_settings_finished(self, res):
        dialog = getattr(self, 'settings_dialog', None)
        if not dialog: return
        self.settings_geometry = dialog.saveGeometry()
        if res == QDialog.DialogCode.Accepted:
            new_scale = dialog.get_scale()
            if abs(new_scale - self.global_scale) > 0.001:
                self.global_scale = new_scale
                QApplication.instance().setStyleSheet(get_scaled_stylesheet(BASE_APP_STYLESHEET, self.global_scale, self.ui_brightness))
                self.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, self.global_scale, self.ui_brightness))
                self.save_toast.update_scale()
                QTimer.singleShot(0, self.update_bpm_match_button_height)
            
            self.master_volume, self.music_volume, self.fx_volume, self.ui_volume = dialog.get_volumes()
            eff_music = self.get_effective_music_volume()
            eff_ui = self.get_effective_ui_volume()
            eff_fx = self.get_effective_fx_volume()
            
            self.current_colors = dialog.get_colors()
            if hasattr(dialog, 'get_keybinds'):
                self.current_keybinds = dialog.get_keybinds()
            self.custom_notes_enabled = dialog.get_custom_notes_enabled()
            self.freeze_custom_note_raw_lines()
            self.custom_notes, self.custom_note_tombstones = set_custom_note_registry(
                dialog.get_custom_notes(),
                dialog.get_custom_note_tombstones(),
            )
            self.refresh_custom_note_objects()
            self.refresh_custom_note_tools()
            self.event_default_order = dialog.get_event_default_order()
            self.enable_3d_sound = dialog.chk_3d_sound.isChecked()
            self.enable_visualizer = dialog.chk_visualizer.isChecked()
            self.update_visualizer_worker_state()
            self.set_video_preview_enabled(dialog.get_video_preview_enabled())
            self.enable_beatflash = dialog.chk_beatflash.isChecked()
            self.auto_save = dialog.get_auto_save()
            self.enable_backups = dialog.get_backups()
            self.disable_tooltips = dialog.get_disable_tooltips()
            QApplication.instance().setProperty("disable_tooltips", self.disable_tooltips)
            self.disable_hold_collisions = dialog.get_disable_hold_collisions()
            self.objects_follow_bpm_grid = dialog.get_objects_follow_bpm_grid()
            self.update_channel = dialog.get_update_channel()
            self.enable_rpc = dialog.chk_rpc.isChecked()
            self.update_rpc_state()
            self.file_extension_setting = dialog.get_file_extension()
            self.timeline_visual_start = dialog.slider_playback_pos.value()
            self.grid_opacity = dialog.get_grid_opacity()
            self.visualizer_opacity = dialog.get_visualizer_opacity()
            self.background_opacity = dialog.get_background_opacity()
            self.preview_bg_opacity = dialog.get_preview_bg_opacity()
            self.grid_thickness = dialog.get_grid_thickness()
            self.lane_opacity = dialog.get_lane_opacity()
            self.ui_brightness = dialog.get_ui_brightness()
            self.current_background = dialog.get_background()
            
            if getattr(self, 'current_playback_channel', None):
                self.current_playback_channel.set_volume(eff_music)
            for name, sound in self.sounds.items():
                if name.startswith("UI"):
                    sound.set_volume(eff_ui)
                else:
                    sound.set_volume(eff_fx)
            
            self.timeline.set_colors(self.current_colors)
            if hasattr(self.timeline, 'set_keybinds'):
                self.timeline.set_keybinds(getattr(self, 'current_keybinds', DEFAULT_KEYBINDS.copy()))
            
            self.background_blur = dialog.get_background_blur()

            if hasattr(self, 'btn_play'):
                self.btn_play.setText("Play / Pause")

            self.save_game_config()
            
            if dialog.sounds_changed or getattr(dialog, "custom_hitsounds_changed", False):
                self.load_sounds()
            
            self.timeline.update()

            if hasattr(self, 'start_screen') and self.start_screen:
                self.start_screen.update_theme()
        else:
            self.master_volume = getattr(self, '_old_settings_master_vol', 1.0)
            self.set_music_volume_live(getattr(self, '_old_settings_music_vol', 1.0))
            self.ui_volume = getattr(self, '_old_settings_ui_vol', 1.0)
            self.set_fx_volume_live(getattr(self, '_old_settings_fx_vol', 1.0))
            eff_music = self.get_effective_music_volume()
            eff_ui = self.get_effective_ui_volume()
            eff_fx = self.get_effective_fx_volume()
            for name, sound in self.sounds.items():
                if name.startswith("UI"):
                    sound.set_volume(eff_ui)
                else:
                    sound.set_volume(eff_fx)
            self.grid_opacity = getattr(self, '_old_settings_grid_opacity', 50)
            self.visualizer_opacity = getattr(self, '_old_settings_vis_opacity', 10)
            self.background_opacity = getattr(self, '_old_settings_bg_opacity', 20)
            self.preview_bg_opacity = getattr(self, '_old_settings_preview_bg_opacity', 30)
            self.grid_thickness = getattr(self, '_old_settings_grid_thick', 2)
            self.lane_opacity = getattr(self, '_old_settings_lane_opacity', 100)
            self.background_blur = getattr(self, '_old_settings_background_blur', 0)
            self.timeline_visual_start = getattr(self, '_old_settings_timeline_start', 150)
            self.drop_shadow_mode = getattr(self, '_old_settings_shadow_mode', "None")
            if self.background_opacity <= 0:
                self.timeline.release_background_image()
            elif not self.timeline.bg_image_path:
                self.timeline.load_background_image()
            schedule_shadow_update(self)
            if hasattr(self, 'timeline'):
                self.timeline.update_color_objects()
            if hasattr(self, 'start_screen') and self.start_screen:
                self.start_screen.update_theme()

        dialog.deleteLater()
        if getattr(self, 'settings_dialog', None) is dialog:
            self.settings_dialog = None

    def keyReleaseEvent(self, e: QKeyEvent):
        if not e.isAutoRepeat():
            self.pressed_keys.discard(e.key())
        if e.isAutoRepeat():
            e.ignore()
            return
        
        if e.key() == Qt.Key.Key_Z or e.key() == Qt.Key.Key_Y:
            if hasattr(self, 'undo_redo_timer') and self.undo_redo_timer.isActive():
                self.undo_redo_timer.stop()
        
        super().keyReleaseEvent(e)
        
    def perform_undo_redo_action(self):
        if not hasattr(self, 'current_undo_key'): return
        
        key, modifiers = self.current_undo_key
        
        if key == Qt.Key.Key_Z:
             if modifiers & Qt.KeyboardModifier.ControlModifier and modifiers & Qt.KeyboardModifier.ShiftModifier:
                 self.timeline.redo()
             elif modifiers & Qt.KeyboardModifier.ControlModifier:
                 self.timeline.undo()
        elif key == Qt.Key.Key_Y:
             if modifiers & Qt.KeyboardModifier.ControlModifier:
                 self.timeline.redo()
                 
    def update_window_title(self):
        title = f"CBM Editor {VERSION_NUMBER}"
        if PREVIEW_VERSION:
            title += " -PREVIEW-"
        
        project_folder = getattr(self, 'project_folder', None)
        if project_folder:
            title += f" [{project_folder.name}]"
            
        current_chart = getattr(self, 'current_chart', None)
        if current_chart and current_chart.unsaved:
            title += " *"
            
        if self.windowTitle() != title:
            self.setWindowTitle(title)
    def mark_unsaved(self, invalidate_timeline=True):
        if self.current_chart:
            self.current_chart._edit_revision = getattr(self.current_chart, '_edit_revision', 0) + 1
            if not self.current_chart.unsaved:
                self.current_chart.unsaved = True
                self.update_window_title()
        if invalidate_timeline and hasattr(self, 'timeline'):
            if not getattr(self.timeline, 'dragging_objects', False) and not getattr(self.timeline, 'dragging_bpm_tag', None):
                self.timeline._force_cache_update = True

    def mark_saved(self):
        if self.current_chart:
            self.current_chart.unsaved = False
            self.update_window_title()

    def update_ui_state(self):
        has_chart = self.current_chart is not None and not self.start_screen.isVisible()
        
        self.combo_diff.setEnabled(has_chart)
        self.btn_play.setEnabled(has_chart)
        self.btn_tool_note.setEnabled(has_chart)
        self.btn_tool_brawl.setEnabled(has_chart)
        self.btn_tool_event.setEnabled(has_chart)
        self.btn_tool_custom.setEnabled(has_chart)
        
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
        self.combo_custom_note.setEnabled(has_chart)
        self.combo_custom_type.setEnabled(has_chart)
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
        
        if hasattr(self, 'btn_add_bpm'):
            self.btn_add_bpm.setEnabled(has_chart)
            self.btn_del_bpm.setEnabled(has_chart)
            self.inp_bpm.setEnabled(has_chart)
            self.list_bpm.setEnabled(has_chart)
            self.btn_tab_meta.setEnabled(has_chart)
            self.btn_tab_timing.setEnabled(has_chart)
        if hasattr(self, 'btn_resources'):
            self.btn_resources.setEnabled(has_chart)
        
        b = getattr(self, 'ui_brightness', 60)
        if b > 180:
            active_color = QColor("#000")
            inactive_color = QColor("#999")
        else:
            active_color = QColor("#EEE")
            inactive_color = QColor("#777")

        for i in range(self.combo_diff.count()):
            diff_name = self.combo_diff.itemText(i)
            if diff_name in self.beatmaps and self.beatmaps[diff_name].created:
                self.combo_diff.setItemData(i, active_color, Qt.ItemDataRole.ForegroundRole)
            else:
                self.combo_diff.setItemData(i, inactive_color, Qt.ItemDataRole.ForegroundRole)

        if hasattr(self, 'lbl_current_ms'):
            ms_color = "white" if b > 180 else UI_THEME['text_secondary']
            self.lbl_current_ms.setStyleSheet(f"font-size: 13px; font-weight: normal; color: {ms_color}; margin-top: 0px; margin-bottom: 10px;")

        if getattr(self, 'start_screen', None) and self.start_screen.isVisible() and self.current_chart:
            self.btn_recent.setText("Close Project Select")
        else:
            if hasattr(self, 'btn_recent'):
                self.btn_recent.setText("Open Project Select")

    def setup_ui(self):
        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_panel.setObjectName("LeftPanel")
        
        self.gb_proj = QGroupBox()

        l_proj = QVBoxLayout()
        l_proj.setContentsMargins(10, 5, 10, 10)
        lbl_proj_title = QLabel("Project")
        lbl_proj_title.setObjectName("ProjectTitle")
        
        proj_effect = FastDropShadowEffect(lbl_proj_title)
        proj_effect.setBlurRadius(8)
        proj_effect.setColor(QColor(0, 0, 0, 200))
        proj_effect.setOffset(0, 2)
        set_manual_shadow(lbl_proj_title, proj_effect)
        
        l_proj.addWidget(lbl_proj_title)
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_open = QPushButton("Open / Create")
        btn_open.setToolTip("Open project folder to store chart files in")
        btn_open.clicked.connect(self.open_project)
        btn_open.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_layout.addWidget(btn_open)
        
        btn_export = QPushButton("Export")
        btn_export.setToolTip("Export project as .zip")
        btn_export.clicked.connect(self.export_project)
        btn_export.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_layout.addWidget(btn_export)
        
        l_proj.addLayout(btn_layout)
        
        self.btn_recent = QPushButton("Open Project Select")
        self.btn_recent.clicked.connect(self.open_recent_popup)
        self.btn_recent.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        l_proj.addWidget(self.btn_recent)

        self.lbl_path = QLabel("No Folder Selected")
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setObjectName("PathLabel")
        self.lbl_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        l_proj.addWidget(self.lbl_path)
        self.combo_diff = QComboBox()
        self.combo_diff.setToolTip("Determines difficulty slot for current level")
        self.combo_diff.setView(SmoothListView(self.combo_diff))
        self.combo_diff.addItems(DIFFICULTIES)
        self.combo_diff.currentTextChanged.connect(self.change_difficulty)
        self.combo_diff.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lbl_diff_sel = QLabel("Select Difficulty:")
        lbl_diff_sel.setToolTip("Determines difficulty slot for current level")
        lbl_diff_sel.setObjectName("WhiteLabel")
        
        diff_sel_effect = FastDropShadowEffect(lbl_diff_sel)
        diff_sel_effect.setBlurRadius(8)
        diff_sel_effect.setColor(QColor(0, 0, 0, 200))
        diff_sel_effect.setOffset(0, 2)
        set_manual_shadow(lbl_diff_sel, diff_sel_effect)
        
        l_proj.addWidget(lbl_diff_sel)
        l_proj.addWidget(self.combo_diff)
        self.gb_proj.setLayout(l_proj)
        left_layout.addWidget(self.gb_proj)
        
        self.tab_buttons_layout = QHBoxLayout()
        self.tab_buttons_layout.setSpacing(2)
        
        self.btn_tab_meta = QPushButton("Metadata")
        self.btn_tab_meta.setCheckable(True)
        self.btn_tab_meta.setChecked(True)
        self.btn_tab_meta.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tab_meta.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_tab_meta.clicked.connect(lambda: self.stack_meta_timing.setCurrentWidget(self.gb_meta) if not (getattr(self, 'start_screen', None) and self.start_screen.isVisible()) else None)

        self.btn_tab_timing = QPushButton("Timing")
        self.btn_tab_timing.setCheckable(True)
        self.btn_tab_timing.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tab_timing.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_tab_timing.clicked.connect(lambda: self.stack_meta_timing.setCurrentWidget(self.gb_timing) if not (getattr(self, 'start_screen', None) and self.start_screen.isVisible()) else None)
        
        self.sidebar_tab_group = QButtonGroup(central)
        self.sidebar_tab_group.addButton(self.btn_tab_meta)
        self.sidebar_tab_group.addButton(self.btn_tab_timing)
        self.sidebar_tab_group.setExclusive(True)
        
        self.tab_buttons_layout.addWidget(self.btn_tab_meta)
        self.tab_buttons_layout.addWidget(self.btn_tab_timing)
        left_layout.addLayout(self.tab_buttons_layout)
        
        self.gb_meta = QGroupBox()
        self.gb_meta.setObjectName("MetadataGroup")

        self.form_meta = QFormLayout()
        self.form_meta.setContentsMargins(10, 5, 10, 10)
        self.lbl_meta_title = QLabel("Metadata")
        self.lbl_meta_title.setObjectName("MetadataTitle")
        
        meta_effect = FastDropShadowEffect(self.lbl_meta_title)
        meta_effect.setBlurRadius(8)
        meta_effect.setColor(QColor(0, 0, 0, 200))
        meta_effect.setOffset(0, 2)
        set_manual_shadow(self.lbl_meta_title, meta_effect)
        
        self.form_meta.addRow(self.lbl_meta_title)
        self.meta_widgets = {}
        
        fields = [
            ("Title", "text"), ("Artist", "text"), ("Charted By", "text"),
            ("BPM", "bpm_row"), ("Level", "int"),
            ("FlavorText", "text"), ("Attributes", "text")
        ]
        
        for name, ftype in fields:
            lbl = QLabel(name)
            lbl.setObjectName("WhiteLabel")
            
            field_effect = FastDropShadowEffect(lbl)
            field_effect.setBlurRadius(8)
            field_effect.setColor(QColor(0, 0, 0, 200))
            field_effect.setOffset(0, 2)
            set_manual_shadow(lbl, field_effect)
            
            if ftype == "text":
                w = NoMenuLineEdit()
                
                w.textChanged.connect(self.update_metadata_from_ui)
                w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
                w.returnPressed.connect(lambda: self.timeline.setFocus())
                
                if name == "FlavorText":
                    w.setToolTip("Text that shows next to the song name in song list")
                    lbl.setToolTip("Text that shows next to the song name in song list")
                elif name == "Attributes":
                    w.setToolTip("An additional tag used by some community tools to identify types of charts for example charts with 4 key sections (4K), charts with motion warnings (MW), or joke charts (joke)")
                    lbl.setToolTip("An additional tag used by some community tools to identify types of charts for example charts with 4 key sections (4K), charts with motion warnings (MW), or joke charts (joke)")
                
                self.meta_widgets[name] = w
                self.form_meta.addRow(lbl, w)
            elif ftype == "int":
                w = CleanSpinBox()
                
                w.setRange(1, 100)
                w.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
                w.valueChanged.connect(self.update_metadata_from_ui)
                w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
                
                if name == "Level":
                    w.setToolTip("Number level for current difficulty (1-25 in base game charts, but can be higher)")
                    lbl.setToolTip("Number level for current difficulty (1-25 in base game charts, but can be higher)")
                
                self.meta_widgets[name] = w
                self.form_meta.addRow(lbl, w)
            elif ftype == "bpm_row":
                row_widget = QWidget()
                row_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                row_widget.setMinimumHeight(35)
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                
                w = CleanDoubleSpinBox()
                w.setObjectName("NoShadow")
                
                bpm_field_effect = FastDropShadowEffect(w)
                bpm_field_effect.setBlurRadius(8)
                bpm_field_effect.setColor(QColor(0, 0, 0, 200))
                bpm_field_effect.setOffset(0, 2)
                set_manual_shadow(w, bpm_field_effect)
                w.setRange(1, 999)
                w.setSingleStep(1)
                w.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
                w.setReadOnly(True)
                w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                w.setMinimumWidth(1)
                w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                w.setObjectName("BPMDoubleSpinBox")
                w.wheelEvent = lambda e: e.ignore()
                
                self.btn_bpm_match = QPushButton("Match")
                self.btn_bpm_match.setObjectName("MatchButton")
                self.btn_bpm_match.setMinimumWidth(1)
                self.btn_bpm_match.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                self.btn_bpm_match.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                self.btn_bpm_match.clicked.connect(self.open_sync_menu)
            
                self.chk_metronome = QCheckBox("Metro")
                self.chk_metronome.setToolTip("Toggle Metronome")
                self.chk_metronome.setObjectName("WhiteLabel")
                metro_effect = FastDropShadowEffect(self.chk_metronome)
                metro_effect.setBlurRadius(8)
                metro_effect.setColor(QColor(0, 0, 0, 200))
                metro_effect.setOffset(0, 2)
                set_manual_shadow(self.chk_metronome, metro_effect)

                self.chk_metronome.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                self.chk_metronome.setMinimumWidth(1)
                self.chk_metronome.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                self.chk_metronome.stateChanged.connect(self.toggle_metronome)
                
                row_layout.addWidget(w, 1)
                row_layout.addWidget(self.btn_bpm_match, 1)
                row_layout.addWidget(self.chk_metronome, 1)
                
                self.meta_widgets[name] = w
                self.form_meta.addRow(lbl, row_widget)
                QTimer.singleShot(0, self.update_bpm_match_button_height)

        self.audio_label = FileDropLabel("Drag song here")
        self.audio_label.setToolTip("Audio file of your song; converts to .mp3")
        self.audio_label.fileDropped.connect(self.handle_audio_drop)
        self.meta_widgets["AudioFilename"] = self.audio_label

        self.cover_label = FileDropLabel("Drag cover here")
        self.cover_label.setToolTip("Album art that will show up in game (converts to .png)")
        self.cover_label.fileDropped.connect(self.handle_cover_drop)

        self.video_label = FileDropLabel("Drag video here (.mp4/.webm)")
        self.video_label.setToolTip("Video file that will play on the playback stage (if video is shorter than song, it will show the last frame for the remainder of the song)")
        self.video_label.fileDropped.connect(self.handle_video_drop)

        self.txt_star_name = NoMenuLineEdit()
        self.txt_star_name.setToolTip("Custom name for this difficulty (changes “version” in file, can be anything)")
        self.txt_star_name.setPlaceholderText("Enter Custom Difficulty Name")
        self.txt_star_name.setStyleSheet(f"border-bottom: 3px solid {UI_THEME['accent']};")
        self.txt_star_name.textChanged.connect(self.update_metadata_from_ui)
        self.txt_star_name.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.txt_star_name.returnPressed.connect(lambda: self.timeline.setFocus())
        lbl_diff_name = QLabel("Difficulty\nName")
        lbl_diff_name.setToolTip("Custom name for this difficulty (changes “version” in file, can be anything)")
        lbl_diff_name.setObjectName("WhiteLabel")
        
        diff_effect = FastDropShadowEffect(lbl_diff_name)
        diff_effect.setBlurRadius(8)
        diff_effect.setColor(QColor(0, 0, 0, 200))
        diff_effect.setOffset(0, 2)
        set_manual_shadow(lbl_diff_name, diff_effect)
        
        self.form_meta.addRow(lbl_diff_name, self.txt_star_name)

        self.btn_resources = HoverButton("Resources")
        self.btn_resources.setToolTip("Audio file of your song; converts to .mp3 / Album art / Video background settings")
        self.btn_resources.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_resources.clicked.connect(self.open_resources_window)
        self.form_meta.addRow(self.btn_resources)

        self.resources_window = None
        
        self.gb_meta.setLayout(self.form_meta)
        self.gb_timing = QGroupBox()
        self.gb_timing.setObjectName("TimingGroup")

        self.timing_layout = QVBoxLayout()
        self.timing_layout.setContentsMargins(10, 5, 10, 10)
        
        self.lbl_timing_title = QLabel("Timing")
        self.lbl_timing_title.setObjectName("MetadataTitle")
        
        timing_effect = FastDropShadowEffect(self.lbl_timing_title)
        timing_effect.setBlurRadius(8)
        timing_effect.setColor(QColor(0, 0, 0, 200))
        timing_effect.setOffset(0, 2)
        set_manual_shadow(self.lbl_timing_title, timing_effect)
        
        self.timing_layout.addWidget(self.lbl_timing_title)
        
        self.lbl_current_time = QLabel("00:00:000")
        self.lbl_current_time.setObjectName("CurrentTimeLabel")
        self.lbl_current_time.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 0px;")
        self.lbl_current_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timing_layout.addWidget(self.lbl_current_time)

        self.lbl_current_ms = QLabel("0 ms")
        self.lbl_current_ms.setStyleSheet(f"font-size: 13px; font-weight: normal; color: {UI_THEME['text_secondary']}; margin-top: 0px; margin-bottom: 10px;")
        self.lbl_current_ms.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timing_layout.addWidget(self.lbl_current_ms)
        
        self.list_bpm = SmoothListWidget()
        self.list_bpm.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
            }
            QListWidget::viewport {
                background-color: transparent;
            }
            QListWidget::item:hover {
                background-color: rgba(255, 255, 255, 15);
                border: 1px solid transparent;
            }
            QListWidget::item:selected {
                background-color: rgba(255, 255, 255, 30);
                border: 1px solid transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                border: none;
                margin: 0px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
                border: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
            }
        """ + f"""
            QScrollBar::handle:vertical {{
                background-color: {UI_THEME['accent']};
                min-height: 20px;
                border-radius: 4px;
                border: none;
                margin: 0px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {UI_THEME['accent_hover']};
            }}
        """)
        self.timing_layout.addWidget(self.list_bpm)
        
        bpm_btn_layout = QHBoxLayout()
        self.btn_add_bpm = QPushButton("Add BPM")
        self.btn_add_bpm.setToolTip("Add timing point at time selection (type BPM below)")
        self.btn_add_bpm.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_add_bpm.clicked.connect(self.add_bpm_point)
        self.btn_del_bpm = QPushButton("Delete BPM")
        self.btn_del_bpm.setToolTip("Delete selected timing point")
        self.btn_del_bpm.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_del_bpm.clicked.connect(self.delete_bpm_point)
        bpm_btn_layout.addWidget(self.btn_add_bpm)
        bpm_btn_layout.addWidget(self.btn_del_bpm)
        self.timing_layout.addLayout(bpm_btn_layout)
        
        self.list_bpm.itemClicked.connect(self.seek_to_bpm_point)
        
        self.inp_bpm = QDoubleSpinBox()
        self.inp_bpm.setRange(1, 999)
        self.inp_bpm.setValue(120.0)
        self.inp_bpm.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.inp_bpm.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.timing_layout.addWidget(self.inp_bpm)
        
        self.gb_timing.setLayout(self.timing_layout)
        
        self.stack_meta_timing = QStackedWidget()
        self.stack_meta_timing.addWidget(self.gb_meta)
        self.stack_meta_timing.addWidget(self.gb_timing)
        left_layout.addWidget(self.stack_meta_timing)
        
        self.stack_meta_timing.setCurrentWidget(self.gb_meta)

        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self.save_current)
        self.btn_save.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_save.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #50ab4f;
                font-weight: bold;
                color: white;
                border-bottom: 3px solid #3d8a3c;
            }
            QPushButton:hover {
                background-color: #65c064;
                border-bottom-color: #3d8a3c;
            }
            QPushButton:pressed {
                background-color: #3d8a3c;
                border-bottom: 0px solid transparent;
                border-top: 3px solid transparent;
                padding-top: 9px;
                margin-bottom: 0px;
            }
        """)
        
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self.delete_current_difficulty)
        self.btn_delete.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_delete.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_delete.setStyleSheet("""
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
        
        current_chart_ops_layout = QHBoxLayout()
        current_chart_ops_layout.addWidget(self.btn_save)
        current_chart_ops_layout.addWidget(self.btn_delete)
        left_layout.addLayout(current_chart_ops_layout)
        

        
        QApplication.instance().installEventFilter(self)
        
        self.btn_settings = QPushButton("Settings")
        self.btn_settings.clicked.connect(self.open_settings)
        self.btn_settings.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        left_layout.addWidget(self.btn_settings)
        
        self.sidebar_vis = SidebarVisualizer()
        self.sidebar_vis.set_visible_based_on_height(self.height())
        left_layout.addWidget(self.sidebar_vis, 1)

        right_panel = QWidget()
        right_panel.setObjectName("RightPanel")
        right_layout = QVBoxLayout(right_panel)

        toolbar = QHBoxLayout()
        self.btn_play = QPushButton("Play / Pause")
        self.btn_play.setToolTip("Why are you looking at this tooltip? You know what this does.")
        self.btn_play.setMinimumWidth(160)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        toolbar.addWidget(self.btn_play)
        toolbar.addSpacing(20)
        
        tool_group_widget = QWidget()
        tool_group_widget.setObjectName("ToolTypeContainer")
        tool_group_layout = QVBoxLayout(tool_group_widget)
        tool_group_layout.setContentsMargins(0, 0, 0, 0)
        tool_group_layout.setSpacing(2)
        
        tool_type_layout = QHBoxLayout()
        tool_type_layout.setSpacing(2)
        tool_type_layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_tool_note = QPushButton("Note")
        self.btn_tool_note.setToolTip("Contains all standard notes")
        self.btn_tool_note.setCheckable(True)
        self.btn_tool_note.setChecked(True)
        self.btn_tool_note.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tool_note.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_tool_note.clicked.connect(lambda: self.change_tool_type("note"))
        
        self.btn_tool_brawl = QPushButton("Brawl")
        self.btn_tool_brawl.setToolTip("Contains all cop notes")
        self.btn_tool_brawl.setCheckable(True)
        self.btn_tool_brawl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tool_brawl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_tool_brawl.clicked.connect(lambda: self.change_tool_type("brawl"))
        
        self.btn_tool_event = QPushButton("Event")
        self.btn_tool_event.setToolTip("Contains all camera triggers")
        self.btn_tool_event.setCheckable(True)
        self.btn_tool_event.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tool_event.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_tool_event.clicked.connect(lambda: self.change_tool_type("event"))

        self.btn_tool_custom = QPushButton("Custom")
        self.btn_tool_custom.setToolTip("Contains custom notes")
        self.btn_tool_custom.setCheckable(True)
        self.btn_tool_custom.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tool_custom.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_tool_custom.clicked.connect(lambda: self.change_tool_type("custom"))
        self.btn_tool_custom.hide()
        
        tool_type_layout.addWidget(self.btn_tool_note)
        tool_type_layout.addWidget(self.btn_tool_brawl)
        tool_type_layout.addWidget(self.btn_tool_event)
        tool_type_layout.addWidget(self.btn_tool_custom)
        tool_group_layout.addLayout(tool_type_layout)
        
        self.tool_stack = QStackedWidget()
        self.tool_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tool_group_layout.addWidget(self.tool_stack)
        
        self.note_type_container = QWidget()
        self.note_type_container.setObjectName("NoteTypeContainer")
        note_type_layout = QHBoxLayout(self.note_type_container)
        note_type_layout.setContentsMargins(0, 0, 0, 0)
        note_type_layout.setSpacing(2)
        
        self.btn_note_normal = QPushButton("Normal")
        self.btn_note_normal.setToolTip("Basic single-hit note")
        self.btn_note_normal.setCheckable(True)
        self.btn_note_normal.setChecked(True)
        self.btn_note_normal.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_note_normal.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_note_normal.clicked.connect(lambda: self.change_note_type("normal"))
        
        self.btn_note_spike = QPushButton("Spike")
        self.btn_note_spike.setToolTip("Enter opposite lane to dodge")
        self.btn_note_spike.setCheckable(True)
        self.btn_note_spike.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_note_spike.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_note_spike.clicked.connect(lambda: self.change_note_type("spike"))
        
        self.btn_note_hold = QPushButton("Hold")
        self.btn_note_hold.setToolTip("Hit to initiate hold, release at the end")
        self.btn_note_hold.setCheckable(True)
        self.btn_note_hold.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_note_hold.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_note_hold.clicked.connect(lambda: self.change_note_type("hold"))
        
        self.btn_note_screamer = QPushButton("Double")
        self.btn_note_screamer.setToolTip("Hit once at start, then again in the opposite lane at the end")
        self.btn_note_screamer.setCheckable(True)
        self.btn_note_screamer.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_note_screamer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_note_screamer.clicked.connect(lambda: self.change_note_type("screamer"))
        
        self.btn_note_spam = QPushButton("Spam")
        self.btn_note_spam.setToolTip("Mash note. Hit as much as you want - only the first hit counts")
        self.btn_note_spam.setCheckable(True)
        self.btn_note_spam.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_note_spam.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_note_spam.clicked.connect(lambda: self.change_note_type("spam"))

        self.btn_note_freestyle = QPushButton("Freestyle")
        self.btn_note_freestyle.setToolTip("Hit with any button. Multiple freestyle notes in a row with no other notes between will create subnotes grouped to the original note")
        self.btn_note_freestyle.setCheckable(True)
        self.btn_note_freestyle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_note_freestyle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_note_freestyle.clicked.connect(lambda: self.change_note_type("freestyle"))
        
        self.combo_note_style = QComboBox()
        self.combo_note_style.setToolTip("Note Modifier:\nNormal: Notes will appear normally\nHide: Notes will disappear shortly before reaching the judgement line\nFly in: Notes will “Fly In” from the top and bottom of the screen (NOISZ notes)")
        self.combo_note_style.setView(SmoothListView(self.combo_note_style))
        self.combo_note_style.addItems(["Normal", "Hide", "Fly In"])
        self.combo_note_style.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_note_style.setFixedWidth(90)
        
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
        
        self.tool_stack.addWidget(self.note_type_container)
        
        self.brawl_type_container = QWidget()
        self.brawl_type_container.setObjectName("BrawlTypeContainer")
        brawl_type_layout = QHBoxLayout(self.brawl_type_container)
        brawl_type_layout.setContentsMargins(0, 0, 0, 0)
        brawl_type_layout.setSpacing(0)
        
        self.btn_brawl_hit = QPushButton("Cop Hit")
        self.btn_brawl_hit.setToolTip("The cop equivalent of a “Normal” note")
        self.btn_brawl_hit.setCheckable(True)
        self.btn_brawl_hit.setChecked(True)
        self.btn_brawl_hit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_brawl_hit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_brawl_hit.setMinimumWidth(1)
        self.btn_brawl_hit.clicked.connect(lambda: self.change_brawl_type("hit"))
        
        self.btn_brawl_final = QPushButton("Cop Knockout")
        self.btn_brawl_final.setToolTip("Removes the cop and plays its knockout animation, is the equivalent of a “Normal” note")
        self.btn_brawl_final.setCheckable(True)
        self.btn_brawl_final.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_brawl_final.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_brawl_final.setMinimumWidth(1)
        self.btn_brawl_final.clicked.connect(lambda: self.change_brawl_type("final"))

        self.btn_brawl_hold = QPushButton("Cop Hold")
        self.btn_brawl_hold.setToolTip("The cop equivalent of a “Hold” note")
        self.btn_brawl_hold.setCheckable(True)
        self.btn_brawl_hold.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_brawl_hold.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_brawl_hold.setMinimumWidth(1)
        self.btn_brawl_hold.clicked.connect(lambda: self.change_brawl_type("hold"))

        self.btn_brawl_hold_ko = QPushButton("Cop Hold Knockout")
        self.btn_brawl_hold_ko.setToolTip("Removes the cop and plays its knockout animation, is the equivalent of a “Hold” note")
        self.btn_brawl_hold_ko.setCheckable(True)
        self.btn_brawl_hold_ko.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_brawl_hold_ko.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_brawl_hold_ko.setMinimumWidth(1)
        self.btn_brawl_hold_ko.clicked.connect(lambda: self.change_brawl_type("hold_knockout"))

        self.btn_brawl_spam = QPushButton("Cop Spam")
        self.btn_brawl_spam.setToolTip("The cop equivalent of a “Spam” note, can only be placed in the bottom lane")
        self.btn_brawl_spam.setCheckable(True)
        self.btn_brawl_spam.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_brawl_spam.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_brawl_spam.setMinimumWidth(1)
        self.btn_brawl_spam.clicked.connect(lambda: self.change_brawl_type("spam"))

        self.btn_brawl_spam_ko = QPushButton("Cop Spam Knockout")
        self.btn_brawl_spam_ko.setToolTip("Removes the cop and plays its knockout animation, is the equivalent of a “Spam” note, can only be placed in the bottom lane")
        self.btn_brawl_spam_ko.setCheckable(True)
        self.btn_brawl_spam_ko.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_brawl_spam_ko.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_brawl_spam_ko.setMinimumWidth(1)
        self.btn_brawl_spam_ko.clicked.connect(lambda: self.change_brawl_type("spam_knockout"))

        self.combo_brawl_cop = QComboBox()
        self.combo_brawl_cop.setToolTip("Changes which cop object the notes are to be played on. Up to 4 can be in play at a single time")
        self.combo_brawl_cop.setView(SmoothListView(self.combo_brawl_cop))
        self.combo_brawl_cop.addItems(["Cop 1", "Cop 2", "Cop 3", "Cop 4"])
        self.combo_brawl_cop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_brawl_cop.setMinimumWidth(40)
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
        
        self.tool_stack.addWidget(self.brawl_type_container)

        self.event_type_container = QWidget()
        self.event_type_container.setObjectName("EventTypeContainer")
        event_type_layout = QHBoxLayout(self.event_type_container)
        event_type_layout.setContentsMargins(0, 0, 0, 0)
        event_type_layout.setSpacing(0)
        
        self.btn_event_flip = QPushButton("Flip")
        self.btn_event_flip.setToolTip("Change direction notes appear from (only affects freestyles in Center mode)")
        self.btn_event_flip.setCheckable(True)
        self.btn_event_flip.setChecked(True)
        self.btn_event_flip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_event_flip.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_event_flip.clicked.connect(lambda: self.change_event_type("flip"))
        
        self.btn_event_toggle = QPushButton("ToggleCenter")
        self.btn_event_toggle.setToolTip("Toggles camera viewing both sides or only left/right")
        self.btn_event_toggle.setCheckable(True)
        self.btn_event_toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_event_toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_event_toggle.clicked.connect(lambda: self.change_event_type("toggle_center"))

        self.btn_event_instant = QPushButton("InstantFlip")
        self.btn_event_instant.setToolTip("Same as Flip, but without anticipation")
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
        
        self.tool_stack.addWidget(self.event_type_container)

        self.custom_type_container = QWidget()
        self.custom_type_container.setObjectName("CustomTypeContainer")
        self.custom_type_layout = QHBoxLayout(self.custom_type_container)
        self.custom_type_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_type_layout.setSpacing(2)
        self.combo_custom_note = AllCustomNotesComboBox()
        self.combo_custom_note.setView(SmoothListView(self.combo_custom_note))
        self.combo_custom_note.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_custom_note.currentIndexChanged.connect(self.change_custom_note)
        self.custom_note_buttons = []
        self.custom_note_button_group = QButtonGroup(self.custom_type_container)
        self.custom_note_button_group.setExclusive(True)
        self._updating_custom_note_buttons = False
        self.combo_custom_type = QComboBox()
        self.combo_custom_type.setView(SmoothListView(self.combo_custom_type))
        self.combo_custom_type.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_custom_type.setProperty("animation_overlay_right_inset", 2)
        self.combo_custom_type.currentIndexChanged.connect(self.change_custom_type)
        self.custom_type_layout.addWidget(self.combo_custom_note)
        self.custom_type_layout.addWidget(self.combo_custom_type)
        self.tool_stack.addWidget(self.custom_type_container)
        
        toolbar.addWidget(tool_group_widget, 1) 
        toolbar.addStretch() 
        
        lbl_speed = QLabel("Speed:")
        lbl_speed.setToolTip("Chart playback speed")
        lbl_speed.setObjectName("WhiteLabel")
        
        speed_effect = FastDropShadowEffect(lbl_speed)
        speed_effect.setBlurRadius(8)
        speed_effect.setColor(QColor(0, 0, 0, 200))
        speed_effect.setOffset(0, 2)
        set_manual_shadow(lbl_speed, speed_effect)
        
        toolbar.addWidget(lbl_speed)
        self.combo_speed = QComboBox()
        self.combo_speed.setToolTip("Chart playback speed")
        self.combo_speed.setView(SmoothListView(self.combo_speed))
        self.combo_speed.addItems(["0.25x", "0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
        self.combo_speed.setCurrentText("1.0x")
        self.combo_speed.currentTextChanged.connect(self.change_speed)
        self.combo_speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_speed.setFixedWidth(70)
        toolbar.addWidget(self.combo_speed)

        lbl_grid = QLabel("Grid:")
        lbl_grid.setToolTip("How many snap points per bar of music, this works like a time signature")
        lbl_grid.setObjectName("WhiteLabel")
        
        grid_effect = FastDropShadowEffect(lbl_grid)
        grid_effect.setBlurRadius(8)
        grid_effect.setColor(QColor(0, 0, 0, 200))
        grid_effect.setOffset(0, 2)
        set_manual_shadow(lbl_grid, grid_effect)
        
        toolbar.addWidget(lbl_grid)
        self.spin_grid = CleanSpinBox()
        self.spin_grid.setToolTip("How many snap points per bar of music, this works like a time signature")
        self.spin_grid.setRange(1, 64)
        self.spin_grid.setValue(4)
        self.spin_grid.setFixedWidth(60)
        self.spin_grid.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_grid.valueChanged.connect(self.change_grid)
        self.spin_grid.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        toolbar.addWidget(self.spin_grid)
        
        right_layout.addLayout(toolbar)
        
        self.timeline_scrollbar = TimerScrollBar(Qt.Orientation.Horizontal)
        self.timeline_scrollbar.setEnabled(False)
        self.timeline_scrollbar.valueChanged.connect(self.on_scrollbar_changed)
        self.timeline_scrollbar.sliderReleased.connect(self.finalize_video_scroll_seek)
        right_layout.addWidget(self.timeline_scrollbar)
        
        self.timeline = TimelineWidget(self)
        self.timeline.set_scrollbar(self.timeline_scrollbar)
        right_layout.addWidget(self.timeline)
        
        timeline_layout = QVBoxLayout(self.timeline)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        self.start_screen = StartScreen(self)
        timeline_layout.addWidget(self.start_screen)
        
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)
        self.update_star_visibility()
        apply_shadows_to_container(self)

    def eventFilter(self, obj, event):
        event_type = event.type()
        if event_type == QEvent.Type.Resize and obj is getattr(self, 'custom_type_container', None):
            self.update_custom_note_button_visibility(event.size().width())
        elif event_type in (
            QEvent.Type.ApplicationDeactivate,
            QEvent.Type.WindowDeactivate,
        ):
            self.clear_pressed_input_state()
        elif event_type == QEvent.Type.MouseButtonPress:
            focus_widget = QApplication.focusWidget()
            if focus_widget and isinstance(focus_widget, (QLineEdit, QSpinBox, QDoubleSpinBox, CleanSpinBox, CleanDoubleSpinBox)):
                should_clear = True
                if focus_widget == obj:
                    should_clear = False
                elif focus_widget.parent() == obj:
                    should_clear = False
                
                if should_clear:
                    focus_widget.clearFocus()

            if obj.property("defer_scroll_control_click"):
                pass
            elif isinstance(obj, QPushButton):
                if obj is self.btn_play or obj.property("is_custom_sound_btn"):
                    pass 
                else:
                    with OutputSuppressor():
                        self.play_ui_sound('UI Click', self.get_pan_for_widget(obj))
            elif isinstance(obj, QComboBox):
                 was_open = obj.view().isVisible() if obj.view() else False
                 if not was_open:
                      with OutputSuppressor():
                          self.play_ui_sound('UI Click', self.get_pan_for_widget(obj))
            elif isinstance(obj, QSlider):
                  self.last_slider_val[id(obj)] = obj.value()
                     
        elif event_type == QEvent.Type.Enter:
             if isinstance(obj, QComboBox):
                  v = obj.view()
                  if v and not v.property("click_connected"):
                       v.setProperty("click_connected", True)
                       v.pressed.connect(lambda _: self.play_ui_sound_suppressed('UI Click', self.get_pan_for_widget(obj)))

        elif event_type == QEvent.Type.MouseButtonRelease:
            if obj.property("defer_scroll_control_click"):
                pass
            elif isinstance(obj, QCheckBox) and obj.isEnabled():
                was_checked = obj.isChecked()
                def check_toggle(o=obj, old=was_checked):
                    try:
                        if o.isChecked() != old:
                            if o.isChecked():
                                 with OutputSuppressor():
                                     self.play_ui_sound('UI Tick On', self.get_pan_for_widget(o))
                            else:
                                 with OutputSuppressor():
                                     self.play_ui_sound('UI Tick Off', self.get_pan_for_widget(o))
                    except: pass
                QTimer.singleShot(0, check_toggle)
            elif isinstance(obj, QSlider):
                  self.last_slider_val.pop(id(obj), None)
            elif isinstance(obj, QComboBox):
                 is_open = obj.view().isVisible() if obj.view() else False
                 if not is_open:
                      with OutputSuppressor():
                          self.play_ui_sound('UI Click', self.get_pan_for_widget(obj))
                     
        elif event_type == QEvent.Type.FocusIn:
            if isinstance(obj, QLineEdit) or isinstance(obj, QSpinBox) or isinstance(obj, QDoubleSpinBox):
                 with OutputSuppressor():
                     self.play_ui_sound('UI Text', self.get_pan_for_widget(obj))
                 
        elif event_type == QEvent.Type.Wheel:
            if isinstance(obj, (QComboBox, QSpinBox, QDoubleSpinBox, CleanSpinBox, CleanDoubleSpinBox)):
                 if isinstance(obj, (IgnoreWheelComboBox, IgnoreWheelSlider)):
                     return False
                 with OutputSuppressor():
                     self.play_ui_sound('UI Scroll', self.get_pan_for_widget(obj))
        
        elif event_type == QEvent.Type.MouseMove:
             if isinstance(obj, QSlider) and obj.isSliderDown():
                  if obj.property("skip_global_sound"):
                      return super().eventFilter(obj, event)
                      
                  last = self.last_slider_val.get(id(obj), obj.value())
                  curr = obj.value()
                  step_thresh = max(1, (obj.maximum() - obj.minimum()) // 30)
                  if abs(curr - last) >= step_thresh:
                       current_time = time.time()
                       if current_time - self.last_global_slider_sound_time > 0.03:
                           val_range = obj.maximum() - obj.minimum()
                           if val_range > 0:
                               ratio = (curr - obj.minimum()) / float(val_range)
                           else:
                               ratio = 0.5
                           i = int(round((ratio - 0.5) * 48))
                           i = max(-24, min(24, i))
                           sound_name = f"UI Scroll P{i}" if i != 0 and f"UI Scroll P{i}" in self.sounds else 'UI Scroll'
                           with OutputSuppressor():
                               self.play_ui_sound(sound_name, self.get_pan_for_widget(obj))
                           self.last_global_slider_sound_time = current_time
                           self.last_slider_val[id(obj)] = curr
        
        elif event_type == QEvent.Type.KeyPress:
             if isinstance(obj, QLineEdit):
                  ke = event
                  if ke.key() == Qt.Key.Key_Return or ke.key() == Qt.Key.Key_Enter:
                       with OutputSuppressor():
                           self.play_ui_sound('UI Tick On', self.get_pan_for_widget(obj))
             
             kb = getattr(self, 'current_keybinds', DEFAULT_KEYBINDS)
             pk = getattr(self, 'pressed_keys', set())
             if check_keybind_match(kb.get("switch_meta_timing", "Tab"), event.key(), event.modifiers(), pk) and not event.isAutoRepeat():
                  if getattr(self, 'start_screen', None) and self.start_screen.isVisible():
                      return True
                  focus_widget = QApplication.focusWidget()
                  if not isinstance(focus_widget, (QLineEdit, QSpinBox, QDoubleSpinBox, CleanSpinBox, CleanDoubleSpinBox)):
                      current = self.stack_meta_timing.currentWidget()
                      if current == self.gb_meta:
                          self.play_ui_sound_suppressed('UI Click', self.get_pan_for_widget(self.btn_tab_timing))
                          self.btn_tab_timing.animateClick()
                          self.stack_meta_timing.setCurrentWidget(self.gb_timing)
                          self.btn_tab_timing.setChecked(True)
                      else:
                          self.play_ui_sound_suppressed('UI Click', self.get_pan_for_widget(self.btn_tab_meta))
                          self.btn_tab_meta.animateClick()
                          self.stack_meta_timing.setCurrentWidget(self.gb_meta)
                          self.btn_tab_meta.setChecked(True)
                      return True
                 
        return super().eventFilter(obj, event)

    def calculate_pan_relative(self, local_x):
        if not self.enable_3d_sound: return 0.0
        try:
            if hasattr(self, 'timeline'):
                tl_width = self.timeline.width()
                if tl_width > 0:
                     center = tl_width / 2
                     diff = local_x - center
                     ratio = diff / (tl_width / 1.5)
                     return max(-0.7, min(0.7, ratio))
        except:
             pass
        return 0.0

    def calculate_pan(self, global_x):
         if hasattr(self, 'timeline'):
              try:
                   tl_global_x = self.timeline.mapToGlobal(QPoint(0,0)).x()
                   local_x = global_x - tl_global_x
                   return self.calculate_pan_relative(local_x)
              except: pass
         return 0.0

    def get_pan_for_widget(self, widget):
         try:
             global_pos = widget.mapToGlobal(QPoint(0, 0))
             center_x = global_pos.x() + widget.width() / 2
             return self.calculate_pan(center_x)
         except:
             pass
         return 0.0

    def play_ui_sound_suppressed(self, name, pan=0.0):
         with OutputSuppressor():
             self.play_ui_sound(name, pan)

    def play_ui_sound(self, name, pan=0.0):
         if not self.enable_3d_sound: pan = 0.0
         key = SOUND_FILES_MAP.get(name)
         if key and key in self.sounds:
             try:
                 with OutputSuppressor():
                    s = self.sounds[key]
                    ui_vol = self.get_effective_ui_volume()
                    try: s.set_volume(ui_vol)
                    except: pass
                    channel = s.play()
                    if channel:
                        left_vol = 1.0 - max(0.0, pan)
                        right_vol = 1.0 + min(0.0, pan)
                        channel.set_volume(left_vol * ui_vol, right_vol * ui_vol)
             except: pass

    def play_toast_enter_sound(self):
         variants = getattr(self, "toast_enter_sound_variants", ())
         self.play_ui_sound(random.choice(variants) if variants else "UI Toast Enter")

    def play_toast_exit_sound(self):
         variants = getattr(self, "toast_exit_sound_variants", ())
         self.play_ui_sound(random.choice(variants) if variants else "UI Toast Exit")

    def play_project_cover_enter_sound(self):
         variants = getattr(self, "project_cover_enter_sound_variants", ())
         self.play_ui_sound(random.choice(variants) if variants else "UI Cover Enter")

    def ensure_game_path(self):
        found_path = None
        found_path = find_unbeatable_root()

        if sys.platform.startswith("win"):
            
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
        else:
            if not found_path:
                try:
                    p_file = Path.home() /".config" / "CBM_Editor"/ "path.json"
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
            msg = QMessageBox(
                QMessageBox.Icon.Warning,
                "Game Path Not Found",
                "UNBEATABLE Path not found.",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                self
            )
            msg.setInformativeText("Please select the UNBEATABLE installation folder.")

            if msg.exec() == QMessageBox.StandardButton.Ok:
                folder = QFileDialog.getExistingDirectory(
                    self,
                    "Select UNBEATABLE Folder",
                    "",
                    QFileDialog.Option.DontUseNativeDialog
                )

                if folder:
                    p = Path(folder)
                    if p.exists():
                        found_path = p
                    else:
                        sys.exit()
            else:
                sys.exit()

        self.game_root_path = found_path
        
        try:
            p_file = self.get_appdata_dir() / "path.json"
            with open(p_file, 'w') as f:
                json.dump({"game_path": str(self.game_root_path)}, f)
        except Exception as e:
            print(f"LOAD UI BG ERROR: {e}")
            import traceback
            traceback.print_exc()
            
        if self.game_root_path:
            display_text = f"Game detected at: {self.game_root_path}"
            display_text = display_text.replace("\\", "\\\u200b").replace("/", "/\u200b")
            self.lbl_path.setText(display_text)
            self.setup_custom_maps_path()
            self.load_game_config() 
            
            bg_target = self.game_root_path / "ChartEditorResources" / "bg.png"
            if self.current_background and self.current_background != "None":
                bg_src = self.game_root_path / "ChartEditorResources" / "backgrounds" / self.current_background
                if bg_src.exists():
                     try: apply_bg_image_with_blur(str(bg_src), str(bg_target), getattr(self, 'background_blur', 0))
                     except Exception as e: print("bg err", e)
            elif self.current_background == "None":
                 if bg_target.exists():
                     try: os.remove(bg_target)
                     except: pass

            if hasattr(self, 'timeline'):
                self.timeline.load_background_image()
                self.timeline.update()

            self.load_sounds()
            
            base_sounds = get_base_path()
            if not base_sounds.endswith("sounds"):
                base_sounds = os.path.join(base_sounds, "sounds")
            
            icon_name = "icon_pre.png" if PREVIEW_VERSION else "icon.png"
            i_src = os.path.join(base_sounds, icon_name)
            i_dst = self.game_root_path / "ChartEditorResources" / icon_name
            
            if not i_dst.exists() and os.path.exists(i_src):
                try:
                    shutil.copy2(i_src, i_dst)
                except:
                    pass

            icon_path = self.game_root_path / "ChartEditorResources" / icon_name
            if icon_path.exists():
                app_icon = QIcon(str(icon_path))
                self.setWindowIcon(app_icon)
                QApplication.setWindowIcon(app_icon)

        else:
            self.lbl_path.setText("Game path not set")

    def is_game_modded(self):
        if not self.game_root_path:
            return False
        try:
            bepinex_path = None
            for p in self.game_root_path.iterdir():
                if p.is_dir() and p.name.lower() == "bepinex":
                    bepinex_path = p
                    break
            
            if not bepinex_path:
                return False
                
            plugins_path = None
            for p in bepinex_path.iterdir():
                if p.is_dir() and p.name.lower() == "plugins":
                    plugins_path = p
                    break
                    
            if not plugins_path:
                return False
                
            for p in plugins_path.rglob("*"):
                if "custombeatmaps" in p.name.lower():
                    return True
        except Exception:
            pass
        return False

    def setup_custom_maps_path(self):
        if self.game_root_path:
            if self.is_game_modded():
                self.game_custom_maps_path = self.game_root_path / "USER_PACKAGES"
            elif sys.platform.startswith("linux"):
                self.game_custom_maps_path = find_linux_custom_songs_path(self.game_root_path)
            else:
                appdata_local_low = os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'LocalLow')
                self.game_custom_maps_path = Path(appdata_local_low) / "D-CELL GAMES" / "UNBEATABLE" / "CustomSongs"
                
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
        for sound in list(self.sounds.values()):
            sound.free()
        self.sounds.clear()
        if self.metronome_sound:
            self.metronome_sound.free()
            self.metronome_sound = None
            
        base_sounds = get_base_path()
        if not base_sounds.endswith("sounds"):
            base_sounds = os.path.join(base_sounds, "sounds")

        bg_src_dir = os.path.join(base_sounds, "backgrounds")
        bg_dst_dir = self.game_root_path / "ChartEditorResources" / "backgrounds"
        
        if os.path.exists(bg_src_dir) and not bg_dst_dir.exists():
            try:
                shutil.copytree(bg_src_dir, bg_dst_dir)
            except:
                pass

        for key in list(SOUND_FILES_MAP):
            if key.startswith("UI Drag P") or key.startswith("UI Scroll P") or key.startswith("UI Toast Enter V") or key.startswith("UI Toast Exit V") or key.startswith("UI Cover Enter V"):
                SOUND_FILES_MAP.pop(key, None)
        self.toast_enter_sound_variants = []
        self.toast_exit_sound_variants = []
        self.project_cover_enter_sound_variants = []

        pitch_sources = []

        for key, filename in list(SOUND_FILES_MAP.items()):
            target_path = self.game_root_path / "ChartEditorResources" / filename
            
            if not target_path.exists():
                source_path = os.path.join(base_sounds, filename)
                if os.path.exists(source_path):
                    try:
                        shutil.copy2(source_path, target_path)
                    except:
                        pass

            if key in ('UI Drag', 'UI Scroll') and target_path.exists():
                pitch_sources.append((key, filename))
            
            if target_path.exists():
                try:
                    if key == 'Metronome':
                        self.metronome_sound = self.audio_engine.load_sound(target_path)
                    else:
                        self.sounds[filename] = self.audio_engine.load_sound(target_path)
                        if key.startswith("UI"):
                             self.sounds[filename].set_volume(self.get_effective_ui_volume())
                        else:
                             self.sounds[filename].set_volume(self.get_effective_fx_volume())
                except Exception as e:
                    pass

        custom_hitsound_files = set()
        for note in getattr(self, "custom_notes", []):
            for type_data in note.get("types", []):
                hitsound = str(type_data.get("hitsound") or "")
                if not hitsound.startswith("custom:"):
                    continue
                filename = hitsound.removeprefix("custom:")
                if filename and Path(filename).name == filename:
                    custom_hitsound_files.add(filename)
        for filename in custom_hitsound_files:
            target_path = self.game_root_path / "ChartEditorResources" / filename
            if not target_path.is_file():
                continue
            try:
                self.sounds[filename] = self.audio_engine.load_sound(target_path)
                self.sounds[filename].set_volume(self.get_effective_fx_volume())
            except Exception:
                pass

        try:
            import hashlib
            note_filename = ORIGINAL_SOUND_FILES_MAP.get('Note')
            hold_filename = ORIGINAL_SOUND_FILES_MAP.get('Hold Start')
            if note_filename and hold_filename:
                note_target = self.game_root_path / "ChartEditorResources" / note_filename
                hold_target = self.game_root_path / "ChartEditorResources" / hold_filename
                
                base_sounds_dir = get_base_path()
                if not base_sounds_dir.endswith("sounds"):
                    base_sounds_dir = os.path.join(base_sounds_dir, "sounds")
                    
                note_orig = os.path.join(base_sounds_dir, note_filename)
                hold_orig = os.path.join(base_sounds_dir, hold_filename)
                
                def get_hash(path):
                    try:
                        with open(path, 'rb') as f:
                            return hashlib.file_digest(f, 'md5').hexdigest()
                    except:
                        return ""
                
                note_orig_hash = get_hash(note_orig)
                hold_orig_hash = get_hash(hold_orig)
                self.is_note_default = (get_hash(note_target) == note_orig_hash) if note_orig_hash else False
                self.is_hold_default = (get_hash(hold_target) == hold_orig_hash) if hold_orig_hash else False
                self.is_default_conflict_active = self.is_note_default and self.is_hold_default
            else:
                self.is_default_conflict_active = False
        except Exception as e:
            self.is_default_conflict_active = False

        if pitch_sources:
            for key, filename in pitch_sources:
                source_sound = self.sounds.get(filename)
                if not source_sound:
                    continue
                for i in range(-24, 25):
                    if i == 0:
                        continue
                    name = f"{key} P{i}"
                    sound = source_sound.create_variant(2 ** ((i * 0.5) / 12.0))
                    sound.set_volume(self.get_effective_ui_volume())
                    self.sounds[name] = sound
                    SOUND_FILES_MAP[name] = name

        toast_enter_filename = SOUND_FILES_MAP.get("UI Toast Enter")
        toast_enter_sound = self.sounds.get(toast_enter_filename)
        if toast_enter_sound:
            for index, semitones in enumerate((-0.75, -0.45, -0.2, 0.2, 0.45, 0.75), 1):
                name = f"UI Toast Enter V{index}"
                sound = toast_enter_sound.create_variant(2 ** (semitones / 12.0))
                sound.set_volume(self.get_effective_ui_volume())
                self.sounds[name] = sound
                SOUND_FILES_MAP[name] = name
                self.toast_enter_sound_variants.append(name)

        toast_exit_filename = SOUND_FILES_MAP.get("UI Toast Exit")
        toast_exit_sound = self.sounds.get(toast_exit_filename)
        if toast_exit_sound:
            for index, semitones in enumerate((-0.75, -0.45, -0.2, 0.2, 0.45, 0.75), 1):
                name = f"UI Toast Exit V{index}"
                sound = toast_exit_sound.create_variant(2 ** (semitones / 12.0))
                sound.set_volume(self.get_effective_ui_volume())
                self.sounds[name] = sound
                SOUND_FILES_MAP[name] = name
                self.toast_exit_sound_variants.append(name)

        cover_enter_filename = SOUND_FILES_MAP.get("UI Cover Enter")
        cover_enter_sound = self.sounds.get(cover_enter_filename)
        if cover_enter_sound:
            for index, semitones in enumerate((-0.9, -0.65, -0.4, -0.15, 0.15, 0.4, 0.65, 0.9), 1):
                name = f"UI Cover Enter V{index}"
                sound = cover_enter_sound.create_variant(2 ** (semitones / 12.0))
                sound.set_volume(self.get_effective_ui_volume())
                self.sounds[name] = sound
                SOUND_FILES_MAP[name] = name
                self.project_cover_enter_sound_variants.append(name)

    def open_project(self):
        if not self.confirm_unsaved_changes("load"):
            return

        start_dir = str(self.game_custom_maps_path) if self.game_custom_maps_path else ""
        folder = QFileDialog.getExistingDirectory(self, "Select Project Folder", start_dir)
        if not folder: return
        self.load_project_from_path(Path(folder))

    def export_project(self):
        if not hasattr(self, 'project_folder') or not self.project_folder:
            dlg = QDialog(self)
            dlg.setWindowTitle("Warning")
            dlg.setModal(True)
            dlg.setMinimumWidth(350)
            dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
            layout = QVBoxLayout(dlg)
            top_layout = QHBoxLayout()
            icon_label = QLabel()
            from PyQt6.QtWidgets import QStyle
            icon_pixmap = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning).pixmap(32, 32)
            icon_label.setPixmap(icon_pixmap)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            top_layout.addWidget(icon_label)
            lbl = QLabel("No project is currently loaded to export.")
            lbl.setWordWrap(True)
            top_layout.addWidget(lbl, stretch=1)
            layout.addLayout(top_layout)
            btn = QPushButton("OK")
            btn.clicked.connect(dlg.accept)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            layout.addWidget(btn)
            dlg.setFixedSize(max(350, dlg.sizeHint().width()), dlg.sizeHint().height())
            dlg.exec()
            return

        title = "UnknownTitle"
        artist = "UnknownArtist"
        mapper = "UnknownMapper"
        if hasattr(self, 'current_chart') and self.current_chart and hasattr(self.current_chart, 'metadata'):
            title = getattr(self.current_chart.metadata, 'Title', title) or title
            artist = getattr(self.current_chart.metadata, 'Artist', artist) or artist
            mapper = getattr(self.current_chart.metadata, 'Creator', mapper) or mapper
            
        import re
        safe_title = re.sub(r'[\\/*?:"<>|]', "", title)
        safe_artist = re.sub(r'[\\/*?:"<>|]', "", artist)
        safe_mapper = re.sub(r'[\\/*?:"<>|]', "", mapper)
        
        default_name = f"{safe_title} - {safe_artist} ({safe_mapper}).zip"
        
        if default_name == "UnknownTitle - UnknownArtist (UnknownMapper).zip":
            default_name = f"{self.project_folder.name}.zip"

        out_path, _ = QFileDialog.getSaveFileName(self, "Export Project", default_name, "ZIP File (*.zip)")
        if not out_path:
            return

        if not out_path.endswith('.zip'):
            out_path += '.zip'
            
        import zipfile
        import os
        
        base_dir = str(self.project_folder)
        
        try:
            with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(base_dir):
                    if 'cbm_files' in dirs:
                        dirs.remove('cbm_files')
                        
                    for f in files:
                        file_path = os.path.join(root, f)
                        if os.path.abspath(file_path) == os.path.abspath(out_path):
                            continue
                        arcname = os.path.relpath(file_path, base_dir)
                        zipf.write(file_path, arcname)
            dlg = QDialog(self)
            dlg.setWindowTitle("Export Success")
            dlg.setModal(True)
            dlg.setMinimumWidth(450)
            dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
            
            layout = QVBoxLayout(dlg)
            
            top_layout = QHBoxLayout()
            icon_label = QLabel()
            from PyQt6.QtWidgets import QStyle
            icon_pixmap = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation).pixmap(32, 32)
            icon_label.setPixmap(icon_pixmap)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            top_layout.addWidget(icon_label)
            
            lbl = QLabel(f"Project exported successfully to:\n{out_path}")
            lbl.setWordWrap(True)
            top_layout.addWidget(lbl, stretch=1)
            
            layout.addLayout(top_layout)
            
            btn = QPushButton("OK")
            btn.clicked.connect(dlg.accept)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            layout.addWidget(btn)
            
            dlg.setFixedSize(max(450, dlg.sizeHint().width()), dlg.sizeHint().height())
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export project:\n{e}")
            import traceback
            traceback.print_exc()

    def load_project_from_path(self, folder_path: Path):
        self.is_loading_project = True
        try:
            self._load_project_from_path(folder_path)
        finally:
            self.is_loading_project = False
            if getattr(self, "current_chart", None):
                self.update_ui_from_metadata()
                self.update_bpm_list()
            if hasattr(self, "timeline"):
                self.timeline.update()

    def _load_project_from_path(self, folder_path: Path):
        self.start_screen.setVisible(False)
        if hasattr(self, "video_controller"):
            self.video_controller.release()
        if self.is_playing:
            self.toggle_play()
        self.stop_music_playback(release=True)
        self.stop_all_hold_sounds()

        self.project_folder = folder_path
        for difficulty in DIFFICULTIES:
            list_beatmap_backups(self.project_folder, difficulty)
        display_text = str(self.project_folder)
        display_text = display_text.replace("\\", "\\\u200b").replace("/", "/\u200b")
        self.lbl_path.setText(display_text)
        self.add_to_recent(folder_path)
        self.beatmaps.clear()
        for diff_name in DIFFICULTIES:
            self.beatmaps[diff_name] = BeatmapData(diff_name)
        
        has_beatmaps = any(self.project_folder.glob("*.txt")) or any(self.project_folder.glob("*.osu"))
        initial_level_name = "New Level"
        
        if not has_beatmaps:
            dlg = NewLevelDialog(self)
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.get_text():
                initial_level_name = dlg.get_text()

        found_audio = None
        for extension in (".mp3", ".wav", ".ogg", ".flac", ".opus", ".m4a", ".aac", ".wma", ".alac", ".aiff", ".aif"):
            found_audio = next(self.project_folder.glob(f"*{extension}"), None)
            if found_audio:
                break
        
        common_audio = found_audio.name if found_audio else ""

        try:
            file_mapping = {}
            
            def get_version_from_file(f_path):
                v_val = None
                try:
                     with open(f_path, "r", encoding="utf-8") as f:
                         for line in f:
                             if line.startswith("Difficulty:"):
                                  return line.split(":", 1)[1].strip()
                             if line.startswith("Version:"):
                                  v_val = line.split(":", 1)[1].strip()
                             if line.startswith("[TimingPoints]") or line.startswith("[HitObjects]"):
                                  break
                except:
                     pass

                import re
                m = re.search(r'\[([^\]]+)\]\s*$', f_path.stem)
                if m:
                    internal_diff = m.group(1)
                    internal_to_editor_map = {
                        "Beginner": "Beginner",
                        "Easy": "Normal",
                        "Normal": "Hard",
                        "Hard": "Expert",
                        "UNBEATABLE": "UNBEATABLE",
                        "Star": "Star"
                    }
                    if internal_diff in internal_to_editor_map:
                        return internal_to_editor_map[internal_diff]

                return v_val

            for f_path in self.project_folder.glob("*.osu"):
                v = get_version_from_file(f_path)
                if v:
                    if v in DIFFICULTIES:
                        file_mapping[v] = f_path.name
                    else:
                        file_mapping["Star"] = f_path.name 
            
            for f_path in self.project_folder.glob("*.txt"):
                 v = get_version_from_file(f_path)
                 if v:
                     target = v if v in DIFFICULTIES else "Star"
                     if target not in file_mapping:
                          file_mapping[target] = f_path.name
                 elif f_path.stem in DIFFICULTIES and f_path.stem not in file_mapping:
                      file_mapping[f_path.stem] = f_path.name

            for diff_name in DIFFICULTIES:
                bm = BeatmapData(diff_name)
                try:
                    if diff_name in file_mapping:
                        bm.load(self.project_folder, file_mapping[diff_name])
                    else:
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
            self.current_chart.metadata.Title = initial_level_name
            self.current_chart.metadata.AudioFilename = common_audio
            self.current_chart.timing_points = [{'time': 0, 'bpm': 120.0}]
        
        if self.current_chart and self.current_chart.metadata.AudioFilename:
            audio_f = self.project_folder / self.current_chart.metadata.AudioFilename
            if audio_f.exists():
                try:
                     backup_dir = self.project_folder / "cbm_files"
                     backup_dir.mkdir(parents=True, exist_ok=True)
                     base_name = audio_f.stem
                     backup_path = backup_dir / f"{base_name}_backup{audio_f.suffix}"
                     if not backup_path.exists():
                         shutil.copy2(audio_f, backup_path)
                except:
                     pass

        self.update_window_title()
        
        if self.current_chart and self.current_chart.metadata.AudioFilename:
            self.load_audio(self.current_chart.metadata.AudioFilename)
            
        self.timeline.current_time = 0
        self.timeline.target_time = 0
        self.sync_audio_to_time()
        self.timeline.update_scrollbar()
        self.timeline.update()
        
        self.timeline.update_scrollbar()
        
        if hasattr(self, "video_controller"):
            self.video_controller.load_project()
            self.video_controller.sync_current(force=True)
        self.timeline.update()
        
        if self.enable_visualizer and self.sidebar_vis:
            self.sidebar_vis.set_bands([0.0]*31)

        self.start_screen.setVisible(False)

    def open_sync_audio(self):
        if not self.current_chart or not self.current_chart.metadata.AudioFilename:
            return
            
        audio_file = self.current_chart.metadata.AudioFilename
        full_path = self.project_folder / audio_file
        
        if not full_path.exists():
            found = False
            for ext in [".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".alac", ".aiff"]:
                t_path = self.project_folder / (str(audio_file) + ext)
                if t_path.exists():
                    full_path = t_path
                    found = True
                    break
            
            if not found:
                QMessageBox.warning(self, "Error", "Audio file not found.")
                return

        if self.is_playing:
            self.toggle_play()
        
        self.stop_music_playback(release=True)
            
        metro_path = ""
        res_path = self.game_root_path / "ChartEditorResources" / "metronome.wav"
        if res_path.exists():
             metro_path = str(res_path)
        
        dialog = AudioSynchronizerDialog(self, str(full_path), self.current_chart.metadata.BPM, self.current_chart.metadata.Offset, metro_path)
        dialog.setStyleSheet(self.styleSheet())
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.stop_music_playback(release=True)

            self.load_audio(self.current_chart.metadata.AudioFilename)
            if hasattr(self, 'generate_vis_data'):
                self.generate_vis_data(full_path)
                 
            self.sync_audio_to_time()
            self.timeline.temp_waveform_offset = 0
            self.timeline._force_cache_update = True
            self.timeline.update_scrollbar()
            self.timeline.update()
        else:
            self.load_audio(self.current_chart.metadata.AudioFilename)
            self.sync_audio_to_time()
        dialog.deleteLater()

    def handle_audio_drop(self, file_path):
        if not self.project_folder:
            return
        if self.audio_import_worker and self.audio_import_worker.isRunning():
            QMessageBox.information(self, "Audio Import", "An audio file is already being converted.")
            return
        src_path = Path(file_path)
        try:
            if not src_path.is_file():
                raise FileNotFoundError(str(src_path))
            if not self.current_chart:
                raise RuntimeError("no chart is currently loaded")
            final_filename = src_path.stem + ".mp3"
            dest_path = self.project_folder / final_filename
            temp_dest = self.project_folder / f".{src_path.stem}.importing.mp3"
            temp_dest.unlink(missing_ok=True)
            old_audio_name = self.current_chart.metadata.AudioFilename
            old_file = self.project_folder / old_audio_name if old_audio_name else None
            self.stop_music_playback(release=True)
            self.audio_import_context = {
                "source": src_path,
                "destination": dest_path,
                "temporary": temp_dest,
                "filename": final_filename,
                "old_file": old_file,
            }
            self.audio_import_dialog = AudioConversionProgressDialog(
                "Import Audio",
                "Converting audio...",
                self,
            )
            self.audio_import_worker = AudioConversionWorker(
                src_path,
                temp_dest,
                output_format="mp3",
                parent=self,
            )
            self.audio_import_worker.progress_changed.connect(self.on_audio_import_progress)
            self.audio_import_worker.conversion_ready.connect(self.on_audio_import_ready)
            self.audio_import_worker.conversion_failed.connect(self.on_audio_import_failed)
            self.audio_import_worker.finished.connect(self.audio_import_worker.deleteLater)
            self.audio_import_dialog.show()
            self.audio_import_worker.start()
        except Exception as e:
            print(f"Failed to import audio: {e}")
            QMessageBox.critical(self, "Error", f"Failed to import audio: {e}")

    def on_audio_import_progress(self, value):
        if self.audio_import_dialog:
            self.audio_import_dialog.set_progress(value)

    def on_audio_import_ready(self, output_path, result):
        context = self.audio_import_context
        try:
            if not context:
                raise RuntimeError("audio import context is missing")
            dest_path = context["destination"]
            old_file = context["old_file"]
            os.replace(output_path, dest_path)
            try:
                if old_file and old_file.exists() and old_file.resolve() != dest_path.resolve():
                    old_file.unlink()
                    old_backup = self.project_folder / "cbm_files" / f"{old_file.stem}_backup{old_file.suffix}"
                    old_backup.unlink(missing_ok=True)
            except OSError:
                pass
            final_filename = context["filename"]
            self.current_chart.metadata.AudioFilename = final_filename
            self.audio_label.set_content_loaded(final_filename)
            for bm in self.beatmaps.values():
                bm.metadata.AudioFilename = final_filename
            self.mark_unsaved()
            self.generate_vis_data(dest_path)
            self.load_audio(final_filename)
            try:
                backup_dir = self.project_folder / "cbm_files"
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / f"{dest_path.stem}_backup{dest_path.suffix}"
                if not backup_path.exists():
                    shutil.copy2(dest_path, backup_path)
            except OSError:
                pass
            if self.audio_import_dialog:
                self.audio_import_dialog.accept()
                self.audio_import_dialog.deleteLater()
        except Exception as e:
            self.on_audio_import_failed(str(e))
            return
        self.audio_import_worker = None
        self.audio_import_dialog = None
        self.audio_import_context = None

    def on_audio_import_failed(self, message):
        context = self.audio_import_context
        if context:
            try:
                Path(context["temporary"]).unlink(missing_ok=True)
            except OSError:
                pass
        if self.audio_import_dialog:
            self.audio_import_dialog.reject()
            self.audio_import_dialog.deleteLater()
        self.audio_import_worker = None
        self.audio_import_dialog = None
        self.audio_import_context = None
        QMessageBox.critical(self, "Conversion Error", f"Could not convert audio with BASS: {message}")

    def handle_cover_drop(self, file_path):
        if not self.project_folder: return
        
        src_path = Path(file_path)
        
        try:
            from PIL import Image
            if src_path.suffix.lower() in ['.wav', '.mp3', '.ogg', '.flac', '.m4a', '.wma', '.aac', '.alac', '.aiff']:
                 QMessageBox.warning(self, "Invalid File", "You dropped an audio file into the Cover Art field.\nPlease drop it into the Audio field above.")
                 return

            with Image.open(src_path) as img:
                img_data = img.convert('RGBA')

            for existing in self.project_folder.glob("cover.*"):
                try:
                    if existing.resolve() != src_path.resolve():
                        os.remove(existing)
                except:
                    pass
            
            dest_path = self.project_folder / "cover.png"
            
            img_data.save(dest_path, "PNG")
            
            self.cover_label.set_content_loaded("Cover Loaded")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import cover: {e}")

    def handle_video_drop(self, file_path):
        if not self.project_folder: return

        src_path = Path(file_path)
        ext = src_path.suffix.lower()

        if ext not in ['.mp4', '.webm']:
            QMessageBox.warning(self, "Invalid File", "Only .mp4 and .webm video files are supported.")
            return

        start_video_import(self, src_path)

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
                msg = QDialog(self)
                msg.setWindowTitle("Copy Beatmap?")
                msg.setFixedSize(300, 120)
                msg.setWindowFlags(msg.windowFlags() | Qt.WindowType.MSWindowsFixedSizeDialogHint)
                l = QVBoxLayout(msg)
                
                lbl = QLabel("Copy Beatmap From Other Difficulty?")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setWordWrap(True)
                l.addWidget(lbl)
                
                bl = QHBoxLayout()
                btn_yes = QPushButton("Yes")
                btn_yes.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn_yes.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn_yes.clicked.connect(msg.accept)
                btn_no = QPushButton("No")
                btn_no.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn_no.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn_no.clicked.connect(msg.reject)
                
                bl.addWidget(btn_yes, 1)
                bl.addWidget(btn_no, 1)
                l.addLayout(bl)
                
                if msg.exec() == QDialog.DialogCode.Accepted:
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
        if hasattr(self, 'update_ui_from_metadata'):
            self.update_ui_from_metadata()
        
        self.update_bpm_list()
        m = self.current_chart.metadata
        self.block_meta_signals(False)
        
        self.update_star_visibility()
        self.timeline.set_beatmap(self.current_chart)
        
        self.load_audio(m.AudioFilename)

        if m.AudioFilename:
            self.generate_vis_data(self.project_folder / m.AudioFilename)
        
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
        self.update_bpm_list()
        self.update_window_title()

    def update_bpm_list(self):
        if not self.current_chart: return

        chart_identity = id(self.current_chart)
        if getattr(self, "_bpm_list_chart_identity", None) != chart_identity:
             self.list_bpm.clear()
             self._bpm_list_chart_identity = chart_identity
        
        if not hasattr(self.current_chart, 'timing_points'):
             self.current_chart.timing_points = []
             
        tps = self.current_chart.timing_points
        
        while self.list_bpm.count() > len(tps):
             self.list_bpm.takeItem(self.list_bpm.count() - 1)
             
        while self.list_bpm.count() < len(tps):
             item = QListWidgetItem()
             lbl = QLabel()
             lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
             lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
             lbl.setStyleSheet("color: white; background: transparent;")
             
             effect = FastDropShadowEffect(lbl)
             effect.setEnabled(False)
             effect.setBlurRadius(8)
             effect.setColor(QColor(0, 0, 0, 200))
             effect.setOffset(0, 2)
             set_manual_shadow(lbl, effect)
             effect.setStaticSource(False)
             
             mode = getattr(self, 'drop_shadow_mode', "None")
             if mode in ["Specific", "All"]:
                 QTimer.singleShot(100, lambda e=effect: e.setEnabled(True))
             else:
                 effect.setEnabled(False)
             
             self.list_bpm.addItem(item)
             self.list_bpm.setItemWidget(item, lbl)
             
        for i, tp in enumerate(tps):
             item = self.list_bpm.item(i)
             item.setData(Qt.ItemDataRole.UserRole, tp)
             
             t = tp['time']
             bpm = tp['bpm']
             timestamp = format_editor_timestamp(t, include_milliseconds=True)
             expected_text = f"{bpm} BPM  -  {timestamp}"
             
             lbl = self.list_bpm.itemWidget(item)
             if lbl and lbl.text() != expected_text:
                  lbl.setText(expected_text)
                  effect = lbl.graphicsEffect()
                  if isinstance(effect, FastDropShadowEffect):
                       effect.update()

        self.update_add_bpm_button_text()

    def bpm_point_at_current_timestamp(self):
        if not getattr(self, 'current_chart', None) or not hasattr(self, 'timeline') or not self.timeline:
            return None
        current_timestamp = int(self.timeline.visual_to_audio_ms(self.timeline.current_time))
        for timing_point in getattr(self.current_chart, 'timing_points', []):
            if abs(float(timing_point['time']) - current_timestamp) < 10.0:
                return timing_point
        return None

    def update_add_bpm_button_text(self):
        if not hasattr(self, 'btn_add_bpm') or not self.btn_add_bpm or not getattr(self, 'current_chart', None):
            return
        if not hasattr(self, 'timeline') or not self.timeline:
            return
        
        existing = self.bpm_point_at_current_timestamp() is not None
        
        target_text = "Change BPM" if existing else "Add BPM"
        target_tooltip = "Change existing BPM tag at current position" if existing else "Add timing point at time selection (type BPM below)"
        
        if self.btn_add_bpm.text() != target_text:
            self.btn_add_bpm.setText(target_text)
        if self.btn_add_bpm.toolTip() != target_tooltip:
            self.btn_add_bpm.setToolTip(target_tooltip)

    def add_bpm_point(self):
        if not self.current_chart: return
        
        current_time = int(self.timeline.visual_to_audio_ms(self.timeline.current_time))
        bpm_val = max(1.0, self.inp_bpm.value())
        existing = self.bpm_point_at_current_timestamp()
        
        if existing:
             self.timeline.save_undo_state()
             follow_state = self.timeline.capture_bpm_follow_state(existing)
             existing['bpm'] = bpm_val
             existing['creation_time'] = time.time()
             self.timeline.apply_bpm_follow_state(follow_state)
        else:
             self.timeline.save_undo_state()
             self.current_chart.timing_points.append({
                 'time': current_time, 
                 'bpm': bpm_val, 
                 'creation_time': time.time()
             })
        
        self.current_chart.timing_points.sort(key=lambda x: x['time'])
        self.mark_unsaved()
        self.update_bpm_list()
        self.timeline.update_scrollbar()
        self.timeline.update()

    def delete_bpm_point(self):
        if not self.current_chart: return
        
        row = self.list_bpm.currentRow()
        if row >= 0:
             item = self.list_bpm.item(row)
             tp_ref = item.data(Qt.ItemDataRole.UserRole)
             tp = None
             for t in self.current_chart.timing_points:
                  if abs(t['time'] - tp_ref['time']) < 1:
                       tp = t
                       break
             if tp:
                  if len(self.current_chart.timing_points) <= 1:
                       QMessageBox.warning(self, "Action Prevented", "Cannot delete the last remaining BPM tag.")
                       return

                  new_tps = [x for x in self.current_chart.timing_points if x is not tp]
                  if new_tps and self.current_chart.hit_objects:
                       first_tp_time = new_tps[0]['time']
                       first_note_time = min(o.time for o in self.current_chart.hit_objects)
                       if first_note_time < first_tp_time:
                            QMessageBox.warning(self, "Action Prevented", "Cannot delete this BPM tag because a note would be left without a preceding BPM tag.")
                            return
                  
                  if hasattr(self.timeline, 'dying_bpm_tags'):
                       self.timeline.dying_bpm_tags.append((tp.copy(), time.time()))

                  self.timeline.save_undo_state()
                  current_audio = self.timeline.visual_to_audio_ms(self.timeline.current_time)
                  self.current_chart.timing_points.remove(tp)
                  self.timeline.current_time = self.timeline.audio_to_visual_ms(current_audio)
                  self.timeline.target_time = self.timeline.current_time
                  self.sync_audio_to_time()
                  self.mark_unsaved()
                  self.update_bpm_list()
                  self.timeline.update_scrollbar()
                  self.timeline.update()
        else:
             to_remove = self.bpm_point_at_current_timestamp()
             if to_remove:
                  if len(self.current_chart.timing_points) <= 1:
                       QMessageBox.warning(self, "Action Prevented", "Cannot delete the last remaining BPM tag.")
                       return

                  new_tps = [x for x in self.current_chart.timing_points if x != to_remove]
                  if new_tps and self.current_chart.hit_objects:
                       first_tp_time = new_tps[0]['time']
                       first_note_time = min(o.time for o in self.current_chart.hit_objects)
                       if first_note_time < first_tp_time:
                            QMessageBox.warning(self, "Action Prevented", "Cannot delete this BPM tag because a note would be left without a preceding BPM tag.")
                            return

                  self.timeline.save_undo_state()
                  current_audio = self.timeline.visual_to_audio_ms(self.timeline.current_time)
                  self.current_chart.timing_points.remove(to_remove)
                  self.timeline.current_time = self.timeline.audio_to_visual_ms(current_audio)
                  self.timeline.target_time = self.timeline.current_time
                  self.sync_audio_to_time()
                  self.mark_unsaved()
                  self.update_bpm_list()
                  self.timeline.update_scrollbar()
                  self.timeline.update()

    def seek_to_bpm_point(self, item):
        tp = item.data(Qt.ItemDataRole.UserRole)
        self.timeline.target_time = self.timeline.audio_to_visual_ms(tp['time'])
        self.timeline.update()
        self.timeline.update_scrollbar()

    def update_star_visibility(self):
        self.txt_star_name.setVisible(True)
        self.form_meta.labelForField(self.txt_star_name).setVisible(True)

    def block_meta_signals(self, block: bool):
        for w in self.meta_widgets.values(): 
            if isinstance(w, QWidget):
                w.blockSignals(block)
        self.txt_star_name.blockSignals(block)

    def update_ui_from_metadata(self, m=None, folder_path=None):
        if m is None:
            if not getattr(self, 'current_chart', None): return
            m = self.current_chart.metadata
        if folder_path is None:
            folder_path = self.project_folder

        self.block_meta_signals(True)
        self.meta_widgets["Title"].setText(m.Title)
        self.meta_widgets["Artist"].setText(m.Artist)
        self.meta_widgets["Charted By"].setText(m.Creator)
        self.meta_widgets["BPM"].setValue(m.BPM)
        self.meta_widgets["BPM"].lineEdit().setText(self.meta_widgets["BPM"].textFromValue(m.BPM))
        self.meta_widgets["Level"].setValue(m.Level)
        self.meta_widgets["Level"].lineEdit().setText(self.meta_widgets["Level"].textFromValue(m.Level))
        self.meta_widgets["FlavorText"].setText(m.FlavorText)
        self.meta_widgets["Attributes"].setText(m.Attributes[0] if m.Attributes else "")
        self.txt_star_name.setText(m.Version)

        if m.AudioFilename and (folder_path / m.AudioFilename).exists():
            self.audio_label.set_content_loaded(m.AudioFilename)
        else:
            self.audio_label.set_empty()

        has_cover = any(folder_path.glob("cover.*"))
        if has_cover:
            self.cover_label.set_content_loaded("Cover Loaded")
        else:
            self.cover_label.set_empty()

        has_video = find_project_video(folder_path) is not None
        if has_video:
            self.video_label.set_content_loaded("Video Loaded")
        else:
            self.video_label.set_empty()
            
        self.block_meta_signals(False)

    def clear_project_metadata_preview(self, force=False):
        if not hasattr(self, "meta_widgets"):
            return
        if not force:
            if getattr(self, "is_loading_project", False):
                return
            start_screen = getattr(self, "start_screen", None)
            if start_screen is not None and not start_screen.isVisible():
                return
        self.block_meta_signals(True)
        for name in ("Title", "Artist", "Charted By", "FlavorText", "Attributes"):
            self.meta_widgets[name].clear()
        self.meta_widgets["BPM"].lineEdit().clear()
        self.meta_widgets["Level"].lineEdit().clear()
        self.txt_star_name.clear()
        self.audio_label.set_empty()
        self.cover_label.set_empty()
        self.video_label.set_empty()
        self.block_meta_signals(False)

    def preview_metadata_for_path(self, folder_path):
        folder_path = Path(folder_path)
        if not folder_path.exists():
            self.clear_project_metadata_preview()
            return

        difficulty_order = {name.lower(): index for index, name in enumerate(DIFFICULTIES)}
        map_files = sorted(
            list(folder_path.glob("*.osu")) + list(folder_path.glob("*.txt")),
            key=lambda path: (difficulty_order.get(path.stem.lower(), len(DIFFICULTIES)), path.name.lower()),
        )
        if not map_files:
            self.clear_project_metadata_preview()
            return

        try:
            map_file = map_files[0]
            stat = map_file.stat()
            cache_key = (str(map_file.resolve()), stat.st_mtime_ns, stat.st_size)
            if getattr(self, "_project_metadata_preview_key", None) == cache_key:
                metadata = self._project_metadata_preview_value
            else:
                metadata = BeatmapMetadata()
                current_section = ""
                extracted_version = None
                extracted_difficulty = None
                with open(map_file, "r", encoding="utf-8-sig") as handle:
                    for line_index, raw_line in enumerate(handle):
                        if line_index >= 4096:
                            break
                        line = raw_line.strip()
                        if not line or line.startswith("//"):
                            continue
                        if line.startswith("[") and line.endswith("]"):
                            current_section = line
                            if current_section == "[HitObjects]":
                                break
                            continue
                        if current_section == "[TimingPoints]":
                            parts = line.split(",")
                            if len(parts) >= 2:
                                try:
                                    timing_offset = float(parts[0])
                                    beat_length = float(parts[1])
                                    if beat_length > 0:
                                        metadata.BPM = round(60000.0 / beat_length, 3)
                                        metadata.Offset = int(timing_offset)
                                        current_section = "[PreviewComplete]"
                                except ValueError:
                                    pass
                        if ":" in line and current_section in ("[General]", "[Metadata]", ""):
                            key, value = line.split(":", 1)
                            key = key.strip()
                            value = value.strip()
                            if key == "Title":
                                metadata.Title = value
                            elif key == "TitleUnicode":
                                metadata.TitleUnicode = value
                            elif key == "Artist":
                                metadata.Artist = value
                            elif key == "ArtistUnicode":
                                metadata.ArtistUnicode = value
                            elif key == "AudioFilename":
                                metadata.AudioFilename = value
                            elif key == "Creator":
                                metadata.Creator = value
                            elif key == "BPM":
                                try:
                                    metadata.BPM = float(value)
                                except ValueError:
                                    pass
                            elif key == "Version":
                                extracted_version = value
                            elif key == "Difficulty":
                                extracted_difficulty = value
                            elif key == "Tags":
                                try:
                                    tag_data = json.loads(value)
                                    metadata.Level = tag_data.get("Level", 1)
                                    metadata.FlavorText = tag_data.get("FlavorText", "")
                                    metadata.Attributes = tag_data.get("Attributes", [])
                                except (TypeError, ValueError):
                                    pass
                            elif key == "AudioLeadIn":
                                try:
                                    metadata.Offset = int(value)
                                except ValueError:
                                    pass
                        elif current_section == "[Editor]" and ":" in line:
                            key, value = line.split(":", 1)
                            if key.strip() == "GridSize":
                                try:
                                    metadata.GridSize = int(value.strip())
                                except ValueError:
                                    pass
                if extracted_difficulty:
                    metadata.Version = extracted_version or extracted_difficulty
                elif extracted_version in DIFFICULTIES:
                    metadata.Version = ""
                else:
                    metadata.Version = extracted_version or "Star"
                self._project_metadata_preview_key = cache_key
                self._project_metadata_preview_value = metadata
            self.update_ui_from_metadata(metadata, folder_path)
        except (OSError, UnicodeError):
            self.clear_project_metadata_preview()

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
        m.Level = self.meta_widgets["Level"].value()
        m.FlavorText = self.meta_widgets["FlavorText"].text()
        attr_text = self.meta_widgets["Attributes"].text()
        m.Attributes = [attr_text] if attr_text else []
        
        m.Version = self.txt_star_name.text()
        
        self.mark_unsaved()

    def update_bmap_file(self):
        if not self.project_folder: return
        bmap_files = list(self.project_folder.glob("*.bmap"))
        
        data = {}
        bmap_path = None
        
        if bmap_files:
            bmap_path = bmap_files[0]
            try:
                with open(bmap_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except:
                pass
        else:
            if not self.current_chart: return
            bmap_filename = "package.bmap"
            bmap_path = self.project_folder / bmap_filename

        song_files = {}
        for diff_key in DIFFICULTIES:
             if diff_key in self.beatmaps and self.beatmaps[diff_key].created:
                 song_files[diff_key] = self.beatmaps[diff_key].get_filename()
        
        data["Songs"] = [song_files]
        
        if bmap_path:
            try:
                with open(bmap_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            except:
                pass

    def save_current(self):
        if not self.current_chart or not self.project_folder: return

        if getattr(self.timeline, 'dragging_bpm_tag', None):
            self.timeline.release_bpm_tag()

        if self.auto_save_worker and self.auto_save_worker.isRunning():
            self.auto_save_worker.wait()

        if not self.current_chart.timing_points:
            self.current_chart.timing_points = [{'time': int(self.current_chart.metadata.Offset), 'bpm': self.current_chart.metadata.BPM}]
        
        self.current_chart.editor_zoom = self.timeline.target_zoom
    
        with self.save_io_lock:
            saved = self.current_chart.save(self.project_folder, self.file_extension_setting)
            if saved and self.enable_backups:
                create_beatmap_backup(
                    self.project_folder,
                    self.current_chart.difficulty_key,
                    self.current_chart.get_filename(),
                )
        if saved:
            self.mark_saved()
            self.update_bmap_file()
            self.update_ui_state()
            self.save_toast.show_message()
        else:
            QMessageBox.critical(self, "Error", "Failed to save file.")

    def do_auto_save(self):
        if self.is_playing or getattr(self.timeline, 'dragging_bpm_tag', None) or not getattr(self, 'auto_save', False):
            return
        if not self.current_chart or not self.project_folder or not getattr(self.current_chart, 'created', False):
            return
        if not getattr(self.current_chart, 'unsaved', False):
            return
        if self.auto_save_worker and self.auto_save_worker.isRunning():
            return
        chart = self.current_chart
        revision = getattr(chart, '_edit_revision', 0)
        metadata = {
            name: getattr(chart.metadata, name)
            for name in BeatmapMetadata.__dataclass_fields__
        }
        metadata['Attributes'] = list(metadata.get('Attributes') or [])
        snapshot = {
            'difficulty_key': chart.difficulty_key,
            'metadata': metadata,
            'hit_objects': [
                (
                    obj.x,
                    obj.y,
                    obj.time,
                    obj.type,
                    obj.hitSound,
                    obj.objectParams,
                    obj.hitSample,
                    obj.order_index,
                    obj.creation_time,
                    obj.last_update_time,
                    obj.tc_is_blue,
                    obj.uid,
                    custom_object_data_to_tuple(obj.custom_data)
                )
                for obj in chart.hit_objects
            ],
            'timing_points': [
                (tp['time'], tp['bpm'])
                for tp in chart.timing_points
            ],
            'filename': chart.filename,
            'editor_zoom': self.timeline.target_zoom
        }
        worker = BeatmapSaveWorker(
            chart,
            revision,
            self.project_folder,
            self.file_extension_setting,
            snapshot,
            self.save_io_lock,
            self.enable_backups,
            self
        )
        self.auto_save_worker = worker
        worker.save_finished.connect(self.on_auto_save_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def on_auto_save_finished(self, chart, revision, success, filename, folder):
        if self.sender() is self.auto_save_worker:
            self.auto_save_worker = None
        if not success or not self.project_folder or str(self.project_folder) != folder:
            return
        if chart not in self.beatmaps.values() or getattr(chart, '_edit_revision', 0) != revision:
            return
        chart.filename = filename
        chart.created = True
        chart.unsaved = False
        if chart is self.current_chart:
            self.update_window_title()
        self.update_bmap_file()

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
        if tool_type == "custom" and not self.btn_tool_custom.isVisible():
            tool_type = "note"
        self.timeline.current_tool_type = tool_type
        self.btn_tool_note.setChecked(tool_type == "note")
        self.btn_tool_brawl.setChecked(tool_type == "brawl")
        self.btn_tool_event.setChecked(tool_type == "event")
        self.btn_tool_custom.setChecked(tool_type == "custom")
        
        if tool_type == "note":
            self.tool_stack.setCurrentWidget(self.note_type_container)
        elif tool_type == "brawl":
            self.tool_stack.setCurrentWidget(self.brawl_type_container)
        elif tool_type == "event":
            self.tool_stack.setCurrentWidget(self.event_type_container)
        elif tool_type == "custom":
            self.tool_stack.setCurrentWidget(self.custom_type_container)
            
        self.btn_event_flip.setVisible(tool_type == "event")
        self.btn_event_toggle.setVisible(tool_type == "event")
        self.btn_event_instant.setVisible(tool_type == "event")

    def refresh_custom_note_tools(self):
        notes = getattr(self, "custom_notes", [])
        visible = bool(getattr(self, "custom_notes_enabled", True) and notes)
        self.btn_tool_custom.setVisible(visible)
        current_note_id = self.combo_custom_note.currentData()
        for button in self.custom_note_buttons:
            self.custom_note_button_group.removeButton(button)
            self.custom_type_layout.removeWidget(button)
            button.deleteLater()
        self.custom_note_buttons.clear()
        self.combo_custom_note.blockSignals(True)
        self.combo_custom_note.clear()
        for note in notes:
            self.combo_custom_note.addItem(note["name"], note["id"])
            button = QPushButton(note["name"])
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setProperty("custom_note_id", note["id"])
            button.clicked.connect(lambda checked=False, note_id=note["id"]: self.select_custom_note(note_id))
            self.custom_note_button_group.addButton(button)
            self.custom_type_layout.insertWidget(self.custom_type_layout.indexOf(self.combo_custom_type), button, 1)
            self.custom_note_buttons.append(button)
        if current_note_id:
            index = self.combo_custom_note.findData(current_note_id)
            if index >= 0:
                self.combo_custom_note.setCurrentIndex(index)
        self.combo_custom_note.blockSignals(False)
        if not visible and getattr(self.timeline, "current_tool_type", "note") == "custom":
            self.change_tool_type("note")
        self.change_custom_note(self.combo_custom_note.currentIndex())

    def select_custom_note(self, note_id):
        index = self.combo_custom_note.findData(note_id)
        if index >= 0:
            self.combo_custom_note.setCurrentIndex(index)

    def update_custom_note_button_visibility(self, available_width=None):
        if not hasattr(self, 'custom_note_buttons') or self._updating_custom_note_buttons:
            return
        self._updating_custom_note_buttons = True
        try:
            width = int(available_width if available_width is not None else self.custom_type_container.width())
            selected_index = self.combo_custom_note.currentIndex()
            selected_name = self.combo_custom_note.itemText(selected_index) if selected_index >= 0 else ""
            all_text = f"All ({selected_name})" if selected_name else "All"
            all_minimum = self.combo_custom_note.fontMetrics().horizontalAdvance(all_text) + 38
            type_width = 240
            self.combo_custom_type.setFixedWidth(type_width)
            button_minimums = [button.fontMetrics().horizontalAdvance(button.text()) + 34 for button in self.custom_note_buttons]
            visible_count = 0
            spacing = self.custom_type_layout.spacing()
            for count in range(1, len(self.custom_note_buttons) + 1):
                main_width = width - type_width - spacing * (count + 1)
                equal_width = main_width // (count + 1)
                if equal_width < max([all_minimum] + button_minimums[:count]):
                    break
                visible_count = count
            main_width = width - type_width - spacing * (visible_count + 1)
            equal_width = max(60, main_width // (visible_count + 1))
            self.combo_custom_note.setFixedWidth(equal_width)
            for index, button in enumerate(self.custom_note_buttons):
                visible = index < visible_count
                button.setVisible(visible)
                if visible:
                    button.setFixedWidth(equal_width)
        finally:
            self._updating_custom_note_buttons = False

    def change_custom_note(self, index):
        note_id = self.combo_custom_note.itemData(index) if index >= 0 else None
        note = next((item for item in getattr(self, "custom_notes", []) if item["id"] == note_id), None)
        for button in self.custom_note_buttons:
            button.setChecked(button.property("custom_note_id") == note_id)
        self.combo_custom_note.update()
        current_type_id = self.combo_custom_type.currentData()
        self.combo_custom_type.blockSignals(True)
        self.combo_custom_type.clear()
        if note:
            for type_data in note["types"]:
                self.combo_custom_type.addItem(type_data["name"], type_data["id"])
        if current_type_id:
            type_index = self.combo_custom_type.findData(current_type_id)
            if type_index >= 0:
                self.combo_custom_type.setCurrentIndex(type_index)
        self.combo_custom_type.blockSignals(False)
        self.change_custom_type(self.combo_custom_type.currentIndex())
        self.update_custom_note_button_visibility()

    def change_custom_type(self, index):
        self.timeline.current_custom_type_id = self.combo_custom_type.itemData(index) if index >= 0 else None

    def freeze_custom_note_raw_lines(self):
        for beatmap in getattr(self, "beatmaps", {}).values():
            for obj in beatmap.hit_objects:
                data = obj.custom_data
                if data is None or data.missing:
                    continue
                type_data = get_custom_type(data.type_id)
                if type_data is None:
                    continue
                values = {
                    "time": obj.time,
                    "end": obj.end_time,
                    "lane": data.lane,
                }
                data.raw_line = render_custom_template(type_data["syntax"], values, type_data)
                data.section = type_data.get("section", "HitObjects")

    def refresh_custom_note_objects(self):
        current_changed = False
        for beatmap in getattr(self, "beatmaps", {}).values():
            changed = False
            for obj in beatmap.hit_objects:
                if obj.custom_data is not None:
                    type_data = get_custom_type(obj.custom_data.type_id)
                    obj.custom_data.missing = type_data is None
                    if type_data is None:
                        continue
                    target_section = type_data.get("section", "HitObjects")
                    if obj.custom_data.section != target_section:
                        obj.custom_data.section = target_section
                        changed = True
                    mode = type_data.get("lane_mode", "Top & Bottom")
                    target_lane = obj.custom_data.lane
                    if mode == "Middle":
                        target_lane = -2
                    elif mode == "Top Only":
                        target_lane = 0
                    elif mode == "Bottom Only":
                        target_lane = 1
                    elif target_lane == -2:
                        target_lane = 0
                    if target_lane != obj.custom_data.lane:
                        previous_lane = obj.custom_data.lane
                        obj.custom_data.lane = target_lane
                        if beatmap is getattr(self, 'current_chart', None) and hasattr(self, 'timeline'):
                            if not hasattr(obj, '_current_visual_lane'):
                                obj._current_visual_lane = self.timeline.get_visual_lane_value(obj, previous_lane)
                            obj._target_visual_lane = self.timeline.get_visual_lane_value(obj, target_lane)
                            self.timeline.visual_interpolating_objects.add(obj)
                        changed = True
                    rendered = render_custom_template(type_data["syntax"], {
                        "time": obj.time,
                        "end": obj.end_time,
                        "lane": obj.custom_data.lane,
                    }, type_data)
                    if rendered != obj.custom_data.raw_line:
                        changed = True
            if changed:
                beatmap.unsaved = True
                beatmap._edit_revision = getattr(beatmap, '_edit_revision', 0) + 1
                if beatmap is getattr(self, 'current_chart', None):
                    current_changed = True
        if current_changed:
            self.update_window_title()
        if hasattr(self, "timeline"):
            self.timeline._force_cache_update = True
            self.timeline.update()
    
    def on_scrollbar_changed(self, value):
        self.timeline.target_time = value
        self.timeline.current_time = value
        self.timeline.update()
        self.update_add_bpm_button_text()
        
        if self.is_playing:
            self.sync_audio_to_time(force_play=True)
        else:
            self.sync_audio_to_time(video_exact=False)

    def finalize_video_scroll_seek(self):
        controller = getattr(self, "video_controller", None)
        if controller:
            audio_ms = self.timeline.visual_to_audio_ms(self.timeline.current_time)
            controller.seek(audio_ms, exact=True)

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
            self.combo_note_style.setEnabled(False)
            self.combo_note_style.addItem("Normal")
        elif note_type == "hold":
            self.combo_note_style.setEnabled(True)
            self.combo_note_style.addItems(["Normal", "Fly In"])
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
        self.timeline.is_triplet_mode = False
        if self.current_chart:
            self.current_chart.metadata.GridSize = self.spin_grid.value()
            self.mark_unsaved()
        self.timeline.update()

    def change_speed(self, text):
        val_str = text.replace('x', '')
        try:
            self.playback_speed = float(val_str)
            was_playing = self.is_playing
            if self.current_playback_channel:
                self.current_playback_channel.set_speed(self.playback_speed)
            elif self.current_chart and self.current_chart.metadata.AudioFilename:
                self.load_audio(self.current_chart.metadata.AudioFilename)
            self.sync_audio_to_time(force_play=was_playing)
            if hasattr(self, "video_controller"):
                self.video_controller.sync_current(force=True)
        except ValueError:
            pass
            
    def open_sync_menu(self):
        d = QDialog(self)
        d.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        d.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout = QVBoxLayout(d)
        layout.setContentsMargins(0, 0, 0, 0)
        
        container = QWidget()
        
        b = self.ui_brightness
        b_panel = max(0, b - 26)
        b_d = max(0, b - int(20 + (b / 255.0) * 30))
        panel_hex = f"#{b_panel:02x}{b_panel:02x}{b_panel:02x}"
        depth_hex = f"#{b_d:02x}{b_d:02x}{b_d:02x}"
        text_color = "black" if b > 180 else "white"

        container.setStyleSheet(f"""
            QWidget {{
                background-color: {panel_hex};
                border: 1px solid {depth_hex};
                border-radius: 10px;
            }}
            QPushButton {{
                background-color: transparent;
                color: {text_color};
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                text-align: center;
                font-family: "Segoe UI", "Selawik", "Arial", sans-serif;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_COLOR};
                color: white;
            }}
        """)
        
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(5, 5, 5, 5)
        container_layout.setSpacing(5)
        
        pan = self.get_pan_for_widget(self.btn_bpm_match)
        
        btn_match = HoverButton("Match BPM", hover_cb=lambda: self.play_ui_sound('UI Scroll', pan))
        btn_match.setToolTip("Determine BPM with tap tempo")
        btn_match.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_match.clicked.connect(lambda: [d.accept(), self.open_bpm_matcher()])
        
        btn_sync = HoverButton("Offset Audio", hover_cb=lambda: self.play_ui_sound('UI Scroll', pan))
        btn_sync.setToolTip("Change offset of audio file to line up with barlines")
        btn_sync.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sync.clicked.connect(lambda: [d.accept(), self.open_sync_audio()])
        
        container_layout.addWidget(btn_match)
        container_layout.addWidget(btn_sync)
        
        layout.addWidget(container)
        
        pos = self.btn_bpm_match.mapToGlobal(QPoint(0, self.btn_bpm_match.height() + 4))
        d.move(pos)
        d.exec()
        d.deleteLater()

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
            
        audio_ms = self.timeline.visual_to_audio_ms(self.timeline.current_time)
        if audio_ms < 0: audio_ms = 0
            
        dialog = BPMMatchDialog(self, audio_file, start_pos_ms=audio_ms)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.calculated_bpm > 0:
                self.meta_widgets["BPM"].setValue(float(dialog.calculated_bpm))
                self.inp_bpm.setValue(float(dialog.calculated_bpm))
                self.add_bpm_point()
        dialog.deleteLater()
        self.load_audio(self.current_chart.metadata.AudioFilename)

    def toggle_metronome(self, state):
        self.metronome_active = (state == Qt.CheckState.Checked.value)

    def generate_vis_data(self, file_path):
        s_path = str(file_path)
        if not os.path.exists(s_path):
            return
        try:
            self.start_audio_analysis(s_path, os.path.getmtime(s_path))
        except OSError:
            pass

    def start_audio_analysis(self, source_path, source_mtime=None):
        source_path = str(source_path)
        if not os.path.exists(source_path):
            return
        if source_mtime is None:
            source_mtime = os.path.getmtime(source_path)
        key = (os.path.normcase(os.path.abspath(source_path)), source_mtime)
        if self._audio_analysis_completed_key == key:
            return
        if self.audio_analysis_worker and self.audio_analysis_worker.isRunning():
            if self._audio_analysis_key == key:
                return
            self.audio_analysis_worker.requestInterruption()
        self._audio_analysis_key = key
        if hasattr(self, 'timeline'):
            self.timeline.generate_waveform(None)
        worker = AudioAnalysisWorker(source_path, 5.0, self)
        self.audio_analysis_worker = worker
        self.audio_analysis_workers.append(worker)
        worker.analysis_started.connect(self.on_audio_analysis_started)
        worker.analysis_progress.connect(self.on_audio_analysis_progress)
        worker.analysis_ready.connect(self.on_audio_analysis_ready)
        worker.finished.connect(self.on_audio_analysis_finished)
        worker.start(QThread.Priority.LowPriority)

    def on_audio_analysis_finished(self):
        worker = self.sender()
        if worker in self.audio_analysis_workers:
            self.audio_analysis_workers.remove(worker)
        if worker is self.audio_analysis_worker:
            self.audio_analysis_worker = None
        worker.deleteLater()

    def on_audio_analysis_started(self, source_path, source_mtime, total_points, waveform_ratio, waveform):
        if self.sender() is not self.audio_analysis_worker:
            return
        key = (os.path.normcase(os.path.abspath(source_path)), source_mtime)
        if key != self._audio_analysis_key:
            return
        if hasattr(self, 'timeline'):
            self.timeline.waveform_data = waveform
            self.timeline.waveform_ratio = float(waveform_ratio)
            self.timeline.waveform_loaded_points = 0
            if not (self.is_playing and self.timeline._vsync_frame_clock):
                self.timeline.update()

    def on_audio_analysis_progress(self, source_path, source_mtime, loaded_points):
        if self.sender() is not self.audio_analysis_worker:
            return
        key = (os.path.normcase(os.path.abspath(source_path)), source_mtime)
        if key != self._audio_analysis_key or not hasattr(self, 'timeline'):
            return
        self.timeline.waveform_loaded_points = max(
            self.timeline.waveform_loaded_points,
            min(len(self.timeline.waveform_data), int(loaded_points))
            if self.timeline.waveform_data is not None
            else 0
        )
        if not (self.is_playing and self.timeline._vsync_frame_clock):
            self.timeline.update()

    def on_audio_analysis_ready(self, source_path, source_mtime, result):
        if self.sender() is not self.audio_analysis_worker:
            return
        key = (os.path.normcase(os.path.abspath(source_path)), source_mtime)
        if key != self._audio_analysis_key:
            return
        self._audio_analysis_completed_key = key
        if hasattr(self, 'timeline'):
            self.timeline.waveform_ratio = result['waveform_ratio']
            self.timeline.waveform_loaded_points = int(result['waveform_length'])
            if not (self.is_playing and self.timeline._vsync_frame_clock):
                self.timeline.update()
        if self.current_chart and self.project_folder and self.current_audio_filename:
            current_path = os.path.normcase(os.path.abspath(str(self.project_folder / self.current_audio_filename)))
            if current_path == key[0]:
                duration = result['duration']
                self.current_chart.metadata.ActualAudioLength = duration
                self.current_chart.metadata.SongLength = duration
                self.timeline._force_cache_update = True
                self.timeline.update_scrollbar()

    def load_audio(self, filename):
        if not self.project_folder or not filename:
            if self.audio_analysis_worker and self.audio_analysis_worker.isRunning():
                self.audio_analysis_worker.requestInterruption()
            self.current_audio_filename = None
            self._current_audio_path = None
            self.visualizer_level = 0.0
            self._audio_analysis_key = None
            self._audio_analysis_completed_key = None
            if hasattr(self, 'timeline'):
                self.timeline.generate_waveform(None)
            self.stop_music_playback(release=True)
            return
        base_path = str(self.project_folder / filename)
        if os.path.exists(base_path):
            try:
                current_mtime = os.path.getmtime(base_path)
                last_mtime = getattr(self, '_audio_last_mtime', 0)
                normalized_base_path = os.path.normcase(os.path.abspath(base_path))

                if filename != self.current_audio_filename or normalized_base_path != self._current_audio_path or current_mtime != last_mtime:
                    self.visualizer_level = 0.0
                    self.current_audio_filename = filename
                    self._current_audio_path = normalized_base_path
                    self._audio_last_mtime = current_mtime
                    self.start_audio_analysis(base_path, current_mtime)
            except Exception as e:
                print(f"Error loading original audio for waveform: {e}")
                self.current_audio_filename = None

        audio_file = str(self.project_folder / filename)

        if os.path.exists(audio_file):
            try:
                self.stop_music_playback(release=True)
                self.current_playback_channel = self.audio_engine.load_stream(audio_file)
                self.current_playback_channel.set_volume(self.get_effective_music_volume())
                self.current_playback_channel.set_speed(self.playback_speed)
                stream_len = self.current_playback_channel.get_length_ms() / 1000.0
                self.current_chart.metadata.ActualAudioLength = stream_len
                self.current_chart.metadata.SongLength = stream_len
                         
                self.timeline._force_cache_update = True
                self.timeline.update_scrollbar()
                     
            except Exception as e: 
                print(f"Audio error loading {audio_file}: {e}")
                self.stop_music_playback(release=True)
        else:
            print(f"Audio file not found: {audio_file}")

    def stop_all_hold_sounds(self):
        if hasattr(self, 'active_hold_sounds'):
            for channel in self.active_hold_sounds.values():
                if channel and channel.get_busy():
                    channel.stop()
            self.active_hold_sounds.clear()

    def start_active_hold_sounds(self):
        if not self.current_chart: return
        audio_ms = self.timeline.visual_to_audio_ms(self.timeline.current_time)
        
        for obj in self.timeline.get_active_tail_objects(audio_ms, include_starts=True):
            if obj.time <= audio_ms < obj.end_time:
                if not hasattr(self, 'active_tails'):
                    self.active_tails = []
                if obj not in self.active_tails:
                    self.active_tails.append(obj)
                self.last_played_notes.add((obj.uid, 'head'))
                
                if obj.is_hold or obj.is_brawl_hold:
                    sound_key_name = 'Hold Start' if obj.is_hold else 'Brawl Hold Start'
                    sound_key = SOUND_FILES_MAP.get(sound_key_name)
                    if not sound_key or sound_key not in self.sounds: continue
                     
                    hold_sound = self.sounds[sound_key]
                    offset_ms = audio_ms - obj.time
                    try:
                        channel = hold_sound.play(offset_ms=offset_ms)
                        if channel:
                            eff_fx = self.get_effective_fx_volume()
                            channel.set_volume(eff_fx, eff_fx)
                            if not hasattr(self, 'active_hold_sounds'):
                                self.active_hold_sounds = {}
                            old_channel = self.active_hold_sounds.get(obj.uid)
                            if old_channel and old_channel.get_busy():
                                old_channel.stop()
                            self.active_hold_sounds[obj.uid] = channel
                    except:
                        pass

    def toggle_play(self):
        if self.is_playing:
            self.stop_music_playback()
            self._audio_waiting_for_zero = False
            self.stop_all_hold_sounds()
            self.is_playing = False
            if hasattr(self, "video_controller"):
                audio_ms = self.timeline.visual_to_audio_ms(self.timeline.current_time)
                self.video_controller.pause(audio_ms)
            gc.enable()
            if self.sidebar_vis:
                self.sidebar_vis.set_active(False)
            self.timeline.update()
        else:
            if not self.current_chart: return
            
            self.timeline.release_bpm_tag()
            
            self.sync_audio_to_time(force_play=True)
            self.start_active_hold_sounds()
            
            self.is_playing = True
            self.last_visualizer_level_update = time.perf_counter()
            gc.disable()
            self.timeline.update()
        if hasattr(self.btn_play, "trigger_action_pulse"):
            self.btn_play.trigger_action_pulse()

    def stop_and_reset(self):
        self.is_playing = False
        gc.enable()
        if self.sidebar_vis:
            self.sidebar_vis.set_active(False)
        
        self.stop_music_playback()
        self._audio_waiting_for_zero = False
        self.stop_all_hold_sounds()
        self.timeline.target_time = 0.0
        self.timeline.current_time = 0.0
        self.audio_start_ms = 0.0
        self.system_start_tick = 0
        self.last_played_notes.clear()
        self.last_metronome_beat = -1
        if hasattr(self, "video_controller"):
            self.video_controller.pause(0)
        self.timeline.update_scrollbar()
        self.timeline.update()

    def sync_audio_to_time(self, force_play=False, video_exact=True):
        audio_ms = self.timeline.visual_to_audio_ms(self.timeline.current_time)
        new_pos_seconds = audio_ms / 1000.0
        if new_pos_seconds < 0:
             playback_pos = 0.0
        else:
             playback_pos = new_pos_seconds
        
        if not self.current_chart: return
        
        playback_pos = max(0.0, new_pos_seconds)
        
        if self.is_playing or force_play:
            try:
                self.stop_all_hold_sounds()
                 
                self.stop_music_playback()

                self.audio_start_ms = self.timeline.current_time
                self.next_note_index = 0
                self.last_played_notes.clear()
                self.active_tails.clear()
                if self.current_chart and getattr(self.current_chart, 'hit_objects', None):
                    audio_pos = self.timeline.visual_to_audio_ms(self.audio_start_ms)
                    self.timeline.update_caches_if_needed()
                    hit_object_times = getattr(self.timeline, '_cached_hit_object_times', [])
                    self.next_note_index = bisect.bisect_left(hit_object_times, audio_pos - 100)
                self.is_playing = force_play or self.is_playing

                self._audio_waiting_for_zero = new_pos_seconds < 0
                if self.current_playback_channel and new_pos_seconds >= 0:
                    self.current_playback_channel.set_volume(self.get_effective_music_volume())
                    self.current_playback_channel.play_from_ms(playback_pos * 1000.0)

                self.system_start_tick = time.perf_counter() * 1000.0

                if self.is_playing:
                    self.start_active_hold_sounds()
                    self.timeline.update()

            except Exception as e:
                print(f"Sync error: {e}")

        if hasattr(self, "video_controller"):
            if self.is_playing or force_play:
                self.video_controller.play(audio_ms)
            else:
                self.video_controller.seek(audio_ms, exact=video_exact)
        
        base_bpm = self.current_chart.metadata.BPM if self.current_chart else 120
        if base_bpm > 0:
             beat_interval = 60000.0 / base_bpm
             seg_off = self.timeline.get_segment_offset_visual(self.timeline.current_time)
             current_beat_index = int(math.floor((self.timeline.current_time - seg_off) / beat_interval))
             self.last_metronome_beat = current_beat_index
             self._last_seg_off = seg_off
        self.update_add_bpm_button_text()

    def tick(self):
        if self.is_playing:
            if self.system_start_tick > 0:
                now_ticks = time.perf_counter() * 1000.0
                elapsed_real_ms = now_ticks - self.system_start_tick

                audio_start_pos = self.timeline.visual_to_audio_ms(self.audio_start_ms)
                target_audio_pos = audio_start_pos + (elapsed_real_ms * self.playback_speed)

                self.timeline.current_time = self.timeline.audio_to_visual_ms(target_audio_pos)
                self.timeline.target_time = self.timeline.current_time
                self.update_add_bpm_button_text()

                if self.is_playing and self._audio_waiting_for_zero and self.current_playback_channel:
                    audio_pos = self.timeline.visual_to_audio_ms(self.timeline.current_time)
                    if audio_pos >= 0:
                        try:
                            t_before = time.perf_counter() * 1000.0
                            self.current_playback_channel.set_volume(self.get_effective_music_volume())
                            self.current_playback_channel.play_from_ms(audio_pos)
                            self._audio_waiting_for_zero = False
                            t_after = time.perf_counter() * 1000.0
                            self.system_start_tick += (t_after - t_before)
                        except:
                            pass

                if now_ticks - self.last_scrollbar_update > 16.0:
                    self.timeline_scrollbar.blockSignals(True)
                    self.timeline_scrollbar.setValue(int(self.timeline.current_time))
                    self.timeline_scrollbar.blockSignals(False)
                    self.last_scrollbar_update = now_ticks

                visual_end = self.timeline.get_visual_song_length()
                if visual_end > 0 and self.timeline.current_time >= visual_end:
                        self.timeline.current_time = visual_end
                        self.timeline.target_time = visual_end
                        self.is_playing = False
                        gc.enable()
                        self.stop_music_playback()
                        self._audio_waiting_for_zero = False
                        self.stop_all_hold_sounds()

                if hasattr(self, "video_controller") and self.video_controller.enabled:
                    video_audio_ms = self.timeline.visual_to_audio_ms(self.timeline.current_time)
                    self.video_controller.sync(video_audio_ms, self.is_playing)

            if not self.is_playing and self.sidebar_vis:
                self.sidebar_vis.set_active(False)
            
            if self.is_playing and self.enable_visualizer and self.sidebar_vis and self.current_playback_channel and self.current_chart:
                 self.sidebar_vis.set_active(True)
                 visualizer_now = time.perf_counter() * 1000.0
                 visualizer_interval = 1000.0 / min(60, TARGET_FPS)
                 if visualizer_now - self.last_visualizer_submit >= visualizer_interval:
                     self.last_visualizer_submit = visualizer_now
                     fft_data = self.current_playback_channel.get_fft()
                     if fft_data is not None and self.vis_worker:
                         self.vis_worker.process_chunk((
                             np.ctypeslib.as_array(fft_data).copy(),
                             self.current_playback_channel.original_frequency
                         ))
                     else:
                         self.sidebar_vis.set_active(False)
                     rms = self.current_playback_channel.get_rms_level()
                     target_level = min(1.0, max(0.0, rms * 3.5))
                     level_now = time.perf_counter()
                     level_dt = min(0.05, max(0.0, level_now - self.last_visualizer_level_update))
                     self.last_visualizer_level_update = level_now
                     level_rate = 32.0 if target_level > self.visualizer_level else 10.5
                     level_factor = 1.0 - math.exp(-level_rate * level_dt)
                     self.visualizer_level += (target_level - self.visualizer_level) * level_factor

            elif self.sidebar_vis:
                 self.sidebar_vis.set_active(False)
                 
            if self.current_chart and self.current_chart.metadata.BPM > 0:
                 base_bpm = self.current_chart.metadata.BPM
                 beat_interval = 60000.0 / base_bpm
                 seg_off = self.timeline.get_segment_offset_visual(self.timeline.current_time)

                 if not hasattr(self, '_last_seg_off') or seg_off != self._last_seg_off:
                     self._last_seg_off = seg_off
                     self.last_metronome_beat = -1

                 current_beat_index = int(math.floor((self.timeline.current_time - seg_off + 10) / beat_interval))

                 if current_beat_index > self.last_metronome_beat:
                     if self.metronome_active and self.metronome_sound:
                         if not getattr(self.timeline, 'dragging_bpm_tag', None):
                             self.metronome_sound.set_volume(1.0)
                             self.metronome_sound.play()

                     if self.enable_beatflash:
                        self.timeline.beat_flash_intensity = 1.0

                     self.last_metronome_beat = current_beat_index

            if self.timeline.selection_start is not None:
                self.timeline.update_selection_rect()
            
            if self.timeline.dragging_objects:
                self.timeline.update_dragged_objects()
            
            self.check_and_play_notes()
            self.timeline.update()

    def update_visualizer_worker_state(self):
        if self.enable_visualizer:
            if self.vis_worker is None:
                self.vis_worker = VisualizerWorker()
                self.vis_worker.result_ready.connect(self.on_vis_result)
                self.vis_worker.start()
            return
        if self.vis_worker:
            self.vis_worker.stop()
            self.vis_worker.deleteLater()
            self.vis_worker = None
        self.visualizer_level = 0.0
        if self.sidebar_vis:
            self.sidebar_vis.set_active(False)
            self.sidebar_vis.set_bands([0.0] * 31)
        self.timeline.vis_bar_heights.fill(0.0)
        self.timeline.update()

    def on_vis_result(self, bands):
        if not self.is_playing: return
        if self.sidebar_vis:
            self.sidebar_vis.set_bands(bands)

    def check_and_play_notes(self):
        if not self.current_chart:
            return
        
        current_time = self.timeline.visual_to_audio_ms(self.timeline.current_time)
        hit_window = 40 * self.playback_speed
        
        played_sounds_this_tick = {}
        played_sounds_meta_this_tick = {}
        
        temp_idx = self.next_note_index
        while temp_idx < len(self.current_chart.hit_objects):
            obj = self.current_chart.hit_objects[temp_idx]
            obj_id = obj.uid
            head_diff = obj.time - current_time

            if head_diff > hit_window:
                break
                
            if obj.time < current_time - hit_window:
                self.next_note_index = temp_idx + 1
                self.last_played_notes.discard((obj_id, 'head'))

            head_key = (obj_id, 'head')
            if abs(head_diff) <= hit_window and head_key not in self.last_played_notes:
                sound_key = None

                custom_type = self.timeline.get_custom_type_data(obj) if obj.custom_data is not None else None
                custom_hitsound = str(custom_type.get("hitsound") or "") if custom_type else ""
                custom_is_event = bool(custom_type and custom_type.get("kind") == "Event")
                if custom_hitsound and not (custom_is_event and getattr(self, 'mute_event_sfx', False)):
                    if custom_hitsound.startswith("standard:"):
                        sound_key = SOUND_FILES_MAP.get(custom_hitsound.removeprefix("standard:"))
                    elif custom_hitsound.startswith("custom:"):
                        filename = custom_hitsound.removeprefix("custom:")
                        if filename and Path(filename).name == filename:
                            sound_key = filename
                elif obj.is_event:
                    if getattr(self, 'mute_event_sfx', False):
                        pass
                    elif obj.is_flip: sound_key = SOUND_FILES_MAP['Event Flip']
                    elif obj.is_instant_flip: sound_key = SOUND_FILES_MAP['Event Instant']
                    elif obj.is_toggle_center: sound_key = SOUND_FILES_MAP['Event Toggle']
                else:
                    if obj.is_spike: sound_key = SOUND_FILES_MAP['Spike']
                    elif obj.is_hold: sound_key = SOUND_FILES_MAP['Hold Start']
                    elif obj.is_brawl_hold: sound_key = SOUND_FILES_MAP['Brawl Hold Start']
                    elif obj.is_screamer: sound_key = SOUND_FILES_MAP['Double Start']
                    elif obj.is_spam: sound_key = SOUND_FILES_MAP['Spam']
                    elif obj.is_brawl_hit: sound_key = SOUND_FILES_MAP['Brawl Hit']
                    elif obj.is_brawl_final: sound_key = SOUND_FILES_MAP['Brawl Knockout']
                    elif obj.is_brawl_spam: sound_key = SOUND_FILES_MAP['Spam']
                    elif obj.is_hide: sound_key = SOUND_FILES_MAP['Hide Note']
                    else:
                        sound_key = SOUND_FILES_MAP['Note']

                if sound_key and sound_key in self.sounds:
                     pan_val = 0.0

                     dedup_key = sound_key
                     is_default_conflict = False
                     
                     s_map_note = SOUND_FILES_MAP.get('Note')
                     s_map_hold = SOUND_FILES_MAP.get('Hold Start')
                     
                     if getattr(self, 'is_default_conflict_active', False):
                         if sound_key in (s_map_note, s_map_hold):
                             dedup_key = 'Note_Hold_Group'
                             is_default_conflict = True

                     channel = None
                     should_play = False
                     
                     if dedup_key not in played_sounds_this_tick:
                         should_play = True
                     else:
                         if is_default_conflict:
                             old_sound_key = played_sounds_meta_this_tick.get(dedup_key)
                             if old_sound_key == s_map_note and sound_key == s_map_hold:
                                 should_play = True
                                 old_channel = played_sounds_this_tick.get(dedup_key)
                                 if old_channel:
                                     old_channel.stop()
                         
                         if not should_play:
                             channel = played_sounds_this_tick[dedup_key]

                     if should_play:
                         channel = self.sounds[sound_key].play()
                         played_sounds_this_tick[dedup_key] = channel
                         if is_default_conflict:
                             played_sounds_meta_this_tick[dedup_key] = sound_key
                         
                         if channel:
                              vol = self.get_effective_fx_volume()
                              left_vol = 1.0 - max(0.0, pan_val)
                              right_vol = 1.0 + min(0.0, pan_val)
                              channel.set_volume(left_vol * vol, right_vol * vol)

                     if channel and (obj.is_hold or obj.is_brawl_hold):
                         if not hasattr(self, 'active_hold_sounds'):
                             self.active_hold_sounds = {}
                         old_channel = self.active_hold_sounds.get(obj_id)
                         if old_channel and old_channel.get_busy():
                             old_channel.stop()
                         self.active_hold_sounds[obj_id] = channel
                self.last_played_notes.add(head_key)
                
                if obj.is_hold or obj.is_screamer or obj.is_brawl_hold or obj.is_spam or obj.is_brawl_spam or self.timeline.is_custom_length(obj):
                    self.active_tails.append(obj)

            if abs(head_diff) <= hit_window:
                self.next_note_index = temp_idx + 1
                self.last_played_notes.discard(head_key)
            
            temp_idx += 1

        still_active_tails = []
        for obj in self.active_tails:
            obj_id = obj.uid
            tail_diff = obj.end_time - current_time
            tail_key = (obj_id, 'tail')

            if tail_diff > hit_window:
                still_active_tails.append(obj)
            elif abs(tail_diff) <= hit_window and tail_key not in self.last_played_notes:
                if (obj.is_hold or obj.is_brawl_hold) and hasattr(self, 'active_hold_sounds'):
                    active_channel = self.active_hold_sounds.get(obj_id)
                    if active_channel and active_channel.get_busy():
                        active_channel.stop()

                if obj.is_brawl_hold:
                    tail_sound_key = SOUND_FILES_MAP['Brawl Knockout'] if getattr(obj, 'is_brawl_hold_knockout', False) else SOUND_FILES_MAP['Brawl Hit']
                else:
                    tail_sound_key = SOUND_FILES_MAP['Note']

                if tail_sound_key in self.sounds:
                    dedup_key = tail_sound_key
                    is_default_conflict = False
                    
                    s_map_note = SOUND_FILES_MAP.get('Note')
                    s_map_hold = SOUND_FILES_MAP.get('Hold Start')
                    
                    if getattr(self, 'is_default_conflict_active', False):
                        if tail_sound_key in (s_map_note, s_map_hold):
                            dedup_key = 'Note_Hold_Group'
                            is_default_conflict = True

                    should_play = False
                    if dedup_key not in played_sounds_this_tick:
                        should_play = True
                    else:
                        if is_default_conflict:
                            old_sound_key = played_sounds_meta_this_tick.get(dedup_key)
                            if old_sound_key == s_map_note and tail_sound_key == s_map_hold:
                                should_play = True
                                old_channel = played_sounds_this_tick.get(dedup_key)
                                if old_channel:
                                    old_channel.stop()

                    if should_play:
                        tail_channel = self.sounds[tail_sound_key].play()
                        played_sounds_this_tick[dedup_key] = tail_channel
                        if is_default_conflict:
                            played_sounds_meta_this_tick[dedup_key] = tail_sound_key
                        if tail_channel:
                            eff_fx = self.get_effective_fx_volume()
                            tail_channel.set_volume(eff_fx, eff_fx)
                self.last_played_notes.add(tail_key)
                self.last_played_notes.discard(tail_key)
        
        self.active_tails = still_active_tails

    def keyPressEvent(self, e: QKeyEvent):
        if getattr(self, 'start_screen', None) and self.start_screen.isVisible():
            e.ignore()
            return
        if not e.isAutoRepeat():
            self.pressed_keys.add(e.key())
        if e.isAutoRepeat():
            e.ignore()
            return
            
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
             if e.key() == Qt.Key.Key_Z or e.key() == Qt.Key.Key_Y:
                 if hasattr(self, 'undo_redo_timer') and self.undo_redo_timer.isActive():
                     return

                 if not hasattr(self, 'undo_redo_timer'):
                     self.undo_redo_timer = QTimer(self)
                     self.undo_redo_timer.timeout.connect(self.perform_undo_redo_action)
                 
                 self.current_undo_key = (e.key(), e.modifiers())
                 self.perform_undo_redo_action()
                 
                 try: self.undo_redo_timer.timeout.disconnect()
                 except: pass
                 
                 def fast_repeat():
                    self.perform_undo_redo_action()
                    self.undo_redo_timer.setInterval(50)

                 self.undo_redo_timer.timeout.connect(fast_repeat)
                 
                 self.undo_redo_timer.start(500)
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
        def play_panned(widget):
            self.play_ui_sound_suppressed('UI Click', self.get_pan_for_widget(widget))
            widget.animateClick()
        pk = self.pressed_keys | (self.timeline.pressed_keys if hasattr(self, 'timeline') else set())
        kb = getattr(self, 'current_keybinds', DEFAULT_KEYBINDS)

        if check_keybind_match_exact(kb.get("toggle_video_preview", "V"), e.key(), e.modifiers(), pk):
            self.toggle_video_preview()
            self.last_hotkey_time[key_id] = current_time
            e.accept()
            return

        is_tab_note = check_keybind_match(kb.get("tab_note", "Ctrl+1"), e.key(), e.modifiers(), pk)
        is_tab_brawl = check_keybind_match(kb.get("tab_brawl", "Ctrl+2"), e.key(), e.modifiers(), pk)
        is_tab_event = check_keybind_match(kb.get("tab_event", "Ctrl+3"), e.key(), e.modifiers(), pk)

        if is_tab_note:
            play_panned(self.btn_tool_note)
            self.last_hotkey_time[key_id] = current_time
            handled = True
        elif is_tab_brawl:
            play_panned(self.btn_tool_brawl)
            self.last_hotkey_time[key_id] = current_time
            handled = True
        elif is_tab_event:
            play_panned(self.btn_tool_event)
            self.last_hotkey_time[key_id] = current_time
            handled = True
        else:
            if self.timeline.current_tool_type == "note":
                if key == Qt.Key.Key_1: play_panned(self.btn_note_normal); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_2: play_panned(self.btn_note_spike); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_3: play_panned(self.btn_note_hold); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_4: play_panned(self.btn_note_screamer); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_5: play_panned(self.btn_note_spam); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_6: play_panned(self.btn_note_freestyle); self.last_hotkey_time[key_id] = current_time; handled = True
            elif self.timeline.current_tool_type == "brawl":
                if key == Qt.Key.Key_1: play_panned(self.btn_brawl_hit); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_2: play_panned(self.btn_brawl_final); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_3: play_panned(self.btn_brawl_hold); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_4: play_panned(self.btn_brawl_hold_ko); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_5: play_panned(self.btn_brawl_spam); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_6: play_panned(self.btn_brawl_spam_ko); self.last_hotkey_time[key_id] = current_time; handled = True
            elif self.timeline.current_tool_type == "event":
                if key == Qt.Key.Key_1: play_panned(self.btn_event_flip); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_2: play_panned(self.btn_event_toggle); self.last_hotkey_time[key_id] = current_time; handled = True
                elif key == Qt.Key.Key_3: play_panned(self.btn_event_instant); self.last_hotkey_time[key_id] = current_time; handled = True

        if handled:
            e.accept()
            return
        
        pk = self.pressed_keys | (self.timeline.pressed_keys if hasattr(self, 'timeline') else set())
        kb = getattr(self, 'current_keybinds', DEFAULT_KEYBINDS)

        if check_keybind_match(kb.get("jump_start", "Shift+Space"), e.key(), e.modifiers(), pk):
            if e.isAutoRepeat():
                e.accept()
                return
            self.stop_and_reset()
            e.accept()

        elif check_keybind_match(kb.get("jump_end", "Ctrl+Space"), e.key(), e.modifiers(), pk):
            if e.isAutoRepeat():
                e.accept()
                return
            if hasattr(self, 'timeline') and self.timeline:
                song_len = self.timeline.get_visual_song_length()
                if song_len > 0:
                    if self.is_playing:
                        self.is_playing = False
                        self.stop_music_playback()
                        self._audio_waiting_for_zero = False
                        self.stop_all_hold_sounds()
                        if self.sidebar_vis:
                            self.sidebar_vis.set_active(False)
                    self.timeline.current_time = float(song_len)
                    self.timeline.target_time = float(song_len)
                    self.sync_audio_to_time()
                    self.timeline.update_scrollbar()
                    self.timeline.update()
            e.accept()

        elif check_keybind_match(kb.get("play_pause", "Space"), e.key(), e.modifiers(), pk):
            if e.isAutoRepeat():
                e.accept()
                return
            self.toggle_play()
            e.accept()

        elif e.key() == Qt.Key.Key_S and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.save_current()
            e.accept()
        elif check_keybind_match(kb.get("triplet_toggle", "T"), e.key(), e.modifiers(), pk):
            if not e.isAutoRepeat():
                self.timeline.toggle_triplet()
            e.accept()
        elif check_keybind_match(kb.get("grid_half", "E"), e.key(), e.modifiers(), pk):
            if not e.isAutoRepeat():
                self.timeline.halve_grid()
            e.accept()
        elif check_keybind_match(kb.get("grid_double", "R"), e.key(), e.modifiers(), pk):
            if not e.isAutoRepeat():
                self.timeline.double_grid()
            e.accept()
        elif check_keybind_match(kb.get("toggle_metronome", "M"), e.key(), e.modifiers(), pk):
            if not e.isAutoRepeat():
                if hasattr(self, 'chk_metronome') and self.chk_metronome:
                    self.chk_metronome.setChecked(not self.chk_metronome.isChecked())
                else:
                    self.metronome_active = not getattr(self, 'metronome_active', False)
            e.accept()
        elif e.key() == Qt.Key.Key_Delete or e.key() == Qt.Key.Key_Backspace:
            if self.timeline.selected_objects:
                self.timeline.save_undo_state()
                removed_objects = tuple(self.timeline.selected_objects)
                self.timeline.queue_delete_animations(removed_objects)
                for o in removed_objects:
                    if o in self.current_chart.hit_objects:
                        self.current_chart.hit_objects.remove(o)
                self.timeline.selected_objects.clear()
                self.timeline.update()
                self.timeline.editor.mark_unsaved()
                self.timeline.sync_structural_object_caches(removed_objects)
            e.accept()

    def on_update_channel_selected(self, channel):
        if channel not in ("Stable", "Preview"):
            return
        previous_channel = getattr(self, "update_channel", "Stable")
        if channel != previous_channel:
            self.discard_pending_update()
        self.update_channel = channel
        self.save_game_config()
        self.check_updates(channel, force=True)

    def discard_pending_update(self, close_toast=True):
        pending = getattr(self, "_pending_update", None)
        worker = getattr(self, "update_download_worker", None)
        if worker is not None and worker.isRunning():
            worker._discarded_update = True
            worker.requestInterruption()
        self._pending_update = None
        self._queued_update_install = None
        if pending:
            try:
                download_path = Path(pending["download"])
                if download_path.is_file() or download_path.is_symlink():
                    download_path.unlink()
            except OSError:
                pass
        if close_toast:
            entry = self.save_toast.find_entry("available_update")
            if entry is not None:
                entry.set_action(None)
                entry.set_close_available(False)
                entry.exiting = True
                activate_ui_animation(self.save_toast)

    def manual_update_check_remaining(self):
        return max(0.0, self._manual_update_check_available_at - time.monotonic())

    def request_manual_update_check(self):
        if self.manual_update_check_remaining() > 0.0:
            return False
        requested_channel = getattr(self, "update_channel", "Stable")
        if any(thread.isRunning() and thread.channel == requested_channel for thread in getattr(self, "_update_check_threads", ())):
            self.save_toast.show_message("Update check already in progress", background_color="#555555")
            return False
        self._manual_update_check_available_at = time.monotonic() + 180.0
        self.check_updates(requested_channel, manual=True, force=True)
        return True

    def update_last_checked_time(self):
        self._update_last_checked_at = time.time()
        dialog = getattr(self, "settings_dialog", None)
        if dialog is not None and hasattr(dialog, "search_update_last_checked_label"):
            dialog.update_search_update_button()

    def check_updates(self, channel=None, manual=False, force=False):
        requested_channel = channel if channel in ("Stable", "Preview") else getattr(self, "update_channel", "Stable")
        if self._update_checks_disabled_for_session and not manual and not force:
            return
        if not manual and not force and self.save_toast.find_entry("available_update") is not None:
            return
        if any(thread.isRunning() and thread.channel == requested_channel for thread in getattr(self, "_update_check_threads", ())):
            if manual:
                self.save_toast.show_message("Update check already in progress", background_color="#555555")
            return
        self._last_requested_update_channel = requested_channel
        if not hasattr(self, "_update_check_threads"):
            self._update_check_threads = set()
        thread = UpdateChecker(requested_channel, self)
        self._update_check_threads.add(thread)
        thread.checked.connect(lambda version, result_channel, is_manual=manual, is_forced=force: self.on_update_check_result(version, result_channel, is_manual, is_forced))
        thread.failed.connect(lambda message, result_channel, is_manual=manual: self.on_update_check_failed(message, result_channel, is_manual))
        thread.finished.connect(lambda worker=thread: self._update_check_threads.discard(worker))
        thread.start()

    def on_update_check_result(self, version, channel, manual=False, force=False):
        if channel != getattr(self, "_last_requested_update_channel", channel):
            return
        self.update_last_checked_time()
        if not version:
            if manual:
                self.save_toast.show_message(
                    f"{channel} is up to date",
                    background_color="#555555",
                )
            return
        if self._update_checks_disabled_for_session and not manual and not force:
            return
        if manual:
            self.show_update_popup(version, channel)
        else:
            QTimer.singleShot(2000, lambda: self.show_delayed_update_popup(version, channel, force))

    def on_update_check_failed(self, message, channel, manual=False):
        if channel == getattr(self, "_last_requested_update_channel", channel):
            self.update_last_checked_time()
        if manual and channel == getattr(self, "_last_requested_update_channel", channel):
            entry = self.save_toast.show_message("Could not check for updates", background_color="#555555")
            entry.setToolTip(message)

    def show_delayed_update_popup(self, version, channel, force=False):
        if (force or not self._update_checks_disabled_for_session) and channel == getattr(self, "_last_requested_update_channel", channel):
            self.show_update_popup(version, channel)

    def play_update_exit_sound(self):
        self.play_ui_sound("UI Update Exit")

    def dismiss_update_popup(self):
        self._update_checks_disabled_for_session = True
        self.update_check_timer.stop()
        self.play_update_exit_sound()

    def show_update_popup(self, version, channel="Stable"):
        display_version = str(version)
        if not display_version.lower().startswith("v"):
            display_version = f"v{display_version}"
        pending = getattr(self, "_pending_update", None)
        if pending and pending.get("ready") and pending.get("version") == str(version) and pending.get("channel") == str(channel):
            entry = self.save_toast.show_message(
                "Click to update now or discard to update on close",
                duration=None,
                background_color="#50AB4F",
                on_click=self.install_ready_update_now,
                persistent=True,
                closable=True,
                key="available_update",
                on_close=self.dismiss_update_popup,
                reserve_text="Click to update now or discard to update on close",
            )
            entry.set_progress(None)
            return
        if pending and pending.get("ready"):
            self.discard_pending_update(close_toast=False)
            pending = None
        worker = getattr(self, "update_download_worker", None)
        if worker is not None and worker.isRunning() and not getattr(worker, "_discarded_update", False):
            return
        blocked = not self.can_install_updates()
        prefix = "[BLOCKED] " if blocked else ""
        action = "Update installation is unavailable" if blocked else "Click to update"
        self.save_toast.show_message(
            f"{prefix}{channel} update available: {display_version} — {action}",
            duration=None,
            background_color="#50AB4F",
            on_click=None if blocked else lambda: self.start_update_install(str(version), channel),
            persistent=True,
            closable=True,
            key="available_update",
            on_close=self.dismiss_update_popup,
            reserve_text="Click to update now or discard to update on close",
        )

    def can_install_updates(self):
        if not is_packaged_application():
            return False
        if os.path.exists("/.flatpak-info") or os.environ.get("FLATPAK_ID"):
            return False
        return sys.platform.startswith("win") or sys.platform.startswith("linux")

    def update_asset_name(self, version):
        clean_version = str(version).strip()
        if not clean_version.lower().startswith("v"):
            clean_version = f"v{clean_version}"
        suffix = ".exe" if sys.platform.startswith("win") else ""
        return f"CBM_Editor_{clean_version}{suffix}"

    def show_update_error(self, message, version=None, channel=None):
        pending = getattr(self, "_pending_update", None)
        version = str(version if version is not None else pending.get("version", "") if pending else "")
        channel = str(channel if channel is not None else pending.get("channel", "Update") if pending else "Update")
        display_version = version if version.lower().startswith("v") else f"v{version}" if version else ""
        label = f"{channel} {display_version} update failed".replace("  ", " ").strip()
        entry = self.save_toast.find_entry("available_update")
        if entry is None:
            entry = self.save_toast.show_message(
                label,
                duration=None,
                background_color="#B5505A",
                persistent=True,
                closable=True,
                key="available_update",
                on_close=self.dismiss_update_popup,
                reserve_text="Click to update now or discard to update on close",
            )
        else:
            entry.set_message(label)
        entry.setToolTip(str(message))
        entry.set_progress(None)
        entry.set_close_available(True)
        if version and channel in ("Stable", "Preview"):
            entry.set_action(lambda: self.start_update_install(version, channel))

    def start_update_install(self, version, channel):
        if not self.can_install_updates():
            return
        existing_worker = getattr(self, "update_download_worker", None)
        if existing_worker is not None and existing_worker.isRunning():
            if getattr(existing_worker, "_discarded_update", False):
                self._queued_update_install = (str(version), str(channel))
            return

        previous = getattr(self, "_pending_update", None)
        if previous and previous.get("ready"):
            try:
                previous_download = Path(previous["download"])
                if previous_download.is_file():
                    previous_download.unlink()
            except Exception as error:
                self.show_update_error(error, version, channel)
                return
            self._pending_update = None

        asset_name = self.update_asset_name(version)
        if Path(asset_name).name != asset_name:
            self.show_update_error("The update asset name is invalid.", version, channel)
            return
        current_executable = get_application_executable_path()
        if current_executable is None:
            self.show_update_error("The running application file could not be located.", version, channel)
            return
        installed_update = sys.platform.startswith("win") and is_windows_installation_active()
        if installed_update:
            target_executable = get_windows_installed_executable(False)
        else:
            target_executable = current_executable.parent / asset_name
        if target_executable.exists() and target_executable != current_executable:
            self.show_update_error(f"The target application already exists:\n{target_executable.name}", version, channel)
            return
        download_path = target_executable.parent / f".{asset_name}.download"
        self._pending_update = {
            "version": str(version),
            "channel": str(channel),
            "asset_name": asset_name,
            "current": current_executable,
            "target": target_executable,
            "download": download_path,
            "installed": installed_update,
            "ready": False,
            "restart_after_update": False,
        }

        display_version = str(version)
        if not display_version.lower().startswith("v"):
            display_version = f"v{display_version}"
        entry = self.save_toast.find_entry("available_update")
        if entry is None:
            entry = self.save_toast.show_message(
                "",
                duration=None,
                background_color="#50AB4F",
                persistent=True,
                closable=True,
                key="available_update",
                on_close=self.dismiss_update_popup,
                reserve_text="Click to update now or discard to update on close",
            )
        entry.set_action(None)
        entry.set_close_available(False)
        entry.set_progress(0)
        entry.set_message(f"Installing {channel} {display_version}... 0%")

        worker = UpdateDownloadWorker(version, asset_name, download_path, self)
        worker._discarded_update = False
        self.update_download_worker = worker
        def update_download_progress(value):
            if getattr(worker, "_discarded_update", False):
                return
            value = max(0, min(100, int(value)))
            entry.set_progress(value)
            entry.set_message(f"Installing {channel} {display_version}... {value}%")
        worker.progress.connect(update_download_progress)
        worker.downloaded.connect(lambda path, current_worker=worker: self.finish_update_download(path, current_worker))
        worker.failed.connect(lambda message, current_worker=worker: self.fail_update_download(message, current_worker))
        worker.finished.connect(lambda current_worker=worker: self.finish_update_download_worker(current_worker))
        worker.start()

    def fail_update_download(self, message, worker=None):
        if worker is not None and getattr(worker, "_discarded_update", False):
            return
        self.show_update_error(message)

    def finish_update_download(self, downloaded_path, worker=None):
        if worker is not None and getattr(worker, "_discarded_update", False):
            try:
                Path(downloaded_path).unlink(missing_ok=True)
            except OSError:
                pass
            return
        pending = getattr(self, "_pending_update", None)
        if not pending or Path(downloaded_path) != pending["download"]:
            return
        pending["ready"] = True
        entry = self.save_toast.find_entry("available_update")
        if entry is not None:
            display_version = str(pending["version"])
            if not display_version.lower().startswith("v"):
                display_version = f"v{display_version}"
            entry.set_progress(None)
            entry.set_message("Click to update now or discard to update on close")
            entry.set_action(self.install_ready_update_now)
            entry.set_close_available(True)

    def finish_update_download_worker(self, worker):
        if getattr(self, "update_download_worker", None) is worker:
            self.update_download_worker = None
        queued = getattr(self, "_queued_update_install", None)
        if not queued:
            return
        self._queued_update_install = None
        version, channel = queued
        if channel == getattr(self, "update_channel", "Stable"):
            QTimer.singleShot(0, lambda: self.start_update_install(version, channel))

    def install_ready_update_now(self):
        pending = getattr(self, "_pending_update", None)
        if not pending or not pending.get("ready") or pending.get("helper_launched"):
            return
        if not self.confirm_unsaved_changes("update"):
            return
        pending["restart_after_update"] = True
        self._update_shutdown_approved = True
        self.close()

    def launch_update_helper(self, pending):
        current = Path(pending["current"]).resolve()
        downloaded = Path(pending["download"]).resolve()
        target = Path(pending["target"]).resolve()
        if target.parent != current.parent:
            raise RuntimeError("The update target is outside the application folder.")
        if not downloaded.is_file():
            raise RuntimeError("The downloaded update file no longer exists.")

        helper_env = get_windows_helper_environment() if sys.platform.startswith("win") else os.environ.copy()
        helper_env.update({
            "CBM_UPDATE_OLD": str(current),
            "CBM_UPDATE_DOWNLOADED": str(downloaded),
            "CBM_UPDATE_TARGET": str(target),
            "CBM_UPDATE_PID": str(os.getpid()),
            "CBM_UPDATE_RESTART": "1" if pending.get("restart_after_update") else "0",
        })

        if sys.platform.startswith("win") and pending.get("installed"):
            shortcut_paths = get_windows_shortcut_paths()
            preview_target = pending["channel"].casefold() == "preview"
            helper_env.update({
                "CBM_UPDATE_SHORTCUT": str(shortcut_paths[1 if preview_target else 0]),
                "CBM_UPDATE_OTHER_SHORTCUT": str(shortcut_paths[0 if preview_target else 1]),
                "CBM_UPDATE_SHORTCUT_DESCRIPTION": "CBM Editor -PREVIEW-" if preview_target else "CBM Editor",
                "CBM_UPDATE_REFRESH_SHORTCUT": "1",
            })
        else:
            helper_env["CBM_UPDATE_REFRESH_SHORTCUT"] = "0"

        if sys.platform.startswith("win"):
            helper_script = (
                "$old=$env:CBM_UPDATE_OLD; $downloaded=$env:CBM_UPDATE_DOWNLOADED; "
                "$target=$env:CBM_UPDATE_TARGET; $processId=[int]$env:CBM_UPDATE_PID; "
                "Wait-Process -Id $processId -ErrorAction SilentlyContinue; "
                "$deadline=[DateTime]::UtcNow.AddSeconds(60); $installed=$false; "
                "while (-not $installed -and [DateTime]::UtcNow -lt $deadline) { "
                "if (Test-Path -LiteralPath $downloaded -PathType Leaf) { "
                "try { Move-Item -LiteralPath $downloaded -Destination $target -Force -ErrorAction Stop; $installed=$true } "
                "catch { Start-Sleep -Milliseconds 100 } "
                "} else { $installed=Test-Path -LiteralPath $target -PathType Leaf } }; "
                "if ($installed -and ($old -ne $target)) { "
                "while ((Test-Path -LiteralPath $old -PathType Leaf) -and [DateTime]::UtcNow -lt $deadline) { "
                "try { Remove-Item -LiteralPath $old -Force -ErrorAction Stop } "
                "catch { Start-Sleep -Milliseconds 100 } } }; "
                "if ($installed -and $env:CBM_UPDATE_REFRESH_SHORTCUT -eq '1') { try { "
                "$shortcutPath=$env:CBM_UPDATE_SHORTCUT; $otherShortcut=$env:CBM_UPDATE_OTHER_SHORTCUT; "
                "if (Test-Path -LiteralPath $shortcutPath -PathType Leaf) { Remove-Item -LiteralPath $shortcutPath -Force }; "
                "if (Test-Path -LiteralPath $otherShortcut -PathType Leaf) { Remove-Item -LiteralPath $otherShortcut -Force }; "
                "$shell=New-Object -ComObject WScript.Shell; $shortcut=$shell.CreateShortcut($shortcutPath); "
                "$shortcut.TargetPath=$target; $shortcut.WorkingDirectory=(Split-Path -LiteralPath $target); "
                "$shortcut.IconLocation=($target + ',0'); $shortcut.Description=$env:CBM_UPDATE_SHORTCUT_DESCRIPTION; "
                "$shortcut.Save() } catch {} }; "
                "if ($installed -and $env:CBM_UPDATE_RESTART -eq '1' -and (($old -eq $target) -or -not (Test-Path -LiteralPath $old))) { "
                "Start-Process -FilePath $target -WorkingDirectory (Split-Path -LiteralPath $target) }"
            )
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-WindowStyle",
                    "Hidden",
                    "-Command",
                    helper_script,
                ],
                env=helper_env,
                creationflags=creation_flags,
                close_fds=True,
            )
            return

        helper_script = (
            "old=$CBM_UPDATE_OLD; downloaded=$CBM_UPDATE_DOWNLOADED; "
            "target=$CBM_UPDATE_TARGET; process_id=$CBM_UPDATE_PID; "
            "while kill -0 \"$process_id\" 2>/dev/null; do sleep 0.1; done; "
            "if [ -f \"$downloaded\" ] && { [ \"$old\" = \"$target\" ] || [ ! -e \"$target\" ]; }; then "
            "chmod 755 \"$downloaded\" && mv -- \"$downloaded\" \"$target\" && "
            "{ [ \"$old\" = \"$target\" ] || rm -- \"$old\"; } && "
            "{ [ \"$CBM_UPDATE_RESTART\" != \"1\" ] || { cd -- \"$(dirname -- \"$target\")\" && exec \"$target\" >/dev/null 2>&1; }; }; fi"
        )
        subprocess.Popen(
            ["/bin/sh", "-c", helper_script],
            env=helper_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )

    def restart_for_setup(self):
        if not sys.platform.startswith("win"):
            return
        if not self.confirm_unsaved_changes("close"):
            return
        if is_packaged_application():
            executable = get_application_executable_path()
            if executable is None:
                StyledWarningDialog(self, "Setup Failed", "The running application file could not be located.").exec()
                return
            command = [str(executable), "--setup"]
        else:
            script = Path(sys.argv[0]).resolve()
            command = [sys.executable, str(script), "--setup"]
        try:
            environment = get_windows_helper_environment()
            subprocess.Popen(command, cwd=str(Path(command[0]).resolve().parent), env=environment, close_fds=True)
        except Exception as error:
            StyledWarningDialog(self, "Setup Failed", str(error)).exec()
            return
        self._update_shutdown_approved = True
        QApplication.quit()
