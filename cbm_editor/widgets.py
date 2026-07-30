from .foundation import *

register_shared_globals(globals())

class OutputSuppressor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


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
        if self.orientation() == Qt.Orientation.Horizontal:
            position = int(round(event.position().x()))
            span = max(1, self.width() - 1)
        else:
            position = int(round(event.position().y()))
            span = max(1, self.height() - 1)
        position = max(0, min(span, position))
        return QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            position,
            span,
            self.invertedAppearance(),
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
        self.update_style()

    def update_style(self):
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {UI_THEME["button_bg"]};
                color: {UI_THEME["text_primary"]};
                border: 1px solid #484848;
                border-bottom: 3px solid {UI_THEME["button_depth"]};
                border-radius: 6px;
                padding: 5px 9px;
                font-size: 12px;
                font-family: 'Segoe UI', sans-serif;
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
                self.tooltip.move(pos)
                self.tooltip.show()
                self.is_hot = True

    def do_hide_tooltip(self):
        self.timer.stop()
        self.tooltip.hide()
        self.current_widget = None
        self.is_hot = False

class SmoothScrollMixin:
    def init_smooth_scroll(self):
        if hasattr(self, "setVerticalScrollMode"):
            self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        
        self.sc_target = 0.0
        self.sc_current = 0.0
        self.sc_added_overshoot_max = 0
        self.sc_added_overshoot_min = 0
        self.sc_last_time = time.time()
        
        interval_ms = max(1, int(1000.0 / TARGET_FPS))
        
        self.sc_timer = QTimer(self)
        self.sc_timer.setInterval(interval_ms)
        self.sc_timer.timeout.connect(self.sc_update_scroll)
        
        sb = self.verticalScrollBar()
        if sb:
            self.sc_current = float(sb.value())
            self.sc_target = self.sc_current
            self.sc_ignore_value_change = False
            self.sc_last_native_value = sb.value()
            sb.valueChanged.connect(self.sc_handle_value_changed)
            sb.installEventFilter(self)

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

        if not self.sc_timer.isActive():
            self.sc_current = float(sb.value())
            self.sc_target = self.sc_current
            self.sc_added_overshoot_max = 0
            self.sc_added_overshoot_min = 0
            self.sc_last_time = time.time()
            self.sc_timer.start()

        step = 120
        if delta > 0:
            self.sc_target -= step
        else:
            self.sc_target += step
        
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
        
        spring_speed = 0.1
        if self.sc_target < real_min:
            diff = real_min - self.sc_target
            self.sc_target += diff * spring_speed * dt_factor
            if abs(self.sc_target - real_min) < 1.0: self.sc_target = real_min
        elif self.sc_target > real_max:
            diff = self.sc_target - real_max
            self.sc_target -= diff * spring_speed * dt_factor
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
            lerp_speed = 0.18
            self.sc_current += diff * lerp_speed * dt_factor
            
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
            sb = getattr(self, "verticalScrollBar", lambda: None)()
            if sb and obj == sb:
                if event.type() == QEvent.Type.MouseMove and sb.isSliderDown():
                    is_overshooting = getattr(self, "sc_added_overshoot_max", 0) > 0 or getattr(self, "sc_added_overshoot_min", 0) > 0
                    if is_overshooting:
                        if not hasattr(self, "sc_last_mouse_y"):
                            self.sc_last_mouse_y = event.pos().y()
                        
                        dy = event.pos().y() - self.sc_last_mouse_y
                        self.sc_last_mouse_y = event.pos().y()
                        
                        if dy != 0:
                            val_range = sb.maximum() - sb.minimum()
                            track_pixels = sb.height()
                            if val_range > 0 and track_pixels > 0:
                                usable_track = track_pixels - 2 * sb.width()
                                if usable_track <= 0: usable_track = track_pixels
                                delta_val = dy * float(val_range + sb.pageStep()) / usable_track
                                
                                self.sc_target += delta_val
                                self.sc_current += delta_val
                                if not self.sc_timer.isActive():
                                    self.sc_timer.start()
                        return True
                    else:
                        if hasattr(self, "sc_last_mouse_y"):
                            del self.sc_last_mouse_y
                elif event.type() == QEvent.Type.MouseButtonRelease:
                    if hasattr(self, "sc_last_mouse_y"):
                        del self.sc_last_mouse_y
        except Exception:
            pass
            
        if hasattr(super(), "eventFilter"):
            return super().eventFilter(obj, event)
        return False

class SmoothListView(SmoothScrollMixin, QListView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_smooth_scroll()

class SmoothListWidget(SmoothScrollMixin, HoverListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_smooth_scroll()

class SmoothScrollArea(SmoothScrollMixin, QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_smooth_scroll()

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
    
    def wheelEvent(self, e: QWheelEvent):
        e.ignore()

    def showPopup(self):
        super().showPopup()
        popup = self.view().parentWidget()
        if popup:
            rect = popup.rect()
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect), 10, 10)
            region = QRegion(path.toFillPolygon().toPolygon())
            popup.setMask(region)
        
        view = self.view()
        if view and not hasattr(view, '_wheel_override_installed'):
            original_wheel_event = view.wheelEvent
            
            def custom_wheel_event(event):
                scrollbar = view.verticalScrollBar()
                if scrollbar and scrollbar.maximum() == scrollbar.minimum():
                    event.ignore()
                    return
                original_wheel_event(event)
            
            view.wheelEvent = custom_wheel_event
            view._wheel_override_installed = True

class NoMenuLineEdit(QLineEdit):
    def contextMenuEvent(self, e):
        pass

QComboBox = IgnoreWheelComboBox

