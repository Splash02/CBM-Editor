from .dialogs import *
from PyQt6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, pyqtProperty
from PyQt6.QtGui import QCursor, QPainterPath, QPicture, QRegion
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QStyle, QStyleOptionTab, QStyleOptionViewItem, QStyledItemDelegate, QTabBar, QTabWidget

register_shared_globals(globals())

def find_layered_note_groups(beatmap):
    groups = {}
    for obj in beatmap.hit_objects:
        if obj.is_event:
            continue
        if obj.custom_data is not None and (
            obj.custom_data.missing or get_custom_type(obj.custom_data.type_id) is None
        ):
            continue
        key = (int(obj.time), int(obj.lane))
        groups.setdefault(key, []).append(obj)
    return tuple(
        (time_ms, lane, tuple(objects))
        for (time_ms, lane), objects in sorted(groups.items())
        if len(objects) > 1
    )

class ObjectOrderDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        owner = self.parent()
        scale = max(0.5, float(getattr(owner.window(), 'global_scale', 1.0)))
        if owner._drag_row == index.row() and not owner._painting_drag_overlay:
            return
        adjusted = QStyleOptionViewItem(option)
        uid = index.data(Qt.ItemDataRole.UserRole)
        adjusted.rect.translate(0, int(round(owner._animated_offsets.get(uid, 0.0))))
        adjusted.state &= ~(
            QStyle.StateFlag.State_MouseOver
            | QStyle.StateFlag.State_Selected
            | QStyle.StateFlag.State_HasFocus
        )
        super().paint(painter, adjusted, index)
        brightness = owner._item_brightness.get(uid, 0.0)
        if brightness > 0.001:
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, int(round(35 * brightness))))
            painter.drawRoundedRect(
                QRectF(adjusted.rect).adjusted(0, 3.0 * scale, 0, -3.0 * scale),
                8.0 * scale,
                8.0 * scale,
            )
            painter.restore()


class ObjectOrderList(SmoothScrollMixin, QListWidget):
    orderChanged = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoScroll(False)
        self.init_smooth_scroll()
        self.viewport().removeEventFilter(self)
        self.sc_drag_targets.discard(self.viewport())
        self.verticalScrollBar().setProperty("transparentTrack", True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setSpacing(4)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setMouseTracking(True)
        self.setItemDelegate(ObjectOrderDelegate(self))
        self._press_pos = None
        self._press_row = -1
        self._drag_row = -1
        self._preview_row = -1
        self._drag_pointer_offset = 0.0
        self._drag_y = 0.0
        self._settle_from_y = 0.0
        self._settle_to_y = 0.0
        self._settle_started = 0.0
        self._settling = False
        self._settle_progress = 0.0
        self._painting_drag_overlay = False
        self._animated_offsets = {}
        self._target_offsets = {}
        self._hover_uid = None
        self._item_brightness = {}
        self._brightness_targets = {}
        self._last_animation_time = time.perf_counter()

    def showEvent(self, event):
        super().showEvent(event)
        self.sc_reset_to_native()

    def hideEvent(self, event):
        self.sc_reset_to_native()
        super().hideEvent(event)

    def apply_ui_scale(self):
        scale = max(0.5, float(getattr(self.window(), 'global_scale', 1.0)))
        self.setSpacing(max(2, int(round(4 * scale))))
        row_height = max(16, int(round(38 * scale)))
        for row in range(self.count()):
            self.item(row).setSizeHint(QSize(0, row_height))
        self.viewport().update()

    def clear(self):
        self.cancel_reorder()
        super().clear()

    def cancel_reorder(self, reset_highlights=True):
        self._press_pos = None
        self._press_row = -1
        self._drag_row = -1
        self._preview_row = -1
        self._settling = False
        self._settle_progress = 0.0
        self._painting_drag_overlay = False
        self._animated_offsets.clear()
        self._target_offsets.clear()
        if reset_highlights:
            self._hover_uid = None
            self._item_brightness.clear()
            self._brightness_targets.clear()
        self.unsetCursor()
        self.viewport().update()

    def _set_highlight(self, uid, strength):
        self._hover_uid = uid
        valid_uids = {
            self.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.count())
        }
        for item_uid in valid_uids:
            self._item_brightness.setdefault(item_uid, 0.0)
            self._brightness_targets[item_uid] = strength if item_uid == uid else 0.0
        for item_uid in tuple(self._item_brightness):
            if item_uid not in valid_uids:
                self._item_brightness.pop(item_uid, None)
                self._brightness_targets.pop(item_uid, None)
        self._last_animation_time = time.perf_counter()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() != Qt.MouseButton.LeftButton or not self.dragEnabled():
            self._press_pos = None
            self._press_row = -1
            return
        item = self.itemAt(event.position().toPoint())
        self._press_pos = event.position().toPoint() if item is not None else None
        self._press_row = self.row(item) if item is not None else -1

    def mouseMoveEvent(self, event):
        position = event.position().toPoint()
        if self._drag_row < 0 and self._press_pos is not None:
            if (position - self._press_pos).manhattanLength() >= QApplication.startDragDistance():
                self._begin_reorder(position)
        if self._drag_row >= 0:
            if not self._settling:
                self._drag_y = self._clamp_drag_y(float(position.y()) - self._drag_pointer_offset)
                preview_row = self._row_nearest(position.y())
                if preview_row != self._preview_row:
                    self._preview_row = preview_row
                    self._update_target_offsets()
                self.viewport().update()
            event.accept()
            return
        item = self.itemAt(position)
        uid = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if uid != self._hover_uid:
            self._set_highlight(uid, 0.46)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._drag_row < 0:
            self._set_highlight(None, 0.0)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_row >= 0 and event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = None
            self._press_row = -1
            target_rect = self.visualItemRect(self.item(self._preview_row))
            self._settle_from_y = self._drag_y
            self._settle_to_y = float(target_rect.top())
            self._settle_started = time.perf_counter()
            self._settling = True
            self._settle_progress = 0.0
            self._set_highlight(None, 0.0)
            self.unsetCursor()
            self.viewport().update()
            event.accept()
            return
        self._press_pos = None
        self._press_row = -1
        super().mouseReleaseEvent(event)

    def _begin_reorder(self, position):
        if self._press_row < 0 or self._press_row >= self.count():
            return
        self._drag_row = self._press_row
        self._preview_row = self._drag_row
        source_rect = self.visualItemRect(self.item(self._drag_row))
        self._drag_pointer_offset = float(self._press_pos.y() - source_rect.top())
        self._drag_y = self._clamp_drag_y(float(position.y()) - self._drag_pointer_offset)
        self._last_animation_time = time.perf_counter()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        uid = self.item(self._drag_row).data(Qt.ItemDataRole.UserRole)
        self._set_highlight(uid, 1.0)
        self._update_target_offsets()

    def _row_nearest(self, y):
        if self.count() <= 1:
            return 0
        return min(
            range(self.count()),
            key=lambda row: abs(self.visualItemRect(self.item(row)).center().y() - y),
        )

    def _clamp_drag_y(self, y):
        if self.count() == 0 or self._drag_row < 0:
            return float(y)
        source_height = self.visualItemRect(self.item(self._drag_row)).height()
        minimum = float(self.visualItemRect(self.item(0)).top())
        maximum = float(self.visualItemRect(self.item(self.count() - 1)).bottom() - source_height + 1)
        return max(minimum, min(maximum, float(y)))

    def _update_target_offsets(self):
        slots = [self.visualItemRect(self.item(row)).top() for row in range(self.count())]
        remaining = [row for row in range(self.count()) if row != self._drag_row]
        remaining.insert(self._preview_row, None)
        targets = {}
        for slot, row in enumerate(remaining):
            if row is None:
                continue
            item = self.item(row)
            uid = item.data(Qt.ItemDataRole.UserRole)
            targets[uid] = float(slots[slot] - self.visualItemRect(item).top())
            self._animated_offsets.setdefault(uid, 0.0)
        self._target_offsets = targets

    def advance_animation(self, now):
        dt = max(0.0, min(0.05, now - self._last_animation_time))
        self._last_animation_time = now
        brightness_factor = 1.0 - math.exp(-19.0 * dt)
        brightness_moving = False
        for uid, target in tuple(self._brightness_targets.items()):
            current = self._item_brightness.get(uid, 0.0)
            updated = current + (target - current) * brightness_factor
            if abs(target - updated) < 0.004:
                updated = target
            else:
                brightness_moving = True
            self._item_brightness[uid] = updated
        if self._drag_row < 0:
            if brightness_moving:
                self.viewport().update()
            return brightness_moving
        factor = 1.0 - math.exp(-28.0 * dt)
        moving = False
        for uid, target in self._target_offsets.items():
            current = self._animated_offsets.get(uid, 0.0)
            updated = current + (target - current) * factor
            if abs(target - updated) < 0.08:
                updated = target
            else:
                moving = True
            self._animated_offsets[uid] = updated
        if self._settling:
            linear = min(1.0, max(0.0, (now - self._settle_started) / 0.24))
            eased = 1.0 - (1.0 - linear) ** 3
            self._settle_progress = eased
            self._drag_y = self._settle_from_y + (self._settle_to_y - self._settle_from_y) * eased
            moving = moving or linear < 1.0
            if linear >= 1.0 and not any(
                abs(self._target_offsets.get(uid, 0.0) - value) >= 0.08
                for uid, value in self._animated_offsets.items()
            ):
                self._finish_reorder()
                return False
        self.viewport().update()
        return moving or brightness_moving or not self._settling

    def _finish_reorder(self):
        source_row = self._drag_row
        target_row = self._preview_row
        before = [self.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self.count())]
        if source_row != target_row:
            item = self.takeItem(source_row)
            self.insertItem(target_row, item)
        after = [self.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self.count())]
        self.cancel_reorder(reset_highlights=False)
        if before != after:
            self.orderChanged.emit(after)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drag_row < 0 or self._drag_row >= self.count():
            return
        index = self.model().index(self._drag_row, 0)
        source_rect = self.visualItemRect(self.item(self._drag_row))
        option = QStyleOptionViewItem()
        self.initViewItemOption(option)
        option.rect = QRect(source_rect.x(), int(round(self._drag_y)), source_rect.width(), source_rect.height())
        option.state |= QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_Active
        painter = QPainter(self.viewport())
        painter.setOpacity(0.94 + (0.06 * self._settle_progress if self._settling else 0.0))
        self._painting_drag_overlay = True
        self.itemDelegate().paint(painter, option, index)
        self._painting_drag_overlay = False


