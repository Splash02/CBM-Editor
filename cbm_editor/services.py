from .timeline import *
from .video import *
from .versioning import release_tag_from_filename, select_available_update

register_shared_globals(globals())

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
        self.timer.setInterval(max(1, int(1000 / TARGET_FPS)))
        self.timer.timeout.connect(self.update_animation)
        self.timer.start()
        
        base_path = get_base_path()
        sound_path = None
        self.boot_sound = None
        self.boot_channel = None
        
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
             if not res_dir.exists():
                 try: res_dir.mkdir(parents=True, exist_ok=True)
                 except: pass

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
                    self.boot_sound = get_audio_engine().load_sound(sound_path)
                    self.boot_sound.set_volume(ui_volume)
                    self.boot_channel = self.boot_sound.play()
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
        self.release_boot_sound_when_finished()

    def release_boot_sound_when_finished(self):
        if self.boot_channel and self.boot_channel.get_busy():
            QTimer.singleShot(250, self.release_boot_sound_when_finished)
            return
        self.boot_channel = None
        if self.boot_sound:
            self.boot_sound.free()
            self.boot_sound = None
        self.deleteLater()
        
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


class AudioSynchronizerDialog(QDialog):
    def showEvent(self, event):
        apply_shadows_to_container(self)
        if hasattr(super(), "showEvent"): super().showEvent(event)

    def __init__(self, parent, audio_path, bpm, offset, metronome_path):
        super().__init__(parent)
        self.setWindowTitle("Offset Audio")
        self.audio_path = audio_path
        self.bpm = bpm
        self.offset = offset
        self.metronome_path = metronome_path
        self.playing = False
        self.preview_stream = None
        self.preview_wait_until = 0.0
        self.timeline = parent.timeline if hasattr(parent, 'timeline') else None
        self.save_worker = None
        self.save_temp_path = None
        self.save_progress_dialog = None
        
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        
        form = QFormLayout()
        self.spin_delay = QSpinBox()
        self.spin_delay.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.spin_delay.setRange(-5000, 5000)
        self.spin_delay.setSuffix(" ms")
        self.spin_delay.setValue(0)
        self.spin_delay.valueChanged.connect(self.on_delay_changed)
        form.addRow("Delay:", self.spin_delay)
        layout.addLayout(form)
        
        self.lbl_status = QLabel("Ready")
        layout.addWidget(self.lbl_status)
        
        btn_layout = QHBoxLayout()
        self.btn_play = QPushButton("Play Preview")
        self.btn_play.setFixedWidth(120)
        self.btn_play.clicked.connect(self.toggle_play)
        btn_layout.addWidget(self.btn_play)
        
        self.btn_reset = QPushButton("Reset")
        self.btn_reset.clicked.connect(self.reset_offset)
        btn_layout.addWidget(self.btn_reset)


        self.btn_save = QPushButton("Save && Close")
        self.btn_save.clicked.connect(self.save)
        btn_layout.addWidget(self.btn_save)
        
        layout.addLayout(btn_layout)
        
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(400)
        self.preview_timer.timeout.connect(self.restart_preview)
        
        self.start_time = 0
        self.beat_interval = 60000 / self.bpm if self.bpm > 0 else 500
        
        try:
            self.click_sound = get_audio_engine().load_sound(self.metronome_path)
        except:
            self.click_sound = None

    def reset_offset(self):
        try:
            audio_path = Path(self.audio_path)
            project_dir = audio_path.parent
            backup_dir = project_dir / "cbm_files"
            base_name = audio_path.stem
            backup_path = backup_dir / f"{base_name}_backup{audio_path.suffix}"
            
            if backup_path.exists():
                self.stop(release=True)
                 
                QApplication.processEvents()
                import time
                time.sleep(0.1)
                
                if audio_path.exists():
                    os.remove(audio_path)
                shutil.copy2(backup_path, audio_path)
                self.lbl_status.setText("Audio reset from backup!")
                
                if self.timeline:
                    self.timeline.temp_waveform_offset = 0
                    self.timeline.update()
                
                self.accept()
                return

            else:
                self.lbl_status.setText("No backup found.")
        except Exception as e:
            self.lbl_status.setText(f"Reset Error: {e}")

        self.on_delay_changed()

    def on_delay_changed(self):
        if self.timeline:
            self.timeline.temp_waveform_offset = self.spin_delay.value()
            self.timeline.update()
        
        if self.playing:
            self.stop()
            self.lbl_status.setText("Updating preview...")
            self.preview_timer.start()

    def restart_preview(self):
        self.play()

    def toggle_play(self):
        if self.playing:
            self.stop()
        else:
            self.play()
            
    def stop(self, release=False):
        if self.preview_stream:
            self.preview_stream.stop()
            if release:
                self.preview_stream.free()
                self.preview_stream = None
        self.timer.stop()
        self.playing = False
        self.preview_wait_until = 0.0
        self.btn_play.setText("Play Preview")
        self.lbl_status.setText("Stopped.")

        
    def play(self):
        if not os.path.exists(self.audio_path): return
        
        self.lbl_status.setText("Starting preview...")
        delay = self.spin_delay.value()
        
        try:
            if self.preview_stream is None:
                self.preview_stream = get_audio_engine().load_stream(self.audio_path)
            else:
                self.preview_stream.stop()
            self.start_time = time.perf_counter() * 1000.0
            if delay > 0:
                self.preview_wait_until = self.start_time + delay
            elif delay < 0:
                self.preview_stream.play_from_ms(abs(delay))
            else:
                self.preview_stream.play_from_ms(0)
            
            if self.timeline:
                start_beats = self.timeline.ms_to_visual_beats(0)
                self.next_beat = math.ceil(start_beats)
            else:
                self.next_beat = self.offset
                
            self.timer.start(10)
            self.playing = True
            self.btn_play.setText("Stop")
            self.lbl_status.setText("Playing...")
            
        except Exception as e:
            self.lbl_status.setText(f"Error: {e}")

    def tick(self):
        if not self.preview_stream:
            self.stop()
            return

        now = time.perf_counter() * 1000.0
        if self.preview_wait_until > 0.0:
            if now >= self.preview_wait_until:
                self.preview_wait_until = 0.0
                self.preview_stream.play_from_ms(0)
        elif not self.preview_stream.get_busy():
            self.stop()
            return
            
        current_pos = now - self.start_time
        
        if self.timeline:
            current_beats = self.timeline.ms_to_visual_beats(current_pos)
            
            if current_beats >= self.next_beat:
                if self.click_sound:
                    try:
                        self.click_sound.play()
                    except: pass
                self.next_beat = math.ceil(current_beats + 0.001)
        else:
            if current_pos >= self.next_beat:
                if self.click_sound:
                    try:
                        self.click_sound.play()
                    except: pass
                self.next_beat += self.beat_interval

    def save(self):
        delay = self.spin_delay.value()
        if delay == 0:
            self.accept()
            return

        self.stop(release=True)
        suffix = Path(self.audio_path).suffix.lower()
        if suffix not in {".mp3", ".wav"}:
            self.lbl_status.setText("Save Error: physical offset saving supports MP3 and WAV.")
            return
        self.lbl_status.setText("Saving audio offset...")
        self.spin_delay.setEnabled(False)
        self.btn_play.setEnabled(False)
        self.btn_reset.setEnabled(False)
        self.btn_save.setEnabled(False)
        source_path = Path(self.audio_path)
        self.save_temp_path = source_path.with_name(f"{source_path.name}.offset.tmp{suffix}")
        self.save_progress_dialog = AudioConversionProgressDialog(
            "Save Audio Offset",
            "Saving audio offset...",
            self,
        )
        self.save_worker = AudioConversionWorker(
            source_path,
            self.save_temp_path,
            output_format=suffix[1:],
            leading_silence_ms=delay if delay > 0 else 0,
            trim_start_ms=abs(delay) if delay < 0 else 0,
            parent=self,
        )
        self.save_worker.progress_changed.connect(self.on_save_progress)
        self.save_worker.conversion_ready.connect(self.on_save_ready)
        self.save_worker.conversion_failed.connect(self.on_save_failed)
        self.save_worker.finished.connect(self.save_worker.deleteLater)
        self.save_progress_dialog.show()
        self.save_worker.start()

    def on_save_progress(self, value):
        if self.save_progress_dialog:
            self.save_progress_dialog.set_progress(value)

    def on_save_ready(self, output_path, result):
        try:
            os.replace(output_path, self.audio_path)
            if self.timeline:
                self.timeline.temp_waveform_offset = 0
                self.timeline.update()
            if self.save_worker:
                self.save_worker.wait()
            if self.save_progress_dialog:
                self.save_progress_dialog.accept()
                self.save_progress_dialog.deleteLater()
            self.save_worker = None
            self.save_temp_path = None
            self.save_progress_dialog = None
            self.accept()
        except Exception as e:
            self.on_save_failed(str(e))

    def on_save_failed(self, message):
        if self.save_temp_path:
            try:
                Path(self.save_temp_path).unlink(missing_ok=True)
            except OSError:
                pass
        self.save_worker = None
        self.save_temp_path = None
        if self.save_progress_dialog:
            self.save_progress_dialog.reject()
            self.save_progress_dialog.deleteLater()
        self.save_progress_dialog = None
        self.spin_delay.setEnabled(True)
        self.btn_play.setEnabled(True)
        self.btn_reset.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.lbl_status.setText(f"Save Error: {message}")

    def release_audio_resources(self):
        self.stop(release=True)
        if self.click_sound:
            self.click_sound.free()
            self.click_sound = None

    def accept(self):
        self.release_audio_resources()
        super().accept()

             
    def closeEvent(self, e):
        if self.save_worker and self.save_worker.isRunning():
            e.ignore()
            return
        self.release_audio_resources()
        if self.click_sound:
            self.click_sound.free()
            self.click_sound = None
        if self.timeline:
            self.timeline.temp_waveform_offset = 0
            self.timeline.update()
        super().closeEvent(e)

