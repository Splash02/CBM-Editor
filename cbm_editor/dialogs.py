from .ui_utils import *
import shutil
import uuid
from pathlib import Path
from .video import (
    VideoJobWorker,
    commit_video_result,
    find_project_video,
    find_video_backup,
    format_file_size,
    format_video_duration,
    load_video_settings,
    save_video_settings,
)
from PyQt6.QtCore import QModelIndex, QRunnable, QThreadPool
from PyQt6.QtGui import QCursor, QFont, QIntValidator
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QGraphicsColorizeEffect, QGraphicsOpacityEffect

register_shared_globals(globals())

from .project_browser import *
from .settings_dialog import *

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
        lbl.setStyleSheet('font-family: "Segoe UI", "Selawik", "Arial", sans-serif; font-size: 14px; font-weight: bold;')
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
        
        brightness = widget_ui_brightness(self)
        warn_color = "#333333" if brightness > 180 else "#C4C4C4"
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


class AudioImportCopyWorker(QThread):
    progress_changed = pyqtSignal(int)
    conversion_ready = pyqtSignal(str, object)
    conversion_failed = pyqtSignal(str)

    def __init__(self, source_path, output_path, parent=None):
        super().__init__(parent)
        self.source_path = str(source_path)
        self.output_path = str(output_path)

    def run(self):
        try:
            total = max(1, os.path.getsize(self.source_path))
            copied = 0
            with open(self.source_path, "rb") as source, open(self.output_path, "wb") as output:
                while True:
                    if self.isInterruptionRequested():
                        return
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    copied += len(chunk)
                    self.progress_changed.emit(min(99, int(copied * 100 / total)))
            shutil.copystat(self.source_path, self.output_path)
            self.progress_changed.emit(100)
            self.conversion_ready.emit(self.output_path, None)
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
            stream = get_audio_engine().load_decode_stream(self.source_path, prescan=True)
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

    def __init__(self, chart, revision, folder, extension, snapshot, save_lock, backup_enabled, time_offset_ms=0, parent=None):
        super().__init__(parent)
        self.chart = chart
        self.revision = revision
        self.folder = Path(folder)
        self.extension = extension
        self.snapshot = snapshot
        self.save_lock = save_lock
        self.backup_enabled = bool(backup_enabled)
        self.time_offset_ms = int(time_offset_ms)

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
                    uid=obj[11],
                    custom_data=custom_object_data_from_tuple(obj[12] if len(obj) > 12 else None)
                )
                for obj in self.snapshot['hit_objects']
            ]
            beatmap.timing_points = [
                {'time': tp[0], 'bpm': tp[1]}
                for tp in self.snapshot['timing_points']
            ]
            beatmap.object_order_overrides = {
                int(time_ms): list(uids)
                for time_ms, uids in self.snapshot.get('object_order', ())
            }
            beatmap.filename = self.snapshot['filename']
            beatmap.editor_zoom = self.snapshot['editor_zoom']
            beatmap.created = True
            beatmap.unsaved = True
            success = beatmap.save(self.folder, self.extension, self.time_offset_ms)
            filename = beatmap.filename or ""
            if success and self.backup_enabled:
                create_beatmap_backup(self.folder, beatmap.difficulty_key, filename)
        except Exception:
            success = False
        finally:
            self.save_lock.release()
        self.save_finished.emit(self.chart, self.revision, success, filename, str(self.folder))
