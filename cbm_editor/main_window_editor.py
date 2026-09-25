from .services import *
from .install import *
from .ui_utils import select_native_folders
import os
import random
import sys
import uuid

register_shared_globals(globals())

class MainWindowEditorMixin:
    @staticmethod
    def resolve_nested_project_folder(folder_path):
        current = Path(folder_path)
        seen = set()
        while current.is_dir():
            try:
                key = os.path.normcase(str(current.resolve()))
            except OSError:
                key = os.path.normcase(os.path.abspath(str(current)))
            if key in seen:
                break
            seen.add(key)
            try:
                nested = next(
                    (
                        child
                        for child in current.iterdir()
                        if child.is_dir() and child.name == current.name
                    ),
                    None,
                )
            except OSError:
                break
            if nested is None:
                break
            current = nested
        return current

    def select_project_folders(self):
        start_dir = str(self.game_custom_maps_path) if self.game_custom_maps_path else ""
        if sys.platform.startswith("win"):
            try:
                selected_folders = select_native_folders(self, "Select Project Folder(s)", start_dir)
            except OSError:
                folder = QFileDialog.getExistingDirectory(self, "Select Project Folder", start_dir)
                selected_folders = [folder] if folder else []
        else:
            folder = QFileDialog.getExistingDirectory(self, "Select Project Folder", start_dir)
            selected_folders = [folder] if folder else []
        folders = []
        seen = set()
        for selected in selected_folders:
            folder = self.resolve_nested_project_folder(selected)
            if not folder.is_dir():
                continue
            try:
                key = os.path.normcase(str(folder.resolve()))
            except OSError:
                key = os.path.normcase(os.path.abspath(str(folder)))
            if key in seen:
                continue
            seen.add(key)
            folders.append(folder)
        return folders

    def open_project(self):
        folders = self.select_project_folders()
        if not folders:
            return
        if len(folders) > 1:
            self.start_screen.add_dropped_projects(folders)
            if not self.start_screen.isVisible():
                self.open_recent_popup()
            return
        if not self.confirm_unsaved_changes("load"):
            return
        self.load_project_from_path(folders[0])

    def export_project(self):
        if not hasattr(self, 'project_folder') or not self.project_folder:
            dlg = QDialog(self)
            scale = widget_global_scale(self)
            dlg.setWindowTitle("Warning")
            dlg.setModal(True)
            dlg.setMinimumWidth(max(175, int(round(350 * scale))))
            dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
            layout = QVBoxLayout(dlg)
            top_layout = QHBoxLayout()
            icon_label = QLabel()
            from PyQt6.QtWidgets import QStyle
            icon_size = max(16, int(round(32 * scale)))
            icon_pixmap = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning).pixmap(icon_size, icon_size)
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
            apply_layout_scale(dlg, scale)
            dlg.setFixedSize(max(int(round(350 * scale)), dlg.sizeHint().width()), dlg.sizeHint().height())
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
            scale = widget_global_scale(self)
            dlg.setWindowTitle("Export Success")
            dlg.setModal(True)
            dlg.setMinimumWidth(max(225, int(round(450 * scale))))
            dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
            
            layout = QVBoxLayout(dlg)
            
            top_layout = QHBoxLayout()
            icon_label = QLabel()
            from PyQt6.QtWidgets import QStyle
            icon_size = max(16, int(round(32 * scale)))
            icon_pixmap = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation).pixmap(icon_size, icon_size)
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
            
            apply_layout_scale(dlg, scale)
            dlg.setFixedSize(max(int(round(450 * scale)), dlg.sizeHint().width()), dlg.sizeHint().height())
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Failed to export project:\n{e}")
            import traceback
            traceback.print_exc()

    def load_project_from_path(self, folder_path: Path):
        folder_path = self.resolve_nested_project_folder(folder_path)
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
        if hasattr(self, "timeline") and hasattr(self.timeline, "side_panel"):
            self.timeline.side_panel.clear_verify_issues()
        if hasattr(self, "video_controller"):
            self.video_controller.release()
        if self.is_playing:
            self.toggle_play()
        self.stop_music_playback(release=True)
        self.stop_all_hold_sounds()

        self.project_folder = folder_path
        self.project_audio_filename = ""
        self.project_beatmap_filenames = set()
        try:
            load_media_settings(self.project_folder)
        except OSError:
            pass
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

        audio_extensions = {".mp3", ".wav", ".ogg", ".flac", ".opus", ".m4a", ".aac", ".wma", ".alac", ".aiff", ".aif"}
        audio_files = sorted(
            (path for path in self.project_folder.iterdir() if path.is_file() and path.suffix.casefold() in audio_extensions),
            key=lambda path: (path.name.casefold(), path.name),
        )
        found_audio = audio_files[0] if audio_files else None
        
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

            valid_beatmap_files = []
            for f_path in sorted(self.project_folder.glob("*.osu"), key=lambda path: (path.name.casefold(), path.name)):
                v = get_version_from_file(f_path)
                if v:
                    valid_beatmap_files.append(f_path)
                    if v in DIFFICULTIES:
                        file_mapping[v] = f_path.name
                    else:
                        file_mapping["Star"] = f_path.name 
            
            for f_path in sorted(self.project_folder.glob("*.txt"), key=lambda path: (path.name.casefold(), path.name)):
                 v = get_version_from_file(f_path)
                 if v:
                     valid_beatmap_files.append(f_path)
                     target = v if v in DIFFICULTIES else "Star"
                     if target not in file_mapping:
                          file_mapping[target] = f_path.name
                 elif f_path.stem in DIFFICULTIES and f_path.stem not in file_mapping:
                      valid_beatmap_files.append(f_path)
                      file_mapping[f_path.stem] = f_path.name

            valid_beatmap_files.sort(key=lambda path: (path.name.casefold(), path.name))
            self.project_beatmap_filenames = {path.name for path in valid_beatmap_files}
            if valid_beatmap_files:
                common_audio = self.read_audio_filename_from_beatmap(valid_beatmap_files[0])
            self.project_audio_filename = common_audio

            for diff_name in DIFFICULTIES:
                bm = BeatmapData(diff_name)
                try:
                    if diff_name in file_mapping:
                        bm.load(self.project_folder, file_mapping[diff_name])
                    else:
                        bm.load(self.project_folder)
                except Exception as e:
                    pass

                if bm.created and self.delay_60ms_enabled:
                    bm.shift_timeline(60)
                
                
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

    @staticmethod
    def read_audio_filename_from_beatmap(path):
        try:
            current_section = ""
            with open(path, "r", encoding="utf-8-sig") as beatmap_file:
                for raw_line in beatmap_file:
                    line = raw_line.strip()
                    if line.startswith("[") and line.endswith("]"):
                        current_section = line.casefold()
                    elif current_section == "[general]" and line.casefold().startswith("audiofilename:"):
                        return line.split(":", 1)[1].strip().strip('"')
        except (OSError, UnicodeError):
            pass
        return ""

    def get_project_audio_filename(self):
        return str(getattr(self, 'project_audio_filename', '') or '')

    @staticmethod
    def rewrite_audio_filename(path, filename):
        raw = path.read_bytes()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.splitlines(keepends=True)
        current_section = ""
        replaced = False
        general_index = None
        for index, raw_line in enumerate(lines):
            stripped = raw_line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped.casefold()
                if current_section == "[general]":
                    general_index = index
                continue
            if current_section == "[general]" and stripped.casefold().startswith("audiofilename:"):
                ending = "\r\n" if raw_line.endswith("\r\n") else ("\n" if raw_line.endswith("\n") else "")
                lines[index] = f"AudioFilename: {filename}{ending}"
                replaced = True
                break
        if not replaced:
            insertion = f"AudioFilename: {filename}{newline}"
            if general_index is None:
                lines[0:0] = [f"[General]{newline}", insertion, newline]
            else:
                lines.insert(general_index + 1, insertion)
        encoded = "".join(lines).encode("utf-8")
        if has_bom:
            encoded = b"\xef\xbb\xbf" + encoded
        temporary = path.with_name(f".{path.name}.audio-{time.time_ns()}.tmp")
        temporary.write_bytes(encoded)
        os.replace(temporary, path)

    def set_project_audio_filename(self, filename, persist=False):
        filename = str(filename or "")
        self.project_audio_filename = filename
        for beatmap in self.beatmaps.values():
            beatmap.metadata.AudioFilename = filename
        if self.current_chart:
            self.current_chart.metadata.AudioFilename = filename
        if persist and self.project_folder:
            if self.auto_save_worker and self.auto_save_worker.isRunning():
                self.auto_save_worker.wait()
            with self.save_io_lock:
                filenames = set(getattr(self, 'project_beatmap_filenames', set()))
                filenames.update(
                    beatmap.get_filename()
                    for beatmap in self.beatmaps.values()
                    if beatmap.created
                )
                for filename_to_update in sorted(filenames, key=lambda value: (value.casefold(), value)):
                    path = self.project_folder / filename_to_update
                    if path.is_file():
                        self.rewrite_audio_filename(path, filename)
        if getattr(self, 'audio_label', None) is not None:
            if filename:
                self.audio_label.set_content_loaded(filename)
            else:
                self.audio_label.set_empty()

    @staticmethod
    def rewrite_preview_time(path, seconds):
        raw = path.read_bytes()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        newline = "\r\n" if "\r\n" in text else "\n"
        lines = text.splitlines(keepends=True)
        current_section = ""
        replaced = False
        general_index = None
        for index, raw_line in enumerate(lines):
            stripped = raw_line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped.casefold()
                if current_section == "[general]":
                    general_index = index
                continue
            if current_section == "[general]" and stripped.casefold().startswith("previewtime:"):
                ending = "\r\n" if raw_line.endswith("\r\n") else ("\n" if raw_line.endswith("\n") else "")
                lines[index] = f"PreviewTime: {int(seconds)}{ending}"
                replaced = True
                break
        if not replaced:
            insertion = f"PreviewTime: {int(seconds)}{newline}"
            if general_index is None:
                lines[0:0] = [f"[General]{newline}", insertion, newline]
            else:
                lines.insert(general_index + 1, insertion)
        encoded = "".join(lines).encode("utf-8")
        if has_bom:
            encoded = b"\xef\xbb\xbf" + encoded
        temporary = path.with_name(f".{path.name}.preview-{time.time_ns()}.tmp")
        temporary.write_bytes(encoded)
        os.replace(temporary, path)

    def set_project_preview_time(self, seconds, persist=False):
        seconds = int(seconds)
        for beatmap in self.beatmaps.values():
            beatmap.metadata.PreviewTime = seconds
        if self.current_chart:
            self.current_chart.metadata.PreviewTime = seconds
        if persist and self.project_folder:
            if self.auto_save_worker and self.auto_save_worker.isRunning():
                self.auto_save_worker.wait()
            with self.save_io_lock:
                filenames = set(getattr(self, 'project_beatmap_filenames', set()))
                filenames.update(
                    beatmap.get_filename()
                    for beatmap in self.beatmaps.values()
                    if beatmap.created
                )
                for filename in sorted(filenames, key=lambda value: (value.casefold(), value)):
                    path = self.project_folder / filename
                    if path.is_file():
                        self.rewrite_preview_time(path, seconds)

    def open_sync_audio(self):
        if getattr(self, '_sync_popup_host', None) is not None:
            return
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
        res_path = self.resource_directory / "metronome.wav"
        if res_path.exists():
             metro_path = str(res_path)
        
        dialog = AudioSynchronizerDialog(self, str(full_path), self.current_chart.metadata.BPM, self.current_chart.metadata.Offset, metro_path)
        dialog.setStyleSheet(self.styleSheet())

        def finished(result):
            if result == QDialog.DialogCode.Accepted.value:
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

        host = EmbeddedPopupHost(self.centralWidget(), shade=False)
        self._sync_popup_host = host
        host.closed.connect(lambda: setattr(self, '_sync_popup_host', None))
        host.present(dialog, finished)

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
            copy_original = bool(getattr(self, 'use_original_audio', False))
            final_filename = src_path.name if copy_original else src_path.stem + ".mp3"
            dest_path = self.project_folder / final_filename
            temp_dest = self.project_folder / f".{src_path.stem}.importing{src_path.suffix if copy_original else '.mp3'}"
            temp_dest.unlink(missing_ok=True)
            old_audio_name = self.get_project_audio_filename()
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
                "Copying original audio..." if copy_original else "Converting audio...",
                self,
            )
            if copy_original:
                self.audio_import_worker = AudioImportCopyWorker(src_path, temp_dest, self)
            else:
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
            self.set_project_audio_filename(final_filename, persist=True)
            self.generate_vis_data(dest_path)
            self.load_audio(final_filename)
            try:
                backup_dir = self.project_folder / "cbm_files"
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / f"{dest_path.stem}_backup{dest_path.suffix}"
                temporary_backup = backup_path.with_name(
                    f".{backup_path.stem}.import-{time.time_ns()}.tmp{backup_path.suffix}"
                )
                shutil.copy2(dest_path, temporary_backup)
                os.replace(temporary_backup, backup_path)
                update_media_offset(self.project_folder, "audio_offset_ms", 0)
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
        QMessageBox.critical(self, "Audio Import Error", f"Could not import audio: {message}")

    def handle_cover_drop(self, file_path):
        if not self.project_folder: return
        
        src_path = Path(file_path)
        
        try:
            if src_path.suffix.lower() in ['.wav', '.mp3', '.ogg', '.flac', '.m4a', '.wma', '.aac', '.alac', '.aiff']:
                 QMessageBox.warning(self, "Invalid File", "You dropped an audio file into the Cover Art field.\nPlease drop it into the Audio field above.")
                 return

            from PIL import Image, ImageOps

            dest_path = self.project_folder / "cover.png"
            temporary_path = dest_path.with_name(f".{dest_path.name}.tmp")
            try:
                with Image.open(src_path) as image:
                    prepared = ImageOps.exif_transpose(image)
                    prepared.thumbnail((2048, 2048), Image.Resampling.LANCZOS, reducing_gap=3.0)
                    has_transparency = prepared.mode in {"RGBA", "LA"} or "transparency" in prepared.info
                    if has_transparency:
                        prepared = prepared.convert("RGBA")
                        color = ImageOps.posterize(prepared.convert("RGB"), 6)
                        color.putalpha(prepared.getchannel("A"))
                        prepared = color
                    else:
                        prepared = ImageOps.posterize(prepared.convert("RGB"), 6)
                    prepared.save(temporary_path, "PNG", optimize=True, compress_level=9)
                os.replace(temporary_path, dest_path)
            finally:
                temporary_path.unlink(missing_ok=True)

            for existing in self.project_folder.glob("cover.*"):
                try:
                    if existing.resolve() != dest_path.resolve():
                        existing.unlink()
                except OSError:
                    pass
            
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
                apply_fixed_window_scale(msg, 300, 120)
                
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
        m.AudioFilename = self.get_project_audio_filename()
        self.block_meta_signals(False)
        
        self.update_star_visibility()
        self.timeline.set_beatmap(self.current_chart)
        
        self.load_audio(self.get_project_audio_filename())

        if self.get_project_audio_filename():
            self.generate_vis_data(self.project_folder / self.get_project_audio_filename())
        
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
             timing_text_color = "#171717" if getattr(self, 'ui_brightness', 60) > 180 else "white"
             lbl.setProperty("timingTextColor", timing_text_color)
             lbl.setStyleSheet(f"color: {timing_text_color}; background: transparent;")
             
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
        tp = next((point for point in self.current_chart.timing_points if point is tp or point == tp), tp)
        self.timeline.selected_objects.clear()
        self.timeline.selected_timing_points = [tp]
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
        if hasattr(self, "timeline_time_label"):
            self.timeline_time_label.setText("0:00")

    def update_project_preview_length(self, seconds):
        if not hasattr(self, "timeline_time_label"):
            return
        milliseconds = max(0.0, float(seconds)) * 1000.0
        self.timeline_time_label.setText(format_editor_timestamp(
            milliseconds,
            force_hours=milliseconds >= 3600000,
            pad_minutes=False,
        ))

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
                                    metadata.SongLength = float(tag_data.get("SongLength", 0.0) or 0.0)
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
            self.update_project_preview_length(metadata.SongLength)
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
        bmap_files = sorted(self.project_folder.glob("*.bmap"), key=lambda path: path.name.casefold())
        if not bmap_files:
            return
        
        data = {}
        bmap_path = bmap_files[0]
        try:
            with open(bmap_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            pass

        if not isinstance(data, dict):
            data = {}
        guid = data.get("GUID")
        if not isinstance(guid, str) or not guid.strip():
            guid = str(uuid.uuid4())

        song_files = {}
        for diff_key in DIFFICULTIES:
             if diff_key in self.beatmaps and self.beatmaps[diff_key].created:
                 song_files[diff_key] = self.beatmaps[diff_key].get_filename()

        updated_data = {"GUID": guid}
        updated_data.update({key: value for key, value in data.items() if key not in ("GUID", "Songs")})
        updated_data["Songs"] = [song_files]
        
        if bmap_path:
            try:
                with open(bmap_path, 'w', encoding='utf-8') as f:
                    json.dump(updated_data, f, indent=2)
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
        self.current_chart.metadata.AudioFilename = self.get_project_audio_filename()
        
        self.current_chart.editor_zoom = self.timeline.target_zoom
    
        with self.save_io_lock:
            time_offset_ms = -60 if self.delay_60ms_enabled else 0
            saved = self.current_chart.save(
                self.project_folder,
                self.file_extension_setting,
                time_offset_ms,
                self.official_editor_values,
            )
            if saved and self.enable_backups:
                create_beatmap_backup(
                    self.project_folder,
                    self.current_chart.difficulty_key,
                    self.current_chart.get_filename(),
                )
        if saved:
            self.project_beatmap_filenames.add(self.current_chart.get_filename())
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
            'object_order': [
                (int(time_ms), tuple(uids))
                for time_ms, uids in chart.object_order_overrides.items()
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
            -60 if self.delay_60ms_enabled else 0,
            self.official_editor_values,
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
        self.project_beatmap_filenames.add(filename)
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
            scale = max(0.5, float(getattr(self, "global_scale", 1.0)))
            width = int(available_width if available_width is not None else self.custom_type_container.width())
            selected_index = self.combo_custom_note.currentIndex()
            selected_name = self.combo_custom_note.itemText(selected_index) if selected_index >= 0 else ""
            all_text = f"All ({selected_name})" if selected_name else "All"
            all_minimum = self.combo_custom_note.fontMetrics().horizontalAdvance(all_text) + int(round(38 * scale))
            type_width = int(round(240 * scale))
            self.combo_custom_type.setFixedWidth(type_width)
            button_minimums = [button.fontMetrics().horizontalAdvance(button.text()) + int(round(34 * scale)) for button in self.custom_note_buttons]
            visible_count = 0
            spacing = self.custom_type_layout.spacing()
            for count in range(1, len(self.custom_note_buttons) + 1):
                main_width = width - type_width - spacing * (count + 1)
                equal_width = main_width // (count + 1)
                if equal_width < max([all_minimum] + button_minimums[:count]):
                    break
                visible_count = count
            main_width = width - type_width - spacing * (visible_count + 1)
            equal_width = max(int(round(60 * scale)), main_width // (visible_count + 1))
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
            self.combo_note_style.addItems(["Normal", "Fly In", "Hide"])
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
        existing = getattr(self, '_sync_action_menu', None)
        if existing is not None and existing.isVisible():
            if existing._closing:
                existing.reopen_animated()
            else:
                existing.dismiss()
            return
        scale = max(0.5, float(getattr(self, 'global_scale', 1.0)))
        menu = EmbeddedActionMenu(self.btn_bpm_match, self.centralWidget())
        padding = max(4, int(round(6 * scale)))
        menu.content_layout.setContentsMargins(padding, padding, padding, padding)
        menu.content_layout.setSpacing(max(2, int(round(3 * scale))))
        menu.setFixedWidth(max(112, int(round(120 * scale))))
        b = self.ui_brightness
        text_color = "black" if b > 180 else "white"
        surface = max(0, b - 26)
        item_base = min(255, surface + 16)
        item_hover = min(255, surface + 34)
        item_pressed = min(255, surface + 8)
        item_depth = max(0, item_base - 10)
        hover_depth = max(0, item_hover - 10)
        base_hex = f"#{item_base:02x}{item_base:02x}{item_base:02x}"
        hover_hex = f"#{item_hover:02x}{item_hover:02x}{item_hover:02x}"
        pressed_hex = f"#{item_pressed:02x}{item_pressed:02x}{item_pressed:02x}"
        depth_hex = f"#{item_depth:02x}{item_depth:02x}{item_depth:02x}"
        hover_depth_hex = f"#{hover_depth:02x}{hover_depth:02x}{hover_depth:02x}"
        menu.setStyleSheet(scale_stylesheet_dimensions(f"""
            QPushButton {{
                background-color: {base_hex};
                color: {text_color};
                border: none;
                border-bottom: 3px solid {depth_hex};
                border-radius: 10px;
                padding: 8px 8px;
                text-align: center;
                font-family: "Segoe UI", "Selawik", "Arial", sans-serif;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {hover_hex};
                border-bottom-color: {hover_depth_hex};
            }}
            QPushButton:pressed {{
                background-color: {pressed_hex};
                border-bottom: 0px solid transparent;
                border-top: 3px solid transparent;
                padding-top: 11px;
            }}
        """, scale))
        pan = self.get_pan_for_widget(self.btn_bpm_match)
        btn_match = HoverButton("Match BPM", hover_cb=lambda: self.play_ui_sound('UI Scroll', pan))
        btn_match.setToolTip("Determine BPM with tap tempo")
        btn_match.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_match.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_match.clicked.connect(lambda: menu.dismiss(self.open_bpm_matcher))
        btn_sync = HoverButton("Offset Audio", hover_cb=lambda: self.play_ui_sound('UI Scroll', pan))
        btn_sync.setToolTip("Change offset of audio file to line up with barlines")
        btn_sync.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_sync.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_sync.clicked.connect(lambda: menu.dismiss(self.open_sync_audio))
        menu.content_layout.addWidget(btn_match)
        menu.content_layout.addWidget(btn_sync)
        menu.closed.connect(lambda: setattr(self, '_sync_action_menu', None))
        self._sync_action_menu = menu
        menu.open_animated()

    def open_bpm_matcher(self):
        if getattr(self, '_sync_popup_host', None) is not None:
            return
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
        def finished(result):
            if result == QDialog.DialogCode.Accepted.value and dialog.calculated_bpm > 0:
                self.meta_widgets["BPM"].setValue(float(dialog.calculated_bpm))
                self.inp_bpm.setValue(float(dialog.calculated_bpm))
                self.add_bpm_point()
            self.load_audio(self.current_chart.metadata.AudioFilename)

        host = EmbeddedPopupHost(self.centralWidget())
        self._sync_popup_host = host
        host.closed.connect(lambda: setattr(self, '_sync_popup_host', None))
        host.present(dialog, finished)

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

    def stop_active_hold_sound(self, object_id):
        active_hold_sounds = getattr(self, 'active_hold_sounds', None)
        if not active_hold_sounds:
            return
        channel = active_hold_sounds.pop(object_id, None)
        if channel and channel.get_busy():
            channel.stop()

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
        self.update_background_playback_timer()

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
        self.update_background_playback_timer()

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

    def tick(self, background=False):
        if self.is_playing:
            if self.system_start_tick > 0:
                now_ticks = time.perf_counter() * 1000.0
                elapsed_real_ms = now_ticks - self.system_start_tick

                audio_start_pos = self.timeline.visual_to_audio_ms(self.audio_start_ms)
                target_audio_pos = audio_start_pos + (elapsed_real_ms * self.playback_speed)

                self.timeline.current_time = self.timeline.audio_to_visual_ms(target_audio_pos)
                self.timeline.target_time = self.timeline.current_time
                if not background:
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

                if not background and now_ticks - self.last_scrollbar_update > 16.0:
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

                if not background and hasattr(self, "video_controller") and self.video_controller.enabled:
                    video_audio_ms = self.timeline.visual_to_audio_ms(self.timeline.current_time)
                    self.video_controller.sync(video_audio_ms, self.is_playing)

            if not self.is_playing and self.sidebar_vis:
                self.sidebar_vis.set_active(False)
            
            analysis_enabled = self.visualizer_analysis_enabled()
            sidebar_visualizer_enabled = getattr(self, "sidebar_display_mode", "Visualizer") == "Visualizer"
            if not background and self.is_playing and analysis_enabled and self.sidebar_vis and self.current_playback_channel and self.current_chart:
                 self.sidebar_vis.set_active(sidebar_visualizer_enabled)
                 visualizer_now = time.perf_counter() * 1000.0
                 visualizer_interval = 1000.0 / min(60, TARGET_FPS)
                 if visualizer_now - self.last_visualizer_submit >= visualizer_interval:
                     self.last_visualizer_submit = visualizer_now
                     if self.vis_worker:
                         self.vis_worker.request_analysis(
                             self.current_playback_channel,
                             include_rms=getattr(self, "visualizer_opacity", 0) > 0,
                         )
                     else:
                         self.sidebar_vis.set_active(False)

            elif not background and self.sidebar_vis:
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

                     if not background and self.enable_beatflash:
                        self.timeline.beat_flash_intensity = 1.0

                     self.last_metronome_beat = current_beat_index

            if not background and self.timeline.selection_start is not None:
                self.timeline.update_selection_rect()
            
            if not background and self.timeline.dragging_objects:
                self.timeline.update_dragged_objects()
            
            self.check_and_play_notes()
            if not background:
                self.timeline.update()

    def update_visualizer_worker_state(self):
        analysis_enabled = self.visualizer_analysis_enabled()
        self.enable_visualizer = analysis_enabled
        if analysis_enabled:
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

    def on_vis_result(self, stream, bands, rms):
        if not self.is_playing or not self.visualizer_analysis_enabled() or stream is not self.current_playback_channel:
            return
        if self.sidebar_vis and getattr(self, "sidebar_display_mode", "Visualizer") == "Visualizer":
            self.sidebar_vis.set_bands(bands)
        if getattr(self, "visualizer_opacity", 0) <= 0:
            self.visualizer_level = 0.0
            return
        target_level = min(1.0, max(0.0, rms * 3.5))
        level_now = time.perf_counter()
        level_dt = min(0.05, max(0.0, level_now - self.last_visualizer_level_update))
        self.last_visualizer_level_update = level_now
        level_rate = 32.0 if target_level > self.visualizer_level else 10.5
        level_factor = 1.0 - math.exp(-level_rate * level_dt)
        self.visualizer_level += (target_level - self.visualizer_level) * level_factor

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

                     if channel and (obj.is_hold or obj.is_brawl_hold or self.timeline.is_custom_length(obj)):
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
                continue

            if obj.is_hold or obj.is_brawl_hold or self.timeline.is_custom_length(obj):
                self.stop_active_hold_sound(obj_id)

            if abs(tail_diff) <= hit_window and tail_key not in self.last_played_notes:
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
                removed_set = set(removed_objects)
                self.current_chart.hit_objects[:] = [
                    obj for obj in self.current_chart.hit_objects
                    if obj not in removed_set
                ]
                self.timeline.selected_objects.clear()
                self.timeline.update()
                self.timeline.editor.mark_unsaved()
                self.timeline.sync_structural_object_caches(removed_objects)
            e.accept()