class SidebarVisualizer(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        surface_format = self.format()
        surface_format.setSamples(0)
        self.setFormat(surface_format)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.bands = [0.0] * 31
        self.target_bands = [0.0] * 31
        self.peak_bands = [0.0] * 31
        self.peak_velocities = [0.0] * 31
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.setMinimumHeight(0)
        self.last_anim_time = time.perf_counter()
        self.active = False
        self._background_cache = None
        self._background_cache_signature = None

    def set_active(self, active):
        if active and not self.active:
            self.last_anim_time = time.perf_counter()
        self.active = active
        if not active:
             self.target_bands = [0.0] * 31
             self.peak_bands = [0.0] * 31

    def set_visible_based_on_height(self, window_height):
        if window_height < 600:
            if not self.isHidden():
                self.hide()
        else:
            if self.isHidden():
                self.show()

    def needs_animation(self):
        return (
            not self.isHidden()
            and (
                self.active
                or max(self.bands, default=0.0) >= 0.0001
                or max(self.peak_bands, default=0.0) >= 0.0001
            )
        )

    def animate(self):
        if self.isHidden(): return
        current_time = time.perf_counter()
        dt = current_time - self.last_anim_time
        self.last_anim_time = current_time
        dt_factor = dt * 60.0
        f_up = min(1.0, 0.4 * dt_factor)
        f_down = min(1.0, 0.15 * dt_factor)
        count = len(self.bands)
        for i in range(count):
            target = self.target_bands[i] if i < len(self.target_bands) else 0.0
            current = self.bands[i]
            
            if target > current:
                self.bands[i] = current + (target - current) * f_up
            else:
                self.bands[i] = current + (target - current) * f_down
                
            if self.bands[i] >= self.peak_bands[i]:
                self.peak_bands[i] = self.bands[i]
                self.peak_velocities[i] = 0.0
            else:
                self.peak_velocities[i] += 0.001 * dt_factor
                self.peak_bands[i] -= self.peak_velocities[i] * dt_factor
            if self.peak_bands[i] < self.bands[i]:
                self.peak_bands[i] = self.bands[i]
                self.peak_velocities[i] = 0.0

        if not self.active and max(self.bands, default=0.0) < 0.0001 and max(self.peak_bands, default=0.0) < 0.0001:
            self.bands = [0.0] * count
            self.peak_bands = [0.0] * count
            self.peak_velocities = [0.0] * count
        self.update()

    def set_bands(self, bands):
        if len(bands) != len(self.target_bands):
            self.bands = [0.0] * len(bands)
            self.target_bands = [0.0] * len(bands)
            self.peak_bands = [0.0] * len(bands)
            self.peak_velocities = [0.0] * len(bands)
        self.target_bands = bands

    def paintGL(self):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        window = self.window()
        dpr = max(1.0, float(self.devicePixelRatioF()))
        origin = self.mapTo(window, QPoint(0, 0))
        main_background = getattr(window, "_cached_main_bg", None)
        main_background_key = main_background.cacheKey() if main_background else 0
        background_signature = (
            max(1, int(round(self.width() * dpr))),
            max(1, int(round(self.height() * dpr))),
            round(dpr, 3),
            origin.x(),
            origin.y(),
            main_background_key,
            int(getattr(window, "ui_bg_opacity", 0)),
            QColor(UI_THEME["bg_dark"]).rgba(),
        )
        if self._background_cache_signature != background_signature:
            self._background_cache_signature = background_signature
            background_cache = QPixmap(background_signature[0], background_signature[1])
            background_cache.setDevicePixelRatio(dpr)
            background_cache.fill(QColor(UI_THEME["bg_dark"]))
            ui_bg_opacity = getattr(window, "ui_bg_opacity", 0)
            if ui_bg_opacity > 0 and main_background:
                background_painter = QPainter(background_cache)
                background_painter.setOpacity(ui_bg_opacity / 100.0)
                pixmap_dpr = main_background.devicePixelRatio()
                background_x = int((window.width() - main_background.width() / pixmap_dpr) / 2)
                background_y = int((window.height() - main_background.height() / pixmap_dpr) / 2)
                background_painter.drawPixmap(
                    QPointF(background_x - origin.x(), background_y - origin.y()),
                    main_background,
                )
                background_painter.end()
            self._background_cache = background_cache
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.drawPixmap(QPointF(0, 0), self._background_cache)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if self.height() < 20:
            p.end()
            return
        sf = getattr(self.window(), 'global_scale', 1.0)
        p.scale(sf, sf)
        w = self.width() / sf
        h = self.height() / sf
        
        count = len(self.bands)
        if count == 0:
            p.end()
            return
        bar_w = w / float(count)

        p.setPen(Qt.PenStyle.NoPen)
        base_col = QColor(ACCENT_COLOR)
        p.setBrush(base_col)

        bar_rects = []
        for i in range(count):
            val = min(1.0, max(0.0, self.bands[i]))
            val = val * val
            bar_h = val * h
            if bar_h > 0.01:
                bar_rects.append(QRectF(i * bar_w + 1, h - bar_h, bar_w - 2, bar_h))
        if bar_rects:
            p.drawRects(bar_rects)
            
        p.setBrush(base_col)
        peak_rects = []
        for i in range(count):
            p_val = min(1.0, max(0.0, self.peak_bands[i]))
            p_val = p_val * p_val
            peak_y = h - p_val * h
            if peak_y < h - 2:
                peak_rects.append(QRectF(i * bar_w + 1, peak_y - 2, bar_w - 2, 2))
        if peak_rects:
            p.drawRects(peak_rects)
        p.end()

class UpdateChecker(QThread):
    available = pyqtSignal(str, str)

    def __init__(self, channel="Stable", parent=None):
        super().__init__(parent)
        self.channel = "Preview" if str(channel).casefold() == "preview" else "Stable"

    def run(self):
        try:
            url = "https://api.github.com/repos/Splash02/CBM-Editor/tags?per_page=100"
            req = urllib.request.Request(url, headers={'User-Agent': 'CBM-Editor'})
            with urllib.request.urlopen(req, timeout=3) as response:
                tags = json.loads(response.read().decode())
            tag_names = [tag.get("name", "") for tag in tags if isinstance(tag, dict)]
            installed_channel = "Preview" if PREVIEW_VERSION else "Stable"
            application_path = get_application_executable_path()
            installed_tag = release_tag_from_filename(application_path.name if application_path else "") or VERSION_NUMBER
            update = select_available_update(
                tag_names,
                self.channel,
                installed_tag,
                installed_channel,
            )
            if update is not None:
                self.available.emit(update.tag, self.channel)
        except Exception:
            pass


class UpdateDownloadWorker(QThread):
    progress = pyqtSignal(int)
    downloaded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, tag, asset_name, destination, parent=None):
        super().__init__(parent)
        self.tag = str(tag)
        self.asset_name = str(asset_name)
        self.destination = Path(destination)

    def run(self):
        try:
            safe_tag = urllib.parse.quote(self.tag, safe="")
            safe_asset = urllib.parse.quote(self.asset_name, safe="")
            url = f"https://github.com/Splash02/CBM-Editor/releases/download/{safe_tag}/{safe_asset}"
            request = urllib.request.Request(url, headers={"User-Agent": "CBM-Editor"})
            self.destination.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(request, timeout=30) as response, open(self.destination, "wb") as output:
                content_type = str(response.headers.get("Content-Type", "")).lower()
                if "text/html" in content_type:
                    raise RuntimeError("GitHub did not return an application file.")
                total = int(response.headers.get("Content-Length", 0) or 0)
                received = 0
                while True:
                    if self.isInterruptionRequested():
                        raise InterruptedError()
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    received += len(chunk)
                    if total > 0:
                        self.progress.emit(min(99, int(received * 100 / total)))

            if self.destination.stat().st_size < 1024 * 1024:
                raise RuntimeError("The downloaded application file is unexpectedly small.")
            with open(self.destination, "rb") as downloaded_file:
                header = downloaded_file.read(4)
            if sys.platform.startswith("win") and not header.startswith(b"MZ"):
                raise RuntimeError("The downloaded Windows file is not a valid executable.")
            if sys.platform.startswith("linux") and header != b"\x7fELF":
                raise RuntimeError("The downloaded Linux file is not a valid executable.")
            self.progress.emit(100)
            self.downloaded.emit(str(self.destination))
        except InterruptedError:
            try:
                self.destination.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception as error:
            try:
                self.destination.unlink(missing_ok=True)
            except Exception:
                pass
            self.failed.emit(str(error))

