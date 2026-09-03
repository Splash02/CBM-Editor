from .foundation import *
from . import foundation as foundation_module
import weakref
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QStyleOptionSlider

register_shared_globals(globals())

class OutputSuppressor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

ACTIVE_UI_ANIMATIONS = weakref.WeakSet()

def widget_ui_brightness(widget):
    current = widget
    while current is not None:
        if hasattr(current, "ui_brightness"):
            return max(0, min(255, int(current.ui_brightness)))
        current = current.parentWidget()
    return 60

def activate_ui_animation(target):
    ACTIVE_UI_ANIMATIONS.add(target)

def update_ui_animations():
    if not ACTIVE_UI_ANIMATIONS:
        return
    now = time.perf_counter()
    for target in tuple(ACTIVE_UI_ANIMATIONS):
        try:
            if not target.advance_ui_animation(now):
                ACTIVE_UI_ANIMATIONS.discard(target)
        except RuntimeError:
            ACTIVE_UI_ANIMATIONS.discard(target)

_QtPushButton = QPushButton
_QtCheckBox = QCheckBox
_QtSlider = QSlider
_QtComboBox = QComboBox

class AnimatedPushButton(_QtPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._action_last_frame = time.perf_counter()
        self._action_pulse = 0.0
        self._hover_progress = 0.0
        self._hover_target = 0.0
        self.clicked.connect(self.trigger_action_pulse)

    def trigger_action_pulse(self):
        self._action_pulse = 1.0
        self._action_last_frame = time.perf_counter()
        activate_ui_animation(self)

    def advance_ui_animation(self, now):
        dt = min(0.05, max(0.0, now - self._action_last_frame))
        self._action_last_frame = now
        self._action_pulse = max(0.0, self._action_pulse - dt / 0.16)
        hover_step = dt / 0.12
        if self._hover_progress < self._hover_target:
            self._hover_progress = min(self._hover_target, self._hover_progress + hover_step)
        elif self._hover_progress > self._hover_target:
            self._hover_progress = max(self._hover_target, self._hover_progress - hover_step)
        self.update()
        return self._action_pulse > 0.001 or abs(self._hover_progress - self._hover_target) > 0.001

    def enterEvent(self, event):
        if self.isEnabled():
            self._hover_target = 1.0
            self._action_last_frame = time.perf_counter()
            activate_ui_animation(self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_target = 0.0
        self._action_last_frame = time.perf_counter()
        activate_ui_animation(self)
        super().leaveEvent(event)

    def paintEvent(self, event):
        stable_pressed_label = bool(self.property("stable_pressed_label"))
        button_option = QStyleOptionButton()
        self.initStyleOption(button_option)
        button_option.state &= ~QStyle.StateFlag.State_MouseOver
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.style().drawControl(QStyle.ControlElement.CE_PushButtonBevel, button_option, painter, self)
        overlay_strength = (
            min(1.0, self._hover_progress * 0.16 + self._action_pulse * 0.62)
            if self.isEnabled()
            else 0.0
        )
        if overlay_strength > 0.001:
            overlay = QColor(255, 255, 255)
            overlay.setAlpha(int(round(255 * overlay_strength)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(overlay)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -4), 5, 5)
        label_option = QStyleOptionButton(button_option)
        if stable_pressed_label:
            label_option.state &= ~QStyle.StateFlag.State_Sunken
            label_option.state |= QStyle.StateFlag.State_Raised
        label_offset_x = int(self.property("stable_label_offset_x") or 0)
        if label_offset_x:
            label_option.rect.translate(label_offset_x, 0)
        if not self.isDown():
            label_option.rect.translate(0, -1)
        self.style().drawControl(QStyle.ControlElement.CE_PushButtonLabel, label_option, painter, self)
        painter.end()

foundation_module.ANIMATED_PUSH_BUTTON_CLASS = AnimatedPushButton

_FoundationColorPickerButton = ColorPickerButton

class ColorPickerButton(_FoundationColorPickerButton, AnimatedPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setProperty("stable_pressed_label", True)
        self.setProperty("stable_label_offset_x", 12)

QPushButton = AnimatedPushButton
QCheckBox = _QtCheckBox
QSlider = _QtSlider


class CleanSpinBox(QSpinBox):
    def wheelEvent(self, e: QWheelEvent):
        super().wheelEvent(e)
        self.lineEdit().deselect()
    def contextMenuEvent(self, e):
        pass

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



class HoverButton(QPushButton):
    def __init__(self, text, hover_cb=None, parent=None):
        super().__init__(text, parent)
        self.hover_cb = hover_cb
        self.setMouseTracking(True)
    def enterEvent(self, e):
        if self.hover_cb: self.hover_cb()
        super().enterEvent(e)

class _SaveToastEntry(QLabel):
    def __init__(self, parent, owner, created_at, text, duration, background_color=None, on_click=None, persistent=False, closable=False, key=None, on_close=None, reserve_text=None):
        super().__init__(text, parent)
        self.owner = owner
        self.created_at = created_at
        self.persistent = bool(persistent)
        self.closable = bool(closable)
        self.close_enabled = bool(closable)
        self.close_visibility_progress = 1.0 if closable else 0.0
        self.close_visibility_target = self.close_visibility_progress
        self.key = key
        self.duration = max(0.5, float(duration if duration is not None else 1.6))
        self.hide_at = math.inf if self.persistent else created_at + self.duration
        self.on_click = on_click
        self.on_close = on_close
        self.reserve_text = str(reserve_text) if reserve_text else None
        self.current_x = float(parent.width() + 24)
        self.current_y = 4.0
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.exiting = False
        self.dragging = False
        self.drag_started = False
        self.drag_start_global = QPointF()
        self.drag_offset_x = 0.0
        self.drag_offset_y = 0.0
        self.close_hover_progress = 0.0
        self.close_hover_target = 0.0
        self.close_pressed = False
        self.progress_value = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        if self.on_click:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_background_color(background_color)
        self.apply_scale()

    def set_background_color(self, background_color=None):
        if background_color:
            surface_color = QColor(background_color)
            depth_color = surface_color.darker(130)
            luminance = 0.299 * surface_color.red() + 0.587 * surface_color.green() + 0.114 * surface_color.blue()
            text_color = "#111111" if luminance >= 170 else "#FFFFFF"
        else:
            brightness = widget_ui_brightness(self)
            surface = min(255, brightness + 12)
            depth = max(0, surface - int(20 + surface / 10))
            surface_color = QColor(surface, surface, surface)
            depth_color = QColor(depth, depth, depth)
            text_color = "#111111" if surface >= 170 else UI_THEME["text_primary"]
        self.toast_text_color = QColor(text_color)
        self.toast_progress_color = surface_color.lighter(145)
        self.toast_surface_color = surface_color
        self.toast_depth_color = depth_color
        self.toast_text_color_name = text_color
        if hasattr(self, "progress_value"):
            self.apply_scale()
            self.update()

    def apply_scale(self):
        scale = max(0.5, float(getattr(self.parent(), "global_scale", 1.0)))
        top_bottom_padding = max(1, int(round(10 * scale)))
        left_padding = max(1, int(round(24 * scale)))
        right_padding = max(1, int(round((46 if self.closable else 24) * scale)))
        font_size = max(1, int(round(11 * scale)))
        depth_height = max(1, int(round(5 * scale)))
        self.setStyleSheet(
            f"background-color: transparent; color: {self.toast_text_color_name}; border: none; "
            f"padding: {top_bottom_padding}px {right_padding}px {top_bottom_padding + depth_height}px {left_padding}px; "
            f"font-size: {font_size}pt; font-weight: 700;"
        )
        font = QFont(self.font())
        font.setPointSize(font_size)
        font.setBold(True)
        self.setFont(font)
        self.adjustSize()
        reserve_width = 0
        if self.reserve_text:
            reserve_width = QFontMetrics(self.font()).horizontalAdvance(self.reserve_text) + left_padding + right_padding
        target_width = max(int(round(270 * scale)), reserve_width, self.sizeHint().width())
        self.setMinimumWidth(target_width)
        self.setFixedHeight(max(1, int(round(58 * scale))))
        self.resize(target_width, self.height())

    def close_button_rect(self):
        scale = max(0.5, float(getattr(self.parent(), "global_scale", 1.0)))
        size = max(22, int(round(27 * scale)))
        margin = max(2, int(round(3 * scale)))
        return QRectF(self.width() - margin - size, margin, size, size)

    def paintEvent(self, event):
        scale = max(0.5, float(getattr(self.parent(), "global_scale", 1.0)))
        depth_height = max(1, int(round(5 * scale)))
        toast_radius = max(1, int(round(8 * scale)))
        toast_shape = QPainterPath()
        toast_shape.addRoundedRect(QRectF(self.rect()), toast_radius, toast_radius)
        background_painter = QPainter(self)
        background_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background_painter.setPen(Qt.PenStyle.NoPen)
        background_painter.setBrush(self.toast_depth_color)
        background_painter.drawPath(toast_shape)
        background_painter.save()
        background_painter.setClipRect(QRectF(0, 0, self.width(), self.height() - depth_height))
        background_painter.setBrush(self.toast_surface_color)
        background_painter.drawPath(toast_shape)
        background_painter.restore()
        background_painter.end()
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.progress_value is not None:
            ratio = max(0.0, min(1.0, float(self.progress_value) / 100.0))
            progress_height = depth_height
            progress_rect = QRectF(0, self.height() - depth_height, self.width() * ratio, progress_height)
            painter.save()
            painter.setClipPath(toast_shape)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.toast_progress_color)
            progress_radius = min(progress_height / 2.0, progress_rect.width() / 2.0)
            painter.drawRoundedRect(progress_rect, progress_radius, progress_radius)
            painter.restore()
        visibility = max(0.0, min(1.0, self.close_visibility_progress))
        if not self.closable or visibility <= 0.001:
            painter.end()
            return
        rect = self.close_button_rect()
        hover = max(0.0, min(1.0, self.close_hover_progress))
        if hover > 0.001:
            surface = QColor(self.toast_text_color)
            surface.setAlpha(int(round(38 * hover * visibility)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(surface)
            painter.drawRoundedRect(rect, 4, 4)
        color = QColor(self.toast_text_color)
        color.setAlpha(int(round((185 + 70 * hover) * visibility)))
        scale = max(0.5, float(getattr(self.parent(), "global_scale", 1.0)))
        pen = QPen(color, max(1.5, 1.7 * scale))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        inset = rect.width() * 0.32
        painter.drawLine(rect.topLeft() + QPointF(inset, inset), rect.bottomRight() - QPointF(inset, inset))
        painter.drawLine(QPointF(rect.right() - inset, rect.top() + inset), QPointF(rect.left() + inset, rect.bottom() - inset))
        painter.end()

    def advance_close_animation(self, dt):
        previous_hover = self.close_hover_progress
        previous_visibility = self.close_visibility_progress
        step = min(1.0, dt / 0.10)
        self.close_hover_progress += (self.close_hover_target - self.close_hover_progress) * step
        visibility_step = min(1.0, dt / 0.16)
        self.close_visibility_progress += (self.close_visibility_target - self.close_visibility_progress) * visibility_step
        if abs(self.close_hover_progress - previous_hover) > 0.001 or abs(self.close_visibility_progress - previous_visibility) > 0.001:
            self.update()

    def set_close_available(self, available):
        self.close_enabled = bool(available)
        self.close_visibility_target = 1.0 if available else 0.0
        if not available:
            self.close_pressed = False
            self.close_hover_target = 0.0
        activate_ui_animation(self.owner)
        self.update()

    def set_progress(self, value):
        self.progress_value = None if value is None else max(0, min(100, int(value)))
        self.update()

    def set_message(self, text):
        self.setText(str(text))
        self.update()

    def set_action(self, callback):
        self.on_click = callback
        cursor = Qt.CursorShape.PointingHandCursor if callback else Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)

    def mousePressEvent(self, event):
        if self.close_enabled and event.button() == Qt.MouseButton.LeftButton and self.close_button_rect().contains(event.position()):
            self.close_pressed = True
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and not self.exiting:
            self.dragging = True
            self.drag_started = False
            self.raise_()
            self.drag_start_global = event.globalPosition()
            self.drag_offset_x = 0.0
            self.drag_offset_y = 0.0
            self.owner.last_frame = time.perf_counter()
            activate_ui_animation(self.owner)
            event.accept()
            return
        event.accept()

    def mouseMoveEvent(self, event):
        if self.closable:
            hovering_close = self.close_enabled and self.close_button_rect().contains(event.position())
            self.close_hover_target = 1.0 if hovering_close else 0.0
            cursor = Qt.CursorShape.PointingHandCursor if hovering_close or self.on_click else Qt.CursorShape.ArrowCursor
            self.setCursor(cursor)
            activate_ui_animation(self.owner)
        if self.dragging and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.globalPosition() - self.drag_start_global
            if abs(delta.x()) + abs(delta.y()) >= 5.0:
                self.drag_started = True
            if self.drag_started:
                self.drag_offset_x = delta.x() * 0.1
                self.drag_offset_y = delta.y() * 0.1
                activate_ui_animation(self.owner)
            event.accept()
            return
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.close_pressed:
            self.close_pressed = False
            if self.close_button_rect().contains(event.position()):
                self.close_enabled = False
                self.exiting = True
                self.dragging = False
                if self.on_close:
                    self.on_close()
                activate_ui_animation(self.owner)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.dragging:
            self.dragging = False
            if self.drag_started:
                self.hide_at = math.inf if self.persistent else time.perf_counter() + self.duration
            elif self.on_click:
                self.on_click()
                if not self.persistent:
                    self.exiting = True
            self.drag_offset_x = 0.0
            self.drag_offset_y = 0.0
            activate_ui_animation(self.owner)
            event.accept()
            return
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    def leaveEvent(self, event):
        self.close_hover_target = 0.0
        self.close_pressed = False
        activate_ui_animation(self.owner)
        super().leaveEvent(event)


class SaveToast(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.entries = []
        self.last_frame = time.perf_counter()

    def invalidate_region(self, rect):
        parent = self.parent()
        dirty = rect.adjusted(-2, -2, 2, 2)
        parent.update(dirty)
        targets = [getattr(parent, 'centralWidget', lambda: None)()]
        targets.extend([
            getattr(parent, 'timeline', None),
            getattr(parent, 'start_screen', None),
            getattr(parent, 'sidebar_vis', None),
        ])
        for target in targets:
            if target is None or not target.isVisible():
                continue
            local_top_left = target.mapFrom(parent, dirty.topLeft())
            target.update(QRect(local_top_left, dirty.size()))

    def show_message(self, text="Beatmap saved", duration=1.6, background_color=None, on_click=None, persistent=False, closable=False, key=None, on_close=None, reserve_text=None):
        now = time.perf_counter()
        if key is not None:
            for existing in self.entries:
                if existing.key == key and not existing.exiting:
                    existing.exiting = True
        entry = _SaveToastEntry(
            self.parent(),
            self,
            now,
            text,
            duration,
            background_color,
            on_click,
            persistent,
            closable,
            key,
            on_close,
            reserve_text,
        )
        entry.move(int(round(entry.current_x)), int(round(entry.current_y)))
        entry.show()
        entry.raise_()
        play_enter_sound = getattr(self.parent(), "play_toast_enter_sound", None)
        if callable(play_enter_sound):
            play_enter_sound()
        self.entries.insert(0, entry)
        self.last_frame = now
        activate_ui_animation(self)
        return entry

    def find_entry(self, key):
        for entry in self.entries:
            if entry.key == key and not entry.exiting:
                return entry
        return None

    def update_scale(self):
        for entry in self.entries:
            entry.apply_scale()
        self.last_frame = time.perf_counter()
        activate_ui_animation(self)

    def advance_ui_animation(self, now):
        if not self.entries:
            return False
        dt = min(0.05, max(0.0, now - self.last_frame))
        self.last_frame = now
        parent = self.parent()
        active_entries = [entry for entry in self.entries if not entry.exiting]
        for entry in active_entries:
            if now >= entry.hide_at and not entry.dragging:
                entry.exiting = True
                play_exit_sound = getattr(parent, "play_toast_exit_sound", None)
                if callable(play_exit_sound):
                    play_exit_sound()
        active_entries = [entry for entry in self.entries if not entry.exiting]
        active_index = {entry: index for index, entry in enumerate(active_entries)}
        top_margin = max(12, int(round(22 * getattr(parent, "global_scale", 1.0))))
        spacing = max(6, int(round(10 * getattr(parent, "global_scale", 1.0))))
        retained = []
        for entry in self.entries:
            entry.advance_close_animation(dt)
            old_geometry = entry.geometry()
            if entry.exiting:
                target_x = float(parent.width() + entry.width() + 24)
                target_y = entry.current_y
            else:
                target_x = float(max(12, parent.width() - entry.width() - 24)) + entry.drag_offset_x
                target_y = float(top_margin + active_index[entry] * (entry.height() + spacing)) + entry.drag_offset_y
            entry.velocity_x += (target_x - entry.current_x) * 250.0 * dt
            entry.velocity_y += (target_y - entry.current_y) * 250.0 * dt
            damping = math.exp(-17.0 * dt)
            entry.velocity_x *= damping
            entry.velocity_y *= damping
            entry.current_x += entry.velocity_x * dt
            entry.current_y += entry.velocity_y * dt
            entry.move(int(round(entry.current_x)), int(round(entry.current_y)))
            self.invalidate_region(old_geometry.united(entry.geometry()))
            entry.raise_()
            outside = (
                entry.current_x + entry.width() < -8
                or entry.current_x > parent.width() + 8
                or entry.current_y + entry.height() < -8
                or entry.current_y > parent.height() + 8
            )
            if entry.exiting and outside:
                self.invalidate_region(entry.geometry())
                entry.hide()
                entry.deleteLater()
            else:
                retained.append(entry)
        for entry in retained:
            if entry.dragging:
                entry.raise_()
        self.entries = retained
        return bool(self.entries)

class CleanDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, e: QWheelEvent):
        super().wheelEvent(e)
        self.lineEdit().deselect()
    def contextMenuEvent(self, e):
        pass

class TimerScrollBar(QScrollBar):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.text = ""
        self.direct_dragging = False

    def pointer_value(self, event):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_ScrollBar,
            option,
            QStyle.SubControl.SC_ScrollBarGroove,
            self,
        )
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_ScrollBar,
            option,
            QStyle.SubControl.SC_ScrollBarSlider,
            self,
        )
        if self.orientation() == Qt.Orientation.Horizontal:
            slider_min = groove.left()
            slider_max = groove.right() - handle.width() + 1
            position = int(round(event.position().x() - handle.width() / 2.0)) - slider_min
        else:
            slider_min = groove.top()
            slider_max = groove.bottom() - handle.height() + 1
            position = int(round(event.position().y() - handle.height() / 2.0)) - slider_min
        span = max(1, slider_max - slider_min)
        position = max(0, min(span, position))
        return QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            position,
            span,
            option.upsideDown,
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.direct_dragging = True
            self.setSliderDown(True)
            self.setValue(self.pointer_value(event))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.direct_dragging and event.buttons() & Qt.MouseButton.LeftButton:
            self.setValue(self.pointer_value(event))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.direct_dragging and event.button() == Qt.MouseButton.LeftButton:
            self.direct_dragging = False
            self.setSliderDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        
    def paintEvent(self, e):
        super().paintEvent(e)
        if self.text:
            p = QPainter(self)
            b = getattr(self.window(), 'ui_brightness', 60)
            if b > 127:
                p.setPen(QColor(0, 0, 0))
            else:
                p.setPen(QColor(255, 255, 255))
            font = p.font()
            p.setFont(font)
            p.drawText(self.rect().adjusted(0, -1, 0, -1), Qt.AlignmentFlag.AlignCenter, self.text)

class CustomTooltipLabel(QLabel):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._animation_value = 0.0
        self._animation_start = 0.0
        self._animation_target = 0.0
        self._animation_started = time.perf_counter()
        self._animation_position = QPoint()
        self.update_style()

    def begin_show(self, position):
        self._animation_position = QPoint(position)
        self._animation_start = self._animation_value
        self._animation_target = 1.0
        self._animation_started = time.perf_counter()
        self.setWindowOpacity(max(0.0, min(1.0, self._animation_value)))
        self.move(self._animation_position + QPoint(0, int(round(4.0 * (1.0 - self._animation_value)))))
        self.show()
        activate_ui_animation(self)

    def begin_hide(self):
        if not self.isVisible():
            return
        self._animation_start = self._animation_value
        self._animation_target = 0.0
        self._animation_started = time.perf_counter()
        activate_ui_animation(self)

    def advance_ui_animation(self, now):
        duration = 0.11 if self._animation_target > self._animation_start else 0.075
        linear = min(1.0, max(0.0, (now - self._animation_started) / duration))
        eased = 1.0 - math.pow(1.0 - linear, 3.0)
        self._animation_value = self._animation_start + (self._animation_target - self._animation_start) * eased
        self.setWindowOpacity(max(0.0, min(1.0, self._animation_value)))
        self.move(self._animation_position + QPoint(0, int(round(4.0 * (1.0 - self._animation_value)))))
        if linear >= 1.0 and self._animation_target <= 0.0:
            self.hide()
        return linear < 1.0

    def update_style(self):
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {UI_THEME["button_bg"]};
                color: {UI_THEME["text_primary"]};
                border: none;
                border-radius: 0px;
                padding: 5px 8px;
                font-size: 12px;
                font-family: 'Segoe UI', 'Selawik', sans-serif;
            }}
        """)

class CustomTooltipManager(QObject):
    def __init__(self):
        super().__init__()
        self.tooltip = CustomTooltipLabel()
        self.current_widget = None
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.show_tooltip)
        
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(50)
        self.hide_timer.timeout.connect(self.do_hide_tooltip)
        
        self.is_hot = False

    def eventFilter(self, obj, event):
        if isinstance(obj, QWidget):
            evt_type = event.type()
            if evt_type == QEvent.Type.ToolTip:
                return True
            if evt_type == QEvent.Type.Enter:
                if QApplication.instance().property("disable_tooltips"):
                    return False
                tip = obj.toolTip()
                if tip:
                    self.current_widget = obj
                    self.hide_timer.stop()
                    if self.tooltip.isVisible() or self.is_hot:
                        self.show_tooltip()
                    else:
                        self.timer.start()
            elif evt_type == QEvent.Type.Leave:
                if self.current_widget == obj:
                    self.hide_timer.start()
            elif evt_type == QEvent.Type.MouseMove:
                if self.current_widget == obj:
                    tip = obj.toolTip()
                    if tip and not self.tooltip.isVisible():
                        if not self.timer.isActive():
                            self.timer.start()
            elif evt_type in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel, QEvent.Type.KeyPress, QEvent.Type.Hide):
                self.hide_timer.stop()
                self.do_hide_tooltip()
        return False
        
    def show_tooltip(self):
        if self.current_widget and getattr(self.current_widget, 'isVisible', lambda: False)():
            tip = self.current_widget.toolTip()
            if tip:
                self.tooltip.update_style()
                self.tooltip.setText(tip)
                self.tooltip.adjustSize()
                from PyQt6.QtGui import QCursor
                pos = QCursor.pos() + QPoint(15, 15)
                screen = QApplication.screenAt(pos)
                if screen:
                    geom = screen.availableGeometry()
                    if pos.x() + self.tooltip.width() > geom.right():
                        pos.setX(geom.right() - self.tooltip.width())
                    if pos.y() + self.tooltip.height() > geom.bottom():
                        pos.setY(pos.y() - self.tooltip.height() - 30)
                self.tooltip.begin_show(pos)
                self.is_hot = True

    def do_hide_tooltip(self):
        self.timer.stop()
        self.tooltip.begin_hide()
        self.current_widget = None
        self.is_hot = False

class FrameDrivenScrollTimer:
    def __init__(self, owner):
        self.owner = owner
        self.active = False

    def start(self):
        self.active = True
        activate_ui_animation(self.owner)

    def stop(self):
        self.active = False

    def isActive(self):
        return self.active

class SmoothScrollMixin:
    def init_smooth_scroll(self):
        if hasattr(self, "setVerticalScrollMode"):
            self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        
        self.sc_target = 0.0
        self.sc_current = 0.0
        self.sc_added_overshoot_max = 0
        self.sc_added_overshoot_min = 0
        self.sc_last_time = time.time()
        
        self.sc_timer = FrameDrivenScrollTimer(self)

        self.sc_drag_targets = set()
        self.sc_drag_pressed = False
        self.sc_dragging = False
        self.sc_drag_velocity_x = 0.0
        self.sc_drag_velocity_y = 0.0
        self.sc_drag_float_x = 0.0
        self.sc_drag_float_y = 0.0
        
        sb = self.verticalScrollBar()
        if sb:
            self.sc_current = float(sb.value())
            self.sc_target = self.sc_current
            self.sc_ignore_value_change = False
            self.sc_last_native_value = sb.value()
            sb.valueChanged.connect(self.sc_handle_value_changed)
            sb.installEventFilter(self)

        self.sc_install_drag_target(self.viewport())

    def advance_ui_animation(self, now):
        if not self.sc_timer.isActive():
            return False
        self.sc_update_scroll()
        return self.sc_timer.isActive()

    def sc_install_drag_target(self, target):
        if target is not None and target not in self.sc_drag_targets:
            self.sc_drag_targets.add(target)
            if isinstance(target, (_QtPushButton, _QtCheckBox, _QtSlider, _QtComboBox)):
                target.setProperty("defer_scroll_control_click", True)
            target.installEventFilter(self)

    def sc_sound_owner(self, control):
        owner = control
        while owner is not None:
            if hasattr(owner, "play_ui_sound"):
                return owner
            owner = owner.parentWidget()
        return None

    def sc_play_confirmed_control_sound(self, control, previous_checked=None):
        owner = self.sc_sound_owner(control)
        if owner is None:
            return
        pan = owner.get_pan_for_widget(control) if hasattr(owner, "get_pan_for_widget") else 0.0
        if isinstance(control, _QtCheckBox):
            if previous_checked is not None and control.isChecked() != previous_checked:
                owner.play_ui_sound("UI Tick On" if control.isChecked() else "UI Tick Off", pan)
        elif isinstance(control, (_QtPushButton, _QtComboBox)):
            if control is getattr(owner, "btn_play", None) or control.property("is_custom_sound_btn"):
                return
            owner.play_ui_sound("UI Click", pan)

    def sc_overshoot_distance(self, distance):
        return 72.0 * math.log1p(max(0.0, distance) / 72.0)

    def sc_raw_overshoot_distance(self, distance):
        return 72.0 * math.expm1(max(0.0, distance) / 72.0)

    def sc_resisted_position(self, position, real_min, real_max):
        if position < real_min:
            return real_min - self.sc_overshoot_distance(real_min - position)
        if position > real_max:
            return real_max + self.sc_overshoot_distance(position - real_max)
        return position

    def sc_raw_position(self, position, real_min, real_max):
        if position < real_min:
            return real_min - self.sc_raw_overshoot_distance(real_min - position)
        if position > real_max:
            return real_max + self.sc_raw_overshoot_distance(position - real_max)
        return position

    def sc_stop_drag_momentum(self):
        self.sc_drag_velocity_x = 0.0
        self.sc_drag_velocity_y = 0.0

    def sc_reset_to_native(self):
        sb = self.verticalScrollBar()
        if sb is None:
            return
        self.sc_timer.stop()
        self.sc_stop_drag_momentum()
        real_min = int(sb.minimum() + self.sc_added_overshoot_min)
        real_max = int(sb.maximum() - self.sc_added_overshoot_max)
        if real_max < real_min:
            real_min = sb.minimum()
            real_max = sb.maximum()
        value = max(real_min, min(real_max, sb.value()))
        self.sc_ignore_value_change = True
        sb.setRange(real_min, real_max)
        sb.setValue(value)
        self.sc_ignore_value_change = False
        self.sc_added_overshoot_min = 0
        self.sc_added_overshoot_max = 0
        self.sc_current = float(value)
        self.sc_target = float(value)
        self.sc_drag_float_y = float(value)
        self.sc_last_native_value = value
        self.sc_last_time = time.time()

    def sc_send_control_press(self, control):
        press_event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            self.sc_control_press_position,
            self.sc_control_press_global_position,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            self.sc_control_press_modifiers,
        )
        control.mousePressEvent(press_event)

    def sc_set_scroll_values(self, x_value, y_value, extend_vertical=False):
        horizontal = self.horizontalScrollBar()
        vertical = self.verticalScrollBar()
        self.sc_ignore_value_change = True
        if horizontal:
            clamped_x = max(float(horizontal.minimum()), min(float(horizontal.maximum()), float(x_value)))
            horizontal.setValue(int(round(clamped_x)))
            self.sc_drag_float_x = clamped_x
        if vertical:
            real_min = getattr(self, "sc_drag_real_min_y", float(vertical.minimum()))
            real_max = getattr(self, "sc_drag_real_max_y", float(vertical.maximum()))
            if extend_vertical:
                clamped_y = float(y_value)
                if clamped_y < real_min:
                    effective_min = int(math.floor(clamped_y))
                    vertical.setMinimum(effective_min)
                    self.sc_added_overshoot_min = int(round(real_min - effective_min))
                elif self.sc_added_overshoot_min > 0:
                    vertical.setMinimum(int(round(real_min)))
                    self.sc_added_overshoot_min = 0
                if clamped_y > real_max:
                    effective_max = int(math.ceil(clamped_y))
                    vertical.setMaximum(effective_max)
                    self.sc_added_overshoot_max = int(round(effective_max - real_max))
                elif self.sc_added_overshoot_max > 0:
                    vertical.setMaximum(int(round(real_max)))
                    self.sc_added_overshoot_max = 0
            else:
                clamped_y = max(float(vertical.minimum()), min(float(vertical.maximum()), float(y_value)))
            vertical.setValue(int(round(clamped_y)))
            self.sc_drag_float_y = clamped_y
            self.sc_current = self.sc_drag_float_y
            self.sc_target = self.sc_drag_float_y
            self.sc_last_native_value = vertical.value()
        self.sc_ignore_value_change = False

    def sc_set_drag_values(self, x_value, y_value):
        real_min = self.sc_drag_real_min_y
        real_max = self.sc_drag_real_max_y
        y_value = self.sc_resisted_position(y_value, real_min, real_max)
        self.sc_set_scroll_values(x_value, y_value, True)
        return self.sc_drag_float_x, self.sc_drag_float_y

    def wheelEvent(self, e: QWheelEvent):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            try:
                super().wheelEvent(e)
            except AttributeError:
                e.ignore()
            return

        delta = e.angleDelta().y()
        if delta == 0:
            return
            
        sb = self.verticalScrollBar()
        if not sb: return
        
        if sb.maximum() == sb.minimum():
            e.ignore()
            return

        self.sc_stop_drag_momentum()

        if not self.sc_timer.isActive():
            self.sc_current = float(sb.value())
            self.sc_target = self.sc_current
            self.sc_last_time = time.time()
            self.sc_timer.start()

        real_min = float(sb.minimum() + self.sc_added_overshoot_min)
        real_max = float(sb.maximum() - self.sc_added_overshoot_max)
        raw_target = self.sc_raw_position(self.sc_target, real_min, real_max)
        raw_target += -120.0 if delta > 0 else 120.0
        self.sc_target = self.sc_resisted_position(raw_target, real_min, real_max)
        
        e.accept()

    def sc_update_scroll(self):
        sb = self.verticalScrollBar()
        if not sb:
            self.sc_timer.stop()
            return

        self.sc_ignore_value_change = True

        current_time = time.time()
        dt = current_time - self.sc_last_time
        self.sc_last_time = current_time
        
        dt = min(dt, 0.1)
        
        reference_dt = 1.0 / 60.0
        dt_factor = dt / reference_dt

        curr_max = sb.maximum()
        real_max = curr_max - self.sc_added_overshoot_max
        if real_max < 0:
             real_max = curr_max
             self.sc_added_overshoot_max = 0
             
        curr_min = sb.minimum()
        if curr_min < 0:
             real_min = curr_min + self.sc_added_overshoot_min
        else:
             real_min = curr_min
             self.sc_added_overshoot_min = 0

        spring_target = self.sc_target
        if self.sc_target < real_min:
             spring_target = real_min
        elif self.sc_target > real_max:
             spring_target = real_max
        
        spring_alpha = 1.0 - math.pow(0.9, dt_factor)
        if self.sc_target < real_min:
            diff = real_min - self.sc_target
            self.sc_target += diff * spring_alpha
            if abs(self.sc_target - real_min) < 1.0: self.sc_target = real_min
        elif self.sc_target > real_max:
            diff = self.sc_target - real_max
            self.sc_target -= diff * spring_alpha
            if abs(self.sc_target - real_max) < 1.0: self.sc_target = real_max

        diff = self.sc_target - self.sc_current
        
        if abs(diff) < 1.0 and abs(self.sc_target - spring_target) < 1.0:
            self.sc_current = self.sc_target
            self.sc_timer.stop()
            
            if self.sc_added_overshoot_max > 0:
                sb.setMaximum(real_max)
                self.sc_added_overshoot_max = 0
            
            if self.sc_added_overshoot_min > 0:
                sb.setMinimum(real_min)
                self.sc_added_overshoot_min = 0

            sb.setValue(int(self.sc_current))
            self.sc_ignore_value_change = False
        else:
            lerp_alpha = 1.0 - math.pow(0.82, dt_factor)
            self.sc_current += diff * lerp_alpha
            
            val_to_set = int(self.sc_current)
            
            if self.sc_current > real_max:
                overshoot = self.sc_current - real_max
                effective_max = real_max + int(overshoot)
                if effective_max != sb.maximum():
                     sb.setMaximum(effective_max)
                     self.sc_added_overshoot_max = int(overshoot)
                val_to_set = effective_max
            elif self.sc_added_overshoot_max > 0:
                sb.setMaximum(real_max)
                self.sc_added_overshoot_max = 0
            
            if self.sc_current < real_min:
                overshoot = real_min - self.sc_current
                effective_min = real_min - int(overshoot)
                if sb.minimum() != effective_min:
                     sb.setMinimum(effective_min)
                     self.sc_added_overshoot_min = int(overshoot)
                val_to_set = effective_min
            elif self.sc_added_overshoot_min > 0:
                sb.setMinimum(real_min)
                self.sc_added_overshoot_min = 0

            sb.setValue(val_to_set)
            self.sc_ignore_value_change = False

    def sc_handle_value_changed(self, value):
        if getattr(self, "sc_ignore_value_change", False):
            return

        last_val = getattr(self, "sc_last_native_value", value)
        delta = value - last_val
        self.sc_last_native_value = value

        self.sc_target += delta
        self.sc_current += delta

        if not self.sc_timer.isActive():
            self.sc_target = float(value)
            self.sc_current = float(value)

    def eventFilter(self, obj, event):
        try:
            if obj in getattr(self, "sc_drag_targets", ()):
                event_type = event.type()
                if isinstance(obj, _QtSlider) and getattr(self, "sc_slider_delegated", False):
                    if event_type == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                        obj.mouseReleaseEvent(event)
                        obj.releaseMouse()
                        owner = self.sc_sound_owner(obj)
                        if owner is not None and hasattr(owner, "last_slider_val"):
                            owner.last_slider_val.pop(id(obj), None)
                        self.sc_slider_delegated = False
                        self.sc_drag_pressed = False
                        self.sc_dragging = False
                        event.accept()
                        return True
                    return False
                if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                    horizontal = self.horizontalScrollBar()
                    vertical = self.verticalScrollBar()
                    real_min = vertical.minimum() + self.sc_added_overshoot_min if vertical else 0
                    real_max = vertical.maximum() - self.sc_added_overshoot_max if vertical else 0
                    can_scroll_vertical = vertical is not None and vertical.isVisible() and real_max > real_min
                    if not can_scroll_vertical:
                        self.sc_drag_pressed = False
                        self.sc_dragging = False
                        return False
                    self.sc_timer.stop()
                    self.sc_stop_drag_momentum()
                    self.sc_drag_pressed = True
                    self.sc_dragging = False
                    self.sc_drag_press_pos = event.globalPosition()
                    self.sc_drag_last_time = time.perf_counter()
                    self.sc_drag_start_x = float(horizontal.value()) if horizontal else 0.0
                    self.sc_drag_start_y = float(vertical.value()) if vertical else 0.0
                    self.sc_current = self.sc_drag_start_y
                    self.sc_target = self.sc_drag_start_y
                    self.sc_drag_real_min_y = float(vertical.minimum() + self.sc_added_overshoot_min) if vertical else 0.0
                    self.sc_drag_real_max_y = float(vertical.maximum() - self.sc_added_overshoot_max) if vertical else 0.0
                    self.sc_drag_float_x = self.sc_drag_start_x
                    self.sc_drag_float_y = self.sc_drag_start_y
                    self.sc_drag_raw_start_y = self.sc_raw_position(
                        self.sc_drag_start_y,
                        self.sc_drag_real_min_y,
                        self.sc_drag_real_max_y,
                    )
                    self.sc_control_press_position = QPointF(event.position())
                    self.sc_control_press_global_position = QPointF(event.globalPosition())
                    self.sc_control_press_modifiers = event.modifiers()
                    if isinstance(obj, (_QtPushButton, _QtCheckBox, _QtSlider, _QtComboBox)):
                        if isinstance(obj, _QtSlider):
                            self.sc_slider_delegated = False
                        elif isinstance(obj, (_QtPushButton, _QtCheckBox)):
                            obj.setDown(True)
                        obj.grabMouse()
                        event.accept()
                        return True
                    if isinstance(self, QAbstractItemView) and obj is self.viewport():
                        obj.grabMouse()
                        event.accept()
                        return True
                elif event_type == QEvent.Type.MouseMove and self.sc_drag_pressed and event.buttons() & Qt.MouseButton.LeftButton:
                    position = event.globalPosition()
                    total_delta = position - self.sc_drag_press_pos
                    if not self.sc_dragging:
                        threshold = 3 if getattr(self, "sc_combo_popup", False) else QApplication.startDragDistance()
                        movement = abs(total_delta.y()) if getattr(self, "sc_combo_popup", False) else abs(total_delta.x()) + abs(total_delta.y())
                        if movement < threshold:
                            if isinstance(obj, (_QtPushButton, _QtCheckBox, _QtSlider, _QtComboBox)):
                                event.accept()
                                return True
                            if isinstance(self, QAbstractItemView) and obj is self.viewport():
                                event.accept()
                                return True
                            return False
                        if isinstance(obj, _QtSlider):
                            horizontal_movement = abs(total_delta.x())
                            vertical_movement = abs(total_delta.y())
                            if horizontal_movement >= threshold and vertical_movement <= horizontal_movement * 1.5:
                                self.sc_send_control_press(obj)
                                owner = self.sc_sound_owner(obj)
                                if owner is not None and hasattr(owner, "last_slider_val"):
                                    owner.last_slider_val[id(obj)] = obj.value()
                                self.sc_slider_delegated = True
                                self.sc_drag_pressed = False
                                return False
                            if vertical_movement <= horizontal_movement * 1.5:
                                event.accept()
                                return True
                        if isinstance(obj, (_QtPushButton, _QtCheckBox)):
                            obj.setDown(False)
                        self.sc_dragging = True
                    now = time.perf_counter()
                    dt = max(0.001, now - self.sc_drag_last_time)
                    previous_x = self.sc_drag_float_x
                    previous_y = self.sc_drag_float_y
                    current_x, current_y = self.sc_set_drag_values(
                        self.sc_drag_start_x - total_delta.x(),
                        self.sc_drag_raw_start_y - total_delta.y(),
                    )
                    instant_x = (current_x - previous_x) / dt
                    instant_y = (current_y - previous_y) / dt
                    self.sc_drag_velocity_x = self.sc_drag_velocity_x * 0.55 + instant_x * 0.45
                    self.sc_drag_velocity_y = self.sc_drag_velocity_y * 0.55 + instant_y * 0.45
                    self.sc_drag_last_time = now
                    event.accept()
                    return True
                elif event_type == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                    was_pressed = self.sc_drag_pressed
                    was_dragging = self.sc_dragging
                    self.sc_drag_pressed = False
                    self.sc_dragging = False
                    if was_dragging:
                        if isinstance(obj, (_QtPushButton, _QtCheckBox, _QtSlider, _QtComboBox)) or (
                            isinstance(self, QAbstractItemView) and obj is self.viewport()
                        ):
                            obj.releaseMouse()
                        now = time.perf_counter()
                        release_delay = max(0.0, now - self.sc_drag_last_time)
                        release_decay = math.exp(-12.0 * release_delay)
                        self.sc_drag_velocity_y *= release_decay
                        self.sc_drag_last_time = now
                        outside = self.sc_drag_float_y < self.sc_drag_real_min_y or self.sc_drag_float_y > self.sc_drag_real_max_y
                        if outside or abs(self.sc_drag_velocity_x) >= 8.0 or abs(self.sc_drag_velocity_y) >= 8.0:
                            raw_current = self.sc_raw_position(
                                self.sc_drag_float_y,
                                self.sc_drag_real_min_y,
                                self.sc_drag_real_max_y,
                            )
                            projected = raw_current + self.sc_drag_velocity_y * 0.34
                            self.sc_target = self.sc_resisted_position(
                                projected,
                                self.sc_drag_real_min_y,
                                self.sc_drag_real_max_y,
                            )
                            self.sc_current = self.sc_drag_float_y
                            self.sc_last_time = time.time()
                            self.sc_timer.start()
                        else:
                            self.sc_target = self.sc_drag_float_y
                            self.sc_current = self.sc_drag_float_y
                        event.accept()
                        return True
                    if isinstance(self, QAbstractItemView) and obj is self.viewport() and was_pressed:
                        obj.releaseMouse()
                        combo_owner_ref = getattr(self, "sc_combo_owner_ref", None)
                        combo_owner = combo_owner_ref() if combo_owner_ref is not None else None
                        if getattr(self, "sc_combo_popup", False) and combo_owner is not None:
                            model_index = self.indexAt(self.sc_control_press_position.toPoint())
                            if model_index.isValid() and model_index.flags() & Qt.ItemFlag.ItemIsEnabled:
                                row = model_index.row()
                                combo_owner.setCurrentIndex(row)
                                combo_owner.activated.emit(row)
                                combo_owner.textActivated.emit(combo_owner.itemText(row))
                                self.sc_play_confirmed_control_sound(combo_owner)
                                combo_owner.hidePopup()
                                event.accept()
                                return True
                        press_event = QMouseEvent(
                            QEvent.Type.MouseButtonPress,
                            self.sc_control_press_position,
                            self.sc_control_press_global_position,
                            Qt.MouseButton.LeftButton,
                            Qt.MouseButton.LeftButton,
                            self.sc_control_press_modifiers,
                        )
                        self.mousePressEvent(press_event)
                        self.mouseReleaseEvent(event)
                        event.accept()
                        return True
                    if isinstance(obj, (_QtPushButton, _QtCheckBox, _QtSlider, _QtComboBox)) and was_pressed:
                        previous_checked = obj.isChecked() if isinstance(obj, _QtCheckBox) else None
                        if isinstance(obj, (_QtPushButton, _QtCheckBox)):
                            obj.setDown(False)
                        obj.releaseMouse()
                        self.sc_send_control_press(obj)
                        if not isinstance(obj, (_QtCheckBox, _QtSlider)):
                            self.sc_play_confirmed_control_sound(obj)
                        obj.mouseReleaseEvent(event)
                        if isinstance(obj, _QtCheckBox):
                            self.sc_play_confirmed_control_sound(obj, previous_checked)
                        event.accept()
                        return True
                    if self.sc_drag_start_y < self.sc_drag_real_min_y or self.sc_drag_start_y > self.sc_drag_real_max_y:
                        self.sc_current = self.sc_drag_start_y
                        self.sc_target = max(self.sc_drag_real_min_y, min(self.sc_drag_real_max_y, self.sc_drag_start_y))
                        self.sc_last_time = time.time()
                        self.sc_timer.start()
                elif event_type in (QEvent.Type.Hide, QEvent.Type.Leave) and not (QApplication.mouseButtons() & Qt.MouseButton.LeftButton):
                    self.sc_drag_pressed = False
                    self.sc_dragging = False

            sb = getattr(self, "verticalScrollBar", lambda: None)()
            if sb and obj == sb:
                if event.type() == QEvent.Type.MouseButtonPress:
                    self.sc_timer.stop()
                    real_min = sb.minimum() + self.sc_added_overshoot_min
                    real_max = sb.maximum() - self.sc_added_overshoot_max
                    value = max(real_min, min(real_max, sb.value()))
                    self.sc_ignore_value_change = True
                    sb.setMinimum(real_min)
                    sb.setMaximum(real_max)
                    sb.setValue(value)
                    self.sc_ignore_value_change = False
                    self.sc_added_overshoot_min = 0
                    self.sc_added_overshoot_max = 0
                    self.sc_current = float(value)
                    self.sc_target = float(value)
                    self.sc_last_native_value = value
        except Exception:
            pass
            
        if hasattr(super(), "eventFilter"):
            return super().eventFilter(obj, event)
        return False

class SmoothListView(SmoothScrollMixin, QListView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoScroll(False)
        self.init_smooth_scroll()

    def showEvent(self, event):
        super().showEvent(event)
        self.sc_reset_to_native()

    def hideEvent(self, event):
        self.sc_reset_to_native()
        super().hideEvent(event)

class SmoothListWidget(SmoothScrollMixin, HoverListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_smooth_scroll()

class SmoothScrollArea(SmoothScrollMixin, QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_smooth_scroll()

    def setWidget(self, widget):
        super().setWidget(widget)
        for child in widget.findChildren(QWidget):
            if isinstance(child, (_QtPushButton, _QtCheckBox, _QtSlider, _QtComboBox)):
                self.sc_install_drag_target(child)

class IgnoreWheelSlider(QSlider):
    def wheelEvent(self, e: QWheelEvent):
        e.ignore()

class IgnoreWheelComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt6.QtWidgets import QStyledItemDelegate
        from PyQt6.QtCore import Qt
        
        class CenterDelegate(QStyledItemDelegate):
            def initStyleOption(self, option, index):
                super().initStyleOption(option, index)
                option.displayAlignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        
        self.setItemDelegate(CenterDelegate(self))
        self._hover_progress = 0.0
        self._hover_target = 0.0
        self._click_flash = 0.0
        self._combo_last_frame = time.perf_counter()
        self.currentIndexChanged.connect(self._flash_selection)

    def _flash_selection(self, index):
        if not self.isVisible() or not self.isEnabled():
            return
        self._click_flash = 1.0
        self._combo_last_frame = time.perf_counter()
        activate_ui_animation(self)

    def advance_ui_animation(self, now):
        if not self.isEnabled():
            self._hover_progress = 0.0
            self._hover_target = 0.0
            self._click_flash = 0.0
            self.update()
            return False
        dt = min(0.05, max(0.0, now - self._combo_last_frame))
        self._combo_last_frame = now
        self._click_flash = max(0.0, self._click_flash - dt / 0.16)
        hover_step = dt / 0.12
        if self._hover_progress < self._hover_target:
            self._hover_progress = min(self._hover_target, self._hover_progress + hover_step)
        elif self._hover_progress > self._hover_target:
            self._hover_progress = max(self._hover_target, self._hover_progress - hover_step)
        self.update()
        return self._click_flash > 0.001 or abs(self._hover_progress - self._hover_target) > 0.001

    def enterEvent(self, event):
        if self.isEnabled():
            self._hover_target = 1.0
            self._combo_last_frame = time.perf_counter()
            activate_ui_animation(self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_target = 0.0
        self._combo_last_frame = time.perf_counter()
        activate_ui_animation(self)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self._click_flash = 1.0
            self._combo_last_frame = time.perf_counter()
            activate_ui_animation(self)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        if not self.isEnabled():
            self._hover_progress = 0.0
            self._hover_target = 0.0
            self._click_flash = 0.0
            super().paintEvent(event)
            return
        if self._hover_progress <= 0.002 and self._click_flash <= 0.002 and not self.underMouse():
            super().paintEvent(event)
            return
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.state &= ~QStyle.StateFlag.State_MouseOver
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.style().drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option, painter, self)
        overlay_strength = min(1.0, self._hover_progress * 0.16 + self._click_flash * 0.42)
        if overlay_strength > 0.001:
            overlay = QColor(255, 255, 255)
            overlay.setAlpha(int(round(255 * overlay_strength)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(overlay)
            right_inset = max(0, int(self.property("animation_overlay_right_inset") or 0))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0, 0, -right_inset, -3), 6, 6)
        self.style().drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option, painter, self)
        painter.end()
    
    def wheelEvent(self, e: QWheelEvent):
        e.ignore()

    def hideEvent(self, event):
        ACTIVE_UI_ANIMATIONS.discard(self)
        self._hover_progress = 0.0
        self._hover_target = 0.0
        self._click_flash = 0.0
        try:
            view = self.view()
            owner_ref = getattr(view, "sc_combo_owner_ref", None)
            if owner_ref is not None and owner_ref() is self:
                view.sc_combo_owner_ref = None
        except RuntimeError:
            pass
        super().hideEvent(event)

    def showPopup(self):
        super().showPopup()
        view = self.view()
        view.sc_combo_popup = True
        view.sc_combo_owner_ref = weakref.ref(self)
        view.setAutoScroll(False)
        viewport = view.viewport()
        viewport.removeEventFilter(view)
        viewport.installEventFilter(view)
        if hasattr(view, "sc_reset_to_native"):
            view.sc_reset_to_native()
        model_index = self.model().index(self.currentIndex(), self.modelColumn(), self.rootModelIndex())
        if model_index.isValid():
            view.setCurrentIndex(model_index)
            selection_model = view.selectionModel()
            if selection_model is not None:
                selection_model.setCurrentIndex(
                    model_index,
                    QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
                )
            view.scrollTo(model_index, QAbstractItemView.ScrollHint.EnsureVisible)
            if hasattr(view, "sc_reset_to_native"):
                view.sc_reset_to_native()
        popup = self.view().parentWidget()
        if popup:
            rect = popup.rect()
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), 10, 10)
            region = QRegion(path.toFillPolygon().toPolygon())
            popup.setMask(region)
        
    def hidePopup(self):
        view = self.view()
        if hasattr(view, "sc_reset_to_native"):
            view.sc_reset_to_native()
        super().hidePopup()

class AllCustomNotesComboBox(IgnoreWheelComboBox):
    def initStyleOption(self, option):
        super().initStyleOption(option)
        index = self.currentIndex()
        option.currentText = f"All ({self.itemText(index)})" if index >= 0 else "All"

class NoMenuLineEdit(QLineEdit):
    def contextMenuEvent(self, e):
        pass

QComboBox = IgnoreWheelComboBox