class VideoProgressDialog(QDialog):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowCloseButtonHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.phase = ""
        self.error_visible = False
        layout = QVBoxLayout(self)
        self.label = QLabel("")
        self.label.setMinimumWidth(420)
        layout.addWidget(self.label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.cancel_button = QPushButton("Cancel")
        layout.addWidget(self.cancel_button)
        self.show_timer = QTimer(self)
        self.show_timer.setSingleShot(True)
        self.show_timer.timeout.connect(self.show)
        self.show_timer.start(250)
        self.setFixedSize(self.sizeHint())

    def set_progress(self, phase, value):
        self.phase = phase
        value = max(0, min(100, int(value)))
        self.progress.setValue(value)
        self.label.setText(f"{phase} {value}%")

    def finish(self):
        self.show_timer.stop()
        self.hide()
        self.deleteLater()

    def show_error(self, message):
        self.show_timer.stop()
        self.error_visible = True
        self.label.setWordWrap(True)
        current = self.progress.value()
        prefix = f"{self.phase} {current}%" if self.phase else "Video processing failed"
        self.label.setText(f"{prefix}\n\n{message}")
        try:
            self.cancel_button.clicked.disconnect()
        except TypeError:
            pass
        self.cancel_button.setText("Close")
        self.cancel_button.clicked.connect(self.accept)
        self.setFixedSize(self.sizeHint())
        self.show()

    def closeEvent(self, event):
        event.ignore()


class VideoConfigurationWindow(QDialog):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.project_folder = Path(editor.project_folder)
        self.video_path = find_project_video(self.project_folder)
        self.saved_settings = load_video_settings(self.project_folder)
        self.worker = None
        self.probe_worker = None
        self.progress_dialog = None
        self.job_had_error = False
        self.preview_override_active = False
        self.video_fps = 30.0
        self.video_width = 0
        self.video_height = 0
        self.setWindowTitle("Video Configuration")
        self.setObjectName("VideoConfigurationDialog")
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(editor.styleSheet())
        scale = getattr(editor, "global_scale", 1.0)
        group_style = (
            "QGroupBox { margin-top: 15px; font-weight: bold; border: none; } "
            "QGroupBox::title { font-size: 24pt; subcontrol-origin: margin; "
            "left: 10px; padding: 0px 5px; border-radius: 4px; }"
        )

        main_layout = QVBoxLayout(self)
        tabs_area = SmoothScrollArea()
        tabs_area.setWidgetResizable(True)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        info_group = QGroupBox("Info")
        info_group.setStyleSheet(group_style)
        info_layout = QFormLayout(info_group)
        info_layout.setContentsMargins(10, 5, 10, 10)
        info_layout.setSpacing(4)
        self.format_value = QLabel(self.video_path.suffix.lower().lstrip(".").upper() if self.video_path else "—")
        self.codec_value = QLabel("Reading...")
        self.resolution_value = QLabel("Reading...")
        self.framerate_value = QLabel("Reading...")
        self.duration_value = QLabel("Reading...")
        self.size_value = QLabel(format_file_size(self.video_path.stat().st_size) if self.video_path else "—")
        info_layout.addRow("Format:", self.format_value)
        info_layout.addRow("Codec:", self.codec_value)
        info_layout.addRow("Resolution:", self.resolution_value)
        info_layout.addRow("Framerate:", self.framerate_value)
        info_layout.addRow("Duration:", self.duration_value)
        info_layout.addRow("File Size:", self.size_value)
        content_layout.addWidget(info_group)

        timing_group = QGroupBox("Offset")
        timing_group.setStyleSheet(group_style)
        timing_layout = QFormLayout(timing_group)
        timing_layout.setContentsMargins(10, 5, 10, 10)
        timing_layout.setSpacing(5)
        self.offset_frames_spin = QSpinBox()
        self.offset_frames_spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.offset_frames_spin.setRange(-100000000, 100000000)
        self.offset_frames_spin.setSuffix(" frames")
        self.offset_frames_spin.setValue(self.saved_offset_frames())
        self.offset_frames_spin.valueChanged.connect(self.preview_settings_changed)
        timing_layout.addRow("Offset:", self.offset_frames_spin)
        self.delay_mode = QComboBox()
        self.delay_mode.setView(SmoothListView(self.delay_mode))
        self.delay_mode.addItem("Black Screen", "black")
        self.delay_mode.addItem("Hold First Frame", "clone")
        self.delay_mode.setCurrentIndex(0)
        self.delay_mode.currentIndexChanged.connect(self.preview_settings_changed)
        timing_layout.addRow("Before Start:", self.delay_mode)
        self.apply_button = QPushButton("Apply Offset")
        self.apply_button.clicked.connect(self.apply_offset)
        timing_layout.addRow(self.apply_button)
        content_layout.addWidget(timing_group)

        resize_group = QGroupBox("Resize")
        resize_group.setStyleSheet(group_style)
        resize_layout = QFormLayout(resize_group)
        resize_layout.setContentsMargins(10, 5, 10, 10)
        resize_layout.setSpacing(5)
        self.resize_resolution = QComboBox()
        self.resize_resolution.setView(SmoothListView(self.resize_resolution))
        self.resize_resolution.addItem("Reading...", 0)
        resize_layout.addRow("Resolution:", self.resize_resolution)
        self.resize_button = QPushButton("Resize Video")
        self.resize_button.clicked.connect(self.resize_video)
        resize_layout.addRow(self.resize_button)
        content_layout.addWidget(resize_group)

        compression_group = QGroupBox("Compression")
        compression_group.setStyleSheet(group_style)
        compression_layout = QFormLayout(compression_group)
        compression_layout.setContentsMargins(10, 5, 10, 10)
        compression_layout.setSpacing(5)
        self.target_size = QDoubleSpinBox()
        self.target_size.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.target_size.setRange(0.1, 102400.0)
        self.target_size.setDecimals(1)
        self.target_size.setSuffix(" MB")
        self.target_size.setValue(50.0)
        compression_layout.addRow("Maximum Size:", self.target_size)
        self.compress_button = QPushButton("Compress Video")
        self.compress_button.clicked.connect(self.compress_video)
        compression_layout.addRow(self.compress_button)
        content_layout.addWidget(compression_group)
        action_layout = QHBoxLayout()
        self.restore_button = QPushButton("Restore Original")
        self.cancel_processing_button = QPushButton("Cancel")
        self.close_button = QPushButton("Close")
        self.restore_button.clicked.connect(self.restore_original)
        self.cancel_processing_button.clicked.connect(self.cancel_processing)
        self.close_button.clicked.connect(self.close)
        action_layout.addWidget(self.restore_button)
        action_layout.addWidget(self.cancel_processing_button)
        action_layout.addWidget(self.close_button)
        tabs_area.setWidget(content_widget)
        main_layout.addWidget(tabs_area)
        main_layout.addLayout(action_layout)

        self.update_control_state()
        self.start_probe()
        self.setFixedSize(int(540 * scale), int(700 * scale))

    def saved_offset_frames(self):
        offset_ms = int(self.saved_settings.get("offset_ms", 0) or 0)
        return int(round(offset_ms * self.video_fps / 1000.0))

    def offset_ms(self):
        return int(
            round(self.offset_frames_spin.value() * 1000.0 / max(0.001, self.video_fps))
        )

    def start_probe(self):
        if not self.video_path:
            return
        self.probe_worker = VideoJobWorker("probe", self.project_folder, self.video_path, parent=self)
        self.probe_worker.job_ready.connect(self.probe_ready)
        self.probe_worker.job_failed.connect(self.probe_failed)
        self.probe_worker.start()

    def probe_ready(self, result):
        metadata = result["metadata"]
        if metadata["fps"] > 0:
            self.video_fps = float(metadata["fps"])
            self.offset_frames_spin.blockSignals(True)
            self.offset_frames_spin.setValue(self.saved_offset_frames())
            self.offset_frames_spin.blockSignals(False)
        self.video_width = int(metadata["width"])
        self.video_height = int(metadata["height"])
        self.populate_resize_resolutions()
        self.format_value.setText(metadata["format"])
        self.codec_value.setText(metadata["codec"])
        self.resolution_value.setText(f"{metadata['width']} × {metadata['height']}")
        self.framerate_value.setText(f"{metadata['fps']:.3f} FPS" if metadata["fps"] > 0 else "Unknown")
        self.duration_value.setText(format_video_duration(metadata["duration_ms"]))
        self.size_value.setText(format_file_size(metadata["size"]))
        self.update_control_state()

    def probe_failed(self, message):
        self.codec_value.setText("Unavailable")
        self.resolution_value.setText("Unavailable")
        self.framerate_value.setText("Unavailable")
        self.duration_value.setText("Unavailable")
        self.apply_button.setToolTip(message)
        self.resize_button.setToolTip(message)
        self.compress_button.setToolTip(message)
        self.restore_button.setToolTip(message)

    def preview_settings_changed(self):
        self.update_control_state()
        controller = getattr(self.editor, "video_controller", None)
        if not controller:
            return
        self.preview_override_active = True
        preview_source = find_video_backup(self.project_folder) or self.video_path
        controller.set_configuration_source(
            preview_source,
            self.offset_ms(),
            self.delay_mode.currentData(),
        )

    def update_control_state(self):
        self.delay_mode.setEnabled(self.offset_frames_spin.value() > 0)
        busy = self.worker is not None and self.worker.isRunning()
        self.apply_button.setEnabled(not busy)
        self.resize_button.setEnabled(not busy and self.video_height > 0)
        self.resize_resolution.setEnabled(not busy and self.video_height > 0)
        self.compress_button.setEnabled(not busy)
        self.target_size.setEnabled(not busy)
        self.restore_button.setEnabled(not busy and find_video_backup(self.project_folder) is not None)
        self.cancel_processing_button.setEnabled(busy)
        self.close_button.setEnabled(not busy)

    def start_job(self, operation, options=None):
        if self.worker and self.worker.isRunning():
            return
        controller = getattr(self.editor, "video_controller", None)
        if controller:
            controller.release(keep_source=True)
        self.worker = VideoJobWorker(operation, self.project_folder, options=options, parent=self)
        self.job_had_error = False
        self.progress_dialog = VideoProgressDialog("Video Processing", self)
        self.progress_dialog.cancel_button.clicked.connect(self.cancel_processing)
        self.worker.progress_changed.connect(self.progress_dialog.set_progress)
        self.worker.job_ready.connect(self.job_ready)
        self.worker.job_failed.connect(self.job_failed)
        self.worker.finished.connect(self.job_finished)
        self.worker.start()
        self.update_control_state()

    def populate_resize_resolutions(self):
        if self.video_width <= 0 or self.video_height <= 0:
            return
        selected_height = self.video_height
        aspect = self.video_width / self.video_height
        heights = [2160, 1440, 1080, 720, 480, 360, 240]
        if selected_height not in heights:
            heights.insert(0, selected_height)
        self.resize_resolution.blockSignals(True)
        self.resize_resolution.clear()
        for height in heights:
            width = max(2, int(round((aspect * height) / 2.0)) * 2)
            label = f"{height}p \u2014 {width} \u00d7 {height}"
            if height == selected_height:
                label = f"Current \u2014 {width} \u00d7 {height}"
            self.resize_resolution.addItem(label, height)
        index = self.resize_resolution.findData(selected_height)
        self.resize_resolution.setCurrentIndex(max(0, index))
        self.resize_resolution.blockSignals(False)

    def job_options(self, compress, action="offset"):
        resize_height = (
            int(self.resize_resolution.currentData() or 0)
            if action == "resize"
            else int(self.video_height)
        )
        return {
            "offset_frames": self.offset_frames_spin.value(),
            "offset_ms": self.offset_ms(),
            "delay_mode": self.delay_mode.currentData(),
            "compress": compress,
            "target_mb": self.target_size.value(),
            "resize_height": resize_height,
            "action": action,
        }

    def apply_offset(self):
        self.start_job(
            "apply",
            self.job_options(False),
        )

    def resize_video(self):
        self.start_job("apply", self.job_options(False, "resize"))

    def compress_video(self):
        self.start_job("apply", self.job_options(True))

    def restore_original(self):
        self.start_job("restore")

    def cancel_processing(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()

    def job_ready(self, result):
        try:
            destination = commit_video_result(self.project_folder, result)
            save_video_settings(self.project_folder, result["settings"])
            self.saved_settings = result["settings"]
            self.video_path = destination
            self.offset_frames_spin.blockSignals(True)
            self.offset_frames_spin.setValue(self.saved_offset_frames())
            self.offset_frames_spin.blockSignals(False)
            self.editor.video_label.set_content_loaded("Video Loaded")
            controller = getattr(self.editor, "video_controller", None)
            if controller:
                self.preview_settings_changed()
            self.probe_ready({"metadata": result["metadata"]})
        except Exception as error:
            self.job_had_error = True
            if self.progress_dialog:
                self.progress_dialog.show_error(f"Failed to install the processed video:\n{error}")

    def job_failed(self, message):
        self.job_had_error = True
        if self.progress_dialog:
            self.progress_dialog.show_error(message)

    def job_finished(self):
        if self.progress_dialog:
            if not self.job_had_error:
                self.progress_dialog.finish()
            self.progress_dialog = None
        controller = getattr(self.editor, "video_controller", None)
        if controller:
            self.preview_settings_changed()
        self.worker = None
        self.update_control_state()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
            return
        if self.probe_worker and self.probe_worker.isRunning():
            self.probe_worker.requestInterruption()
            self.probe_worker.wait(1000)
        controller = getattr(self.editor, "video_controller", None)
        if controller and self.preview_override_active:
            controller.restore_project_source()
        self.editor.video_configuration_window = None
        super().closeEvent(event)

def start_video_import(editor, source_path):
    if getattr(editor, "video_job_worker", None) and editor.video_job_worker.isRunning():
        QMessageBox.information(editor, "Video Import", "Another video operation is already running.")
        return
    controller = getattr(editor, "video_controller", None)
    if controller:
        controller.release(keep_source=True)
    worker = VideoJobWorker("import", editor.project_folder, source_path, parent=editor)
    dialog = VideoProgressDialog("Video Import", editor)
    editor.video_job_worker = worker
    editor.video_progress_dialog = dialog
    state = {"error": False}
    dialog.cancel_button.clicked.connect(worker.cancel)
    worker.progress_changed.connect(dialog.set_progress)

    def ready(result):
        try:
            destination = commit_video_result(editor.project_folder, result)
            save_video_settings(editor.project_folder, result["settings"])
            editor.video_label.set_content_loaded("Video Loaded")
            if hasattr(editor, "resources_window") and editor.resources_window:
                editor.resources_window.update_video_state()
            if controller:
                controller.release()
                controller.load_project()
                controller.sync_current(force=True)
        except Exception as error:
            state["error"] = True
            dialog.show_error(f"Failed to install imported video:\n{error}")

    def failed(message):
        state["error"] = True
        dialog.show_error(message)

    def finished():
        if not state["error"]:
            dialog.finish()
        editor.video_job_worker = None
        editor.video_progress_dialog = None
        if controller:
            controller.load_project()

    worker.job_ready.connect(ready)
    worker.job_failed.connect(failed)
    worker.finished.connect(finished)
    worker.start()