class DiscordRPCWorker(QThread):
    connected = pyqtSignal()

    def __init__(self, client_id, parent=None):
        super().__init__(parent)
        self.client_id = client_id
        self.condition = threading.Condition()
        self.pending = None
        self.has_pending = False
        self.running = True

    def set_presence(self, payload):
        with self.condition:
            self.pending = payload
            self.has_pending = True
            self.condition.notify()

    def stop(self):
        with self.condition:
            self.running = False
            self.condition.notify()
        self.wait(3000)

    def run(self):
        rpc = None
        try:
            from pypresence import Presence
            rpc = Presence(self.client_id)
            rpc.connect()
            self.connected.emit()
            while True:
                with self.condition:
                    while self.running and not self.has_pending:
                        self.condition.wait()
                    if not self.running:
                        break
                    payload = self.pending
                    self.pending = None
                    self.has_pending = False
                try:
                    if payload is None:
                        rpc.clear()
                    else:
                        rpc.update(**payload)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            if rpc:
                try:
                    rpc.close()
                except Exception:
                    pass


class VisualizerWorker(QThread):
    result_ready = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.chunk_data = None
        self.running = True
        self.wait_cond = QWaitCondition()
        self.mutex = QMutex()
        self.vis_auto_gain = 1.0
        self._band_cache_key = None
        self._band_indices = None
        self._band_boosts = np.geomspace(1.0, 8.0, 31)

    def process_chunk(self, chunk_data):
        self.mutex.lock()
        self.chunk_data = chunk_data
        self.wait_cond.wakeAll()
        self.mutex.unlock()

    def stop(self):
        self.mutex.lock()
        self.running = False
        self.wait_cond.wakeAll()
        self.mutex.unlock()
        self.wait(2000)

    def run(self):
        while self.running:
            self.mutex.lock()
            if self.chunk_data is None:
                self.wait_cond.wait(self.mutex)
            
            if not self.running:
                self.mutex.unlock()
                break
                
            data = self.chunk_data
            self.chunk_data = None
            self.mutex.unlock()
            
            if data is None: continue

            fft_data, rate = data
            try:
                fft_arr = np.asarray(fft_data, dtype=np.float64)
                if len(fft_arr) > 10:
                    band_count = 31
                    min_freq = 40
                    max_freq = min(15000.0, rate / 2.0 * 0.95)

                    cache_key = (len(fft_arr), rate)
                    if self._band_cache_key != cache_key:
                        freqs = np.geomspace(min_freq, max_freq, band_count)
                        indices = np.rint(freqs * 2048.0 / rate).astype(np.int64)
                        for i in range(1, band_count):
                            if indices[i] <= indices[i - 1]:
                                indices[i] = indices[i - 1] + 1
                        self._band_cache_key = cache_key
                        self._band_indices = indices

                    mags = np.zeros(band_count, dtype=np.float64)
                    valid = self._band_indices < len(fft_arr)
                    mags[valid] = fft_arr[self._band_indices[valid]]
                    vis_bands = np.log10(1.0 + mags * self._band_boosts * 1200.0) * 1.2
                    current_max = max(0.01, float(vis_bands.max()))
                        
                    if current_max > self.vis_auto_gain:
                        self.vis_auto_gain = self.vis_auto_gain * 0.9 + current_max * 0.1
                    else:
                        self.vis_auto_gain = self.vis_auto_gain * 0.99 + current_max * 0.01
                        
                    if self.vis_auto_gain < 0.1: self.vis_auto_gain = 0.1
                    
                    norm_bands = vis_bands / self.vis_auto_gain
                    norm_bands /= 1.0 + norm_bands * 0.1
                    np.minimum(norm_bands, 1.0, out=norm_bands)
                    self.result_ready.emit(norm_bands.tolist())
            except Exception as e:
                pass

