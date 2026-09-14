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

PROJECT_DELETE_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24"><path fill="#FFFFFF" d="M7.035 3.5c-.9 0-1.629.675-1.737 1.527A.8.8 0 0 1 5.5 5h13q.105 0 .201.027A1.75 1.75 0 0 0 16.965 3.5zM6.85 19.83a.75.75 0 0 0 .745.67h8.807a.75.75 0 0 0 .746-.67L18.59 6.496a1 1 0 0 1-.09.005h-13a1 1 0 0 1-.091-.005zM3.803 5.6A3.25 3.25 0 0 1 7.035 2h9.93a3.25 3.25 0 0 1 3.231 3.6L18.64 19.991A2.25 2.25 0 0 1 16.403 22H7.596a2.25 2.25 0 0 1-2.237-2.008zm7.989 4.81a.25.25 0 0 1 .415 0l.67 1a.75.75 0 0 0 1.246-.835l-.669-1a1.75 1.75 0 0 0-2.909 0l-.669 1a.75.75 0 1 0 1.247.834zM9.636 12.6a.75.75 0 0 1 .257 1.028l-.364.607a.5.5 0 0 0 .428.757h.793a.75.75 0 0 1 0 1.5h-.793c-1.554 0-2.514-1.696-1.715-3.029l.365-.607a.75.75 0 0 1 1.029-.257m4.473 1.028a.75.75 0 1 1 1.286-.771l.364.607c.799 1.333-.161 3.028-1.715 3.028h-.794a.75.75 0 0 1 0-1.5h.794a.5.5 0 0 0 .429-.757z"/></svg>'
PROJECT_DELETE_RENDERER = None

class ProjectCoverLoadSignals(QObject):
    loaded = pyqtSignal(object, object)

class ProjectCoverLoadTask(QRunnable):
    def __init__(self, key, cover_path, pixel_size, signals):
        super().__init__()
        self.key = key
        self.cover_path = str(cover_path)
        self.pixel_size = pixel_size
        self.signals = signals

    def run(self):
        reader = QImageReader(self.cover_path)
        reader.setAutoTransform(True)
        source_size = reader.size()
        if source_size.isValid():
            scale = min(1.0, max(
                self.pixel_size / max(1, source_size.width()),
                self.pixel_size / max(1, source_size.height()),
            ))
            reader.setScaledSize(QSize(
                max(1, int(round(source_size.width() * scale))),
                max(1, int(round(source_size.height() * scale))),
            ))
        image = reader.read()
        try:
            self.signals.loaded.emit(self.key, image)
        except RuntimeError:
            pass

def initialize_project_delete(widget, callback):
    widget.delete_callback = callback
    widget.delete_hold_active = False
    widget.delete_hold_started = 0.0
    widget.delete_hold_progress = 0.0
    widget.delete_hold_triggered = False
    widget.delete_hold_last_frame = time.perf_counter()

def start_project_delete_hold(widget):
    if widget.delete_hold_triggered:
        return
    widget.delete_hold_active = True
    widget.delete_hold_started = time.perf_counter()
    widget.delete_hold_last_frame = widget.delete_hold_started
    widget.delete_hold_progress = 0.0
    activate_ui_animation(widget)
    widget.update()

def cancel_project_delete_hold(widget):
    widget.delete_hold_active = False
    if widget.delete_hold_progress > 0.0:
        activate_ui_animation(widget)
    widget.update()

def advance_project_delete_hold(widget, now):
    active = False
    dt = min(0.05, max(0.0, now - widget.delete_hold_last_frame))
    widget.delete_hold_last_frame = now
    if widget.delete_hold_active and not widget.delete_hold_triggered:
        widget.delete_hold_progress = min(1.0, (now - widget.delete_hold_started) / 0.85)
        active = widget.delete_hold_progress < 1.0
        if widget.delete_hold_progress >= 1.0:
            widget.delete_hold_active = False
            widget.delete_hold_triggered = True
            callback = widget.delete_callback
            if callback:
                QTimer.singleShot(0, callback)
    elif widget.delete_hold_progress > 0.0 and not widget.delete_hold_triggered:
        widget.delete_hold_progress = max(0.0, widget.delete_hold_progress - dt / 0.18)
        active = widget.delete_hold_progress > 0.0
    widget.update()
    return active

def reset_project_delete_hold(widget):
    widget.delete_hold_active = False
    widget.delete_hold_progress = 0.0
    widget.delete_hold_triggered = False
    widget.update()

def draw_project_delete_icon(painter, rect, progress):
    global PROJECT_DELETE_RENDERER
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    background = QColor(10, 10, 10, 92)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(background)
    painter.drawRoundedRect(rect, 7, 7)
    if progress > 0.0:
        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(rect, 7, 7)
        painter.setClipPath(clip)
        fill_height = rect.height() * progress
        fill_color = QColor(ACCENT_COLOR)
        fill_color.setAlpha(235)
        painter.fillRect(QRectF(rect.left(), rect.bottom() - fill_height, rect.width(), fill_height), fill_color)
        painter.restore()
    if PROJECT_DELETE_RENDERER is None:
        PROJECT_DELETE_RENDERER = QSvgRenderer(QByteArray(PROJECT_DELETE_SVG))
    icon_padding = max(6.0, rect.width() * 0.19)
    PROJECT_DELETE_RENDERER.render(painter, rect.adjusted(icon_padding, icon_padding, -icon_padding, -icon_padding))
    painter.restore()

