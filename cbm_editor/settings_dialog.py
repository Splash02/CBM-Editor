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

from .project_browser import ConfirmationDialog, StyledWarningDialog

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
        self.lbl_name = lbl_name
        layout.addWidget(lbl_name)
        
        self.btn_play = QPushButton("Play")
        self.btn_play.setProperty("is_custom_sound_btn", True)
        self.btn_play.clicked.connect(self.play_sound)
        layout.addWidget(self.btn_play)
        
        self.btn_reset = QPushButton("Reset")
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
            "UI Update Exit": "Plays when dismissing the update notification",
            "UI Toast Exit": "Plays when a notification closes automatically",
            "UI Toast Enter": "Plays when a notification appears",
            "UI Cover Enter": "Plays when a project cover animates into view",
            "Boot": "Plays when opening CBM Editor"
        }
        if friendly_name in SOUND_TOOLTIPS:
            tip = SOUND_TOOLTIPS[friendly_name]
            lbl_name.setToolTip(tip)
            self.setToolTip(tip)

        self.drop_label = FileDropLabel(
            "Drag new audio here",
            dialog_title="Select Audio",
            file_filter="Audio Files (*.mp3 *.wav *.ogg *.flac *.opus *.m4a *.aac *.wma *.alac *.aiff *.aif);;All Files (*)",
        )
        if friendly_name in SOUND_TOOLTIPS:
            self.drop_label.setToolTip(SOUND_TOOLTIPS[friendly_name])
        self.drop_label.fileDropped.connect(self.handle_drop)
        layout.addWidget(self.drop_label)
        self.apply_ui_scale()

    def apply_ui_scale(self):
        scale = widget_global_scale(self)
        self.lbl_name.setFixedWidth(max(60, int(round(120 * scale))))
        self.btn_play.setFixedWidth(max(30, int(round(60 * scale))))
        self.btn_reset.setFixedWidth(max(30, int(round(60 * scale))))
        apply_layout_scale(self, scale)

    def showEvent(self, event):
        self.apply_ui_scale()
        super().showEvent(event)
        
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


class CustomNotePreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = "Note"
        self.length = False
        self.shape = "Circle"
        self.color = QColor("#FF4FA3")
        self.connection_color = QColor("#B52D73")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.apply_ui_scale()

    def apply_ui_scale(self):
        scale = widget_global_scale(self)
        self.setFixedHeight(max(65, int(round(130 * scale))))

    def showEvent(self, event):
        self.apply_ui_scale()
        super().showEvent(event)

    def set_preview(self, kind, length, shape, color, connection_color):
        self.kind = kind
        self.length = bool(length)
        self.shape = shape
        self.color = QColor(color)
        self.connection_color = QColor(connection_color)
        self.update()

    def draw_shape(self, painter, center, radius):
        scale = widget_global_scale(self)
        outline = QColor("#202020") if widget_ui_brightness(self) > 180 else QColor("#F0F0F0")
        painter.setPen(QPen(outline, max(1.0, 2.0 * scale)))
        painter.setBrush(self.color)
        if self.shape == "Square":
            half_size = radius * 0.75
            painter.drawRect(QRectF(center.x() - half_size, center.y() - half_size, half_size * 2, half_size * 2))
        elif self.shape == "Triangle":
            half_size = radius * 0.91
            painter.drawPolygon(QPolygonF([
                QPointF(center.x(), center.y() - half_size),
                QPointF(center.x() + half_size, center.y() + half_size),
                QPointF(center.x() - half_size, center.y() + half_size),
            ]))
        else:
            painter.drawEllipse(center, radius, radius)

    def paintEvent(self, event):
        scale = widget_global_scale(self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        brightness = widget_ui_brightness(self)
        background = max(0, brightness - 9) if brightness <= 180 else min(255, brightness + 9)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background, background, background))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6 * scale, 6 * scale)
        center_y = self.height() / 2.0
        if self.kind == "Event":
            center = QPointF(self.width() / 2.0, center_y)
            painter.setPen(QPen(self.color, max(1.0, 4.0 * scale)))
            painter.drawLine(QPointF(center.x(), center.y() - 30 * scale), QPointF(center.x(), center.y() + 30 * scale))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.color)
            painter.drawEllipse(center, 9 * scale, 9 * scale)
        elif self.length:
            start = QPointF(self.width() * 0.28, center_y)
            end = QPointF(self.width() * 0.72, center_y)
            painter.setPen(QPen(self.connection_color, max(1.0, 7.0 * scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)
            self.draw_shape(painter, start, 20 * scale)
            self.draw_shape(painter, end, 17 * scale)
        else:
            self.draw_shape(painter, QPointF(self.width() / 2.0, center_y), 23 * scale)
        painter.end()


class CompoundStepDialog(QDialog):
    def __init__(self, step_kind, notes, current_type_id, step=None, parent=None):
        super().__init__(parent)
        self.step_kind = "delay" if step_kind == "delay" else "object"
        self.notes = notes or []
        self.current_type_id = str(current_type_id or "")
        default_step = {"kind": self.step_kind}
        if self.step_kind == "delay":
            default_step.update({"unit": "grid", "grid_division": 4, "value": 1})
        else:
            default_step.update({"length_unit": "grid", "length_grid_division": 4, "length_value": 1})
        self.step = normalize_compound_step(step or default_step)
        self.setWindowTitle("Add Delay" if self.step_kind == "delay" else "Add Object")
        self.setModal(True)
        scale = widget_global_scale(self)
        self.setMinimumWidth(max(225, int(round(450 * scale))))
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        margins = layout.contentsMargins()
        layout.addStrut(max(0, int(round(450 * scale)) - margins.left() - margins.right()))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(12)
        if self.step_kind == "object":
            self.target_combo = IgnoreWheelComboBox()
            self.target_combo.setView(SmoothListView(self.target_combo))
            for target_id, label, _is_length in BUILTIN_COMPOUND_TARGETS:
                self.target_combo.addItem(label, target_id)
            for note in self.notes:
                for type_data in note.get("types", []):
                    type_id = str(type_data.get("id") or "")
                    if not type_id or type_id == self.current_type_id:
                        continue
                    self.target_combo.addItem(
                        f"Custom / {note.get('name', 'Custom')} / {type_data.get('name', 'Type')}",
                        "custom:" + type_id,
                    )
            target_index = self.target_combo.findData(self.step.get("target"))
            self.target_combo.setCurrentIndex(target_index if target_index >= 0 else 0)
            self.object_controls_timer = QTimer(self)
            self.object_controls_timer.setSingleShot(True)
            self.object_controls_timer.timeout.connect(self.update_object_controls)
            self.target_combo.currentIndexChanged.connect(self.schedule_object_controls_update)
            form.addRow("Object:", self.target_combo)
            self.lane_combo = IgnoreWheelComboBox()
            self.lane_combo.setView(SmoothListView(self.lane_combo))
            form.addRow("Lane:", self.lane_combo)
            self.length_unit = IgnoreWheelComboBox()
            self.length_unit.setView(SmoothListView(self.length_unit))
            self.length_unit.addItem("Grid", "grid")
            self.length_unit.addItem("Milliseconds", "ms")
            unit_index = self.length_unit.findData(self.step.get("length_unit", "grid"))
            self.length_unit.setCurrentIndex(max(0, unit_index))
            self.length_grid_division = QSpinBox()
            self.length_grid_division.setRange(1, 64)
            self.length_grid_division.setValue(max(1, min(64, int(self.step.get("length_grid_division", 4)))))
            self.length_grid_division.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            self.length_grid_count = QSpinBox()
            self.length_grid_count.setRange(1, 1000000)
            self.length_grid_count.setValue(max(1, int(round(float(self.step.get("length_value", 1.0))))))
            self.length_grid_count.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            self.length_value = QDoubleSpinBox()
            self.length_value.setRange(0.001, 1000000.0)
            self.length_value.setDecimals(3)
            self.length_value.setValue(max(0.001, float(self.step.get("length_value", 1.0))))
            self.length_value.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            form.addRow("Length:", self.length_unit)
            form.addRow("Grid Size:", self.length_grid_division)
            form.addRow("Grids:", self.length_grid_count)
            form.addRow("Milliseconds:", self.length_value)
            self.length_grid_label = form.labelForField(self.length_grid_division)
            self.length_grid_count_label = form.labelForField(self.length_grid_count)
            self.length_value_label = form.labelForField(self.length_value)
            self.length_unit_label = form.labelForField(self.length_unit)
            self.length_labels = (
                form.labelForField(self.target_combo),
                form.labelForField(self.lane_combo),
                self.length_unit_label,
                self.length_grid_label,
                self.length_grid_count_label,
                self.length_value_label,
            )
            length_label_width = max(label.sizeHint().width() for label in self.length_labels) + 16
            for label in self.length_labels:
                label.setFixedWidth(length_label_width)
                label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.mode_controls_timer = QTimer(self)
            self.mode_controls_timer.setSingleShot(True)
            self.mode_controls_timer.timeout.connect(self.update_length_value_controls)
            self.length_unit.currentIndexChanged.connect(self.schedule_mode_controls_update)
            self.length_controls = (self.length_unit, self.length_grid_division, self.length_grid_count, self.length_value)
        else:
            self.delay_unit = IgnoreWheelComboBox()
            self.delay_unit.setView(SmoothListView(self.delay_unit))
            self.delay_unit.addItem("Grid", "grid")
            self.delay_unit.addItem("Milliseconds", "ms")
            unit_index = self.delay_unit.findData(self.step.get("unit", "grid"))
            self.delay_unit.setCurrentIndex(max(0, unit_index))
            form.addRow("Mode:", self.delay_unit)
            self.delay_grid_division = QSpinBox()
            self.delay_grid_division.setRange(1, 64)
            self.delay_grid_division.setValue(max(1, min(64, int(self.step.get("grid_division", 4)))))
            self.delay_grid_division.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            self.delay_grid_count = QSpinBox()
            self.delay_grid_count.setRange(1, 1000000)
            self.delay_grid_count.setValue(max(1, int(round(float(self.step.get("value", 1.0))))))
            self.delay_grid_count.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            self.delay_value = QDoubleSpinBox()
            self.delay_value.setRange(0.001, 1000000.0)
            self.delay_value.setDecimals(3)
            self.delay_value.setValue(max(0.001, float(self.step.get("value", 1.0))))
            self.delay_value.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            form.addRow("Grid Size:", self.delay_grid_division)
            form.addRow("Grids:", self.delay_grid_count)
            form.addRow("Milliseconds:", self.delay_value)
            self.delay_grid_label = form.labelForField(self.delay_grid_division)
            self.delay_grid_count_label = form.labelForField(self.delay_grid_count)
            self.delay_value_label = form.labelForField(self.delay_value)
            self.delay_unit_label = form.labelForField(self.delay_unit)
            delay_labels = (self.delay_unit_label, self.delay_grid_label, self.delay_grid_count_label, self.delay_value_label)
            delay_label_width = max(label.sizeHint().width() for label in delay_labels) + 16
            for label in delay_labels:
                label.setFixedWidth(delay_label_width)
                label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.mode_controls_timer = QTimer(self)
            self.mode_controls_timer.setSingleShot(True)
            self.mode_controls_timer.timeout.connect(self.update_delay_controls)
            self.delay_unit.currentIndexChanged.connect(self.schedule_mode_controls_update)
        layout.addLayout(form)
        actions = QHBoxLayout()
        okay = QPushButton("OK")
        cancel = QPushButton("Cancel")
        okay.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cancel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        okay.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        actions.addWidget(okay, 1)
        actions.addWidget(cancel, 1)
        layout.addLayout(actions)
        if self.step_kind == "object":
            self.update_length_value_controls()
            self.update_object_controls()
        else:
            self.update_delay_controls()
        apply_layout_scale(self, scale)

    def schedule_object_controls_update(self):
        self.object_controls_timer.start(0)

    def schedule_mode_controls_update(self):
        self.mode_controls_timer.start(0)

    def update_object_controls(self):
        self.update_length_controls()
        current_lane = self.lane_combo.currentText() or self.step.get("lane", "Placement")
        valid_lanes = compound_target_lane_modes(self.target_combo.currentData(), self.notes)
        self.lane_combo.blockSignals(True)
        self.lane_combo.clear()
        self.lane_combo.addItems(valid_lanes)
        self.lane_combo.setCurrentText(current_lane if current_lane in valid_lanes else valid_lanes[0])
        self.lane_combo.blockSignals(False)

    def update_length_controls(self):
        target = self.target_combo.currentData()
        enabled = compound_target_is_length(target, self.notes)
        tooltip = "" if enabled else "This object has no tail length."
        for widget in self.length_controls + self.length_labels[2:]:
            widget.setEnabled(enabled)
            widget.setToolTip(tooltip)

    def update_length_value_controls(self):
        grid_mode = self.length_unit.currentData() == "grid"
        self.length_grid_division.setVisible(grid_mode)
        self.length_grid_count.setVisible(grid_mode)
        self.length_value.setVisible(not grid_mode)
        self.length_grid_label.setVisible(grid_mode)
        self.length_grid_count_label.setVisible(grid_mode)
        self.length_value_label.setVisible(not grid_mode)
        self.layout().invalidate()
        self.layout().activate()
        self.adjustSize()

    def update_delay_controls(self):
        grid_mode = self.delay_unit.currentData() == "grid"
        self.delay_grid_division.setVisible(grid_mode)
        self.delay_grid_count.setVisible(grid_mode)
        self.delay_value.setVisible(not grid_mode)
        self.delay_grid_label.setVisible(grid_mode)
        self.delay_grid_count_label.setVisible(grid_mode)
        self.delay_value_label.setVisible(not grid_mode)
        self.layout().invalidate()
        self.layout().activate()
        self.adjustSize()

    def accept(self):
        if self.step_kind == "delay":
            grid_mode = self.delay_unit.currentData() == "grid"
            self.step = normalize_compound_step({
                "kind": "delay",
                "value": self.delay_grid_count.value() if grid_mode else self.delay_value.value(),
                "unit": self.delay_unit.currentData(),
                "grid_division": self.delay_grid_division.value(),
            })
        else:
            grid_mode = self.length_unit.currentData() == "grid"
            self.step = normalize_compound_step({
                "kind": "object",
                "target": self.target_combo.currentData(),
                "lane": self.lane_combo.currentText(),
                "length_value": self.length_grid_count.value() if grid_mode else self.length_value.value(),
                "length_unit": self.length_unit.currentData(),
                "length_grid_division": self.length_grid_division.value(),
            })
        super().accept()


class CustomNoteEditorDialog(QDialog):
    def __init__(self, note, parent=None, available_notes=None, game_root=None):
        super().__init__(parent)
        self.note = normalize_custom_note(copy.deepcopy(note))
        self.available_notes = normalize_custom_notes(copy.deepcopy(available_notes or []))
        self.game_root = Path(game_root) if game_root else None
        self.current_compound_steps = []
        self.current_type_index = -1
        self.loading_type = False
        self.current_custom_hitsound = ""
        self.copied_custom_hitsound_files = set()
        self.setWindowTitle("Custom Note")
        scale = widget_global_scale(self)
        main_layout = QVBoxLayout(self)
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.note_name = QLineEdit(self.note["name"])
        name_layout.addWidget(self.note_name)
        main_layout.addLayout(name_layout)
        body_layout = QHBoxLayout()
        type_column = QVBoxLayout()
        type_column.addWidget(QLabel("Types"))
        self.type_list = QListWidget()
        self.type_list.setVerticalScrollBar(RoundedScrollBar(Qt.Orientation.Vertical, self.type_list))
        self.type_list.setMinimumWidth(max(90, int(round(180 * scale))))
        type_list_font = self.type_list.font()
        type_list_font.setWeight(QFont.Weight.DemiBold)
        self.type_list.setFont(type_list_font)
        type_column.addWidget(self.type_list)
        type_buttons = QHBoxLayout()
        add_type = QPushButton("Add")
        delete_type = QPushButton("Delete")
        add_type.clicked.connect(self.add_type)
        delete_type.clicked.connect(self.delete_type)
        type_buttons.addWidget(add_type)
        type_buttons.addWidget(delete_type)
        type_column.addLayout(type_buttons)
        body_layout.addLayout(type_column)
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        self.type_form = form
        self.type_name = QLineEdit()
        form.addRow("Type Name:", self.type_name)
        self.kind_combo = IgnoreWheelComboBox()
        self.kind_combo.setView(SmoothListView(self.kind_combo))
        self.kind_combo.addItems(CUSTOM_NOTE_KINDS)
        self.kind_combo.currentTextChanged.connect(self.update_type_controls)
        form.addRow("Object:", self.kind_combo)
        self.section_combo = IgnoreWheelComboBox()
        self.section_combo.setView(SmoothListView(self.section_combo))
        for section in CUSTOM_NOTE_SECTIONS:
            self.section_combo.addItem(f"[{section}]", section)
        form.addRow("Section:", self.section_combo)
        self.length_combo = IgnoreWheelComboBox()
        self.length_combo.setView(SmoothListView(self.length_combo))
        self.length_combo.addItems(["One-Time", "Length"])
        self.length_combo.currentTextChanged.connect(self.update_type_controls)
        form.addRow("Timing:", self.length_combo)
        self.shape_combo = IgnoreWheelComboBox()
        self.shape_combo.setView(SmoothListView(self.shape_combo))
        self.shape_combo.addItems(CUSTOM_NOTE_SHAPES)
        form.addRow("Shape:", self.shape_combo)
        self.lane_combo = IgnoreWheelComboBox()
        self.lane_combo.setView(SmoothListView(self.lane_combo))
        self.lane_combo.addItems(CUSTOM_NOTE_LANE_MODES)
        self.lane_combo.currentTextChanged.connect(self.update_type_controls)
        form.addRow("Position:", self.lane_combo)
        self.lane_values_widget = QWidget()
        lane_values_layout = QHBoxLayout(self.lane_values_widget)
        lane_values_layout.setContentsMargins(0, 0, 0, 0)
        lane_values_layout.setSpacing(6)
        self.lane_top_label = QLabel("Top:")
        self.lane_top_edit = QLineEdit()
        self.lane_top_edit.setValidator(QIntValidator(-2147483648, 2147483647, self.lane_top_edit))
        self.lane_top_edit.setMaximumWidth(max(37, int(round(74 * scale))))
        self.lane_bottom_label = QLabel("Bottom:")
        self.lane_bottom_edit = QLineEdit()
        self.lane_bottom_edit.setValidator(QIntValidator(-2147483648, 2147483647, self.lane_bottom_edit))
        self.lane_bottom_edit.setMaximumWidth(max(37, int(round(74 * scale))))
        self.lane_single_label = QLabel("Value:")
        self.lane_single_edit = QLineEdit()
        self.lane_single_edit.setValidator(QIntValidator(-2147483648, 2147483647, self.lane_single_edit))
        self.lane_single_edit.setMaximumWidth(max(37, int(round(74 * scale))))
        lane_values_layout.addWidget(self.lane_top_label)
        lane_values_layout.addWidget(self.lane_top_edit)
        lane_values_layout.addWidget(self.lane_bottom_label)
        lane_values_layout.addWidget(self.lane_bottom_edit)
        lane_values_layout.addWidget(self.lane_single_label)
        lane_values_layout.addWidget(self.lane_single_edit)
        lane_values_layout.addStretch()
        form.addRow("Lane Values:", self.lane_values_widget)
        self.collision_check = QCheckBox("Enable Collision")
        self.collision_check.setChecked(True)
        form.addRow(self.collision_check)
        self.color_button = ColorPickerButton("#FF4FA3", "#FF4FA3")
        form.addRow("Color:", self.color_button)
        self.connection_color_button = ColorPickerButton("#B52D73", "#B52D73")
        self.connection_color_disabled_effect = QGraphicsColorizeEffect(self.connection_color_button)
        self.connection_color_disabled_effect.setColor(QColor(110, 110, 110))
        self.connection_color_disabled_effect.setStrength(1.0)
        self.connection_color_button.setGraphicsEffect(self.connection_color_disabled_effect)
        form.addRow("Connection Color:", self.connection_color_button)
        self.hitsound_widget = QWidget()
        hitsound_layout = QVBoxLayout(self.hitsound_widget)
        hitsound_layout.setContentsMargins(0, 0, 0, 0)
        hitsound_layout.setSpacing(6)
        self.hitsound_combo = IgnoreWheelComboBox()
        self.hitsound_combo.setView(SmoothListView(self.hitsound_combo))
        self.hitsound_combo.addItem("No Custom Hit Sound", "")
        for sound_name in (
            "Note", "Spike", "Hold Start", "Double Start", "Spam",
            "Brawl Hit", "Brawl Hold Start", "Brawl Knockout", "Hide Note",
            "Event Flip", "Event Instant", "Event Toggle",
        ):
            self.hitsound_combo.addItem(sound_name, f"standard:{sound_name}")
        self.hitsound_combo.addItem("Custom Audio File", "custom")
        hitsound_layout.addWidget(self.hitsound_combo)
        custom_hitsound_layout = QHBoxLayout()
        self.custom_hitsound_drop = FileDropLabel(
            "Drop an audio file here",
            self,
            dialog_title="Select Hit Sound",
            file_filter="Audio Files (*.wav *.ogg *.mp3 *.flac *.m4a *.aac *.opus);;All Files (*)",
        )
        self.custom_hitsound_drop.fileDropped.connect(self.import_custom_hitsound)
        self.remove_hitsound_button = QPushButton("Remove")
        self.remove_hitsound_button.clicked.connect(self.remove_custom_hitsound)
        custom_hitsound_layout.addWidget(self.custom_hitsound_drop, 1)
        custom_hitsound_layout.addWidget(self.remove_hitsound_button)
        hitsound_layout.addLayout(custom_hitsound_layout)
        form.addRow("Hit Sound:", self.hitsound_widget)
        self.syntax_edit = QLineEdit()
        form.addRow("Syntax:", self.syntax_edit)
        token_widget = QWidget()
        self.token_widget = token_widget
        token_layout = QGridLayout(token_widget)
        token_layout.setContentsMargins(0, 0, 0, 0)
        for index, token in enumerate(CUSTOM_NOTE_TOKENS):
            button = QPushButton("{" + token + "}")
            button.clicked.connect(lambda checked=False, value=token: self.insert_token(value))
            token_layout.addWidget(button, index // 3, index % 3)
        form.addRow(token_widget)
        self.syntax_preview = QLabel("")
        self.syntax_preview.setWordWrap(True)
        form.addRow("Preview:", self.syntax_preview)
        self.note_preview = CustomNotePreview(self)
        form.addRow(self.note_preview)
        self.compound_widget = QWidget()
        compound_layout = QVBoxLayout(self.compound_widget)
        compound_layout.setContentsMargins(0, 0, 0, 0)
        self.compound_list = QListWidget()
        self.compound_list.setVerticalScrollBar(RoundedScrollBar(Qt.Orientation.Vertical, self.compound_list))
        self.compound_list.setMinimumHeight(max(122, int(round(245 * scale))))
        self.compound_list.setDragEnabled(True)
        self.compound_list.setAcceptDrops(True)
        self.compound_list.setDropIndicatorShown(True)
        self.compound_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.compound_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.compound_list.model().rowsMoved.connect(self.compound_steps_reordered)
        self.compound_list.itemDoubleClicked.connect(self.edit_compound_step)
        compound_layout.addWidget(self.compound_list)
        compound_actions = QGridLayout()
        add_object = QPushButton("Add Object")
        add_delay = QPushButton("Add Delay")
        edit_step = QPushButton("Edit")
        delete_step = QPushButton("Delete")
        move_up = QPushButton("Move Up")
        move_down = QPushButton("Move Down")
        add_object.clicked.connect(self.add_compound_object)
        add_delay.clicked.connect(self.add_compound_delay)
        edit_step.clicked.connect(self.edit_compound_step)
        delete_step.clicked.connect(self.delete_compound_step)
        move_up.clicked.connect(lambda: self.move_compound_step(-1))
        move_down.clicked.connect(lambda: self.move_compound_step(1))
        for index, button in enumerate((add_object, add_delay, move_up, delete_step, edit_step, move_down)):
            compound_actions.addWidget(button, index // 3, index % 3)
        compound_layout.addLayout(compound_actions)
        form.addRow("Sequence:", self.compound_widget)
        body_layout.addWidget(form_widget, 1)
        main_layout.addLayout(body_layout, 1)
        actions = QHBoxLayout()
        okay = QPushButton("OK")
        cancel = QPushButton("Cancel")
        okay.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        actions.addWidget(okay)
        actions.addWidget(cancel)
        main_layout.addLayout(actions)
        for type_data in self.note["types"]:
            self.type_list.addItem(type_data["name"])
        self.type_list.currentRowChanged.connect(self.select_type)
        self.syntax_edit.textChanged.connect(self.update_syntax_preview)
        self.lane_top_edit.textChanged.connect(self.update_syntax_preview)
        self.lane_bottom_edit.textChanged.connect(self.update_syntax_preview)
        self.lane_single_edit.textChanged.connect(self.update_syntax_preview)
        self.shape_combo.currentTextChanged.connect(self.update_note_preview)
        self.color_button.colorChanged.connect(self.update_note_preview)
        self.connection_color_button.colorChanged.connect(self.update_note_preview)
        self.hitsound_combo.currentIndexChanged.connect(self.hitsound_selection_changed)
        self.type_list.setCurrentRow(0)
        apply_fixed_window_scale(self, 780, 800, scale)

    def insert_token(self, token):
        self.syntax_edit.insert("{" + token + "}")

    def update_syntax_preview(self):
        template = mark_custom_template(self.syntax_edit.text())

        def preview_line(logical_lane, lane_value):
            result = template.replace("{lane}", str(lane_value)).replace("{time}", "TIME").replace("{end}", "END")
            return result

        mode = self.lane_combo.currentText()
        if mode == "Top & Bottom":
            top_value = self.read_lane_value(self.lane_top_edit, 0)
            bottom_value = self.read_lane_value(self.lane_bottom_edit, 1)
            preview = f"Top: {preview_line(0, top_value)}\nBottom: {preview_line(1, bottom_value)}"
        else:
            logical_lane = -2 if mode == "Middle" else (1 if mode == "Bottom Only" else 0)
            lane_value = self.read_lane_value(self.lane_single_edit, 0)
            preview = preview_line(logical_lane, lane_value)
        self.syntax_preview.setText(preview)

    def read_lane_value(self, edit, default):
        return normalize_lane_value(edit.text(), default)

    def update_lane_value_controls(self):
        mode = self.lane_combo.currentText()
        dual = mode == "Top & Bottom"
        self.lane_top_label.setVisible(dual)
        self.lane_top_edit.setVisible(dual)
        self.lane_bottom_label.setVisible(dual)
        self.lane_bottom_edit.setVisible(dual)
        self.lane_single_label.setVisible(not dual)
        self.lane_single_edit.setVisible(not dual)
        if not dual:
            labels = {
                "Middle": "Middle:",
                "Top Only": "Top:",
                "Bottom Only": "Bottom:",
            }
            self.lane_single_label.setText(labels.get(mode, "Value:"))

    def update_type_controls(self):
        kind = self.kind_combo.currentText()
        is_compound = kind == "Compound"
        is_note = kind == "Note"
        is_length = is_note and self.length_combo.currentText() == "Length"
        self.length_combo.setEnabled(is_note)
        self.shape_combo.setEnabled(is_note)
        self.connection_color_button.setEnabled(is_length)
        brightness = widget_ui_brightness(self)
        disabled_tone = max(0, brightness - 24) if brightness <= 180 else min(255, brightness + 24)
        self.connection_color_disabled_effect.setColor(QColor(disabled_tone, disabled_tone, disabled_tone))
        self.connection_color_disabled_effect.setEnabled(not is_length)
        standard_widgets = (
            self.section_combo,
            self.length_combo,
            self.shape_combo,
            self.lane_combo,
            self.lane_values_widget,
            self.collision_check,
            self.color_button,
            self.connection_color_button,
            self.hitsound_widget,
            self.syntax_edit,
            self.token_widget,
            self.syntax_preview,
            self.note_preview,
        )
        for widget in standard_widgets:
            widget.setVisible(not is_compound)
            label = self.type_form.labelForField(widget)
            if label is not None:
                label.setVisible(not is_compound)
        self.compound_widget.setVisible(is_compound)
        compound_label = self.type_form.labelForField(self.compound_widget)
        if compound_label is not None:
            compound_label.setVisible(is_compound)
        self.update_lane_value_controls()
        self.update_syntax_preview()
        self.update_note_preview()

    def update_hitsound_controls(self):
        is_custom = self.hitsound_combo.currentData() == "custom"
        self.custom_hitsound_drop.setVisible(is_custom)
        self.remove_hitsound_button.setVisible(is_custom and bool(self.current_custom_hitsound))
        if is_custom and self.current_custom_hitsound:
            self.custom_hitsound_drop.set_content_loaded(self.current_custom_hitsound)
        else:
            self.custom_hitsound_drop.set_empty()

    def hitsound_selection_changed(self):
        if not self.loading_type and self.hitsound_combo.currentData() != "custom":
            self.discard_uncommitted_hitsound(self.current_custom_hitsound)
            self.current_custom_hitsound = ""
        self.update_hitsound_controls()

    def discard_uncommitted_hitsound(self, filename):
        if filename not in self.copied_custom_hitsound_files or self.game_root is None:
            return
        target = self.game_root / "ChartEditorResources" / filename
        try:
            if target.is_file():
                target.unlink()
        except OSError:
            return
        self.copied_custom_hitsound_files.discard(filename)

    def import_custom_hitsound(self, source_path):
        source = Path(source_path)
        if not source.is_file() or source.suffix.lower() not in {".wav", ".ogg", ".mp3", ".flac", ".m4a", ".aac", ".opus"}:
            StyledWarningDialog(self, "Custom Hit Sound", "Choose a supported audio file.").exec()
            return
        if self.game_root is None or self.current_type_index < 0:
            StyledWarningDialog(self, "Custom Hit Sound", "UNBEATABLE's resource folder is unavailable.").exec()
            return
        type_id = str(self.note["types"][self.current_type_index].get("id") or "")
        if not type_id:
            StyledWarningDialog(self, "Custom Hit Sound", "This custom note type has no valid ID.").exec()
            return
        filename = f"custom_hitsound_{type_id}_{uuid.uuid4().hex}{source.suffix.lower()}"
        destination = self.game_root / "ChartEditorResources" / filename
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
        except OSError as error:
            StyledWarningDialog(self, "Custom Hit Sound", f"The audio file could not be copied.\n\n{error}").exec()
            return
        self.discard_uncommitted_hitsound(self.current_custom_hitsound)
        self.copied_custom_hitsound_files.add(filename)
        self.current_custom_hitsound = filename
        self.hitsound_combo.setCurrentIndex(self.hitsound_combo.findData("custom"))
        self.update_hitsound_controls()

    def remove_custom_hitsound(self):
        self.discard_uncommitted_hitsound(self.current_custom_hitsound)
        self.current_custom_hitsound = ""
        self.hitsound_combo.setCurrentIndex(0)
        self.update_hitsound_controls()

    def current_hitsound_value(self):
        selected = self.hitsound_combo.currentData()
        if selected == "custom":
            return f"custom:{self.current_custom_hitsound}" if self.current_custom_hitsound else ""
        return str(selected or "")

    def update_note_preview(self, value=None):
        self.note_preview.set_preview(
            self.kind_combo.currentText(),
            self.kind_combo.currentText() == "Note" and self.length_combo.currentText() == "Length",
            self.shape_combo.currentText(),
            self.color_button.get_hex(),
            self.connection_color_button.get_hex(),
        )

    def save_current_type(self):
        if self.loading_type or self.current_type_index < 0 or self.current_type_index >= len(self.note["types"]):
            return
        item = self.note["types"][self.current_type_index]
        kind = self.kind_combo.currentText()
        item.update({
            "name": self.type_name.text().strip() or "Type",
            "kind": kind,
            "section": self.section_combo.currentData() or "HitObjects",
            "length": kind == "Note" and self.length_combo.currentText() == "Length",
            "shape": self.shape_combo.currentText(),
            "lane_mode": self.lane_combo.currentText(),
            "collision": self.collision_check.isChecked(),
            "color": self.color_button.get_hex(),
            "connection_color": self.connection_color_button.get_hex(),
            "hitsound": self.current_hitsound_value() if kind != "Compound" else "",
            "syntax": strip_custom_marker(self.syntax_edit.text()),
            "lane_top_value": self.read_lane_value(self.lane_top_edit, 0),
            "lane_bottom_value": self.read_lane_value(self.lane_bottom_edit, 1),
            "lane_single_value": self.read_lane_value(self.lane_single_edit, 0),
            "steps": copy.deepcopy(self.current_compound_steps) if kind == "Compound" else [],
        })
        self.type_list.item(self.current_type_index).setText(item["name"])

    def select_type(self, index):
        self.save_current_type()
        self.current_type_index = index
        if index < 0 or index >= len(self.note["types"]):
            return
        item = self.note["types"][index]
        self.loading_type = True
        self.type_name.setText(item["name"])
        self.kind_combo.setCurrentText(item["kind"])
        section_index = self.section_combo.findData(item.get("section", "HitObjects"))
        self.section_combo.setCurrentIndex(max(0, section_index))
        self.length_combo.setCurrentText("Length" if item["length"] else "One-Time")
        self.shape_combo.setCurrentText(item["shape"])
        self.lane_combo.setCurrentText(item["lane_mode"])
        self.collision_check.setChecked(item["collision"])
        self.color_button.set_color(item["color"])
        self.connection_color_button.set_color(item["connection_color"])
        hitsound = str(item.get("hitsound") or "")
        self.current_custom_hitsound = hitsound.removeprefix("custom:") if hitsound.startswith("custom:") else ""
        selected_hitsound = "custom" if self.current_custom_hitsound else hitsound
        hitsound_index = self.hitsound_combo.findData(selected_hitsound)
        self.hitsound_combo.setCurrentIndex(max(0, hitsound_index))
        self.syntax_edit.setText(item["syntax"])
        self.lane_top_edit.setText(str(item["lane_top_value"]))
        self.lane_bottom_edit.setText(str(item["lane_bottom_value"]))
        self.lane_single_edit.setText(str(item["lane_single_value"]))
        self.current_compound_steps = copy.deepcopy(item.get("steps", []))
        self.refresh_compound_list()
        self.loading_type = False
        self.update_type_controls()
        self.update_hitsound_controls()
        self.update_syntax_preview()

    def add_type(self):
        self.save_current_type()
        item = default_custom_type(f"Type {len(self.note['types']) + 1}")
        self.note["types"].append(item)
        self.type_list.addItem(item["name"])
        self.type_list.setCurrentRow(len(self.note["types"]) - 1)

    def compound_notes_for_picker(self):
        notes = copy.deepcopy(self.available_notes)
        replaced = False
        for index, note in enumerate(notes):
            if note.get("id") == self.note.get("id"):
                notes[index] = copy.deepcopy(self.note)
                replaced = True
                break
        if not replaced:
            notes.append(copy.deepcopy(self.note))
        return notes

    def compound_target_label(self, target):
        for target_id, label, _is_length in BUILTIN_COMPOUND_TARGETS:
            if target == target_id:
                return label
        if str(target).startswith("custom:"):
            type_id = str(target).split(":", 1)[1]
            for note in self.compound_notes_for_picker():
                for type_data in note.get("types", []):
                    if str(type_data.get("id")) == type_id:
                        return f"Custom / {note.get('name', 'Custom')} / {type_data.get('name', 'Type')}"
        return "Missing Object"

    def refresh_compound_list(self):
        current = self.compound_list.currentRow()
        self.compound_list.clear()
        notes = self.compound_notes_for_picker()
        for index, step in enumerate(self.current_compound_steps):
            if step.get("kind") == "delay":
                if step.get("unit") == "grid":
                    count = int(round(float(step.get("value", 1))))
                    label = "grid" if count == 1 else "grids"
                    text = f"Delay — {count} {label} on grid size {int(step.get('grid_division', 4))}"
                else:
                    text = f"Delay — {float(step.get('value', 0)):g} ms"
            else:
                text = self.compound_target_label(step.get("target"))
                text += f" — {step.get('lane', 'Placement')}"
                if compound_target_is_length(step.get("target"), notes):
                    if step.get("length_unit") == "grid":
                        count = int(round(float(step.get("length_value", 1))))
                        label = "grid" if count == 1 else "grids"
                        text += f" — length {count} {label} on grid size {int(step.get('length_grid_division', 4))}"
                    else:
                        text += f" — length {float(step.get('length_value', 1)):g} ms"
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, index)
            self.compound_list.addItem(list_item)
        if self.current_compound_steps:
            self.compound_list.setCurrentRow(max(0, min(current, len(self.current_compound_steps) - 1)))

    def compound_steps_reordered(self, *args):
        old_steps = list(self.current_compound_steps)
        source_indices = [
            self.compound_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.compound_list.count())
        ]
        if len(source_indices) != len(old_steps) or set(source_indices) != set(range(len(old_steps))):
            self.refresh_compound_list()
            return
        self.current_compound_steps = [old_steps[index] for index in source_indices]
        for row in range(self.compound_list.count()):
            self.compound_list.item(row).setData(Qt.ItemDataRole.UserRole, row)

    def add_compound_object(self):
        dialog = CompoundStepDialog("object", self.compound_notes_for_picker(), self.note["types"][self.current_type_index]["id"], parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.current_compound_steps.append(dialog.step)
            self.refresh_compound_list()
            self.compound_list.setCurrentRow(len(self.current_compound_steps) - 1)

    def add_compound_delay(self):
        dialog = CompoundStepDialog("delay", self.compound_notes_for_picker(), self.note["types"][self.current_type_index]["id"], parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.current_compound_steps.append(dialog.step)
            self.refresh_compound_list()
            self.compound_list.setCurrentRow(len(self.current_compound_steps) - 1)

    def edit_compound_step(self, item=None):
        index = self.compound_list.currentRow()
        if index < 0 or index >= len(self.current_compound_steps):
            return
        step = self.current_compound_steps[index]
        dialog = CompoundStepDialog(step.get("kind"), self.compound_notes_for_picker(), self.note["types"][self.current_type_index]["id"], step, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.current_compound_steps[index] = dialog.step
            self.refresh_compound_list()
            self.compound_list.setCurrentRow(index)

    def delete_compound_step(self):
        index = self.compound_list.currentRow()
        if index < 0:
            return
        self.current_compound_steps.pop(index)
        self.refresh_compound_list()

    def move_compound_step(self, direction):
        index = self.compound_list.currentRow()
        target = index + int(direction)
        if index < 0 or target < 0 or target >= len(self.current_compound_steps):
            return
        self.current_compound_steps[index], self.current_compound_steps[target] = self.current_compound_steps[target], self.current_compound_steps[index]
        self.refresh_compound_list()
        self.compound_list.setCurrentRow(target)

    def delete_type(self):
        if len(self.note["types"]) <= 1:
            StyledWarningDialog(
                self,
                "Custom Notes",
                "A custom note must contain at least one type.",
                QStyle.StandardPixmap.SP_MessageBoxInformation,
            ).exec()
            return
        index = self.type_list.currentRow()
        if index < 0:
            return
        self.note["types"].pop(index)
        self.type_list.takeItem(index)
        self.current_type_index = -1
        self.type_list.setCurrentRow(min(index, len(self.note["types"]) - 1))

    def accept(self):
        self.save_current_type()
        name = self.note_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Custom Notes", "Enter a custom note name.")
            return
        seen_names = set()
        for item in self.note["types"]:
            normalized_name = item["name"].casefold()
            if normalized_name in seen_names:
                QMessageBox.warning(self, "Custom Notes", "Type names must be unique inside a custom note.")
                return
            seen_names.add(normalized_name)
            valid, message = validate_custom_type(item)
            if not valid:
                StyledWarningDialog(self, "Invalid Syntax", f"{item['name']}: {message}").exec()
                return
        self.note["name"] = name
        super().accept()

    def reject(self):
        for filename in tuple(self.copied_custom_hitsound_files):
            self.discard_uncommitted_hitsound(filename)
        super().reject()


class CustomNotesDialog(QDialog):
    def __init__(self, notes, tombstones, parent=None):
        super().__init__(parent)
        self.original_notes = normalize_custom_notes(copy.deepcopy(notes))
        self.notes = normalize_custom_notes(copy.deepcopy(notes))
        self.tombstones = normalize_custom_tombstones(copy.deepcopy(tombstones))
        self.game_root = getattr(parent, "game_root", None)
        self.removed_custom_hitsound_files = set()
        self.created_custom_hitsound_files = set()
        self.setWindowTitle("Custom Notes")
        layout = QVBoxLayout(self)
        self.note_list = QListWidget()
        self.note_list.setVerticalScrollBar(RoundedScrollBar(Qt.Orientation.Vertical, self.note_list))
        self.note_list.itemDoubleClicked.connect(self.edit_note)
        layout.addWidget(self.note_list)
        note_actions = QHBoxLayout()
        add_button = QPushButton("Add")
        edit_button = QPushButton("Edit")
        delete_button = QPushButton("Delete")
        add_button.clicked.connect(self.add_note)
        edit_button.clicked.connect(self.edit_note)
        delete_button.clicked.connect(self.delete_note)
        note_actions.addWidget(add_button)
        note_actions.addWidget(edit_button)
        note_actions.addWidget(delete_button)
        layout.addLayout(note_actions)
        actions = QHBoxLayout()
        okay = QPushButton("OK")
        cancel = QPushButton("Cancel")
        okay.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        actions.addWidget(okay)
        actions.addWidget(cancel)
        layout.addLayout(actions)
        self.refresh_list()
        apply_fixed_window_scale(self, 520, 560)

    def refresh_list(self):
        current = self.note_list.currentRow()
        self.note_list.clear()
        for note in self.notes:
            type_count = len(note["types"])
            type_label = "type" if type_count == 1 else "types"
            self.note_list.addItem(f"{note['name']}  ({type_count} {type_label})")
        if self.notes:
            self.note_list.setCurrentRow(max(0, min(current, len(self.notes) - 1)))

    def add_note(self):
        note = default_custom_note(f"Custom Note {len(self.notes) + 1}")
        dialog = CustomNoteEditorDialog(note, self, self.notes, self.game_root)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.notes.append(dialog.note)
            self.created_custom_hitsound_files.update(dialog.copied_custom_hitsound_files)
            self.refresh_list()
            self.note_list.setCurrentRow(len(self.notes) - 1)

    def edit_note(self, item=None):
        index = self.note_list.currentRow()
        if index < 0:
            return
        dialog = CustomNoteEditorDialog(self.notes[index], self, self.notes, self.game_root)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.notes[index] = dialog.note
            self.created_custom_hitsound_files.update(dialog.copied_custom_hitsound_files)
            self.refresh_list()
            self.note_list.setCurrentRow(index)

    def delete_note(self):
        index = self.note_list.currentRow()
        if index < 0:
            return
        dialog = ConfirmationDialog(
            self,
            "Delete Custom Note",
            f"Delete {self.notes[index]['name']}?",
            "Existing objects will become Missing objects.",
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.notes.pop(index)
        self.refresh_list()

    def custom_hitsound_files(self, notes):
        files = set()
        for note in notes:
            for type_data in note.get("types", []):
                hitsound = str(type_data.get("hitsound") or "")
                filename = hitsound.removeprefix("custom:") if hitsound.startswith("custom:") else ""
                type_id = str(type_data.get("id") or "")
                expected_prefix = f"custom_hitsound_{type_id}"
                if filename and Path(filename).name == filename and filename.startswith(expected_prefix):
                    files.add(filename)
        return files

    def delete_custom_hitsound_files(self, filenames):
        if not self.game_root:
            return
        resource_directory = Path(self.game_root) / "ChartEditorResources"
        for filename in filenames:
            target = resource_directory / filename
            try:
                if target.is_file():
                    target.unlink()
            except OSError:
                pass

    def accept(self):
        names = set()
        syntaxes = set()
        current_types = {}
        for note in self.notes:
            name_key = note["name"].casefold()
            if name_key in names:
                QMessageBox.warning(self, "Custom Notes", "Custom note names must be unique.")
                return
            names.add(name_key)
            for item in note["types"]:
                if item.get("kind") != "Compound":
                    syntax_key = (item.get("section", "HitObjects"), item["syntax"])
                    if syntax_key in syntaxes:
                        StyledWarningDialog(self, "Custom Notes", "Every type in the same section must have a unique syntax.").exec()
                        return
                    syntaxes.add(syntax_key)
                current_types[item["id"]] = item
        compound_graph = {}
        for type_id, item in current_types.items():
            if item.get("kind") != "Compound":
                continue
            dependencies = []
            for step in item.get("steps", []):
                target = str(step.get("target") or "")
                if step.get("kind") != "object" or not target.startswith("custom:"):
                    continue
                target_id = target.split(":", 1)[1]
                target_type = current_types.get(target_id)
                if target_type is None:
                    StyledWarningDialog(self, "Invalid Compound", f"{item['name']}: a referenced custom object no longer exists.").exec()
                    return
                if target_type.get("kind") == "Compound":
                    dependencies.append(target_id)
            compound_graph[type_id] = dependencies

        visiting = set()
        visited = set()

        def has_cycle(type_id):
            if type_id in visiting:
                return True
            if type_id in visited:
                return False
            visiting.add(type_id)
            if any(has_cycle(child_id) for child_id in compound_graph.get(type_id, [])):
                return True
            visiting.remove(type_id)
            visited.add(type_id)
            return False

        if any(has_cycle(type_id) for type_id in compound_graph):
            StyledWarningDialog(self, "Invalid Compound", "Compounds cannot contain themselves, directly or indirectly.").exec()
            return
        tombstone_keys = {custom_type_parser_key(item) for item in self.tombstones}
        for note in self.original_notes:
            for item in note["types"]:
                if item.get("kind") == "Compound":
                    continue
                current = current_types.get(item["id"])
                if current is None or custom_type_parser_key(current) != custom_type_parser_key(item):
                    tombstone = custom_type_to_tombstone(note, item)
                    key = custom_type_parser_key(tombstone)
                    if key not in tombstone_keys:
                        self.tombstones.append(tombstone)
                        tombstone_keys.add(key)
        self.removed_custom_hitsound_files = self.custom_hitsound_files(self.original_notes) - self.custom_hitsound_files(self.notes)
        used_files = self.custom_hitsound_files(self.notes)
        self.delete_custom_hitsound_files(self.created_custom_hitsound_files - used_files)
        self.created_custom_hitsound_files.intersection_update(used_files)
        super().accept()

    def reject(self):
        self.delete_custom_hitsound_files(self.created_custom_hitsound_files)
        self.created_custom_hitsound_files.clear()
        super().reject()


class SettingsDialog(QDialog):
    def search_for_update(self):
        if self.parent_window.request_manual_update_check():
            self.update_search_update_button()

    def update_search_update_button(self):
        remaining = self.parent_window.manual_update_check_remaining()
        self.search_update_btn.setText("Search for Update")
        self.search_update_btn.setEnabled(remaining <= 0.0)
        checked_at = getattr(self.parent_window, "_update_last_checked_at", 0.0)
        elapsed = max(0, int(time.time() - checked_at)) if checked_at else 0
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        checked_text = f"{hours} hours {minutes} minutes {seconds} seconds ago" if checked_at else "Never"
        self.search_update_last_checked_label.setText(f"Last checked: {checked_text}")
        if remaining > 0.0:
            self.search_update_timer.start(max(1, int(math.ceil(remaining * 1000.0))))
        else:
            self.search_update_timer.stop()

    def refresh_background_choices(self):
        current_text = self.combo_bg.currentText()
        current_filename = self.bg_map.get(current_text)
        bg_folder = Path(self.game_root) / "ChartEditorResources" / "backgrounds"
        bg_files = []
        if bg_folder.is_dir():
            bg_files = sorted(
                (
                    path.name
                    for path in bg_folder.iterdir()
                    if path.is_file() and path.suffix.casefold() in {".png", ".jpg", ".jpeg"}
                ),
                key=str.casefold,
            )
        self.bg_map = {Path(filename).stem: filename for filename in bg_files}
        self.bg_map["None"] = "None"
        preferred_filename = current_filename
        if not preferred_filename or preferred_filename == "None":
            preferred_filename = self.original_background
        preferred_text = "None"
        if preferred_filename and preferred_filename != "None":
            candidate = Path(preferred_filename).stem
            if candidate in self.bg_map:
                preferred_text = candidate
        self.combo_bg.clear()
        self.combo_bg.addItems(["None"] + sorted((Path(filename).stem for filename in bg_files), key=str.casefold))
        self.combo_bg.setCurrentText(preferred_text)

    def get_group_style(self):
         scale = max(0.5, float(getattr(self.parent(), 'global_scale', 1.0)))
         return scale_stylesheet_dimensions("QGroupBox { margin-top: 15px; font-weight: bold; border: none; } QGroupBox::title { font-size: 24pt; subcontrol-origin: margin; left: 10px; padding: 0px 5px; border-radius: 4px; }", scale)

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

    def __init__(self, parent, current_scale, current_master_vol, current_music_vol, current_fx_vol, current_ui_vol, current_colors, game_root, event_default_order="Before", enable_3d_sound=True, enable_visualizer=True, enable_beatflash=True, auto_save=False, file_extension=".txt", geometry=None, grid_opacity=50, visualizer_opacity=10, background_opacity=20, grid_thickness=2, current_background="None", preview_bg_opacity=30, lane_opacity=100, background_blur=0, ui_brightness=60, current_keybinds=None, custom_notes_enabled=True, custom_notes=None, custom_note_tombstones=None, display_scale=None):
        super().__init__(parent)
        self.global_scale = max(0.5, min(1.5, float(display_scale if display_scale is not None else current_scale)))
        self.setWindowTitle("Settings")
        self.setModal(False)
        self.sounds_changed = False
        self.custom_hitsounds_changed = False
        self.custom_hitsound_files_to_remove = set()
        self.created_custom_hitsound_files = set()
        if geometry:
            self.restoreGeometry(geometry)
            geometry_scale = max(0.5, min(1.5, float(getattr(parent, "settings_geometry_scale", self.global_scale) or self.global_scale)))
            scale_ratio = self.global_scale / geometry_scale
            self.resize(
                max(1, int(round(self.width() * scale_ratio))),
                max(1, int(round(self.height() * scale_ratio))),
            )
        else:
            self.resize(max(350, int(round(700 * self.global_scale))), max(375, int(round(750 * self.global_scale))))

        self.original_colors = current_colors.copy()
        self.current_colors = current_colors.copy()
        if current_keybinds is None:
            self.current_keybinds = DEFAULT_KEYBINDS.copy()
        else:
            self.current_keybinds = current_keybinds.copy()
        self.custom_notes = normalize_custom_notes(copy.deepcopy(custom_notes or []))
        self.custom_note_tombstones = normalize_custom_tombstones(copy.deepcopy(custom_note_tombstones or []))
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
        self.settings_scroll_area = tabs_area
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
        self.scale_slider.setToolTip("Set the base scale of all UI elements; monitor resolution adjustments are applied automatically")
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

        self.chk_video_preview = QCheckBox("Video Preview")
        self.chk_video_preview.setToolTip("Show the project video behind the timeline when a video exists")
        self.chk_video_preview.setChecked(getattr(parent, "video_preview_enabled", True))
        editor_layout.addWidget(self.chk_video_preview)
        
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

        self.chk_60ms_delay = QCheckBox("60ms Delay")
        self.chk_60ms_delay.setToolTip(
            "All of UNBEATABLE's default charts are made with a -60 ms delay.\n"
            "If you enable this option, the editor will also use a -60 ms delay,\n"
            "giving you parity with the base charts. However, for the charts to stay\n"
            "synchronized, you also have to offset your in-game chart offset by -60 ms.\n\n"
            "If a chart you loaded is noticeably desynchronized, switching this option\n"
            "may fix it."
        )
        self.chk_60ms_delay.setChecked(getattr(parent, 'delay_60ms_enabled', False))
        editor_layout.addWidget(self.chk_60ms_delay)

        self.chk_use_original_audio = QCheckBox("Use Original Audio")
        self.chk_use_original_audio.setToolTip(
            "CBM normally converts imported audio to a resource-efficient and compatible .mp3 format.\n"
            "When enabled, the original audio file is copied into the project without conversion."
        )
        self.chk_use_original_audio.setChecked(getattr(parent, 'use_original_audio', False))
        editor_layout.addWidget(self.chk_use_original_audio)

        if not MICROSOFT_STORE_BUILD:
            self.combo_update_channel = IgnoreWheelComboBox()
            self.combo_update_channel.setToolTip("Choose between official Stable and Preview updates")
            self.combo_update_channel.setView(SmoothListView(self.combo_update_channel))
            self.combo_update_channel.addItems(["Stable", "Preview"])
            self.combo_update_channel.setCurrentText(getattr(parent, "update_channel", "Stable"))
            self.combo_update_channel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            editor_layout.addWidget(QLabel("Update Channel:"))
            self.combo_update_channel.currentTextChanged.connect(parent.on_update_channel_selected)
            editor_layout.addWidget(self.combo_update_channel)
        
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
        
        self.bg_drop_label = FileDropLabel(
            "Drag image here to add background",
            dialog_title="Select Background",
            file_filter="Image Files (*.png *.jpg *.jpeg);;All Files (*)",
        )
        
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

        side_menu_opacity = getattr(parent, "side_menu_opacity", 97)
        side_menu_opacity_layout = QHBoxLayout()
        side_menu_opacity_layout.addWidget(QLabel("Side Menu Opacity:"))
        self.side_menu_opacity_slider = IgnoreWheelSlider(Qt.Orientation.Horizontal)
        self.side_menu_opacity_slider.setToolTip("Opacity of the timeline side menu")
        self.side_menu_opacity_slider.setRange(0, 100)
        self.side_menu_opacity_slider.setValue(side_menu_opacity)
        self.side_menu_opacity_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        side_menu_opacity_layout.addWidget(self.side_menu_opacity_slider)
        self.side_menu_opacity_label = QLabel(f"{side_menu_opacity}%")
        self.side_menu_opacity_label.setFixedWidth(50)
        side_menu_opacity_layout.addWidget(self.side_menu_opacity_label)
        
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
            self.side_menu_opacity_slider.setValue(97)
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
        editor_layout.addLayout(side_menu_opacity_layout)
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
        
        def on_ui_volume_changed(v):
            self.ui_label.setText(f"{v}%")
            self.update_parent_ui_volume(parent, v)
                
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

        def update_side_menu_opacity(v):
            self.side_menu_opacity_label.setText(f"{v}%")
            parent.side_menu_opacity = v
            if hasattr(parent, 'timeline') and hasattr(parent.timeline, 'side_panel'):
                parent.timeline.side_panel.set_sidebar_opacity(v)
        
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
                if hasattr(parent, 'video_configuration_window') and parent.video_configuration_window:
                    parent.video_configuration_window.setStyleSheet(parent.styleSheet())
                if hasattr(parent, 'start_screen') and parent.start_screen:
                    parent.start_screen.update_theme()
                if hasattr(parent, 'update_ui_state'):
                    parent.update_ui_state()
                if hasattr(parent, 'timeline') and hasattr(parent.timeline, 'side_panel'):
                    parent.timeline.side_panel.update_style()
                if hasattr(parent, 'sidebar_vis') and parent.sidebar_vis:
                    parent.sidebar_vis.update()
                parent.update()
                for button in self.findChildren(ColorPickerButton):
                    button.update_appearance()

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

        def reset_ui_brightness():
            if hasattr(self, '_brightness_timer'):
                self._brightness_timer.stop()
                self._brightness_timer.deleteLater()
                del self._brightness_timer
            _apply_brightness(60)
        
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
                    parent.sidebar_vis.update()
        self.ui_bg_opacity_slider.valueChanged.connect(update_ui_bg_opacity)
        self.visualizer_opacity_slider.valueChanged.connect(update_visualizer_opacity)
        self.side_menu_opacity_slider.valueChanged.connect(update_side_menu_opacity)
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

        dynamic_combo_width = max(132, int(round(264 * current_scale)))
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
            "toggle_video_preview": "Toggle Video Preview",
            "grid_half": "Halve Grid",
            "grid_double": "Double Grid",
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
            "grid_half": "Halve the current grid value when the result is a whole number within the allowed range",
            "grid_double": "Double the current grid value within the allowed range",
            "toggle_metronome": "Toggle Metronome on or off",
            "toggle_video_preview": "Toggle project video playback in the timeline",
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

        for k in ["play_pause", "jump_start", "jump_end", "switch_meta_timing", "timeline_left", "timeline_right", "smooth_placement", "triplet_toggle", "grid_half", "grid_double", "toggle_metronome", "toggle_video_preview", "tab_note", "tab_brawl", "tab_event"]:
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

        custom_notes_group = QGroupBox("Custom Notes")
        custom_notes_group.setStyleSheet(self.get_group_style())
        custom_notes_layout = QVBoxLayout()
        custom_notes_layout.setContentsMargins(10, 5, 10, 10)
        self.chk_custom_notes = QCheckBox("Enable Custom Note Placement")
        self.chk_custom_notes.setChecked(bool(custom_notes_enabled))
        custom_notes_layout.addWidget(self.chk_custom_notes)
        manage_custom_notes = QPushButton("Manage Custom Notes")
        manage_custom_notes.clicked.connect(self.open_custom_notes)
        custom_notes_layout.addWidget(manage_custom_notes)
        custom_notes_group.setLayout(custom_notes_layout)
        content_layout.addWidget(custom_notes_group)

        info_group = QGroupBox("Information")
        info_group.setStyleSheet(self.get_group_style())
        info_layout = QVBoxLayout()

        edition_text = " -PREVIEW-" if PREVIEW_VERSION else ""
        version_label = QLabel(f"Version: {VERSION_NUMBER}{edition_text}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(version_label)
        
        legal_btn = QPushButton("Legal Information")
        legal_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        legal_btn.clicked.connect(self.show_legal_info)
        info_layout.addWidget(legal_btn)

        if not MICROSOFT_STORE_BUILD:
            self.search_update_btn = QPushButton("Search for Update")
            self.search_update_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.search_update_btn.clicked.connect(self.search_for_update)
            info_layout.addWidget(self.search_update_btn)
            self.search_update_last_checked_label = QLabel("Last checked: Never")
            self.search_update_last_checked_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info_layout.addWidget(self.search_update_last_checked_label)
            self.search_update_timer = QTimer(self)
            self.search_update_timer.setSingleShot(True)
            self.search_update_timer.timeout.connect(self.update_search_update_button)
            self.update_search_update_button()

        if not MICROSOFT_STORE_BUILD and (sys.platform.startswith("win") or sys.platform.startswith("linux")):
            run_setup_btn = QPushButton("Run Setup")
            run_setup_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            def run_setup():
                parent_window = self.parent_window
                self.reject()
                QTimer.singleShot(0, parent_window.restart_for_setup)
            run_setup_btn.clicked.connect(run_setup)
            info_layout.addWidget(run_setup_btn)

        self.get_backgrounds_btn = QPushButton("Get Backgrounds")
        self.get_backgrounds_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.get_backgrounds_btn.clicked.connect(parent.start_background_download)
        worker = getattr(parent, "background_download_worker", None)
        self.get_backgrounds_btn.setEnabled(not (worker is not None and worker.isRunning()))
        info_layout.addWidget(self.get_backgrounds_btn)
        
        info_group.setLayout(info_layout)
        content_layout.addWidget(info_group)
        self.setting_groups = [
            audio_group,
            editor_group,
            color_group,
            sound_group,
            keybinds_group,
            custom_notes_group,
            info_group,
        ]

        tabs_area.setWidget(content_widget)
        main_layout.addWidget(tabs_area)
        
        self.set_double_click_reset(self.master_slider, 100, master_layout.itemAt(0).widget(), self.master_label)
        self.set_double_click_reset(self.music_slider, 100, music_layout.itemAt(0).widget(), self.music_label)
        self.set_double_click_reset(self.fx_slider, 100, fx_layout.itemAt(0).widget(), self.fx_label)
        self.set_double_click_reset(self.ui_slider, 100, ui_layout.itemAt(0).widget(), self.ui_label)
        self.set_double_click_reset(self.chk_mute_events, False)
        self.set_double_click_reset(self.chk_use_original_audio, False)

        self.set_double_click_reset(self.slider_playback_pos, 150, playback_layout.itemAt(0).widget(), self.lbl_playback_pos)
        self.set_double_click_reset(self.scale_slider, 100, scale_layout.itemAt(0).widget(), self.lbl_scale)
        self.set_double_click_reset(self.chk_3d_sound, True)
        self.set_double_click_reset(self.chk_rpc, True)
        self.set_double_click_reset(self.chk_visualizer, True)
        self.set_double_click_reset(self.chk_video_preview, True)
        self.set_double_click_reset(self.chk_beatflash, True)
        self.set_double_click_reset(self.chk_auto_save, False)
        self.set_double_click_reset(self.chk_backups, True)
        self.set_double_click_reset(self.chk_disable_hold_collisions, False)
        self.set_double_click_reset(self.chk_objects_follow_bpm_grid, True)
        self.set_double_click_reset(self.chk_60ms_delay, False)

        if not MICROSOFT_STORE_BUILD:
            self.set_double_click_reset(self.combo_update_channel, "Stable")
        self.set_double_click_reset(self.combo_event_order, "Before")
        self.set_double_click_reset(self.combo_file_ext, ".txt")
        self.set_double_click_reset(self.combo_bg, "None")

        self.set_double_click_reset(self.grid_thickness_slider, 2, grid_thickness_layout.itemAt(0).widget(), self.grid_thickness_label)
        self.set_double_click_reset(self.grid_opacity_slider, 50, grid_opacity_layout.itemAt(0).widget(), self.grid_opacity_label)
        self.set_double_click_reset(self.ui_brightness_slider, 60, ui_brightness_layout.itemAt(0).widget(), self.ui_brightness_label, reset_ui_brightness)
        self.set_double_click_reset(self.ui_bg_opacity_slider, 0, ui_bg_opacity_layout.itemAt(0).widget(), self.ui_bg_opacity_label)
        self.set_double_click_reset(self.ui_bg_blur_slider, 0, ui_bg_blur_layout.itemAt(0).widget(), self.ui_bg_blur_label)
        self.set_double_click_reset(self.visualizer_opacity_slider, 10, visualizer_opacity_layout.itemAt(0).widget(), self.visualizer_opacity_label)
        self.set_double_click_reset(self.side_menu_opacity_slider, 97, side_menu_opacity_layout.itemAt(0).widget(), self.side_menu_opacity_label)
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
        for label in (
            self.master_label,
            self.music_label,
            self.fx_label,
            self.ui_label,
            self.lbl_playback_pos,
            self.lbl_scale,
            self.grid_opacity_label,
            self.visualizer_opacity_label,
            self.side_menu_opacity_label,
            self.background_opacity_label,
            self.preview_bg_opacity_label,
            self.ui_bg_opacity_label,
            self.grid_thickness_label,
            self.ui_brightness_label,
            self.lane_opacity_label,
            self.background_blur_label,
            self.ui_bg_blur_label,
        ):
            label.setFixedWidth(max(25, int(round(50 * self.global_scale))))
        apply_layout_scale(self, self.global_scale)
        
    def set_double_click_reset(self, widget, default_val, extra_widgets=None, value_label=None, reset_callback=None):
        if not widget: return
        class ResetFilter(QObject):
            def __init__(self, target_widget, default, parent_dialog, callback):
                super().__init__(target_widget)
                self.target_widget = target_widget
                self.default = default
                self.parent_dialog = parent_dialog
                self.callback = callback

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

                    if self.callback:
                        self.callback()
                    
                    if hasattr(self.parent_dialog, 'parent_window') and hasattr(self.parent_dialog.parent_window, 'play_ui_sound'):
                        self.parent_dialog.parent_window.play_ui_sound('UI Click')
                    return True
                return super().eventFilter(obj, event)

        filt = ResetFilter(widget, default_val, self, reset_callback)
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

                        scale = widget_global_scale(self.parent_dialog)
                        d.global_scale = scale
                        apply_layout_scale(d, scale)
                        d.setMinimumWidth(max(160, int(round(320 * scale))))

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
        text += "Video processing uses a minimal FFmpeg 8.1.2 build with x264, libvpx and dav1d under GPL-2.0-or-later.\n"
        text += "The Linux UI uses Microsoft Selawik, licensed under the SIL Open Font License 1.1.\n"
        text += "Contact: Discord @splash029"
        
        lbl = QLabel(text)
        scale = widget_global_scale(self)
        d.global_scale = scale
        lbl.setFixedWidth(max(225, int(round(450 * scale))))
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        
        ok_btn = QPushButton("OK")
        ok_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ok_btn.clicked.connect(d.accept)
        layout.addWidget(ok_btn)
        
        d.setLayout(layout)
        apply_layout_scale(d, scale)
        d.adjustSize()
        d.setFixedSize(d.sizeHint())
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
            if hasattr(main_ed.timeline, 'side_panel'):
                main_ed.timeline.side_panel.update_style()
            main_ed.timeline.update()

        self.setStyleSheet(get_scaled_stylesheet(BASE_WINDOW_STYLESHEET, scale, bright))
        if hasattr(main_ed, 'video_configuration_window') and main_ed.video_configuration_window:
            main_ed.video_configuration_window.setStyleSheet(main_ed.styleSheet())
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

    def open_custom_notes(self):
        dialog = CustomNotesDialog(self.custom_notes, self.custom_note_tombstones, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.custom_notes = dialog.notes
            self.custom_note_tombstones = dialog.tombstones
            self.custom_hitsounds_changed = True
            self.custom_hitsound_files_to_remove.update(dialog.removed_custom_hitsound_files)
            self.custom_hitsound_files_to_remove.difference_update(dialog.custom_hitsound_files(self.custom_notes))
            self.created_custom_hitsound_files.update(dialog.created_custom_hitsound_files)

    def get_custom_notes_enabled(self):
        return self.chk_custom_notes.isChecked()

    def get_custom_notes(self):
        return copy.deepcopy(self.custom_notes)

    def get_custom_note_tombstones(self):
        return copy.deepcopy(self.custom_note_tombstones)

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

    def get_60ms_delay(self):
        return self.chk_60ms_delay.isChecked()

    def get_use_original_audio(self):
        return self.chk_use_original_audio.isChecked()

    def get_update_channel(self):
        combo = getattr(self, "combo_update_channel", None)
        return combo.currentText() if combo is not None else "Stable"

    def get_video_preview_enabled(self):
        return self.chk_video_preview.isChecked()
        
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

    def get_side_menu_opacity(self):
        return self.side_menu_opacity_slider.value()
    
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
        resource_directory = Path(self.game_root) / "ChartEditorResources"
        for filename in self.custom_hitsound_files_to_remove:
            target = resource_directory / filename
            try:
                if target.is_file():
                    target.unlink()
            except OSError:
                pass
        super().accept()

    def reject(self):
        resource_directory = Path(self.game_root) / "ChartEditorResources"
        for filename in self.created_custom_hitsound_files:
            target = resource_directory / filename
            try:
                if target.is_file():
                    target.unlink()
            except OSError:
                pass
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