class BackupRestoreConfirmationDialog(QDialog):
    def __init__(self, difficulty, backup_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restore From Backup")
        self.setModal(True)

        year, month, day, hour, minute, second = get_beatmap_backup_timestamp_parts(backup_path)
        layout = QVBoxLayout(self)
        self.lbl_message = QLabel(
            f"This will overwrite the current {difficulty} beatmap with the state from the "
            f"{day}.{month}.{year} at {hour}:{minute}:{second}"
        )
        self.lbl_message.setWordWrap(True)
        self.lbl_message.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.lbl_message)

        self.button_layout = QHBoxLayout()
        self.button_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_yes = HoverButton("Yes")
        self.btn_yes.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_yes.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_yes.clicked.connect(self.accept)
        self.btn_no = HoverButton("No")
        self.btn_no.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_no.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_no.clicked.connect(self.reject)
        self.button_layout.addWidget(self.btn_yes, 1)
        self.button_layout.addWidget(self.btn_no, 1)
        layout.addLayout(self.button_layout)

        self.setFixedWidth(380)
        self.setFixedHeight(self.sizeHint().height())


class BackupRestoreSuccessDialog(QDialog):
    def __init__(self, difficulty, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Backup Applied")
        self.setModal(True)

        layout = QVBoxLayout(self)
        self.lbl_message = QLabel(f"The {difficulty} beatmap was restored successfully.")
        self.lbl_message.setWordWrap(True)
        self.lbl_message.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.lbl_message)

        self.btn_ok = HoverButton("OK")
        self.btn_ok.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_ok.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_ok.clicked.connect(self.accept)
        layout.addWidget(self.btn_ok)

        self.setFixedWidth(360)
        self.setFixedHeight(self.sizeHint().height())