class ProjectCoverTile(QWidget):
    def __init__(self, name, cover_path, object_count=None, parent=None):
        super().__init__(parent)
        self.name = name
        self.cover_path = Path(cover_path)
        self.object_count = object_count
        self.cover_pixmap = None
        self.cover_request_key = None
        self.hovered = False
        self.cover_reveal_progress = 0.0
        self.cover_reveal_direction = -1.0 if sum(ord(char) for char in name) % 2 else 1.0
        self.sort_rotation = 0.0
        self.hover_progress = 0.0
        self.hover_target = 0.0
        self.hover_last_frame = time.perf_counter()
        self.open_progress = 0.0
        self.open_started = 0.0
        self.open_callback = None
        self.title_scroll_offset = 0.0
        self.title_scroll_started = time.perf_counter()
        self.title_scroll_geometry = 0
        self.title_scroll_overflow = 0.0
        self.card_cache = None
        self.card_cache_key = None
        initialize_project_delete(self, None)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_cover_pixmap(self, pixmap):
        self.cover_pixmap = pixmap
        self.cover_reveal_progress = 0.0
        self.title_scroll_offset = 0.0
        self.title_scroll_started = time.perf_counter()
        self.card_cache = None
        self.card_cache_key = None
        self.update()

    def set_cover_reveal_progress(self, progress):
        self.cover_reveal_progress = max(0.0, min(1.0, float(progress)))
        self.update()

    def set_sort_rotation(self, rotation):
        rotation = float(rotation)
        if abs(rotation - self.sort_rotation) >= 0.01:
            self.sort_rotation = rotation
            self.update()

    def release_cover(self):
        self.cover_request_key = None
        if self.cover_pixmap is not None:
            self.cover_pixmap = None
            self.cover_reveal_progress = 0.0
            self.card_cache = None
            self.card_cache_key = None
            self.update()

    def set_hovered(self, hovered):
        hovered = bool(hovered)
        if self.hovered != hovered:
            self.hovered = hovered
            self.hover_target = 1.0 if hovered else 0.0
            self.hover_last_frame = time.perf_counter()
            activate_ui_animation(self)
            self.update()

    def start_open_animation(self, callback):
        if self.open_callback is not None:
            return
        self.open_progress = 0.0
        self.open_started = time.perf_counter()
        self.open_callback = callback
        activate_ui_animation(self)

    def card_target_rect(self):
        widget_rect = QRectF(self.rect())
        available_side = min(widget_rect.width(), widget_rect.height())
        open_scale = 1.075
        needed_padding = (available_side - max(1.0, available_side - 4.0) / open_scale) / 2.0
        padding = max(8.0, needed_padding)
        side = max(1.0, available_side - padding * 2.0)
        return QRectF(
            widget_rect.center().x() - side / 2.0,
            widget_rect.center().y() - side / 2.0,
            side,
            side,
        )

    def delete_icon_rect(self):
        target = self.card_target_rect()
        size = max(30.0, min(38.0, target.width() * 0.17))
        return QRectF(target.right() - size - 9.0, target.top() + 9.0, size, size)

    def advance_ui_animation(self, now):
        active = False
        dt = min(0.05, max(0.0, now - self.hover_last_frame))
        self.hover_last_frame = now
        hover_distance = self.hover_target - self.hover_progress
        if abs(hover_distance) > 0.001:
            self.hover_progress += math.copysign(min(abs(hover_distance), dt / 0.12), hover_distance)
            active = True
        else:
            self.hover_progress = self.hover_target
        if self.open_callback is not None:
            linear = min(1.0, max(0.0, (now - self.open_started) / 0.16))
            self.open_progress = 1.0 - math.pow(1.0 - linear, 3.0)
            if linear >= 1.0:
                callback = self.open_callback
                self.open_callback = None
                callback()
            else:
                active = True
        if advance_project_delete_hold(self, now):
            active = True
        self.update()
        return active

    def update_title_scroll(self, now):
        if self.cover_pixmap is None or self.cover_reveal_progress < 1.0:
            return
        available = max(1.0, self.card_target_rect().width() - 24.0)
        geometry = max(1, int(round(available)))
        if geometry != self.title_scroll_geometry:
            font = self.font()
            font.setPointSize(12)
            font.setBold(True)
            metrics = QFontMetrics(font)
            self.title_scroll_overflow = max(0.0, metrics.horizontalAdvance(self.name) - available)
            self.title_scroll_geometry = geometry
        overflow = self.title_scroll_overflow
        if overflow <= 0.0:
            if self.title_scroll_offset != 0.0:
                self.title_scroll_offset = 0.0
                self.update()
            return
        pause = 0.9
        travel = overflow / 42.0
        cycle = pause * 2.0 + travel * 2.0
        position = (now - self.title_scroll_started) % cycle
        if position < pause:
            offset = 0.0
        elif position < pause + travel:
            offset = (position - pause) / travel * overflow
        elif position < pause * 2.0 + travel:
            offset = overflow
        else:
            offset = (1.0 - (position - pause * 2.0 - travel) / travel) * overflow
        if abs(offset - self.title_scroll_offset) >= 0.05:
            self.title_scroll_offset = offset
            self.update()

    def get_card_cache(self, side):
        dpr = max(1.0, float(self.devicePixelRatioF()))
        pixel_side = max(1, int(round(side * dpr)))
        pixmap_key = self.cover_pixmap.cacheKey() if self.cover_pixmap and not self.cover_pixmap.isNull() else 0
        cache_key = (pixel_side, round(dpr, 4), pixmap_key, self.object_count)
        if self.card_cache is not None and self.card_cache_key == cache_key:
            return self.card_cache
        card = QPixmap(pixel_side, pixel_side)
        card.setDevicePixelRatio(dpr)
        card.fill(Qt.GlobalColor.transparent)
        card_painter = QPainter(card)
        card_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card_painter.setFont(self.font())
        target = QRectF(0.0, 0.0, side, side)
        clip = QPainterPath()
        clip.addRoundedRect(target, 8, 8)
        card_painter.setClipPath(clip)
        card_painter.fillRect(target, QColor(15, 15, 15))
        if self.cover_pixmap and not self.cover_pixmap.isNull():
            source_width = max(1.0, float(self.cover_pixmap.width()))
            source_height = max(1.0, float(self.cover_pixmap.height()))
            source_ratio = source_width / source_height
            if abs(source_ratio - 1.0) / max(source_ratio, 1.0) <= 0.025:
                source = QRectF(0.0, 0.0, source_width, source_height)
            elif source_ratio > 1.0:
                source = QRectF((source_width - source_height) / 2.0, 0.0, source_height, source_height)
            else:
                source = QRectF(0.0, (source_height - source_width) / 2.0, source_width, source_width)
            card_painter.drawPixmap(target, self.cover_pixmap, source)
        if self.object_count is not None:
            count_height = max(36.0, side * 0.2)
            count_gradient = QLinearGradient(0.0, 0.0, 0.0, count_height)
            count_gradient.setColorAt(0.0, QColor(0, 0, 0, 215))
            count_gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
            card_painter.fillRect(QRectF(0.0, 0.0, side, count_height), count_gradient)
            count_font = card_painter.font()
            count_font.setPointSize(10)
            count_font.setBold(True)
            card_painter.setFont(count_font)
            card_painter.setPen(QColor("white"))
            card_painter.drawText(
                QRectF(12.0, 7.0, side - 24.0, 24.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{self.object_count:,} objects",
            )
        overlay_height = max(52.0, side * 0.28)
        gradient = QLinearGradient(0.0, side - overlay_height, 0.0, side)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        gradient.setColorAt(0.35, QColor(0, 0, 0, 125))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 225))
        card_painter.fillRect(QRectF(0.0, side - overlay_height, side, overlay_height), gradient)
        card_painter.end()
        self.card_cache = card
        self.card_cache_key = cache_key
        return card

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        target = self.card_target_rect()
        side = target.width()
        reveal = self.cover_reveal_progress
        reveal_scale = (0.9 + 0.1 * reveal) * (0.985 + 0.015 * self.hover_progress + 0.075 * self.open_progress)
        reveal_rotation = self.cover_reveal_direction * 7.0 * math.pow(1.0 - reveal, 2.0) + self.sort_rotation
        painter.setOpacity(reveal)
        painter.translate(target.center())
        painter.rotate(reveal_rotation)
        painter.scale(reveal_scale, reveal_scale)
        painter.translate(-target.center().x(), -target.center().y())
        painter.drawPixmap(target.topLeft(), self.get_card_cache(side))
        painter.setPen(QColor("white"))
        font = painter.font()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        text_rect = QRectF(target.left() + 12, target.bottom() - 48, target.width() - 24, 38)
        metrics = painter.fontMetrics()
        if metrics.horizontalAdvance(self.name) <= text_rect.width():
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.name)
        else:
            painter.save()
            painter.setClipRect(text_rect)
            baseline = text_rect.center().y() + (metrics.ascent() - metrics.descent()) / 2.0
            painter.drawText(QPointF(text_rect.left() - self.title_scroll_offset, baseline), self.name)
            painter.restore()
        if self.hover_progress > 0.002:
            hover_color = QColor(ACCENT_COLOR)
            hover_color.setAlpha(int(round(255 * self.hover_progress)))
            painter.setPen(QPen(hover_color, 4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(target.adjusted(2.0, 2.0, -2.0, -2.0), 6, 6)
        draw_project_delete_icon(painter, self.delete_icon_rect(), self.delete_hold_progress)
        painter.end()

class ProjectListRow(QWidget):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        initialize_project_delete(self, None)
        self.hovered = False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 62, 4)
        self.label = QLabel(text)
        self.label.setStyleSheet("background: transparent; color: white; font-size: 18px; font-weight: normal; padding: 2px;")
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.label)
        effect = FastDropShadowEffect(self.label)
        effect.setBlurRadius(12)
        effect.setColor(QColor(0, 0, 0, 150))
        effect.setOffset(0, 3)
        set_manual_shadow(self.label, effect)
        self.reveal_effect = None
        self.reveal_started = 0.0
        self.reveal_active = False

    def set_text(self, text):
        self.label.setText(text)

    def set_hovered(self, hovered):
        hovered = bool(hovered)
        if self.hovered != hovered:
            self.hovered = hovered
            self.update()

    def start_reveal(self, delay=0.0):
        if self.reveal_effect is None:
            self.reveal_effect = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(self.reveal_effect)
        self.reveal_started = time.perf_counter() + max(0.0, float(delay))
        self.reveal_active = True
        self.reveal_effect.setOpacity(0.0)
        self.reveal_effect.setEnabled(True)
        activate_ui_animation(self)

    def finish_reveal(self):
        self.reveal_active = False
        if self.reveal_effect is not None:
            self.reveal_effect.setOpacity(1.0)
            self.reveal_effect.setEnabled(False)

    def delete_icon_rect(self):
        size = min(44.0, max(38.0, self.height() - 12.0))
        return QRectF(self.width() - size - 10.0, (self.height() - size) / 2.0, size, size)

    def advance_ui_animation(self, now):
        active = advance_project_delete_hold(self, now)
        if self.reveal_active:
            linear = min(1.0, max(0.0, (now - self.reveal_started) / 0.22))
            eased = 1.0 - math.pow(1.0 - linear, 3.0)
            self.reveal_effect.setOpacity(eased)
            if linear >= 1.0:
                self.reveal_active = False
                self.reveal_effect.setOpacity(1.0)
                self.reveal_effect.setEnabled(False)
            else:
                active = True
        return active

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background = QColor(0, 0, 0, 48 if self.hovered else 28)
        border = QColor(255, 255, 255, 34 if self.hovered else 20)
        painter.setPen(QPen(border, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        draw_project_delete_icon(painter, self.delete_icon_rect(), self.delete_hold_progress)
        painter.end()

class ConfirmationDialog(QDialog):
    def __init__(self, parent, title, message, detail="", detail_bold=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        top_layout = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning).pixmap(32, 32))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        text_layout.addWidget(message_label)
        if detail:
            detail_label = QLabel(detail)
            detail_label.setWordWrap(True)
            detail_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if detail_bold:
                detail_font = detail_label.font()
                detail_font.setBold(True)
                detail_label.setFont(detail_font)
            if not detail_bold:
                detail_color = "#333333" if widget_ui_brightness(self) > 180 else "#C4C4C4"
                detail_label.setStyleSheet(f"color: {detail_color};")
            text_layout.addWidget(detail_label)
        top_layout.addWidget(icon)
        top_layout.addLayout(text_layout, 1)
        layout.addLayout(top_layout)
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 8, 0, 0)
        yes_button = QPushButton("Yes")
        no_button = QPushButton("No")
        yes_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        no_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        yes_button.clicked.connect(self.accept)
        no_button.clicked.connect(self.reject)
        button_layout.addWidget(yes_button, 1)
        button_layout.addWidget(no_button, 1)
        layout.addLayout(button_layout)
        self.setFixedSize(max(420, self.sizeHint().width()), self.sizeHint().height())

    def showEvent(self, event):
        apply_shadows_to_container(self)
        super().showEvent(event)