class EqualWidthTabBar(QTabBar):
    def __init__(self, panel, parent=None):
        super().__init__(parent)
        self.panel = panel
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hover_index = -1
        self._hover_progress = []
        self._click_flash = []
        self._last_animation_time = time.perf_counter()
        self.setMouseTracking(True)

    def tabSizeHint(self, index):
        size = super().tabSizeHint(index)
        if self.count() > 0 and self.width() > 0:
            size.setWidth(max(1, self.width() // self.count()))
        return size

    def tabInserted(self, index):
        super().tabInserted(index)
        self._hover_progress.insert(index, 0.0)
        self._click_flash.insert(index, 0.0)

    def tabRemoved(self, index):
        super().tabRemoved(index)
        if index < len(self._hover_progress):
            self._hover_progress.pop(index)
            self._click_flash.pop(index)

    def mouseMoveEvent(self, event):
        hover_index = self.tabAt(event.position().toPoint())
        if hover_index != self._hover_index:
            self._hover_index = hover_index
            self._last_animation_time = time.perf_counter()
            activate_ui_animation(self)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_index = -1
        self._last_animation_time = time.perf_counter()
        activate_ui_animation(self)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        index = self.tabAt(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and index >= 0 and self.isTabEnabled(index):
            while len(self._click_flash) < self.count():
                self._click_flash.append(0.0)
            self._click_flash[index] = 1.0
            self._last_animation_time = time.perf_counter()
            activate_ui_animation(self)
            self.panel.play_control_sound(self)
        super().mousePressEvent(event)

    def advance_ui_animation(self, now):
        dt = min(0.05, max(0.0, now - self._last_animation_time))
        self._last_animation_time = now
        active = False
        while len(self._hover_progress) < self.count():
            self._hover_progress.append(0.0)
            self._click_flash.append(0.0)
        step = dt / 0.12
        for index in range(self.count()):
            target = 1.0 if index == self._hover_index else 0.0
            current = self._hover_progress[index]
            if current < target:
                current = min(target, current + step)
            elif current > target:
                current = max(target, current - step)
            self._hover_progress[index] = current
            self._click_flash[index] = max(0.0, self._click_flash[index] - dt / 0.16)
            active = active or abs(current - target) > 0.001 or self._click_flash[index] > 0.001
        self.update()
        return active

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for index in range(self.count()):
            option = QStyleOptionTab()
            self.initStyleOption(option, index)
            option.state &= ~QStyle.StateFlag.State_MouseOver
            self.style().drawControl(QStyle.ControlElement.CE_TabBarTabShape, option, painter, self)
            hover = self._hover_progress[index] if index < len(self._hover_progress) else 0.0
            flash = self._click_flash[index] if index < len(self._click_flash) else 0.0
            strength = min(1.0, hover * 0.12 + flash * 0.42)
            if strength > 0.001:
                brightness = int(getattr(self.panel.editor, 'ui_brightness', 60))
                shade = 0 if brightness > 180 else 255
                overlay = QColor(shade, shade, shade, int(round(255 * strength)))
                scale = max(0.5, float(getattr(self.panel.editor, 'global_scale', 1.0)))
                overlay_rect = QRectF(self.tabRect(index)).adjusted(
                    2.0 * scale,
                    1.0 * scale,
                    -2.0 * scale,
                    -5.0 * scale,
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(overlay)
                painter.drawRoundedRect(overlay_rect, 7.0 * scale, 7.0 * scale)
            self.style().drawControl(QStyle.ControlElement.CE_TabBarTabLabel, option, painter, self)


class TimelineChevronButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0.0
        self.surface_color = QColor(34, 34, 34)
        self.hover_color = QColor(47, 47, 47)
        self.pressed_color = QColor(54, 54, 54)
        self.outline_color = QColor(255, 255, 255, 36)
        self.text_color = QColor(238, 238, 238)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent; border: none; padding: 0px;")

    def set_theme(self, surface, hover, pressed, outline, text):
        self.surface_color = QColor(surface)
        self.hover_color = QColor(hover)
        self.pressed_color = QColor(pressed)
        self.outline_color = QColor(outline)
        self.text_color = QColor(text)
        self.update()

    def set_progress(self, progress):
        self.progress = max(0.0, min(1.0, float(progress)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.pressed_color if self.isDown() else self.surface_color)
        width = float(self.width())
        height = float(self.height())
        radius = min(9.0 * getattr(self.parent().editor, 'global_scale', 1.0), height * 0.5)
        surface = QPainterPath()
        surface.moveTo(width, 0.0)
        surface.lineTo(radius, 0.0)
        surface.quadTo(0.0, 0.0, 0.0, radius)
        surface.lineTo(0.0, height - radius)
        surface.quadTo(0.0, height, radius, height)
        surface.lineTo(width, height)
        surface.closeSubpath()
        painter.fillPath(surface, color)
        strength = min(1.0, getattr(self, '_hover_progress', 0.0) * 0.16 + getattr(self, '_action_pulse', 0.0) * 0.62)
        if strength > 0.001:
            painter.fillPath(surface, QColor(255, 255, 255, int(round(255 * strength))))
        outline = QPainterPath()
        outline.moveTo(width, 0.5)
        outline.lineTo(radius, 0.5)
        outline.quadTo(0.5, 0.5, 0.5, radius)
        outline.lineTo(0.5, height - radius)
        outline.quadTo(0.5, height - 0.5, radius, height - 0.5)
        outline.lineTo(width, height - 0.5)
        painter.setPen(QPen(self.outline_color, 1.0))
        painter.drawPath(outline)
        color = QColor(self.text_color)
        if not self.isEnabled():
            color.setAlpha(100)
        pen = QPen(color, max(1.5, 2.0 * getattr(self.parent().editor, 'global_scale', 1.0)))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        center = self.rect().center()
        direction = math.cos(math.pi * self.progress)
        half_width = max(2.0, self.width() * 0.2) * direction
        half_height = max(7.0, self.height() * 0.16)
        painter.drawLine(QPointF(center.x() + half_width, center.y() - half_height), QPointF(center.x() - half_width, center.y()))
        painter.drawLine(QPointF(center.x() - half_width, center.y()), QPointF(center.x() + half_width, center.y() + half_height))


class ClipboardPreviewCard(QPushButton):
    def __init__(self, panel, entry):
        super().__init__(panel.clipboard_container)
        self.panel = panel
        self.entry = entry
        self._preview_pixmap = None
        self._preview_cache_key = None
        self._target_height = 0
        self._appear_started = 0.0
        self._appear_active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents, True)
        self.setProperty("defer_scroll_control_click", True)
        self.setProperty("is_custom_sound_btn", True)
        self.pressed.connect(lambda: panel.play_control_sound(self))
        self.clicked.connect(lambda: panel.activate_clipboard_entry(self.entry))
        self.setStyleSheet("background: transparent; border: none;")
        self._appear_effect = QGraphicsOpacityEffect(self)
        self._appear_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._appear_effect)

    def set_target_height(self, height):
        self._target_height = max(1, int(height))
        self.setMinimumHeight(self._target_height)
        self.setMaximumHeight(self._target_height)
        if self.height() != self._target_height:
            self.resize(max(1, self.width()), self._target_height)
        self.updateGeometry()

    def sizeHint(self):
        hint = super().sizeHint()
        if self._target_height > 0:
            hint.setHeight(self._target_height)
        return hint

    def minimumSizeHint(self):
        return self.sizeHint()

    def start_appear(self):
        if self._appear_effect is None or self._appear_active:
            return
        self._appear_effect.setOpacity(0.0)
        self._appear_started = time.perf_counter()
        self._appear_active = True
        activate_ui_animation(self)

    def finish_appear(self):
        self._appear_active = False
        if self._appear_effect is not None:
            self._appear_effect.setOpacity(1.0)
            self.setGraphicsEffect(None)
            self._appear_effect = None

    def advance_ui_animation(self, now):
        base_active = super().advance_ui_animation(now)
        if self._appear_active and self._appear_effect is not None:
            linear = min(1.0, max(0.0, (now - self._appear_started) / 0.19))
            eased = 1.0 - math.pow(1.0 - linear, 3.0)
            self._appear_effect.setOpacity(eased)
            if linear >= 1.0:
                self.finish_appear()
        return base_active or self._appear_active

    def update_style(self):
        self._preview_cache_key = None
        self._preview_pixmap = None
        self.update()

    def resizeEvent(self, event):
        self._preview_cache_key = None
        self._preview_pixmap = None
        super().resizeEvent(event)

    def ensure_preview(self):
        if self.entry.get('preview') is None:
            preview, duration = self.panel.timeline.build_clipboard_preview(self.entry['items'])
            self.entry['preview'] = preview
            self.entry['duration'] = duration
        brightness = int(getattr(self.panel.editor, 'ui_brightness', 60))
        scale = max(0.5, float(getattr(self.panel.editor, 'global_scale', 1.0)))
        dpr = max(1.0, float(self.devicePixelRatioF()))
        key = (self.width(), self.height(), round(dpr, 2), brightness, round(scale, 3))
        if key == self._preview_cache_key and self._preview_pixmap is not None:
            return
        width = max(1, self.width())
        height = max(1, self.height())
        pixmap = QPixmap(max(1, int(math.ceil(width * dpr))), max(1, int(math.ceil(height * dpr))))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        light = brightness > 180
        base = QColor(0, 0, 0, 17) if light else QColor(255, 255, 255, 11)
        outline = QColor(0, 0, 0, 40) if light else QColor(255, 255, 255, 24)
        text_color = QColor(45, 45, 45) if light else QColor(190, 190, 190)
        rect = QRectF(0.5, 0.5, width - 1.0, height - 1.0)
        painter.setPen(QPen(outline, max(0.5, scale)))
        painter.setBrush(base)
        painter.drawRoundedRect(rect, 11.0 * scale, 11.0 * scale)
        left = 13.0 * scale
        right = max(left + 1.0, width - 13.0 * scale)
        top = 12.0 * scale
        bottom = max(top + 1.0, height - 31.0 * scale)
        lane_y = {
            0: top + (bottom - top) * 0.08,
            1: top + (bottom - top) * 0.31,
            2: top + (bottom - top) * 0.50,
            3: top + (bottom - top) * 0.69,
            4: top + (bottom - top) * 0.92,
        }
        lane_color = QColor(0, 0, 0, 34) if brightness > 180 else QColor(255, 255, 255, 24)
        painter.setPen(QPen(lane_color, max(0.5, scale)))
        for row in (0, 1, 3, 4):
            painter.drawLine(QPointF(left, lane_y[row]), QPointF(right, lane_y[row]))
        scale_x = max(1.0, right - left)
        count = max(1, int(self.entry['count']))
        duration = max(0, int(self.entry['duration']))
        density_scale = min(1.0, math.log2(count + 1) / 7.5)
        length_scale = min(1.0, duration / 40000.0)
        radius = max(2.2, min(6.2, 6.2 - density_scale * 3.3 - length_scale * 1.0)) * scale
        for snapshot in self.entry['preview']:
            start, end, row, end_row, pair_row, head_rgba, line_rgba, tail_rgba, diagonal, event_kind = snapshot
            start_x = left + (start / 255.0) * scale_x
            end_x = left + (end / 255.0) * scale_x
            if event_kind:
                color = QColor.fromRgba(head_rgba)
                color.setAlpha(max(95, color.alpha()))
                painter.setPen(QPen(color, max(0.5, radius * 0.45)))
                painter.drawLine(QPointF(start_x, lane_y[0]), QPointF(start_x, lane_y[4]))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor("white") if event_kind == 2 else color)
                painter.drawEllipse(QPointF(start_x, lane_y[2]), radius, radius)
                continue
            if line_rgba and end > start:
                painter.setPen(QPen(QColor.fromRgba(line_rgba), max(0.7, radius * 0.75), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                target_row = end_row if diagonal else row
                painter.drawLine(QPointF(start_x, lane_y[row]), QPointF(end_x, lane_y[target_row]))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor.fromRgba(tail_rgba))
                painter.drawEllipse(QPointF(end_x, lane_y[target_row]), radius, radius)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor.fromRgba(head_rgba))
            painter.drawEllipse(QPointF(start_x, lane_y[row]), radius, radius)
            if pair_row >= 0:
                painter.drawEllipse(QPointF(start_x, lane_y[pair_row]), radius, radius)
        count_text = f"{count} object{'s' if count != 1 else ''}"
        if duration > 0:
            count_text += f"  ·  {duration / 1000.0:.2f} s"
        font = QFont(painter.font())
        font.setPixelSize(max(5, int(round(12 * scale))))
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(
            QRectF(12.0 * scale, height - 28.0 * scale, width - 24.0 * scale, 20.0 * scale),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            count_text,
        )
        painter.end()
        self._preview_cache_key = key
        self._preview_pixmap = pixmap

    def paintEvent(self, event):
        painter = QPainter(self)
        self.ensure_preview()
        if self._preview_pixmap is not None:
            painter.drawPixmap(0, 0, self._preview_pixmap)
        strength = min(1.0, getattr(self, '_hover_progress', 0.0) * 0.16 + getattr(self, '_action_pulse', 0.0) * 0.62)
        if strength > 0.001:
            scale = max(0.5, float(getattr(self.panel.editor, 'global_scale', 1.0)))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, int(round(255 * strength))))
            inset = max(0.5, scale)
            painter.drawRoundedRect(
                QRectF(self.rect()).adjusted(inset, inset, -inset, -inset),
                10.0 * scale,
                10.0 * scale,
            )
        painter.end()