class BackupWindow(QDialog):
    def __init__(self, editor, parent=None):
        super().__init__(parent or editor)
        self.editor = editor
        self.setWindowTitle("Restore From Backup")
        self.setModal(True)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Difficulty"))
        self.combo_difficulty = QComboBox()
        self.combo_difficulty.setView(SmoothListView(self.combo_difficulty))
        self.combo_difficulty.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_difficulty.currentTextChanged.connect(self.refresh_backups)
        layout.addWidget(self.combo_difficulty)

        layout.addWidget(QLabel("Backup"))
        self.combo_backup = QComboBox()
        self.combo_backup.setView(SmoothListView(self.combo_backup))
        self.combo_backup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_backup.currentIndexChanged.connect(self.update_apply_state)
        layout.addWidget(self.combo_backup)

        button_layout = QHBoxLayout()
        self.btn_apply = HoverButton("Apply")
        self.btn_apply.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_apply.clicked.connect(self.apply_backup)
        button_layout.addWidget(self.btn_apply)
        self.btn_close = HoverButton("Close")
        self.btn_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_close.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_close)
        layout.addLayout(button_layout)

        self.refresh_difficulties()
        self.setFixedWidth(420)
        self.setFixedHeight(self.sizeHint().height())

    def showEvent(self, event):
        brightness = getattr(self.editor, 'ui_brightness', 60)
        scale = getattr(self.editor, 'global_scale', 1.0)
        self.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, scale, brightness))
        apply_shadows_to_container(self)
        super().showEvent(event)

    def refresh_difficulties(self):
        selected = self.combo_difficulty.currentText()
        current_difficulty = getattr(getattr(self.editor, 'current_chart', None), 'difficulty_key', "")
        self.combo_difficulty.blockSignals(True)
        self.combo_difficulty.clear()
        for difficulty in DIFFICULTIES:
            chart = self.editor.beatmaps.get(difficulty)
            if chart and chart.created:
                self.combo_difficulty.addItem(difficulty)
        target = selected or current_difficulty
        index = self.combo_difficulty.findText(target)
        if index >= 0:
            self.combo_difficulty.setCurrentIndex(index)
        self.combo_difficulty.blockSignals(False)
        self.refresh_backups(self.combo_difficulty.currentText())

    def refresh_backups(self, difficulty):
        self.combo_backup.blockSignals(True)
        self.combo_backup.clear()
        project_folder = getattr(self.editor, 'project_folder', None)
        backups = list_beatmap_backups(project_folder, difficulty) if project_folder and difficulty else []
        duplicate_labels = {}
        for backup_path in backups:
            base_label = format_beatmap_backup_timestamp(backup_path)
            duplicate_labels[base_label] = duplicate_labels.get(base_label, 0) + 1
            label = base_label
            if duplicate_labels[base_label] > 1:
                label = f"{base_label} ({duplicate_labels[base_label]})"
            self.combo_backup.addItem(label, str(backup_path))
        self.combo_backup.blockSignals(False)
        self.update_apply_state()

    def update_apply_state(self):
        self.btn_apply.setEnabled(bool(self.combo_backup.currentData()))

    def apply_backup(self):
        difficulty = self.combo_difficulty.currentText()
        backup_value = self.combo_backup.currentData()
        if not difficulty or not backup_value:
            return
        confirmation = BackupRestoreConfirmationDialog(difficulty, Path(backup_value), self)
        confirmation_result = confirmation.exec()
        confirmation.deleteLater()
        if confirmation_result != QDialog.DialogCode.Accepted:
            return
        success, error = self.editor.restore_beatmap_backup(difficulty, Path(backup_value))
        if not success:
            QMessageBox.critical(self, "Backup Restore Failed", error)
            return
        success_dialog = BackupRestoreSuccessDialog(difficulty, self)
        success_dialog.exec()
        success_dialog.deleteLater()
        self.accept()


