from .ui_utils import *
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
        geometry = max(1, min(self.width(), self.height()))
        if geometry != self.title_scroll_geometry:
            font = self.font()
            font.setPointSize(12)
            font.setBold(True)
            metrics = QFontMetrics(font)
            available = max(1.0, geometry - 24.0)
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
    def __init__(self, parent, title, message):
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
                if isinstance(widget, ProjectCoverTile):
                    rotation = self.rotation_directions.get(widget, 0.0) * 3.5 * math.sin(math.pi * linear)
                    widget.set_sort_rotation(rotation)
                widget.raise_()
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
        self.active_cover_animations = set()
        self.visible_cover_tiles = set()
        self.managed_cover_tiles = set()
        self.hovered_cover_item = None
        self.cover_generation = 0
        self.cover_grid_target_size = 0
        self.cover_grid_cell_size = 0
        self.cover_grid_columns = 0
        self.cover_grid_dpr = 0.0
        self.cover_screen_connection = None
        self.cover_thread_pool = QThreadPool(self)
        self.cover_thread_pool.setMaxThreadCount(1)
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
            )
        except OSError:
            tile.set_cover_pixmap(QPixmap())
            return
        tile.cover_request_key = signature
        self.cover_request_tiles[signature] = tile
        cached = self.cover_pixmap_cache.pop(signature, None)
        if cached is not None:
            self.cover_request_tiles.pop(signature, None)
            self.cover_pixmap_cache[signature] = cached
            tile.set_cover_pixmap(cached)
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
        self.pending_cover_requests.discard(signature)
        tile = self.cover_request_tiles.pop(signature, None)
        if not signature or signature[0] != self.cover_generation:
            return
        pixmap = QPixmap.fromImage(image)
        if not pixmap.isNull():
            pixmap.setDevicePixelRatio(signature[5])
        self.cover_pixmap_cache[signature] = pixmap
        while len(self.cover_pixmap_cache) > 24:
            self.cover_pixmap_cache.pop(next(iter(self.cover_pixmap_cache)))
        if tile is not None and tile.cover_request_key == signature:
            tile.set_cover_pixmap(pixmap)
            if tile in self.visible_cover_tiles:
                self.start_cover_animation(tile)

    def start_cover_animation(self, tile):
        if tile.cover_pixmap is None or tile.cover_pixmap.isNull():
            tile.set_cover_reveal_progress(1.0)
            return
        if tile in self.active_cover_animations or tile.cover_reveal_progress >= 1.0:
            return
        tile.cover_reveal_started = time.perf_counter()
        self.active_cover_animations.add(tile)

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
            except RuntimeError:
                self.active_cover_animations.discard(tile)
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
            return None, None
        project = next((item for item in self.projects_data if item["path"] == str(project_path)), None)
        map_files = project["map_files"] if project else ()
        title = project["name"] if project else project_root.name
        audio_filename = None
        for map_file in map_files:
            current_section = ""
            title_value = ""
            title_unicode = ""
            candidate_audio = None
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
                        if current_section == "[General]" and key.strip() == "AudioFilename":
                            candidate_audio = value.strip('"')
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
                break
        if audio_filename:
            try:
                audio_path = (project_root / audio_filename).resolve(strict=True)
                audio_path.relative_to(project_root)
                if audio_path.is_file():
                    return audio_path, title
            except (OSError, ValueError):
                pass
        supported = {".mp3", ".wav", ".ogg", ".flac", ".opus", ".m4a", ".aac", ".wma", ".alac", ".aiff", ".aif"}
        try:
            for audio_path in sorted(project_root.iterdir(), key=lambda item: item.name.casefold()):
                if audio_path.is_file() and audio_path.suffix.lower() in supported:
                    return audio_path, title
        except OSError:
            pass
        return None, title

    def start_project_audio_preview(self, project_path):
        self.project_preview_attempted_path = project_path
        audio_path, title = self.resolve_project_audio_preview(project_path)
        if audio_path is None:
            return
        stream = None
        try:
            stream = get_audio_engine().load_stream(audio_path, prescan=False)
            length_ms = max(0.0, stream.get_length_ms())
            start_ms = length_ms * 0.15
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
        preload_distance = visible_rect.height() // 2
        preload_rect = visible_rect.adjusted(0, -preload_distance, 0, preload_distance)
        target_size = min(768, max(192, self.cover_grid_target_size))
        visible_tiles = set()
        preload_tiles = set()
        cell_size = max(1, self.cover_grid_cell_size)
        columns = max(1, self.cover_grid_columns)
        scroll_value = self.list_widget.verticalScrollBar().value()
        first_row = max(0, (scroll_value - preload_distance) // cell_size - 1)
        last_row = (scroll_value + visible_rect.height() + preload_distance) // cell_size + 1
        first_index = max(0, int(first_row * columns))
        last_index = min(self.list_widget.count(), int((last_row + 1) * columns))
        for index in range(first_index, last_index):
            item = self.list_widget.item(index)
            tile = self.list_widget.itemWidget(item)
            if not isinstance(tile, ProjectCoverTile):
                continue
            item_rect = self.list_widget.visualItemRect(item)
            if item_rect.intersects(visible_rect):
                visible_tiles.add(tile)
            if item_rect.intersects(preload_rect):
                preload_tiles.add(tile)
                if tile.cover_pixmap is None and tile.cover_request_key is None:
                    self.request_cover_pixmap(tile, target_size)
        for tile in tuple(self.managed_cover_tiles - preload_tiles):
            try:
                tile.release_cover()
            except RuntimeError:
                self.visible_cover_tiles.discard(tile)
            self.active_cover_animations.discard(tile)
        self.managed_cover_tiles = preload_tiles
        self.visible_cover_tiles = visible_tiles
        for tile in visible_tiles:
            if tile.cover_pixmap is not None and tile.cover_reveal_progress < 1.0:
                self.start_cover_animation(tile)

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
        self.item_move_animator.finish()
        self.active_cover_animations.clear()
        self.visible_cover_tiles.clear()
        self.managed_cover_tiles.clear()
        self.cover_generation += 1
        self.pending_cover_requests.clear()
        self.cover_request_tiles.clear()
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
                widget.object_count = project["notes"] if sort_mode == "Object Amount" else None
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
        if cover_view:
            self.update_cover_grid_geometry()
        else:
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
        self.cover_thread_pool.clear()
        self.cover_pixmap_cache.clear()
        self.active_cover_animations.clear()
        self.visible_cover_tiles.clear()
        self.managed_cover_tiles.clear()
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


class CustomNotePreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.kind = "Note"
        self.length = False
        self.shape = "Circle"
        self.color = QColor("#FF4FA3")
        self.connection_color = QColor("#B52D73")
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_preview(self, kind, length, shape, color, connection_color):
        self.kind = kind
        self.length = bool(length)
        self.shape = shape
        self.color = QColor(color)
        self.connection_color = QColor(connection_color)
        self.update()

    def draw_shape(self, painter, center, radius):
        outline = QColor("#202020") if widget_ui_brightness(self) > 180 else QColor("#F0F0F0")
        painter.setPen(QPen(outline, 2))
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        brightness = widget_ui_brightness(self)
        background = max(0, brightness - 9) if brightness <= 180 else min(255, brightness + 9)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(background, background, background))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        center_y = self.height() / 2.0
        if self.kind == "Event":
            center = QPointF(self.width() / 2.0, center_y)
            painter.setPen(QPen(self.color, 4))
            painter.drawLine(QPointF(center.x(), center.y() - 30), QPointF(center.x(), center.y() + 30))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.color)
            painter.drawEllipse(center, 9, 9)
        elif self.length:
            start = QPointF(self.width() * 0.28, center_y)
            end = QPointF(self.width() * 0.72, center_y)
            painter.setPen(QPen(self.connection_color, 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)
            self.draw_shape(painter, start, 20)
            self.draw_shape(painter, end, 17)
        else:
            self.draw_shape(painter, QPointF(self.width() / 2.0, center_y), 23)
        painter.end()


class CompoundStepDialog(QDialog):
    def __init__(self, step_kind, notes, current_type_id, step=None, parent=None):
        super().__init__(parent)
        self.step_kind = "delay" if step_kind == "delay" else "object"
        self.notes = notes or []
        self.current_type_id = str(current_type_id or "")
        self.step = normalize_compound_step(step or {"kind": self.step_kind})
        self.setWindowTitle("Add Delay" if self.step_kind == "delay" else "Add Object")
        self.setModal(True)
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        form = QFormLayout()
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
            self.target_combo.currentIndexChanged.connect(self.update_object_controls)
            form.addRow("Object:", self.target_combo)
            self.lane_combo = IgnoreWheelComboBox()
            self.lane_combo.setView(SmoothListView(self.lane_combo))
            form.addRow("Lane:", self.lane_combo)
            length_widget = QWidget()
            length_layout = QHBoxLayout(length_widget)
            length_layout.setContentsMargins(0, 0, 0, 0)
            self.length_value = QDoubleSpinBox()
            self.length_value.setRange(0.001, 1000000.0)
            self.length_value.setDecimals(3)
            self.length_value.setValue(max(0.001, float(self.step.get("length_value", 1.0))))
            self.length_unit = IgnoreWheelComboBox()
            self.length_unit.addItem("Beats", "beats")
            self.length_unit.addItem("Milliseconds", "ms")
            unit_index = self.length_unit.findData(self.step.get("length_unit", "beats"))
            self.length_unit.setCurrentIndex(max(0, unit_index))
            length_layout.addWidget(self.length_value, 1)
            length_layout.addWidget(self.length_unit, 1)
            self.length_widget = length_widget
            form.addRow("Length:", length_widget)
        else:
            delay_widget = QWidget()
            delay_layout = QHBoxLayout(delay_widget)
            delay_layout.setContentsMargins(0, 0, 0, 0)
            self.delay_value = QDoubleSpinBox()
            self.delay_value.setRange(0.001, 1000000.0)
            self.delay_value.setDecimals(3)
            self.delay_value.setValue(max(0.001, float(self.step.get("value", 1.0))))
            self.delay_unit = IgnoreWheelComboBox()
            self.delay_unit.addItem("Beats", "beats")
            self.delay_unit.addItem("Milliseconds", "ms")
            unit_index = self.delay_unit.findData(self.step.get("unit", "beats"))
            self.delay_unit.setCurrentIndex(max(0, unit_index))
            delay_layout.addWidget(self.delay_value, 1)
            delay_layout.addWidget(self.delay_unit, 1)
            form.addRow("Delay:", delay_widget)
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
            self.update_object_controls()

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
        self.length_widget.setEnabled(enabled)
        self.length_widget.setToolTip("" if enabled else "This object has no tail length.")

    def accept(self):
        if self.step_kind == "delay":
            self.step = normalize_compound_step({
                "kind": "delay",
                "value": self.delay_value.value(),
                "unit": self.delay_unit.currentData(),
            })
        else:
            self.step = normalize_compound_step({
                "kind": "object",
                "target": self.target_combo.currentData(),
                "lane": self.lane_combo.currentText(),
                "length_value": self.length_value.value(),
                "length_unit": self.length_unit.currentData(),
            })
        super().accept()


class CustomNoteEditorDialog(QDialog):
    def __init__(self, note, parent=None, available_notes=None):
        super().__init__(parent)
        self.note = normalize_custom_note(copy.deepcopy(note))
        self.available_notes = normalize_custom_notes(copy.deepcopy(available_notes or []))
        self.current_compound_steps = []
        self.current_type_index = -1
        self.loading_type = False
        self.setWindowTitle("Custom Note")
        self.setFixedSize(780, 720)
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
        self.type_list.setMinimumWidth(180)
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
        self.lane_top_edit.setMaximumWidth(74)
        self.lane_bottom_label = QLabel("Bottom:")
        self.lane_bottom_edit = QLineEdit()
        self.lane_bottom_edit.setValidator(QIntValidator(-2147483648, 2147483647, self.lane_bottom_edit))
        self.lane_bottom_edit.setMaximumWidth(74)
        self.lane_single_label = QLabel("Value:")
        self.lane_single_edit = QLineEdit()
        self.lane_single_edit.setValidator(QIntValidator(-2147483648, 2147483647, self.lane_single_edit))
        self.lane_single_edit.setMaximumWidth(74)
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
        self.compound_list.setMinimumHeight(245)
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
        self.type_list.setCurrentRow(0)

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
        self.syntax_edit.setText(item["syntax"])
        self.lane_top_edit.setText(str(item["lane_top_value"]))
        self.lane_bottom_edit.setText(str(item["lane_bottom_value"]))
        self.lane_single_edit.setText(str(item["lane_single_value"]))
        self.current_compound_steps = copy.deepcopy(item.get("steps", []))
        self.refresh_compound_list()
        self.loading_type = False
        self.update_type_controls()
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
                unit = "beats" if step.get("unit") == "beats" else "ms"
                text = f"Delay — {float(step.get('value', 0)):g} {unit}"
            else:
                text = self.compound_target_label(step.get("target"))
                text += f" — {step.get('lane', 'Placement')}"
                if compound_target_is_length(step.get("target"), notes):
                    unit = "beats" if step.get("length_unit") == "beats" else "ms"
                    text += f" — length {float(step.get('length_value', 1)):g} {unit}"
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
            QMessageBox.information(self, "Custom Notes", "A custom note must contain at least one type.")
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


class CustomNotesDialog(QDialog):
    def __init__(self, notes, tombstones, parent=None):
        super().__init__(parent)
        self.original_notes = normalize_custom_notes(copy.deepcopy(notes))
        self.notes = normalize_custom_notes(copy.deepcopy(notes))
        self.tombstones = normalize_custom_tombstones(copy.deepcopy(tombstones))
        self.setWindowTitle("Custom Notes")
        self.setFixedSize(520, 560)
        layout = QVBoxLayout(self)
        self.note_list = QListWidget()
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
        dialog = CustomNoteEditorDialog(note, self, self.notes)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.notes.append(dialog.note)
            self.refresh_list()
            self.note_list.setCurrentRow(len(self.notes) - 1)

    def edit_note(self, item=None):
        index = self.note_list.currentRow()
        if index < 0:
            return
        dialog = CustomNoteEditorDialog(self.notes[index], self, self.notes)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.notes[index] = dialog.note
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
        super().accept()


class SettingsDialog(QDialog):
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

    def __init__(self, parent, current_scale, current_master_vol, current_music_vol, current_fx_vol, current_ui_vol, current_colors, game_root, event_default_order="Before", enable_3d_sound=True, enable_visualizer=True, enable_beatflash=True, auto_save=False, file_extension=".txt", geometry=None, grid_opacity=50, visualizer_opacity=10, background_opacity=20, grid_thickness=2, current_background="None", preview_bg_opacity=30, lane_opacity=100, background_blur=0, ui_brightness=60, current_keybinds=None, custom_notes_enabled=True, custom_notes=None, custom_note_tombstones=None):
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

        editor_layout.addWidget(QLabel("Update Channel:"))
        self.combo_update_channel = IgnoreWheelComboBox()
        self.combo_update_channel.setToolTip("Choose between official Stable and Preview updates")
        self.combo_update_channel.setView(SmoothListView(self.combo_update_channel))
        self.combo_update_channel.addItems(["Stable", "Preview"])
        self.combo_update_channel.setCurrentText(getattr(parent, "update_channel", "Stable"))
        self.combo_update_channel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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

        if sys.platform.startswith("win"):
            run_setup_btn = QPushButton("Run Setup")
            run_setup_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            def run_setup():
                parent_window = self.parent_window
                self.reject()
                QTimer.singleShot(0, parent_window.restart_for_setup)
            run_setup_btn.clicked.connect(run_setup)
            info_layout.addWidget(run_setup_btn)
        
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
        text += "Video processing uses a minimal FFmpeg 8.1.2 build with x264, libvpx and dav1d under GPL-2.0-or-later. Complete notices and build information are included with the application.\n"
        text += "The Linux UI uses Microsoft Selawik, licensed under the SIL Open Font License 1.1.\n"
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

    def get_update_channel(self):
        return self.combo_update_channel.currentText()

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
                    uid=obj[11],
                    custom_data=custom_object_data_from_tuple(obj[12] if len(obj) > 12 else None)
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