class VerifyIssueCard(QWidget):
    removed = pyqtSignal(str)
    activated = pyqtSignal(str)

    def __init__(self, issue_id, title, detail, parent=None):
        super().__init__(parent)
        self.issue_id = issue_id
        self.setObjectName("VerifyIssueCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: 700;")
        self.detail_label = QLabel(detail)
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.detail_label)
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self._animation = None
        self._actionable = False
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.detail_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.update_style(widget_ui_brightness(self))

    def set_actionable(self, actionable):
        self._actionable = bool(actionable)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._actionable else Qt.CursorShape.ArrowCursor)
        self.setToolTip("Go to layered notes" if self._actionable else "")

    def mouseReleaseEvent(self, event):
        if (
            self._actionable
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.activated.emit(self.issue_id)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def update_style(self, brightness):
        scale = max(0.5, widget_ui_scale(self))
        px = lambda value, minimum=0: max(minimum, int(round(value * scale)))
        layout = self.layout()
        layout.setContentsMargins(px(10, 3), px(8, 2), px(10, 3), px(8, 2))
        layout.setSpacing(px(2, 1))
        light = int(brightness) > 180
        title = "#171717" if light else "#eeeeee"
        detail = "#4f4f4f" if light else "#bdbdbd"
        surface = "rgba(0,0,0,12)" if light else "rgba(255,255,255,14)"
        depth = "rgba(0,0,0,45)" if light else "rgba(0,0,0,75)"
        self.title_label.setStyleSheet(f"font-weight: 700; color: {title};")
        self.detail_label.setStyleSheet(f"color: {detail};")
        self.setStyleSheet(scale_stylesheet_dimensions(
            f"#VerifyIssueCard {{ background-color: {surface}; border: none; border-bottom: 3px solid {depth}; border-radius: 9px; }}"
        , scale))

    def update_content(self, title, detail):
        if self._animation is not None:
            self._animation.stop()
            self._animation = None
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.opacity_effect.setOpacity(1.0)
        self.title_label.setText(title)
        self.detail_label.setText(detail)

    def animate_out(self):
        if self._animation is not None:
            return
        current_height = max(1, self.height())
        self.setMinimumHeight(0)
        height_animation = QPropertyAnimation(self, b"maximumHeight")
        height_animation.setDuration(210)
        height_animation.setStartValue(current_height)
        height_animation.setEndValue(0)
        height_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        opacity_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        opacity_animation.setDuration(170)
        opacity_animation.setStartValue(self.opacity_effect.opacity())
        opacity_animation.setEndValue(0.0)
        group = QParallelAnimationGroup(self)
        group.addAnimation(height_animation)
        group.addAnimation(opacity_animation)
        group.finished.connect(lambda: self.removed.emit(self.issue_id))
        self._animation = group
        group.start()


class TimelineSidePanel(QWidget):
    def __init__(self, timeline):
        super().__init__(timeline)
        self.timeline = timeline
        self.editor = timeline.editor
        self._slide_progress = 0.0
        self._open = False
        self._available = False
        self._object_signature = None
        self._issue_cards = {}
        self._missing_custom_cache = {}
        self._layered_note_cache = {}
        self._verify_targets = {}
        self._clipboard_cards = {}
        self._clipboard_signature = None
        self._slide_animation_active = False
        self._slide_animation_started = 0.0
        self._slide_animation_from = 0.0
        self._slide_animation_to = 0.0
        self._slide_animation_duration = 0.36
        self._sidebar_background_opacity = max(0.0, min(1.0, float(getattr(self.editor, "side_menu_opacity", 97)) / 100.0))
        self._panel_color = QColor(34, 34, 34, 248)
        self._outline_color = QColor(255, 255, 255, 36)
        self.setObjectName("TimelineSidePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(50)
        self.refresh_timer.timeout.connect(self.refresh_active_tab)

        self.main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("TimelineSidePanelTabs")
        self.tabs.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tabs.setTabBar(EqualWidthTabBar(self, self.tabs))
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setExpanding(True)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.main_layout.addWidget(self.tabs)

        object_page = QWidget()
        object_page.setStyleSheet("background: transparent; border: none;")
        self.object_layout = QVBoxLayout(object_page)
        self.object_time_label = QLabel("No objects at the playhead")
        self.object_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.object_order_list = ObjectOrderList()
        self.object_order_list.setObjectName("ObjectOrderList")
        self.object_order_list.orderChanged.connect(self._apply_object_order)
        self.object_layout.addWidget(self.object_time_label)
        self.object_layout.addWidget(self.object_order_list)
        self.tabs.addTab(object_page, "Order")

        clipboard_page = QWidget()
        clipboard_page.setStyleSheet("background: transparent; border: none;")
        self.clipboard_layout = QVBoxLayout(clipboard_page)
        self.clipboard_empty_label = QLabel("Clipboard history is empty")
        self.clipboard_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clipboard_layout.addWidget(self.clipboard_empty_label)
        self.clipboard_scroll = SmoothScrollArea()
        self.clipboard_scroll.setObjectName("TimelineClipboardScroll")
        self.clipboard_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clipboard_scroll.verticalScrollBar().setProperty("transparentTrack", True)
        self.clipboard_scroll.setWidgetResizable(True)
        self.clipboard_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.clipboard_scroll.verticalScrollBar().rangeChanged.connect(self._update_clipboard_content_padding)
        self.clipboard_scroll.verticalScrollBar().valueChanged.connect(self._sync_clipboard_card_hovers)
        self.clipboard_container = QWidget()
        self.clipboard_container.setStyleSheet("background: transparent; border: none;")
        self.clipboard_cards_layout = QVBoxLayout(self.clipboard_container)
        self.clipboard_cards_layout.setContentsMargins(0, 0, 8, 0)
        self.clipboard_cards_layout.setSpacing(7)
        self.clipboard_cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.clipboard_scroll.setWidget(self.clipboard_container)
        self.clipboard_layout.addWidget(self.clipboard_scroll)
        self.tabs.addTab(clipboard_page, "Clipboard")

        verify_page = QWidget()
        verify_page.setStyleSheet("background: transparent; border: none;")
        self.verify_layout = QVBoxLayout(verify_page)
        self.verify_summary = QLabel("No issues found")
        self.verify_summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.verify_layout.addWidget(self.verify_summary)
        self.verify_scroll = QScrollArea()
        self.verify_scroll.setObjectName("TimelineVerifyScroll")
        self.verify_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.verify_scroll.setVerticalScrollBar(RoundedScrollBar(Qt.Orientation.Vertical, self.verify_scroll))
        self.verify_scroll.verticalScrollBar().setProperty("transparentTrack", True)
        self.verify_scroll.setWidgetResizable(True)
        self.verify_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.verify_container = QWidget()
        self.verify_container.setStyleSheet("background: transparent; border: none;")
        self.verify_cards_layout = QVBoxLayout(self.verify_container)
        self.verify_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.verify_cards_layout.setSpacing(6)
        self.verify_cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.verify_scroll.setWidget(self.verify_container)
        self.verify_layout.addWidget(self.verify_scroll)
        self.tabs.addTab(verify_page, "Verify")
        self.tabs.currentChanged.connect(self._tab_changed)

        self.toggle_button = TimelineChevronButton(timeline)
        self.toggle_button.setObjectName("TimelineSidePanelToggle")
        self.toggle_button.setProperty("defer_scroll_control_click", True)
        self.toggle_button.pressed.connect(lambda: self.play_control_sound(self.toggle_button))
        self.toggle_button.clicked.connect(self.toggle)
        self.update_style()
        self.set_sidebar_opacity(getattr(self.editor, "side_menu_opacity", 97))

        self.hide()
        self.toggle_button.hide()

    def set_sidebar_opacity(self, value):
        opacity = max(0.0, min(1.0, float(value) / 100.0))
        self._sidebar_background_opacity = opacity
        self._panel_color.setAlpha(int(round(255.0 * opacity)))
        self.update()

    def update_style(self):
        scale = max(0.5, float(getattr(self.editor, 'global_scale', 1.0)))
        px = lambda value, minimum=0: max(minimum, int(round(value * scale)))
        self.main_layout.setContentsMargins(px(8, 3), px(8, 3), 0, px(8, 3))
        self.main_layout.setSpacing(px(6, 2))
        self.object_layout.setContentsMargins(px(4, 1), px(6, 2), px(8, 3), px(4, 1))
        self.object_layout.setSpacing(px(6, 2))
        self.clipboard_layout.setContentsMargins(0, px(6, 2), 0, px(4, 1))
        self.clipboard_layout.setSpacing(px(6, 2))
        self.clipboard_cards_layout.setContentsMargins(0, 0, px(8, 3), 0)
        self.clipboard_cards_layout.setSpacing(px(7, 2))
        self.verify_layout.setContentsMargins(px(4, 1), px(6, 2), px(8, 3), px(4, 1))
        self.verify_layout.setSpacing(px(6, 2))
        self.verify_cards_layout.setSpacing(px(6, 2))
        self.object_order_list.apply_ui_scale()
        brightness = int(getattr(self.editor, 'ui_brightness', 60))
        panel_brightness = max(0, min(255, brightness - 26))
        hover_brightness = min(255, panel_brightness + 13)
        pressed_brightness = min(255, panel_brightness + 20)
        light = brightness > 180
        primary_text = "#171717" if light else "#eeeeee"
        secondary_text = "#555555" if light else "#a8a8a8"
        hover_text = "#292929" if light else "#e6e6e6"
        selected_text = "#111111" if light else "#ffffff"
        layer_alpha = 12 if light else 10
        selected_alpha = 20 if light else 25
        tab_hover_surface = "rgba(0,0,0,18)" if light else f"rgba(255,255,255,{layer_alpha})"
        tab_selected_surface = "rgba(0,0,0,30)" if light else "rgba(255,255,255,18)"
        accent = QColor(ACCENT_COLOR)
        if not accent.isValid():
            accent = QColor("#d9bf24")
        panel_alpha = int(round(255.0 * self._sidebar_background_opacity))
        self._panel_color = QColor(panel_brightness, panel_brightness, panel_brightness, panel_alpha)
        self._outline_color = QColor(0, 0, 0, 52) if light else QColor(255, 255, 255, 34)
        self.setStyleSheet(scale_stylesheet_dimensions(
            f"#TimelineSidePanel {{ background: transparent; border: none; color: {primary_text}; }}"
            f"#TimelineSidePanel QLabel {{ color: {primary_text}; }}"
            "#TimelineSidePanelTabs { background: transparent; border: none; }"
            "#TimelineSidePanelTabs::pane { background: transparent; border: none; top: -1px; }"
            "#TimelineSidePanelTabs QStackedWidget { background: transparent; border: none; }"
            "#TimelineSidePanelTabs QTabBar { background: transparent; }"
            f"#TimelineSidePanelTabs QTabBar::tab {{ background: transparent; border: none; border-radius: 7px; padding: 9px 12px; margin: 0px 2px 5px 2px; color: {secondary_text}; font-weight: 600; }}"
            f"#TimelineSidePanelTabs QTabBar::tab:hover {{ background-color: {tab_hover_surface}; color: {hover_text}; }}"
            f"#TimelineSidePanelTabs QTabBar::tab:selected {{ background-color: {tab_selected_surface}; color: {selected_text}; }}"
            "#ObjectOrderList { background: transparent; border: none; outline: none; padding: 0px; }"
            f"#ObjectOrderList::item {{ background-color: rgba(255,255,255,{8 if not light else 7}); color: {primary_text}; border: none; border-radius: 8px; margin: 3px 0px; padding: 9px 11px; }}"
            f"#ObjectOrderList::item:hover {{ background-color: rgba(255,255,255,{15 if not light else 12}); border: none; }}"
            f"#ObjectOrderList::item:selected {{ background-color: rgba(255,255,255,{selected_alpha}); color: {selected_text}; border: none; }}"
            f"#ObjectOrderList::item:selected:hover {{ background-color: rgba(255,255,255,{selected_alpha + 6}); color: {selected_text}; border: none; }}"
            "#TimelineVerifyScroll, #TimelineVerifyScroll > QWidget > QWidget, #TimelineClipboardScroll, #TimelineClipboardScroll > QWidget > QWidget { background: transparent; border: none; }"
            "#ObjectOrderList QScrollBar:vertical, #TimelineClipboardScroll QScrollBar:vertical { background: transparent; border: none; width: 8px; margin: 3px 0px; }"
            f"#ObjectOrderList QScrollBar::handle:vertical, #TimelineClipboardScroll QScrollBar::handle:vertical {{ background: rgba({accent.red()},{accent.green()},{accent.blue()},190); border: none; border-radius: 3px; min-height: 24px; margin: 0px 1px; }}"
            f"#ObjectOrderList QScrollBar::handle:vertical:hover, #TimelineClipboardScroll QScrollBar::handle:vertical:hover {{ background: rgba({accent.red()},{accent.green()},{accent.blue()},235); }}"
            "#ObjectOrderList QScrollBar::add-line:vertical, #ObjectOrderList QScrollBar::sub-line:vertical, #TimelineClipboardScroll QScrollBar::add-line:vertical, #TimelineClipboardScroll QScrollBar::sub-line:vertical { height: 0px; background: transparent; border: none; }"
            "#ObjectOrderList QScrollBar::add-page:vertical, #ObjectOrderList QScrollBar::sub-page:vertical, #TimelineClipboardScroll QScrollBar::add-page:vertical, #TimelineClipboardScroll QScrollBar::sub-page:vertical { background: transparent; }"
        , scale))
        if hasattr(self, 'toggle_button'):
            self.toggle_button.set_theme(
                QColor(panel_brightness, panel_brightness, panel_brightness),
                QColor(hover_brightness, hover_brightness, hover_brightness),
                QColor(pressed_brightness, pressed_brightness, pressed_brightness),
                self._outline_color,
                QColor(selected_text),
            )
        for card in self._issue_cards.values():
            card.update_style(brightness)
        for card in self._clipboard_cards.values():
            card.update_style()
        if self._clipboard_cards:
            card_height = max(48, int(round(128 * scale)))
            for card in self._clipboard_cards.values():
                card.set_target_height(card_height)
            card_count = len(self._clipboard_cards)
            total_height = card_height * card_count + self.clipboard_cards_layout.spacing() * max(0, card_count - 1)
            self.clipboard_container.setMinimumHeight(total_height)
        self.update()

    def play_control_sound(self, widget):
        if hasattr(self.editor, 'play_ui_sound_suppressed'):
            pan = self.editor.get_pan_for_widget(widget) if hasattr(self.editor, 'get_pan_for_widget') else 0.0
            self.editor.play_ui_sound_suppressed('UI Click', pan)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        scale = max(0.5, float(getattr(self.editor, 'global_scale', 1.0)))
        radius = max(3.5, 12.0 * scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._panel_color)
        painter.drawRoundedRect(rect, radius, radius)
        if hasattr(self, 'toggle_button'):
            gap_y = self.toggle_button.y() - self.y()
            clip = QRegion(self.rect()).subtracted(QRegion(-2, gap_y, 5, self.toggle_button.height()))
            painter.setClipRegion(clip)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self._outline_color, max(0.5, scale)))
        painter.drawRoundedRect(rect, radius, radius)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'tabs'):
            scale = max(0.5, float(getattr(self.editor, 'global_scale', 1.0)))
            self.tabs.tabBar().setFixedWidth(max(1, self.width() - int(round(16 * scale))))

    @pyqtProperty(float)
    def slideProgress(self):
        return self._slide_progress

    @slideProgress.setter
    def slideProgress(self, progress):
        self._slide_progress = max(0.0, min(1.0, float(progress)))
        self.toggle_button.set_progress(self._slide_progress)
        self.reposition()

    def set_available(self, available):
        self._available = bool(available)
        if not self._available:
            self._open = False
            self._slide_animation_active = False
            self._slide_progress = 0.0
            self.refresh_timer.stop()
            self.object_order_list.sc_reset_to_native()
            self.clipboard_scroll.sc_reset_to_native()
            self._finish_clipboard_appearances()
            self.hide()
            self.toggle_button.hide()
            return
        self.update_style()
        self.toggle_button.show()
        self.toggle_button.raise_()
        self.reposition()

    def toggle(self):
        if not self._available:
            return
        self._open = not self._open
        if self._open:
            self.show()
            self.raise_()
            self.toggle_button.raise_()
            if self.tabs.currentIndex() != 1:
                self.refresh_timer.start()
            self.refresh_active_tab(force=True)
        self._slide_animation_from = self._slide_progress
        self._slide_animation_to = 1.0 if self._open else 0.0
        self._slide_animation_started = time.perf_counter()
        self._slide_animation_duration = 0.72 if self._open else 0.30
        self._slide_animation_active = True
        self.timeline.update()

    def advance_animation(self, now):
        if not self._slide_animation_active:
            return False
        linear = min(1.0, max(0.0, (now - self._slide_animation_started) / self._slide_animation_duration))
        if self._slide_animation_to > self._slide_animation_from:
            damping = 0.56
            frequency = 17.5
            damped_frequency = frequency * math.sqrt(1.0 - damping * damping)
            phase = math.atan(math.sqrt(1.0 - damping * damping) / damping)
            eased = 1.0 - (
                math.exp(-damping * frequency * linear)
                * math.sin(damped_frequency * linear + phase)
                / math.sqrt(1.0 - damping * damping)
            )
        else:
            eased = 1.0 - (1.0 - linear) ** 3
        progress = self._slide_animation_from + (self._slide_animation_to - self._slide_animation_from) * eased
        self._slide_progress = max(-0.08, min(1.16, progress))
        self.toggle_button.set_progress(self._slide_progress)
        self.reposition()
        if linear >= 1.0:
            self._slide_progress = self._slide_animation_to
            self._slide_animation_active = False
            self.toggle_button.set_progress(self._slide_progress)
            self.reposition()
            self._on_slide_finished()
        return self._slide_animation_active

    def _on_slide_finished(self):
        if not self._open:
            self.refresh_timer.stop()
            self.object_order_list.sc_reset_to_native()
            self.clipboard_scroll.sc_reset_to_native()
            self._finish_clipboard_appearances()
            self.hide()
        self.toggle_button.raise_()

    def reposition(self):
        if not self._available:
            return
        old_panel_geometry = self.geometry()
        old_button_geometry = self.toggle_button.geometry()
        scale = max(0.5, float(getattr(self.editor, 'global_scale', 1.0)))
        margin = max(3, int(round(8 * scale)))
        button_width = max(11, int(round(22 * scale)))
        button_height = max(30, int(round(68 * scale)))
        desired_width = max(140, int(round(310 * scale)))
        panel_width = min(desired_width, max(140, int(self.timeline.width() * 0.48)))
        panel_height = max(80, self.timeline.height() - margin * 2)
        closed_x = self.timeline.width()
        open_x = self.timeline.width() - panel_width - margin
        panel_x = int(round(closed_x + (open_x - closed_x) * self._slide_progress))
        self.setGeometry(panel_x, margin, panel_width, panel_height)
        button_x = panel_x - button_width + 1
        button_y = max(0, (self.timeline.height() - button_height) // 2)
        self.toggle_button.setGeometry(button_x, button_y, button_width, button_height)
        self.toggle_button.raise_()
        dirty_geometry = old_panel_geometry.united(self.geometry())
        dirty_geometry = dirty_geometry.united(old_button_geometry)
        dirty_geometry = dirty_geometry.united(self.toggle_button.geometry())
        self.timeline.update(dirty_geometry.adjusted(-2, -2, 2, 2))

    def _tab_changed(self, index):
        if index != 0:
            self.object_order_list.sc_reset_to_native()
        if index == 1:
            self.refresh_timer.stop()
        else:
            self.clipboard_scroll.sc_reset_to_native()
            self._finish_clipboard_appearances()
            self.refresh_timer.setInterval(50 if index == 0 else 400)
            if self._open:
                self.refresh_timer.start()
        self.refresh_active_tab(force=True)

    def mousePressEvent(self, event):
        event.accept()

    def mouseMoveEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    def refresh_active_tab(self, force=False):
        if not self._open:
            return
        if self.tabs.currentIndex() == 0:
            self.refresh_object_order(force)
        elif self.tabs.currentIndex() == 1:
            self.refresh_clipboard(force)
        else:
            self.refresh_verify()

    def refresh_object_order(self, force=False):
        beatmap = self.timeline.beatmap
        status, time_ms = self._object_order_context()
        if beatmap is None or time_ms is None:
            signature = (id(beatmap), status)
            objects = []
        else:
            self.timeline.ensure_object_cache()
            times = getattr(self.timeline, '_cached_obj_times', ())
            objects_cache = getattr(self.timeline, '_cached_all_objs', ())
            start = bisect.bisect_left(times, time_ms)
            end = bisect.bisect_right(times, time_ms)
            objects = beatmap.ordered_objects_at(time_ms, objects_cache[start:end]) if end > start else []
            signature = (
                id(beatmap),
                time_ms,
                tuple((obj.uid, self.object_label(obj)) for obj in objects),
            )
        if not force and signature == self._object_signature:
            return
        self._object_signature = signature
        self.object_order_list.blockSignals(True)
        self.object_order_list.clear()
        if status == "playback":
            self.object_time_label.setText("Disabled during playback")
        elif status == "multiple":
            self.object_time_label.setText("Please select only one note")
        elif objects:
            self.object_time_label.setText(f"{time_ms} ms")
            for obj in objects:
                label = self.object_label(obj)
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, obj.uid)
                item.setToolTip(label)
                item.setSizeHint(QSize(0, max(16, int(round(38 * getattr(self.editor, 'global_scale', 1.0))))))
                self.object_order_list.addItem(item)
        else:
            self.object_time_label.setText(f"No objects at {time_ms} ms")
        self.object_order_list.setDragEnabled(status == "ready" and len(objects) > 1)
        self.object_order_list.blockSignals(False)

    def _object_order_context(self):
        if getattr(self.editor, 'is_playing', False):
            return "playback", None
        selected = tuple(self.timeline.selected_objects)
        if len(selected) > 1:
            return "multiple", None
        if len(selected) == 1:
            return "ready", int(selected[0].time)
        _, snapped_audio = self.timeline.get_snapped_timeline_time(self.timeline.current_time)
        return "ready", snapped_audio

    def object_label(self, obj):
        lane = self.object_lane_label(obj)

        def add_lane(label):
            return f"{label}  ·  {lane}" if lane else label

        if obj.custom_data is not None:
            type_data = get_custom_type(obj.custom_data.type_id)
            return add_lane(f"Custom ({type_data.get('name', 'Missing') if type_data else 'Missing'})")
        if obj.is_toggle_center:
            return "Event (Toggle Center)"
        if obj.is_instant_flip:
            return "Event (Instant Flip)"
        if obj.is_flip:
            return "Event (Flip)"
        if obj.is_brawl_hold:
            name = "Cop Hold Knockout" if obj.is_brawl_hold_knockout else "Cop Hold"
            return add_lane(f"{name} (Cop {obj.brawl_cop_number})")
        if obj.is_brawl_spam:
            name = "Cop Spam Knockout" if obj.is_brawl_spam_knockout else "Cop Spam"
            return add_lane(f"{name} (Cop {obj.brawl_cop_number})")
        if obj.is_brawl_final:
            return add_lane(f"Cop Knockout (Cop {obj.brawl_cop_number})")
        if obj.is_brawl_hit:
            return add_lane(f"Cop Hit (Cop {obj.brawl_cop_number})")
        if obj.is_screamer:
            return add_lane("Note (Double)")
        if obj.is_spam:
            return add_lane("Note (Spam)")
        if obj.is_hold:
            if obj.is_no_circle_hold:
                return add_lane("Note (Hide)")
            return add_lane("Note (Fly In Hold)" if obj.is_fly_in else "Note (Hold)")
        if obj.is_spike:
            return add_lane("Note (Spike)")
        if obj.is_hide:
            return add_lane("Note (Hide)")
        if obj.is_fly_in:
            return add_lane("Note (Fly In)")
        if obj.is_freestyle:
            return "Note (Freestyle)  ·  Middle"
        return add_lane("Note (Normal)")

    def object_lane_label(self, obj):
        if obj.is_event:
            return ""
        if obj.is_freestyle:
            return "Middle"
        lane = obj.custom_data.lane if obj.custom_data is not None else obj.lane
        return {
            -2: "Middle",
            -1: "Outer Top",
            0: "Top",
            1: "Bottom",
            2: "Outer Bottom",
        }.get(lane, "")

    def _apply_object_order(self, ordered_uids):
        beatmap = self.timeline.beatmap
        if beatmap is None or len(ordered_uids) < 2:
            return
        status, time_ms = self._object_order_context()
        if status != "ready" or time_ms is None:
            return
        self.timeline.ensure_object_cache()
        times = getattr(self.timeline, '_cached_obj_times', ())
        objects = getattr(self.timeline, '_cached_all_objs', ())
        start = bisect.bisect_left(times, time_ms)
        end = bisect.bisect_right(times, time_ms)
        current_uids = [obj.uid for obj in beatmap.ordered_objects_at(time_ms, objects[start:end])]
        if current_uids == list(ordered_uids):
            return
        self.timeline.save_undo_state()
        group_by_uid = {obj.uid: obj for obj in objects[start:end]}
        ordered_group = [group_by_uid[uid] for uid in ordered_uids if uid in group_by_uid]
        note_indices = [index for index, obj in enumerate(ordered_group) if not obj.is_event]
        first_note_index = note_indices[0] if note_indices else None
        last_note_index = note_indices[-1] if note_indices else None
        for index, obj in enumerate(ordered_group):
            if obj.is_event and not obj.is_toggle_center:
                if first_note_index is None or index < first_note_index:
                    desired_order = 0
                elif index > last_note_index:
                    desired_order = 1
                else:
                    desired_order = 0.5
                if obj.order_index != desired_order:
                    obj.order_index = desired_order
                    obj.last_update_time = time.time()
        objects[start:end] = ordered_group
        beatmap.set_object_order(time_ms, ordered_uids, ordered_group)
        self.timeline._force_cache_update = True
        self.timeline.update_caches_if_needed()
        self.editor.mark_unsaved(invalidate_timeline=False)
        self._object_signature = None
        self.refresh_object_order(force=True)
        self.timeline.update()

    def notify_clipboard_history_changed(self):
        self._clipboard_signature = None
        if self._open and self.tabs.currentIndex() == 1:
            self.refresh_clipboard(force=True)

    def _update_clipboard_content_padding(self, minimum=None, maximum=None):
        if not hasattr(self, 'clipboard_cards_layout'):
            return
        scrollbar = self.clipboard_scroll.verticalScrollBar()
        if minimum is None:
            minimum = scrollbar.minimum()
        if maximum is None:
            maximum = scrollbar.maximum()
        scrollbar_width = scrollbar.sizeHint().width() if maximum > minimum else 0
        scale = max(0.5, float(getattr(self.editor, 'global_scale', 1.0)))
        right_padding = max(0, max(3, int(round(8 * scale))) - scrollbar_width)
        left, top, current_right, bottom = self.clipboard_cards_layout.getContentsMargins()
        if current_right != right_padding:
            self.clipboard_cards_layout.setContentsMargins(left, top, right_padding, bottom)
            QTimer.singleShot(0, self._sync_clipboard_card_hovers)

    def _sync_clipboard_card_hovers(self, value=None):
        if not self._open or self.tabs.currentIndex() != 1:
            return
        cursor = QCursor.pos()
        dragging = bool(getattr(self.clipboard_scroll, 'sc_dragging', False))
        now = time.perf_counter()
        for card in self._clipboard_cards.values():
            hovered = not dragging and card.isVisible() and card.rect().contains(card.mapFromGlobal(cursor))
            target = 1.0 if hovered else 0.0
            if abs(getattr(card, '_hover_target', 0.0) - target) > 0.001:
                card._hover_target = target
                card._action_last_frame = now
                activate_ui_animation(card)

    def refresh_clipboard(self, force=False):
        history = tuple(getattr(self.timeline, 'clipboard_history', ()))
        signature = (
            getattr(self.timeline, '_clipboard_history_generation', 0),
            len(history),
            round(float(getattr(self.editor, 'global_scale', 1.0)), 3),
        )
        if not force and signature == self._clipboard_signature:
            return
        self._clipboard_signature = signature
        desired = {id(entry) for entry in history}
        for entry_id, card in tuple(self._clipboard_cards.items()):
            if entry_id not in desired:
                self.clipboard_cards_layout.removeWidget(card)
                card.deleteLater()
                self._clipboard_cards.pop(entry_id, None)
        scale = max(0.5, float(getattr(self.editor, 'global_scale', 1.0)))
        card_height = max(48, int(round(128 * scale)))
        total_height = 0
        new_cards = []
        for index, entry in enumerate(history):
            entry_id = id(entry)
            card = self._clipboard_cards.get(entry_id)
            if card is None:
                card = ClipboardPreviewCard(self, entry)
                self._clipboard_cards[entry_id] = card
                self.clipboard_scroll.sc_install_drag_target(card)
                new_cards.append(card)
            card.set_target_height(card_height)
            card.setMinimumWidth(1)
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.clipboard_cards_layout.insertWidget(index, card)
            card.show()
            total_height += card_height
        if history:
            total_height += self.clipboard_cards_layout.spacing() * (len(history) - 1)
        self.clipboard_container.setMinimumHeight(total_height)
        self.clipboard_cards_layout.invalidate()
        self.clipboard_cards_layout.activate()
        self.clipboard_container.updateGeometry()
        self._update_clipboard_content_padding()
        has_entries = bool(history)
        self.clipboard_empty_label.setVisible(not has_entries)
        self.clipboard_scroll.setVisible(has_entries)
        if new_cards:
            QTimer.singleShot(0, lambda cards=tuple(new_cards): self._finalize_new_clipboard_cards(cards))

    def _finalize_new_clipboard_cards(self, cards):
        scale = max(0.5, float(getattr(self.editor, 'global_scale', 1.0)))
        card_height = max(48, int(round(128 * scale)))
        valid_cards = [card for card in cards if self._clipboard_cards.get(id(card.entry)) is card]
        for card in valid_cards:
            card.set_target_height(card_height)
        history_count = len(self._clipboard_cards)
        total_height = card_height * history_count
        if history_count:
            total_height += self.clipboard_cards_layout.spacing() * (history_count - 1)
        self.clipboard_container.setMinimumHeight(total_height)
        self.clipboard_cards_layout.invalidate()
        self.clipboard_cards_layout.activate()
        self.clipboard_container.updateGeometry()
        self._update_clipboard_content_padding()
        if self._open and self.tabs.currentIndex() == 1:
            self.clipboard_scroll.sc_reset_to_native()
            self.clipboard_scroll.verticalScrollBar().setValue(0)
            for card in valid_cards:
                card.start_appear()
        else:
            for card in valid_cards:
                card.finish_appear()

    def _finish_clipboard_appearances(self):
        for card in self._clipboard_cards.values():
            card.finish_appear()

    def activate_clipboard_entry(self, entry):
        self.timeline.activate_clipboard_history_entry(entry)

    def collect_verify_issues(self):
        issues = {}
        targets = {}
        self._verify_targets = targets
        project_folder = getattr(self.editor, 'project_folder', None)
        created = [beatmap for beatmap in getattr(self.editor, 'beatmaps', {}).values() if beatmap.created]
        current_chart = getattr(self.editor, 'current_chart', None)
        checked_beatmaps = list(created)
        if current_chart is not None and current_chart not in checked_beatmaps:
            checked_beatmaps.append(current_chart)
        if not project_folder:
            return issues
        if not any(path.is_file() for path in project_folder.glob("cover.*")):
            issues["cover_missing"] = ("Cover is missing", "Add a cover image in Resources.")
        audio_name = self.editor.get_project_audio_filename() if hasattr(self.editor, 'get_project_audio_filename') else ""
        if not audio_name:
            issues["audio_missing"] = ("Audio is missing", "Set the project audio in Resources.")
        elif not (project_folder / audio_name).is_file():
            issues["audio_file_missing"] = ("Audio file is missing", f"The beatmap references {audio_name}, but that file does not exist.")
        required = (("Title", "song name"), ("Artist", "artist"), ("Creator", "charted by"))
        custom_signature = tuple(
            (str(item.get("id", "")), bool(item.get("enabled", True)))
            for item in getattr(self.editor, "custom_notes", ())
        )
        for beatmap in checked_beatmaps:
            for field, display_name in required:
                if not str(getattr(beatmap.metadata, field, "") or "").strip():
                    key = f"metadata_missing:{beatmap.difficulty_key}:{field}"
                    issues[key] = ("Required metadata is missing", f"{beatmap.difficulty_key}: {display_name} is empty.")
            cache_key = (getattr(beatmap, '_edit_revision', 0), custom_signature)
            cached_missing = self._missing_custom_cache.get(id(beatmap))
            if cached_missing is not None and cached_missing[0] == cache_key:
                missing_custom = cached_missing[1]
            else:
                missing_custom = sum(
                    1
                    for obj in beatmap.hit_objects
                    if obj.custom_data is not None
                    and (obj.custom_data.missing or get_custom_type(obj.custom_data.type_id) is None)
                )
                self._missing_custom_cache[id(beatmap)] = (cache_key, missing_custom)
            if missing_custom:
                key = f"custom_note_missing:{beatmap.difficulty_key}"
                noun = "note" if missing_custom == 1 else "notes"
                issues[key] = (
                    "Custom note is missing",
                    f"{beatmap.difficulty_key}: {missing_custom} custom {noun} cannot be resolved.",
                )
            layered_cache_key = (
                getattr(beatmap, '_edit_revision', 0),
                len(beatmap.hit_objects),
                custom_signature,
            )
            cached_layered = self._layered_note_cache.get(id(beatmap))
            if cached_layered is not None and cached_layered[0] == layered_cache_key:
                layered_groups = cached_layered[1]
            else:
                layered_groups = find_layered_note_groups(beatmap)
                self._layered_note_cache[id(beatmap)] = (layered_cache_key, layered_groups)
            for time_ms, lane, objects in layered_groups:
                key = f"layered_notes:{beatmap.difficulty_key}:{time_ms}:{lane}"
                lane_name = self.object_lane_label(objects[0]) or "Unknown lane"
                timestamp = format_editor_timestamp(time_ms, include_milliseconds=True)
                issues[key] = (
                    "Notes are layered on top of each other",
                    f"{beatmap.difficulty_key}: {len(objects)} notes at {timestamp} in {lane_name}.",
                )
                targets[key] = (beatmap.difficulty_key, time_ms, objects)
        if len(created) > 1:
            reference = created[0]
            fields = (
                ("Title", "song name"),
                ("TitleUnicode", "Unicode song name"),
                ("Artist", "artist"),
                ("ArtistUnicode", "Unicode artist"),
                ("Creator", "charted by"),
                ("AudioFilename", "audio filename"),
                ("PreviewTime", "preview time"),
                ("Attributes", "attributes"),
            )
            for field, display_name in fields:
                reference_value = getattr(reference.metadata, field, None)
                if field == "TitleUnicode":
                    reference_value = reference_value or reference.metadata.Title
                elif field == "ArtistUnicode":
                    reference_value = reference_value or reference.metadata.Artist
                mismatched = [
                    beatmap.difficulty_key
                    for beatmap in created[1:]
                    if (
                        (getattr(beatmap.metadata, field, None) or beatmap.metadata.Title)
                        if field == "TitleUnicode"
                        else (
                            (getattr(beatmap.metadata, field, None) or beatmap.metadata.Artist)
                            if field == "ArtistUnicode"
                            else getattr(beatmap.metadata, field, None)
                        )
                    ) != reference_value
                ]
                if mismatched:
                    key = f"metadata_inconsistent:{field}"
                    names = ", ".join([reference.difficulty_key] + mismatched)
                    issues[key] = ("Metadata differs between difficulties", f"{display_name}: {names}")
        return issues

    def refresh_verify(self):
        issues = self.collect_verify_issues()
        self.verify_summary.setText("No issues found" if not issues else f"{len(issues)} issue{'s' if len(issues) != 1 else ''} found")
        for issue_id, (title, detail) in issues.items():
            card = self._issue_cards.get(issue_id)
            if card is None:
                card = VerifyIssueCard(issue_id, title, detail, self.verify_container)
                card.update_style(getattr(self.editor, 'ui_brightness', 60))
                card.removed.connect(self._remove_issue_card)
                card.activated.connect(self._activate_verify_issue)
                self._issue_cards[issue_id] = card
                self.verify_cards_layout.addWidget(card)
            else:
                card.update_content(title, detail)
            card.set_actionable(issue_id in self._verify_targets)
        for issue_id, card in tuple(self._issue_cards.items()):
            if issue_id not in issues:
                card.animate_out()

    def _remove_issue_card(self, issue_id):
        card = self._issue_cards.pop(issue_id, None)
        if card is not None:
            self.verify_cards_layout.removeWidget(card)
            card.deleteLater()

    def _activate_verify_issue(self, issue_id):
        target = self._verify_targets.get(issue_id)
        if target is None:
            return
        difficulty, time_ms, objects = target
        beatmap = getattr(self.editor, 'beatmaps', {}).get(difficulty)
        if beatmap is None:
            return
        if getattr(self.editor, 'current_chart', None) is not beatmap:
            combo = getattr(self.editor, 'combo_diff', None)
            if combo is not None:
                index = combo.findText(difficulty)
                if index >= 0:
                    combo.setCurrentIndex(index)
            if getattr(self.editor, 'current_chart', None) is not beatmap:
                self.editor.change_difficulty(difficulty)
        if self.timeline.beatmap is not beatmap:
            return
        active_objects = tuple(obj for obj in objects if obj in beatmap.hit_objects)
        if len(active_objects) < 2:
            self.refresh_verify()
            return
        visual_time = self.timeline.audio_to_visual_ms(time_ms)
        self.timeline.current_time = visual_time
        self.timeline.target_time = visual_time
        flash_time = time.time()
        self.timeline.flashing_blocked_objects = [(obj, flash_time) for obj in active_objects]
        self.timeline.update_scrollbar()
        if hasattr(self.editor, 'sync_audio_to_time'):
            self.editor.sync_audio_to_time(force_play=bool(getattr(self.editor, 'is_playing', False)), video_exact=False)
        self.timeline.update()

    def clear_verify_issues(self):
        for card in self._issue_cards.values():
            if card._animation is not None:
                card._animation.stop()
            self.verify_cards_layout.removeWidget(card)
            card.deleteLater()
        self._issue_cards.clear()
        self._missing_custom_cache.clear()
        self._layered_note_cache.clear()
        self._verify_targets.clear()
        self.verify_summary.setText("No issues found")