class ResourcesWindow(QDialog):
    def showEvent(self, event):
        b = self.editor.ui_brightness if hasattr(self.editor, 'ui_brightness') else 60
        scale = self.editor.global_scale if hasattr(self.editor, 'global_scale') else 1.0
        self.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, scale, b))
        self.apply_resource_styles()
        self.update_video_state()
        if hasattr(super(), "showEvent"):
            super().showEvent(event)
        self.reset_action_hover_states()
        apply_shadows_to_container(self)
        QTimer.singleShot(0, self.reset_action_hover_states)

    def reset_action_hover_states(self):
        cursor = __import__("PyQt6.QtGui", fromlist=["QCursor"]).QCursor.pos()
        for button in (
            self.btn_video_configuration,
            self.btn_reset_video,
            self.btn_backups,
        ):
            if hasattr(button, "_hover_progress"):
                hovered = button.isEnabled() and button.rect().contains(
                    button.mapFromGlobal(cursor)
                )
                button._hover_progress = 1.0 if hovered else 0.0
                button._hover_target = button._hover_progress
                button._action_pulse = 0.0
                button.update()

    def get_group_style(self):
        brightness = getattr(self.editor, 'ui_brightness', 60)
        panel_value = max(0, brightness - 26)
        panel_color = f"#{panel_value:02x}{panel_value:02x}{panel_value:02x}"
        return (
            f"QGroupBox {{ background-color: {panel_color}; margin-top: 15px; font-weight: bold; border: none; border-radius: 5px; }}"
            f"QGroupBox::title {{ background-color: {panel_color}; font-size: 24pt; subcontrol-origin: margin; left: 10px; padding: 2px 5px; border-radius: 4px; }}"
        )

    def apply_resource_styles(self):
        brightness = getattr(self.editor, 'ui_brightness', 60)
        background_value = max(0, brightness - 30)
        background_color = f"#{background_value:02x}{background_value:02x}{background_value:02x}"
        if hasattr(self, 'content_widget'):
            self.content_widget.setStyleSheet(
                f"QWidget#ResourcesContent {{ background-color: {background_color}; border-radius: 6px; }}"
            )
        group_style = self.get_group_style()
        for group in getattr(self, 'resource_groups', []):
            group.setStyleSheet(group_style)

    def __init__(self, editor, audio_label, cover_label, video_label):
        super().__init__(editor)
        self.editor = editor
        self.setWindowTitle("Map Resources")
        self.setModal(True)
        self.video_label = video_label


        b = self.editor.ui_brightness if hasattr(self.editor, 'ui_brightness') else 60
        scale = self.editor.global_scale if hasattr(self.editor, 'global_scale') else 1.0
        self.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, scale, b))

        main_layout = QVBoxLayout(self)
        self.content_widget = QWidget()
        self.content_widget.setObjectName("ResourcesContent")
        content_layout = QVBoxLayout(self.content_widget)

        self.audio_group = QGroupBox("Audio")
        audio_inner = QVBoxLayout()
        audio_inner.setContentsMargins(10, 5, 10, 10)
        audio_inner.addWidget(audio_label)
        self.audio_group.setLayout(audio_inner)
        content_layout.addWidget(self.audio_group)

        self.cover_group = QGroupBox("Cover Art")
        cover_inner = QVBoxLayout()
        cover_inner.setContentsMargins(10, 5, 10, 10)
        cover_inner.addWidget(cover_label)
        self.cover_group.setLayout(cover_inner)
        content_layout.addWidget(self.cover_group)

        self.video_group = QGroupBox("Video Background")
        video_inner = QVBoxLayout()
        video_inner.setContentsMargins(10, 5, 10, 10)
        video_inner.addWidget(video_label)
        self.btn_video_configuration = HoverButton("Video Configuration")
        self.btn_video_configuration.setToolTip("Configure video preview, offset and compression")
        self.btn_video_configuration.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_video_configuration.clicked.connect(self.open_video_configuration)
        video_inner.addWidget(self.btn_video_configuration)
        self.btn_reset_video = HoverButton("Reset Video")
        self.btn_reset_video.setToolTip("Remove currently selected video")
        self.btn_reset_video.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_reset_video.clicked.connect(self.reset_video)
        video_inner.addWidget(self.btn_reset_video)
        self.video_group.setLayout(video_inner)
        content_layout.addWidget(self.video_group)

        self.backups_group = QGroupBox("Backups")
        backups_layout = QVBoxLayout()
        backups_layout.setContentsMargins(10, 5, 10, 10)
        self.btn_backups = HoverButton("Restore From Backup")
        self.btn_backups.setToolTip("Browse and restore saved beatmap versions")
        self.btn_backups.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_backups.clicked.connect(self.open_backups)
        backups_layout.addWidget(self.btn_backups)
        self.backups_group.setLayout(backups_layout)
        content_layout.addWidget(self.backups_group)

        self.resource_groups = [
            self.audio_group,
            self.cover_group,
            self.video_group,
            self.backups_group,
        ]
        self.apply_resource_styles()
        self.update_video_state()
        main_layout.addWidget(self.content_widget)

        self.adjustSize()
        self.setFixedSize(450, self.sizeHint().height())

    def open_backups(self):
        dialog = BackupWindow(self.editor, self)
        dialog.exec()
        dialog.deleteLater()

    def update_video_state(self):
        has_video = find_project_video(getattr(self.editor, "project_folder", None)) is not None
        self.btn_video_configuration.setEnabled(has_video)
        self.btn_reset_video.setEnabled(has_video)

    def open_video_configuration(self):
        self.editor.open_video_configuration()
        self.accept()

    def reset_video(self):
        if not self.editor.project_folder:
            return
        removed = False
        controller = getattr(self.editor, "video_controller", None)
        if controller:
            controller.release()
        for name in ("video.mp4", "video.webm"):
            f = self.editor.project_folder / name
            if not f.exists():
                continue
            try:
                os.remove(f)
                removed = True
            except:
                pass
        cache_directory = self.editor.project_folder / "cbm_files"
        if cache_directory.is_dir():
            cache_paths = list(cache_directory.glob("video_preview_720_*.mp4"))
            cache_paths.append(cache_directory / "previewcache.mp4")
            for cache_path in cache_paths:
                try:
                    if cache_path.is_file():
                        cache_path.unlink()
                except OSError:
                    pass
        if removed:
            self.video_label.set_empty()
        self.update_video_state()