class StyledWarningDialog(QDialog):
    def __init__(self, parent, title, message, icon_type=QStyle.StandardPixmap.SP_MessageBoxWarning):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        top_layout = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(QApplication.style().standardIcon(icon_type).pixmap(32, 32))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        top_layout.addWidget(icon)
        top_layout.addWidget(message_label, 1)
        layout.addLayout(top_layout)
        okay = QPushButton("OK")
        okay.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        okay.clicked.connect(self.accept)
        layout.addWidget(okay)
        self.setFixedSize(max(420, self.sizeHint().width()), self.sizeHint().height())

    def showEvent(self, event):
        apply_shadows_to_container(self)
        super().showEvent(event)


class GamePathSelectionDialog(QDialog):
    """Prompt for a missing game path using the editor's current buttons."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Game Path Not Found")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.MSWindowsFixedSizeDialogHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        top_layout = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning).pixmap(32, 32)
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)
        message = QLabel("UNBEATABLE Path not found.")
        detail = QLabel("Please select the UNBEATABLE installation folder.")
        message.setWordWrap(True)
        detail.setWordWrap(True)
        detail_color = "#333333" if widget_ui_brightness(self) > 180 else "#C4C4C4"
        detail.setStyleSheet(f"color: {detail_color};")
        text_layout.addWidget(message)
        text_layout.addWidget(detail)
        top_layout.addWidget(icon)
        top_layout.addLayout(text_layout, 1)
        layout.addLayout(top_layout)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 8, 0, 0)
        select_button = QPushButton("Select Folder")
        cancel_button = QPushButton("Cancel")
        select_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cancel_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        select_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(select_button, 1)
        button_layout.addWidget(cancel_button, 1)
        layout.addLayout(button_layout)
        self.setFixedSize(max(420, self.sizeHint().width()), self.sizeHint().height())

    def showEvent(self, event):
        apply_shadows_to_container(self)
        super().showEvent(event)


class ProjectDeleteConfirmationDialog(ConfirmationDialog):
    def __init__(self, parent, project_name):
        super().__init__(
            parent,
            "Delete Beatmap",
            "Do you want to permanently delete this beatmap?",
            project_name,
            detail_bold=True,
        )


class ProjectRemovalChoiceDialog(QDialog):
    def __init__(self, parent, project_name):
        super().__init__(parent)
        self.choice = None
        self.setWindowTitle("Remove Beatmap")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.MSWindowsFixedSizeDialogHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(7)
        top_layout = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion).pixmap(32, 32))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        message_label = QLabel("What do you want to do with this beatmap?")
        message_label.setWordWrap(False)
        message_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        text_layout.addWidget(message_label)
        project_label = QLabel(project_name)
        project_label.setWordWrap(True)
        project_font = project_label.font()
        project_font.setBold(True)
        project_label.setFont(project_font)
        text_layout.addWidget(project_label)
        detail_label = QLabel("Removing it from Project Select keeps all files on your computer.")
        detail_label.setWordWrap(False)
        detail_color = "#333333" if widget_ui_brightness(self) > 180 else "#C4C4C4"
        detail_label.setStyleSheet(f"color: {detail_color}; font-size: 10pt;")
        text_layout.addWidget(detail_label)

        top_layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        top_layout.addLayout(text_layout, 1)
        layout.addLayout(top_layout)

        remove_button = QPushButton("Remove")
        delete_button = QPushButton("Delete")
        cancel_button = QPushButton("Cancel")
        remove_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        delete_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cancel_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        remove_button.clicked.connect(lambda: self.finish_with_choice("remove"))
        delete_button.clicked.connect(lambda: self.finish_with_choice("delete"))
        cancel_button.clicked.connect(self.reject)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 5, 0, 0)
        button_layout.addWidget(remove_button, 1)
        button_layout.addWidget(delete_button, 1)
        button_layout.addWidget(cancel_button, 1)
        layout.addLayout(button_layout)
        self.setFixedSize(max(420, self.sizeHint().width()), self.sizeHint().height())

    def finish_with_choice(self, choice):
        self.choice = choice
        self.accept()

    def showEvent(self, event):
        apply_shadows_to_container(self)
        super().showEvent(event)

class ProjectItemMoveAnimator(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.view = parent.list_widget
        self.moves = []
        self.rotation_directions = {}
        self.started = 0.0
        self.scroll_origin = 0

    def start(self, moves):
        self.finish()
        self.moves = list(moves)
        if not self.moves:
            return
        for widget, start_rect, end_rect in self.moves:
            if isinstance(widget, ProjectCoverTile):
                delta_x = end_rect.x() - start_rect.x()
                delta_y = end_rect.y() - start_rect.y()
                if abs(delta_x) > 1.0 or abs(delta_y) > 1.0:
                    primary_delta = delta_x if abs(delta_x) > 1.0 else delta_y
                    self.rotation_directions[widget] = 1.0 if primary_delta >= 0.0 else -1.0
            widget.setGeometry(start_rect.toRect())
            widget.show()
            widget.raise_()
        self.scroll_origin = self.view.verticalScrollBar().value()
        self.started = time.perf_counter()
        activate_ui_animation(self)

    def finish(self):
        scroll_offset = self.scroll_origin - self.view.verticalScrollBar().value()
        for widget, start_rect, end_rect in self.moves:
            try:
                widget.setGeometry(end_rect.translated(0, scroll_offset).toRect())
                if isinstance(widget, ProjectCoverTile):
                    widget.set_sort_rotation(0.0)
            except RuntimeError:
                pass
        self.moves = []
        self.rotation_directions.clear()

    def advance_ui_animation(self, now):
        if not self.moves:
            return False
        linear = min(1.0, max(0.0, (now - self.started) / 0.32))
        shifted = linear - 1.0
        eased = 1.0 + 1.8 * shifted * shifted * shifted + 0.8 * shifted * shifted
        scroll_offset = self.scroll_origin - self.view.verticalScrollBar().value()
        for widget, start_rect, end_rect in self.moves:
            try:
                rect = QRectF(
                    start_rect.x() + (end_rect.x() - start_rect.x()) * eased,
                    start_rect.y() + (end_rect.y() - start_rect.y()) * eased + scroll_offset,
                    start_rect.width() + (end_rect.width() - start_rect.width()) * eased,
                    start_rect.height() + (end_rect.height() - start_rect.height()) * eased,
                )
                widget.setGeometry(rect.toRect())
                widget.raise_()
                if isinstance(widget, ProjectCoverTile):
                    rotation = self.rotation_directions.get(widget, 0.0) * 3.5 * math.sin(math.pi * linear)
                    widget.set_sort_rotation(rotation)
            except RuntimeError:
                pass
        if linear >= 1.0:
            self.finish()
            return False
        return True

class StartScreen(QWidget):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        
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
        self.lbl_recent = QLabel("Projects")
        self.lbl_recent.setStyleSheet("font-size: 28px; font-weight: bold;")
        
        recent_effect = FastDropShadowEffect(self.lbl_recent)
        recent_effect.setBlurRadius(8)
        recent_effect.setColor(QColor(0, 0, 0, 200))
        recent_effect.setOffset(0, 2)
        set_manual_shadow(self.lbl_recent, recent_effect)
        
        ctrl_layout.addWidget(self.lbl_recent)

        ctrl_layout.addStretch()

        self.lbl_view_as = QLabel("View:")
        view_effect = FastDropShadowEffect(self.lbl_view_as)
        view_effect.setBlurRadius(8)
        view_effect.setColor(QColor(0, 0, 0, 200))
        view_effect.setOffset(0, 2)
        set_manual_shadow(self.lbl_view_as, view_effect)
        ctrl_layout.addWidget(self.lbl_view_as)
        self.combo_view = IgnoreWheelComboBox()
        self.combo_view.setView(SmoothListView(self.combo_view))
        self.combo_view.addItems(["List View", "Cover View"])
        initial_view = getattr(self.editor, "project_view_mode", "Cover View")
        self.combo_view.setCurrentText(initial_view if initial_view in ("List View", "Cover View") else "Cover View")
        self.combo_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_view.currentIndexChanged.connect(self.on_view_mode_changed)
        ctrl_layout.addWidget(self.combo_view)

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
        self.combo_sort.activated.connect(self.sort_project_items)
        ctrl_layout.addWidget(self.combo_sort)
        
        layout.addLayout(ctrl_layout)
        
        self.list_widget = SmoothListWidget()
        self.list_widget.itemClicked.connect(self.on_item_click)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list_widget.setMouseTracking(True)
        self.list_widget.setAcceptDrops(True)
        self.list_widget.viewport().setAcceptDrops(True)
        self.list_widget.itemEntered.connect(self.update_cover_hover)
        self.list_widget.viewport().installEventFilter(self)
        self.list_widget.verticalScrollBar().valueChanged.connect(self.schedule_visible_cover_update)
        self.list_widget.verticalScrollBar().valueChanged.connect(self.update_project_hover_at_cursor)
        layout.addWidget(self.list_widget)
        self.item_move_animator = ProjectItemMoveAnimator(self)
        
        self.projects_data = []
        self.project_stats_cache = {}
        self.cover_pixmap_cache = {}
        self.pending_cover_requests = set()
        self.cover_request_tiles = {}
        self.cover_load_sequence = 0
        self.cover_commit_sequence = 0
        self.completed_cover_loads = {}
        self.active_cover_animations = set()
        self.pending_cover_animations = []
        self.pending_cover_animation_tiles = set()
        self.preloaded_cover_tiles = set()
        self.cover_enter_sound_counter = 0
        self.visible_cover_tiles = set()
        self.reveal_cover_tiles = set()
        self.managed_cover_tiles = set()
        self.revealed_cover_paths = set()
        self.hovered_cover_item = None
        self.cover_generation = 0
        self.cover_grid_target_size = 0
        self.cover_grid_cell_size = 0
        self.cover_grid_columns = 0
        self.cover_grid_dpr = 0.0
        self.cover_screen_connection = None
        self.cover_thread_pool = QThreadPool(self)
        self.cover_thread_pool.setMaxThreadCount(5)
        self.project_tiles = {}
        self.pending_project_open = False
        self.active_delete_widget = None
        self.delete_pointer_captured = False
        self.cover_load_signals = ProjectCoverLoadSignals(self)
        self.cover_load_signals.loaded.connect(self.cover_loaded)
        self.cover_resize_timer = QTimer(self)
        self.cover_resize_timer.setSingleShot(True)
        self.cover_resize_timer.setInterval(60)
        self.cover_resize_timer.timeout.connect(self.update_cover_grid_geometry)
        self.visible_cover_timer = QTimer(self)
        self.visible_cover_timer.setSingleShot(True)
        self.visible_cover_timer.timeout.connect(self.update_visible_covers)
        self.cover_reveal_timer = QTimer(self)
        self.cover_reveal_timer.setSingleShot(True)
        self.cover_reveal_timer.timeout.connect(self.start_next_cover_animation)
        self.project_preview_hover_path = None
        self.project_preview_hover_started = 0.0
        self.project_preview_attempted_path = None
        self.project_preview_active_path = None
        self.project_preview_stream = None
        self.project_preview_start_ms = 0.0
        self.project_preview_level = 0.0
        self.project_preview_target = 0.0
        self.project_preview_last_frame = time.perf_counter()
        self.update_theme()

    def update_theme(self):
        if not hasattr(self, 'editor'): return
        
        text_color = "white"

        self.lbl_recent.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {text_color};")
        self.lbl_view_as.setStyleSheet(f"color: {text_color};")
        self.lbl_sort_by.setStyleSheet(f"color: {text_color};")
        self.apply_project_view_style()

        self.list_widget.verticalScrollBar().setProperty("transparentTrack", False)
        self.list_widget.verticalScrollBar().setStyleSheet(
            f"QScrollBar:vertical {{ background: transparent; background-color: transparent; width: 8px; border: none; margin: 0px; }}"
            f"QScrollBar::handle:vertical {{ background-color: {ACCENT_COLOR}; min-height: 30px; border-radius: 4px; margin: 0px; }}"
            f"QScrollBar::handle:vertical:hover {{ background-color: {ACCENT_HOVER}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; border: none; background: transparent; background-color: transparent; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; background-color: transparent; border: none; }}"
        )
        for tile in self.list_widget.findChildren(ProjectCoverTile):
            tile.update()

    def apply_project_view_style(self):
        if self.combo_view.currentText() == "Cover View":
            self.list_widget.setStyleSheet(
                "QListWidget { background: transparent; background-color: transparent; border: none; padding: 8px; outline: 0; }"
                "QListWidget::viewport { background: transparent; background-color: transparent; border: none; }"
                "QListWidget::item { background: transparent; border: none; margin: 0px; }"
                "QListWidget::item:hover { background: transparent; border: none; }"
                "QListWidget::item:selected { background: transparent; border: none; }"
                "QListWidget::item:selected:hover { background: transparent; border: none; }"
            )
        else:
            self.list_widget.setStyleSheet(
                "QListWidget { background: transparent; background-color: transparent; border: none; padding: 10px 24px 10px 10px; font-size: 18px; outline: 0; color: white; }"
                "QListWidget::viewport { background: transparent; background-color: transparent; border: none; }"
                "QListWidget::item { background: transparent; padding: 6px; margin: 4px 10px 4px 0px; border: none; color: white; }"
                "QListWidget::item:hover { background: transparent; border: none; }"
                "QListWidget::item:selected { background: transparent; color: white; border: none; }"
                "QListWidget::item:selected:!active { background: transparent; color: white; border: none; }"
                "QListWidget::item:selected:hover { background: transparent; color: white; border: none; }"
            )

    def find_project_cover(self, project_path):
        for extension in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            path = project_path / f"cover{extension}"
            if path.is_file():
                return path
        return Path(__file__).resolve().parent / "sounds" / "no_cover.jpg"

    def on_view_mode_changed(self, index=0):
        mode = self.combo_view.currentText()
        if mode not in ("List View", "Cover View"):
            mode = "Cover View"
        self.editor.project_view_mode = mode
        if mode == "List View":
            self.cover_generation += 1
            self.pending_cover_requests.clear()
            self.cover_request_tiles.clear()
            self.cover_load_sequence = 0
            self.cover_commit_sequence = 0
            self.completed_cover_loads.clear()
            self.preloaded_cover_tiles.clear()
            self.cover_thread_pool.clear()
            self.cover_pixmap_cache.clear()
        if getattr(self.editor, '_is_initialized', False):
            self.editor.config_save_timer.start()
        self.populate_list()

    def configure_project_view(self):
        cover_view = self.combo_view.currentText() == "Cover View"
        self.list_widget.setViewMode(QListView.ViewMode.IconMode if cover_view else QListView.ViewMode.ListMode)
        self.list_widget.setFlow(QListView.Flow.LeftToRight if cover_view else QListView.Flow.TopToBottom)
        self.list_widget.setWrapping(cover_view)
        self.list_widget.setMovement(QListView.Movement.Static)
        self.list_widget.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_widget.setUniformItemSizes(cover_view)
        self.list_widget.setSpacing(0)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        if not cover_view:
            self.list_widget.setGridSize(QSize())
        self.apply_project_view_style()

    def update_cover_grid_geometry(self):
        if self.combo_view.currentText() != "Cover View":
            return
        viewport_width = max(1, self.list_widget.viewport().width())
        window = self.window()
        window_ratio = window.width() / max(1, window.height())
        if window_ratio >= 1.7:
            columns = 5
        elif window_ratio >= 1.5:
            columns = 4
        elif window_ratio >= 0.95:
            columns = 3
        elif window_ratio >= 0.7:
            columns = 2
        else:
            columns = 1
        columns = max(1, min(columns, viewport_width // 100))
        cell_width = max(100, (viewport_width - 6 * columns) // columns)
        item_width = max(84, cell_width - 16)
        item_size = QSize(cell_width, cell_width)
        dpr = max(1.0, float(self.devicePixelRatioF()))
        if (
            item_width != self.cover_grid_target_size
            or columns != self.cover_grid_columns
            or abs(dpr - self.cover_grid_dpr) > 0.001
        ):
            self.cover_grid_target_size = item_width
            self.cover_grid_columns = columns
            self.cover_grid_dpr = dpr
            self.cover_generation += 1
            self.pending_cover_requests.clear()
            self.cover_request_tiles.clear()
            self.cover_load_sequence = 0
            self.cover_commit_sequence = 0
            self.completed_cover_loads.clear()
            self.preloaded_cover_tiles.clear()
            self.cover_thread_pool.clear()
            self.cover_pixmap_cache.clear()
            for tile in self.list_widget.findChildren(ProjectCoverTile):
                try:
                    tile.release_cover()
                except RuntimeError:
                    pass
        self.list_widget.setGridSize(QSize(cell_width, cell_width))
        self.cover_grid_cell_size = cell_width
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            item.setSizeHint(item_size)
        self.list_widget.doItemsLayout()
        self.schedule_visible_cover_update()

    def schedule_visible_cover_update(self, value=0):
        if self.combo_view.currentText() == "Cover View":
            self.visible_cover_timer.start(0)

    def request_cover_pixmap(self, tile, target_size):
        cover_path = Path(tile.cover_path)
        try:
            stat = cover_path.stat()
            dpr = max(1.0, float(self.devicePixelRatioF()))
            pixel_size = max(1, int(round(target_size * dpr)))
            signature = (
                self.cover_generation,
                str(cover_path),
                stat.st_mtime_ns,
                stat.st_size,
                pixel_size,
                dpr,
                id(tile),
                self.cover_load_sequence,
            )
            self.cover_load_sequence += 1
        except OSError:
            tile.set_cover_pixmap(QPixmap())
            return
        tile.cover_request_key = signature
        self.cover_request_tiles[signature] = tile
        cache_key = signature[1:6]
        cached = self.cover_pixmap_cache.pop(cache_key, None)
        if cached is not None:
            self.cover_pixmap_cache[cache_key] = cached
            self.completed_cover_loads[signature[7]] = (signature, cached)
            self.drain_completed_cover_loads()
            return
        if signature in self.pending_cover_requests:
            return
        self.pending_cover_requests.add(signature)
        self.cover_thread_pool.start(ProjectCoverLoadTask(
            signature,
            cover_path,
            pixel_size,
            self.cover_load_signals,
        ))

    def cover_loaded(self, signature, image):
        if not signature or signature[0] != self.cover_generation:
            return
        self.completed_cover_loads[signature[7]] = (signature, image)
        self.drain_completed_cover_loads()

    def drain_completed_cover_loads(self):
        while self.cover_commit_sequence in self.completed_cover_loads:
            completed_signature, completed_cover = self.completed_cover_loads.pop(self.cover_commit_sequence)
            self.cover_commit_sequence += 1
            self.commit_cover_load(completed_signature, completed_cover)

    def commit_cover_load(self, signature, cover):
        self.pending_cover_requests.discard(signature)
        tile = self.cover_request_tiles.pop(signature, None)
        if isinstance(cover, QPixmap):
            pixmap = cover
        else:
            pixmap = QPixmap.fromImage(cover)
            if not pixmap.isNull():
                pixmap.setDevicePixelRatio(signature[5])
        cache_key = signature[1:6]
        self.cover_pixmap_cache[cache_key] = pixmap
        while len(self.cover_pixmap_cache) > 24:
            self.cover_pixmap_cache.pop(next(iter(self.cover_pixmap_cache)))
        if tile is not None and tile.cover_request_key == signature:
            tile.set_cover_pixmap(pixmap)
            self.commit_cover_tile(tile)

    def cover_tile_key(self, tile):
        return str(getattr(tile, "project_path", tile.cover_path))

    def reveal_cover_immediately(self, tile):
        self.revealed_cover_paths.add(self.cover_tile_key(tile))
        tile.set_cover_reveal_progress(1.0)

    def commit_cover_tile(self, tile):
        if self.cover_tile_key(tile) in self.revealed_cover_paths:
            tile.set_cover_reveal_progress(1.0)
        elif tile in self.reveal_cover_tiles and self.is_cover_tile_visible(tile):
            self.queue_cover_animation(tile)
        elif self.active_cover_animations or self.pending_cover_animations:
            self.preloaded_cover_tiles.add(tile)
        else:
            self.reveal_cover_immediately(tile)

    def queue_cover_animation(self, tile):
        if tile.cover_pixmap is None or tile.cover_reveal_progress >= 1.0:
            return
        if self.cover_tile_key(tile) in self.revealed_cover_paths:
            tile.set_cover_reveal_progress(1.0)
            return
        if tile in self.active_cover_animations or tile in self.pending_cover_animation_tiles:
            return
        self.pending_cover_animations.append(tile)
        self.pending_cover_animation_tiles.add(tile)
        if not self.cover_reveal_timer.isActive():
            self.cover_reveal_timer.start(0)

    def start_next_cover_animation(self):
        while self.pending_cover_animations:
            tile = self.pending_cover_animations.pop(0)
            self.pending_cover_animation_tiles.discard(tile)
            if tile not in self.reveal_cover_tiles or not self.is_cover_tile_visible(tile):
                continue
            self.start_cover_animation(tile)
            break
        if self.pending_cover_animations:
            self.cover_reveal_timer.start(20)

    def start_cover_animation(self, tile):
        if tile.cover_pixmap is None or tile.cover_pixmap.isNull():
            self.reveal_cover_immediately(tile)
            return
        if (
            tile in self.active_cover_animations
            or tile.cover_reveal_progress >= 1.0
            or not self.is_cover_tile_visible(tile)
        ):
            return
        tile.cover_reveal_started = time.perf_counter()
        self.active_cover_animations.add(tile)
        self.cover_enter_sound_counter += 1
        if self.cover_enter_sound_counter % 2 == 0:
            self.editor.play_project_cover_enter_sound()

    def update_cover_animations(self):
        now = time.perf_counter()
        self.update_project_audio_preview(now)
        for tile in tuple(self.active_cover_animations):
            try:
                if tile.cover_pixmap is None:
                    self.active_cover_animations.discard(tile)
                    continue
                linear = max(0.0, min(1.0, (now - tile.cover_reveal_started) / 0.24))
                tile.set_cover_reveal_progress(1.0 - math.pow(1.0 - linear, 3.0))
                if linear >= 1.0:
                    self.active_cover_animations.discard(tile)
                    self.revealed_cover_paths.add(self.cover_tile_key(tile))
            except RuntimeError:
                self.active_cover_animations.discard(tile)
        if not self.active_cover_animations and not self.pending_cover_animations:
            for tile in tuple(self.preloaded_cover_tiles):
                try:
                    self.reveal_cover_immediately(tile)
                except RuntimeError:
                    pass
            self.preloaded_cover_tiles.clear()
        for tile in tuple(self.visible_cover_tiles):
            try:
                tile.update_title_scroll(now)
            except RuntimeError:
                self.visible_cover_tiles.discard(tile)

    def set_project_audio_preview_hover(self, project_path):
        path = str(project_path) if project_path else None
        if path == self.project_preview_hover_path:
            return
        self.project_preview_hover_path = path
        self.project_preview_hover_started = time.perf_counter()
        self.project_preview_attempted_path = None
        if path != self.project_preview_active_path:
            self.project_preview_target = 0.0

    def resolve_project_audio_preview(self, project_path):
        try:
            project_root = Path(project_path).resolve(strict=True)
        except OSError:
            return None, None, None
        project = next((item for item in self.projects_data if item["path"] == str(project_path)), None)
        map_files = project["map_files"] if project else ()
        title = project["name"] if project else project_root.name
        audio_filename = None
        preview_time = None
        for map_file in map_files:
            current_section = ""
            title_value = ""
            title_unicode = ""
            candidate_audio = None
            candidate_preview_time = None
            try:
                with open(map_file, "r", encoding="utf-8-sig") as handle:
                    for raw_line in handle:
                        line = raw_line.strip()
                        if line.startswith("[") and line.endswith("]"):
                            current_section = line
                            if current_section in ("[Events]", "[TimingPoints]", "[HitObjects]") and candidate_audio:
                                break
                            continue
                        if ":" not in line:
                            continue
                        key, value = line.split(":", 1)
                        value = value.strip()
                        if current_section == "[General]":
                            if key.strip() == "AudioFilename":
                                candidate_audio = value.strip('"')
                            elif key.strip() == "PreviewTime":
                                try:
                                    candidate_preview_time = int(value)
                                except (TypeError, ValueError, OverflowError):
                                    candidate_preview_time = None
                        elif current_section == "[Metadata]":
                            if key.strip() == "Title":
                                title_value = value
                            elif key.strip() == "TitleUnicode":
                                title_unicode = value
            except (OSError, UnicodeError):
                continue
            if title_unicode or title_value:
                title = title_unicode or title_value
            if candidate_audio:
                audio_filename = candidate_audio
                preview_time = candidate_preview_time
                break
        if audio_filename:
            try:
                audio_path = (project_root / audio_filename).resolve(strict=True)
                audio_path.relative_to(project_root)
                if audio_path.is_file():
                    return audio_path, title, preview_time
            except (OSError, ValueError):
                pass
        supported = {".mp3", ".wav", ".ogg", ".flac", ".opus", ".m4a", ".aac", ".wma", ".alac", ".aiff", ".aif"}
        try:
            for audio_path in sorted(project_root.iterdir(), key=lambda item: item.name.casefold()):
                if audio_path.is_file() and audio_path.suffix.lower() in supported:
                    return audio_path, title, preview_time
        except OSError:
            pass
        return None, title, preview_time

    def start_project_audio_preview(self, project_path):
        self.project_preview_attempted_path = project_path
        audio_path, title, preview_time = self.resolve_project_audio_preview(project_path)
        if audio_path is None:
            return
        stream = None
        try:
            stream = get_audio_engine().load_stream(audio_path, prescan=False)
            length_ms = max(0.0, stream.get_length_ms())
            preview_ms = preview_time * 1000.0 if preview_time is not None else -1.0
            start_ms = preview_ms if 0.0 <= preview_ms <= length_ms else length_ms * 0.15
            stream.set_volume(0.0)
            if not stream.play_from_ms(start_ms):
                stream.free()
                return
            self.project_preview_stream = stream
            self.project_preview_active_path = project_path
            self.project_preview_start_ms = start_ms
            self.project_preview_level = 0.0
            self.project_preview_target = 1.0
            self.editor.save_toast.show_message(f"Now Playing: {title}")
        except (BassError, OSError, ValueError):
            if stream is not None:
                try:
                    stream.free()
                except BassError:
                    pass

    def release_project_audio_preview(self):
        stream = self.project_preview_stream
        if stream is not None:
            try:
                stream.stop()
                stream.free()
            except BassError:
                pass
        self.project_preview_stream = None
        self.project_preview_active_path = None
        self.project_preview_start_ms = 0.0
        self.project_preview_level = 0.0
        self.project_preview_target = 0.0

    def update_project_audio_preview(self, now):
        dt = min(0.05, max(0.0, now - self.project_preview_last_frame))
        self.project_preview_last_frame = now
        hover_ready = (
            self.project_preview_hover_path is not None
            and now - self.project_preview_hover_started >= 2.0
        )
        if (
            hover_ready
            and self.project_preview_stream is None
            and self.project_preview_attempted_path != self.project_preview_hover_path
        ):
            self.start_project_audio_preview(self.project_preview_hover_path)
        stream = self.project_preview_stream
        if stream is None:
            return
        should_play = hover_ready and self.project_preview_hover_path == self.project_preview_active_path
        self.project_preview_target = 1.0 if should_play else 0.0
        step = dt / 0.5
        if self.project_preview_level < self.project_preview_target:
            self.project_preview_level = min(self.project_preview_target, self.project_preview_level + step)
        elif self.project_preview_level > self.project_preview_target:
            self.project_preview_level = max(self.project_preview_target, self.project_preview_level - step)
        try:
            stream.set_volume(self.project_preview_level * self.editor.get_effective_music_volume())
            if should_play and not stream.get_busy():
                stream.play_from_ms(self.project_preview_start_ms)
        except BassError:
            self.release_project_audio_preview()
            return
        if not should_play and self.project_preview_level <= 0.0:
            self.release_project_audio_preview()

    def update_visible_covers(self):
        if self.combo_view.currentText() != "Cover View" or not self.list_widget.isVisible():
            return
        viewport = self.list_widget.viewport()
        visible_rect = viewport.rect()
        target_size = min(768, max(192, self.cover_grid_target_size))
        visible_tiles = set()
        reveal_tiles = []
        preload_tiles = []
        preload_tile_set = set()
        columns = max(1, self.cover_grid_columns)
        row_count = (self.list_widget.count() + columns - 1) // columns
        visible_rows = []
        for row in range(row_count):
            row_item = self.list_widget.item(row * columns)
            if row_item is not None and self.list_widget.visualItemRect(row_item).intersects(visible_rect):
                visible_rows.append(row)
        if not visible_rows:
            return
        first_row = max(0, visible_rows[0] - 1)
        last_row = min(row_count - 1, visible_rows[-1] + 1)
        first_index = first_row * columns
        last_index = min(self.list_widget.count(), (last_row + 1) * columns)
        for index in range(first_index, last_index):
            item = self.list_widget.item(index)
            tile = self.list_widget.itemWidget(item)
            if not isinstance(tile, ProjectCoverTile):
                continue
            item_rect = self.list_widget.visualItemRect(item)
            if item_rect.intersects(visible_rect):
                visible_tiles.add(tile)
                reveal_tiles.append(tile)
            if tile not in preload_tile_set:
                preload_tiles.append(tile)
                preload_tile_set.add(tile)
        for tile in preload_tiles:
            if tile.cover_pixmap is None and tile.cover_request_key is None:
                self.request_cover_pixmap(tile, target_size)
        released_tiles = self.managed_cover_tiles - preload_tile_set
        for tile in tuple(released_tiles):
            try:
                tile.release_cover()
            except RuntimeError:
                self.visible_cover_tiles.discard(tile)
            self.active_cover_animations.discard(tile)
            self.pending_cover_animation_tiles.discard(tile)
            self.preloaded_cover_tiles.discard(tile)
        if released_tiles:
            self.pending_cover_animations = [
                tile for tile in self.pending_cover_animations
                if tile not in released_tiles
            ]
        self.managed_cover_tiles = preload_tile_set
        self.visible_cover_tiles = visible_tiles
        self.reveal_cover_tiles = set(reveal_tiles)
        for tile in reveal_tiles:
            if tile.cover_pixmap is not None and tile.cover_reveal_progress < 1.0:
                if self.cover_tile_key(tile) in self.revealed_cover_paths:
                    tile.set_cover_reveal_progress(1.0)
                    continue
                if tile in self.preloaded_cover_tiles:
                    self.preloaded_cover_tiles.discard(tile)
                    if self.active_cover_animations or self.pending_cover_animations:
                        self.queue_cover_animation(tile)
                    else:
                        self.reveal_cover_immediately(tile)
                else:
                    self.queue_cover_animation(tile)

    def is_cover_tile_visible(self, tile):
        viewport = self.list_widget.viewport()
        card = tile.card_target_rect()
        top_left = tile.mapTo(viewport, card.topLeft().toPoint())
        card_rect = QRectF(top_left.x(), top_left.y(), card.width(), card.height())
        intersection = card_rect.intersected(QRectF(viewport.rect()))
        return intersection.width() * intersection.height() >= card.width() * card.height() * 0.08

    def update_cover_hover(self, item):
        if item is self.hovered_cover_item:
            return
        previous = self.hovered_cover_item
        self.hovered_cover_item = item
        if previous is not None:
            previous_tile = self.list_widget.itemWidget(previous)
            if isinstance(previous_tile, (ProjectCoverTile, ProjectListRow)):
                previous_tile.set_hovered(False)
        if item is not None:
            tile = self.list_widget.itemWidget(item)
            if isinstance(tile, (ProjectCoverTile, ProjectListRow)):
                tile.set_hovered(True)
            path = item.data(Qt.ItemDataRole.UserRole)
            self.set_project_audio_preview_hover(path)
            if path and hasattr(self.editor, "preview_metadata_for_path"):
                self.editor.preview_metadata_for_path(path)
        else:
            self.set_project_audio_preview_hover(None)
            if hasattr(self.editor, "clear_project_metadata_preview"):
                self.editor.clear_project_metadata_preview()

    def update_project_hover_at_cursor(self, value=0):
        viewport = self.list_widget.viewport()
        if not viewport.underMouse():
            self.update_cover_hover(None)
            return
        local_pos = viewport.mapFromGlobal(QCursor.pos())
        self.update_cover_hover(self.list_widget.itemAt(local_pos))

    def eventFilter(self, watched, event):
        if watched is self.list_widget.viewport():
            event_type = event.type()
            if event_type in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                if self.project_folder_from_mime_data(event.mimeData()) is not None:
                    event.acceptProposedAction()
                    return True
            elif event_type == QEvent.Type.Drop:
                project_path = self.project_folder_from_mime_data(event.mimeData())
                if project_path is not None:
                    event.acceptProposedAction()
                    self.open_dropped_project(project_path)
                    return True
            elif event_type == QEvent.Type.Leave:
                self.update_cover_hover(None)
                if self.active_delete_widget is not None:
                    try:
                        cancel_project_delete_hold(self.active_delete_widget)
                    except RuntimeError:
                        pass
                    self.active_delete_widget = None
            elif event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self.delete_pointer_captured = False
                item = self.list_widget.itemAt(event.position().toPoint())
                widget = self.list_widget.itemWidget(item) if item is not None else None
                if widget is not None and hasattr(widget, 'delete_icon_rect'):
                    local_pos = widget.mapFrom(self.list_widget.viewport(), event.position().toPoint())
                    if widget.delete_icon_rect().adjusted(-5.0, -5.0, 5.0, 5.0).contains(QPointF(local_pos)):
                        self.delete_pointer_captured = True
                        self.active_delete_widget = widget
                        start_project_delete_hold(widget)
                        event.accept()
                        return True
            elif event_type == QEvent.Type.MouseMove:
                if self.delete_pointer_captured:
                    if self.active_delete_widget is not None:
                        try:
                            local_pos = self.active_delete_widget.mapFrom(self.list_widget.viewport(), event.position().toPoint())
                            if not self.active_delete_widget.delete_icon_rect().adjusted(-5.0, -5.0, 5.0, 5.0).contains(QPointF(local_pos)):
                                cancel_project_delete_hold(self.active_delete_widget)
                                self.active_delete_widget = None
                        except RuntimeError:
                            self.active_delete_widget = None
                    event.accept()
                    return True
                self.update_cover_hover(self.list_widget.itemAt(event.position().toPoint()))
            elif event_type == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton and self.delete_pointer_captured:
                if self.active_delete_widget is not None:
                    try:
                        cancel_project_delete_hold(self.active_delete_widget)
                    except RuntimeError:
                        pass
                self.active_delete_widget = None
                self.delete_pointer_captured = False
                event.accept()
                return True
        return super().eventFilter(watched, event)

    @staticmethod
    def project_folder_from_mime_data(mime_data):
        if mime_data is None or not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            candidate = Path(url.toLocalFile())
            if candidate.is_dir():
                return candidate
        return None

    def dragEnterEvent(self, event):
        if self.project_folder_from_mime_data(event.mimeData()) is not None:
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self.project_folder_from_mime_data(event.mimeData()) is not None:
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        project_path = self.project_folder_from_mime_data(event.mimeData())
        if project_path is None:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        self.open_dropped_project(project_path)

    def open_dropped_project(self, project_path):
        if self.pending_project_open:
            return
        if hasattr(self.editor, 'play_ui_sound_suppressed'):
            pan = self.editor.get_pan_for_widget(self.list_widget)
            self.editor.play_ui_sound_suppressed('UI Click', pan)
        if not self.editor.confirm_unsaved_changes("load"):
            return
        self.editor.load_project_from_path(Path(project_path))

    @staticmethod
    def normalized_project_path(path):
        try:
            return os.path.normcase(str(Path(path).resolve()))
        except OSError:
            return os.path.normcase(os.path.abspath(str(path)))

    def remove_project_from_select(self, project_path):
        project_key = self.normalized_project_path(project_path)
        self.editor.recent_projects = [
            entry for entry in self.editor.recent_projects
            if self.normalized_project_path(entry) != project_key
        ]
        self.editor.save_game_config()
        self.load_projects()
        self.editor.save_toast.show_message("Removed from Project Select")

    def confirm_project_delete(self, path, widget):
        self.update_cover_hover(None)
        self.release_project_audio_preview()
        try:
            reset_project_delete_hold(widget)
        except RuntimeError:
            pass
        self.active_delete_widget = None
        self.delete_pointer_captured = False
        project_path = Path(path)
        choice_dialog = ProjectRemovalChoiceDialog(self, project_path.name)
        if choice_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if choice_dialog.choice == "remove":
            self.remove_project_from_select(project_path)
            return
        if choice_dialog.choice != "delete":
            return
        dialog = ProjectDeleteConfirmationDialog(self, project_path.name)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            resolved = project_path.resolve(strict=True)
            protected = {Path(resolved.anchor).resolve()}
            for candidate in (getattr(self.editor, 'game_root_path', None), getattr(self.editor, 'game_custom_maps_path', None)):
                if candidate:
                    try:
                        protected.add(Path(candidate).resolve())
                    except OSError:
                        pass
            if not resolved.is_dir() or project_path.is_symlink() or resolved in protected:
                raise OSError("This folder cannot be deleted safely.")
            current_path = getattr(self.editor, 'project_folder', None)
            deleting_current = False
            if current_path:
                try:
                    deleting_current = Path(current_path).resolve() == resolved
                except OSError:
                    deleting_current = False
            if deleting_current:
                if getattr(self.editor, 'is_playing', False):
                    self.editor.toggle_play()
                if hasattr(self.editor, 'video_controller'):
                    self.editor.video_controller.release()
                self.editor.stop_music_playback(release=True)
                self.editor.stop_all_hold_sounds()
            shutil.rmtree(resolved)
            resolved_key = os.path.normcase(str(resolved))
            self.editor.recent_projects = [
                entry for entry in self.editor.recent_projects
                if os.path.normcase(str(Path(entry).resolve())) != resolved_key
            ]
            if deleting_current:
                self.editor.project_folder = None
                self.editor.current_chart = None
                self.editor.beatmaps.clear()
                self.editor.current_audio_filename = None
                self.editor._current_audio_path = None
                self.editor.timeline.beatmap = None
                self.editor.timeline.selected_objects.clear()
                self.editor.lbl_path.setText("No project loaded")
                self.editor.update_window_title()
                self.editor.update_ui_state()
            self.editor.save_game_config()
            self.load_projects()
            self.editor.save_toast.show_message("Beatmap Deleted")
        except (OSError, PermissionError) as error:
            QMessageBox.critical(self, "Delete Beatmap", f"The beatmap could not be deleted:\n{error}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'combo_view') and self.combo_view.currentText() == "Cover View":
            self.cover_resize_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.project_preview_last_frame = time.perf_counter()
        handle = self.window().windowHandle()
        if handle is not None and handle is not self.cover_screen_connection:
            if self.cover_screen_connection is not None:
                try:
                    self.cover_screen_connection.screenChanged.disconnect(self.cover_screen_changed)
                except (RuntimeError, TypeError):
                    pass
            handle.screenChanged.connect(self.cover_screen_changed)
            self.cover_screen_connection = handle
        self.cover_resize_timer.start(0)
        self.schedule_visible_cover_update()

    def cover_screen_changed(self, screen):
        self.cover_grid_dpr = 0.0
        self.cover_resize_timer.start(0)

    def hideEvent(self, event):
        self.set_project_audio_preview_hover(None)
        self.release_project_audio_preview()
        self.visible_cover_timer.stop()
        self.cover_reveal_timer.stop()
        self.item_move_animator.finish()
        self.active_cover_animations.clear()
        self.pending_cover_animations.clear()
        self.pending_cover_animation_tiles.clear()
        self.cover_enter_sound_counter = 0
        self.visible_cover_tiles.clear()
        self.reveal_cover_tiles.clear()
        self.managed_cover_tiles.clear()
        self.cover_generation += 1
        self.pending_cover_requests.clear()
        self.cover_request_tiles.clear()
        self.cover_load_sequence = 0
        self.cover_commit_sequence = 0
        self.completed_cover_loads.clear()
        self.preloaded_cover_tiles.clear()
        self.cover_thread_pool.clear()
        self.cover_pixmap_cache.clear()
        for tile in self.list_widget.findChildren(ProjectCoverTile):
            try:
                tile.release_cover()
            except RuntimeError:
                pass
        super().hideEvent(event)

    def count_project_objects(self, map_files):
        note_count = 0
        for file in map_files:
            try:
                with open(file, "r", encoding="utf-8") as handle:
                    object_section = None
                    is_centered = False
                    for line in handle:
                        line = line.strip()
                        if line.startswith("[") and line.endswith("]"):
                            object_section = line.strip("[]") if line in ("[HitObjects]", "[Events]") else None
                            continue
                        if object_section and line and not line.startswith("//"):
                            if match_custom_hitobject_line(line, object_section) is not None:
                                note_count += 1
                                continue
                            if object_section != "HitObjects":
                                continue
                            parts = line.split(",")
                            if len(parts) >= 5:
                                try:
                                    x_val = interpreted_hitobject_x(parts[0].strip())
                                except (TypeError, ValueError):
                                    continue
                                if x_val is None:
                                    continue
                                hitsound = parts[4].strip()
                                if x_val == 384 and hitsound == "2":
                                    is_centered = not is_centered
                                elif x_val == 384 and hitsound == "8" and is_centered:
                                    continue
                            note_count += 1
            except (OSError, UnicodeError):
                pass
        return note_count

    def ensure_project_note_counts(self):
        for project in self.projects_data:
            if project["notes"] is not None:
                continue
            note_count = self.count_project_objects(project["map_files"])
            project["notes"] = note_count
            self.project_stats_cache[project["cache_key"]] = (
                project["stats_signature"],
                note_count,
            )

    def sort_projects_data(self):
        sort_mode = self.combo_sort.currentText()
        if sort_mode == "Recent":
            self.projects_data.sort(key=lambda item: item["recent_index"])
        elif sort_mode == "Name":
            self.projects_data.sort(key=lambda item: item["name"].lower())
        elif sort_mode == "Object Amount":
            self.ensure_project_note_counts()
            self.projects_data.sort(key=lambda item: item["notes"], reverse=True)

    def start_list_reveal(self):
        if self.combo_view.currentText() != "List View" or not self.isVisible():
            return
        self.list_widget.doItemsLayout()
        visible_rect = QRectF(self.list_widget.viewport().rect()).adjusted(0, -20, 0, 20)
        moves = []
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            row = self.list_widget.itemWidget(item)
            if not isinstance(row, ProjectListRow):
                continue
            target = QRectF(row.geometry())
            if not target.intersects(visible_rect):
                continue
            row.start_reveal()
            moves.append((row, target.translated(0, 12), target))
        self.item_move_animator.start(moves)

    def sort_project_items(self, index=0):
        if not hasattr(self, 'list_widget') or self.list_widget.count() != len(self.projects_data):
            self.populate_list()
            return
        self.item_move_animator.finish()
        self.update_cover_hover(None)
        records = {}
        for item_index in range(self.list_widget.count()):
            item = self.list_widget.item(item_index)
            path = item.data(Qt.ItemDataRole.UserRole)
            widget = self.list_widget.itemWidget(item)
            if not path or widget is None:
                self.populate_list()
                return
            records[path] = (item, widget, QRectF(widget.geometry()))
        scroll_value = self.list_widget.verticalScrollBar().value()
        viewport = self.list_widget.viewport()
        self.sort_projects_data()
        current_paths = [
            self.list_widget.item(item_index).data(Qt.ItemDataRole.UserRole)
            for item_index in range(self.list_widget.count())
        ]
        model = self.list_widget.model()
        root = QModelIndex()
        for target_index, project in enumerate(self.projects_data):
            path = project["path"]
            source_index = current_paths.index(path)
            if source_index == target_index:
                continue
            destination = target_index if source_index > target_index else target_index + 1
            if not model.moveRow(root, source_index, root, destination):
                self.populate_list()
                return
            current_paths.insert(target_index, current_paths.pop(source_index))
        actual_paths = [
            self.list_widget.item(item_index).data(Qt.ItemDataRole.UserRole)
            for item_index in range(self.list_widget.count())
        ]
        if actual_paths != [project["path"] for project in self.projects_data]:
            self.populate_list()
            return
        cover_view = self.combo_view.currentText() == "Cover View"
        sort_mode = self.combo_sort.currentText()
        for project in self.projects_data:
            item, widget, old_rect = records[project["path"]]
            if cover_view:
                object_count = project["notes"] if sort_mode == "Object Amount" else None
                if widget.object_count != object_count:
                    widget.object_count = object_count
                    widget.card_cache = None
                    widget.card_cache_key = None
                if self.cover_grid_cell_size > 0:
                    item.setSizeHint(QSize(self.cover_grid_cell_size, self.cover_grid_cell_size))
            else:
                display_text = project["name"]
                if sort_mode == "Object Amount":
                    display_text += f"  ({project['notes']} objects)"
                widget.set_text(display_text)
                widget.finish_reveal()
                item.setSizeHint(QSize(0, 94))
            widget.show()
        self.list_widget.doItemsLayout()
        self.list_widget.verticalScrollBar().setValue(scroll_value)
        self.list_widget.doItemsLayout()
        visible_rect = QRectF(viewport.rect()).adjusted(0, -100, 0, 100)
        moves = []
        for project in self.projects_data:
            item, widget, old_rect = records[project["path"]]
            target = QRectF(widget.geometry())
            if old_rect.intersects(visible_rect) or target.intersects(visible_rect):
                moves.append((widget, old_rect, target))
        self.item_move_animator.start(moves)
        if cover_view:
            self.schedule_visible_cover_update()

    def load_projects(self):
        if hasattr(self.editor, "clear_project_metadata_preview"):
            self.editor.clear_project_metadata_preview(force=True)
        configured_view = getattr(self.editor, "project_view_mode", "Cover View")
        configured_view = configured_view if configured_view in ("List View", "Cover View") else "Cover View"
        if self.combo_view.currentText() != configured_view:
            self.combo_view.blockSignals(True)
            self.combo_view.setCurrentText(configured_view)
            self.combo_view.blockSignals(False)
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
            map_files.sort(key=lambda file: (file.name.casefold(), file.name))
            signature = tuple(sorted(signature_parts))
            cache_key = os.path.normcase(os.path.abspath(path_str))
            active_cache_keys.add(cache_key)
            cached = self.project_stats_cache.get(cache_key)
            if cached and cached[0] == signature:
                note_count = cached[1]
            else:
                note_count = None

            self.projects_data.append({
                "path": path_str,
                "name": p.name,
                "mtime": mtime,
                "notes": note_count,
                "recent_index": idx,
                "cover_path": self.find_project_cover(p),
                "map_files": tuple(map_files),
                "cache_key": cache_key,
                "stats_signature": signature,
            })

        self.project_stats_cache = {
            key: value
            for key, value in self.project_stats_cache.items()
            if key in active_cache_keys
        }
        self.populate_list()

    def populate_list(self):
        self.item_move_animator.finish()
        self.update_cover_hover(None)
        self.cover_generation += 1
        self.pending_cover_requests.clear()
        self.cover_request_tiles.clear()
        self.cover_load_sequence = 0
        self.cover_commit_sequence = 0
        self.completed_cover_loads.clear()
        self.preloaded_cover_tiles.clear()
        self.cover_thread_pool.clear()
        self.cover_pixmap_cache.clear()
        self.active_cover_animations.clear()
        self.pending_cover_animations.clear()
        self.pending_cover_animation_tiles.clear()
        self.cover_enter_sound_counter = 0
        self.visible_cover_tiles.clear()
        self.reveal_cover_tiles.clear()
        self.managed_cover_tiles.clear()
        self.revealed_cover_paths.clear()
        self.cover_reveal_timer.stop()
        self.list_widget.clear()
        self.project_tiles = {}
        self.configure_project_view()
        self.sort_projects_data()
        sort_mode = self.combo_sort.currentText()

        cover_view = self.combo_view.currentText() == "Cover View"
        for proj in self.projects_data:
            display_text = proj["name"]
            if sort_mode == "Object Amount" and not cover_view:
                display_text += f"  ({proj['notes']} objects)"

            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, proj["path"])
            self.list_widget.addItem(item)
            if cover_view:
                object_count = proj["notes"] if sort_mode == "Object Amount" else None
                tile = ProjectCoverTile(proj["name"], proj["cover_path"], object_count)
                tile.project_path = proj["path"]
                tile.list_item = item
                tile.delete_callback = lambda project_path=proj["path"], target=tile: self.confirm_project_delete(project_path, target)
                self.project_tiles[proj["path"]] = tile
                self.list_widget.setItemWidget(item, tile)
            else:
                row = ProjectListRow(display_text)
                row.project_path = proj["path"]
                row.delete_callback = lambda project_path=proj["path"], target=row: self.confirm_project_delete(project_path, target)
                item.setSizeHint(QSize(0, 94))
                self.list_widget.setItemWidget(item, row)
        if cover_view:
            QTimer.singleShot(0, self.update_cover_grid_geometry)
        else:
            QTimer.singleShot(0, self.start_list_reveal)

    def on_item_click(self, item):
        if self.pending_project_open:
            return
        widget = self.list_widget.itemWidget(item)
        if widget is not None and hasattr(widget, "delete_icon_rect"):
            local_pos = widget.mapFromGlobal(QCursor.pos())
            if widget.delete_icon_rect().adjusted(-5.0, -5.0, 5.0, 5.0).contains(QPointF(local_pos)):
                return
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            if hasattr(self.editor, 'play_ui_sound_suppressed'):
                pan = self.editor.get_pan_for_widget(self.list_widget)
                self.editor.play_ui_sound_suppressed('UI Click', pan)
            if not self.editor.confirm_unsaved_changes("load"):
                return
            tile = widget
            if isinstance(tile, ProjectCoverTile):
                self.pending_project_open = True
                tile.start_open_animation(lambda project_path=Path(path): self.complete_project_open(project_path))
            else:
                self.editor.load_project_from_path(Path(path))

    def complete_project_open(self, path):
        self.pending_project_open = False
        self.editor.load_project_from_path(path)
