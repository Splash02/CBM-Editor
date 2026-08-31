from .models import *

register_shared_globals(globals())

class FileDropLabel(QLabel):
    fileDropped = pyqtSignal(str)
    
    def __init__(self, default_text, parent=None):
        super().__init__(default_text, parent)
        self.setObjectName("FileDropLabel")
        self.setProperty("state", "empty")
        self.default_text = default_text
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setContentsMargins(0, 0, 0, 0)
        self.setIndent(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setFixedHeight(40)
        self.full_text = default_text
        
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.update_elided_text()
        if self.graphicsEffect():
            self.graphicsEffect().setEnabled(self.property("state") == "loaded")
        
    def update_elided_text(self):
        if not self.full_text: return
        w = self.width() - 8
        if w <= 0: return
        metrics = self.fontMetrics()
        elided = metrics.elidedText(self.full_text, Qt.TextElideMode.ElideMiddle, w)
        super().setText(elided)
    
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.accept()
        else:
            e.ignore()
            
    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls()]
        if files:
            self.fileDropped.emit(files[0])
            
    def set_content_loaded(self, text):
        self.full_text = text
        self.setProperty("state", "loaded")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setWordWrap(False)
        self.update_elided_text()
        if self.graphicsEffect(): self.graphicsEffect().setEnabled(True)
        if self.graphicsEffect():
            self.graphicsEffect().setEnabled(self.property("state") == "loaded")

    def set_empty(self):
        self.full_text = self.default_text
        self.setProperty("state", "empty")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setWordWrap(True)
        self.update_elided_text()
        if self.graphicsEffect(): self.graphicsEffect().setEnabled(False)
        if self.graphicsEffect():
            self.graphicsEffect().setEnabled(self.property("state") == "loaded")


from PyQt6.QtWidgets import QGraphicsEffect
from PyQt6.QtGui import QTransform
class FastDropShadowEffect(QGraphicsEffect):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._blur_radius = 0.0
        self._color = QColor(63, 63, 63, 180)
        self._offset = QPointF(8.0, 8.0)
        self._shadow_cache = None
        self._cache_dirty = True
        self._cache_source_size = QSize()
        self._cache_dpr = 0.0
        self._static_source = False

    def blurRadius(self):
        return self._blur_radius

    def setBlurRadius(self, radius):
        radius = max(0.0, float(radius))
        if self._blur_radius != radius:
            self._blur_radius = radius
            self._invalidate_cache()
            self.updateBoundingRect()

    def color(self):
        return QColor(self._color)

    def setColor(self, color):
        color = QColor(color)
        if self._color != color:
            self._color = color
            self._invalidate_cache()

    def offset(self):
        return QPointF(self._offset)

    def setOffset(self, dx, dy=None):
        if dy is None:
            offset = QPointF(dx)
        else:
            offset = QPointF(float(dx), float(dy))
        if self._offset != offset:
            self._offset = offset
            self.updateBoundingRect()
            super().update()

    def boundingRectFor(self, rect):
        spread = self._blur_radius + 2.0
        shadow_rect = QRectF(rect)
        shadow_rect.translate(self._offset)
        shadow_rect.adjust(-spread, -spread, spread, spread)
        return rect.united(shadow_rect)

    def sourceChanged(self, flags):
        geometry_flags = (
            QGraphicsEffect.ChangeFlag.SourceAttached
            | QGraphicsEffect.ChangeFlag.SourceDetached
            | QGraphicsEffect.ChangeFlag.SourceBoundingRectChanged
        )
        if not self._static_source or flags & geometry_flags:
            self._cache_dirty = True
        super().sourceChanged(flags)

    def setStaticSource(self, enabled):
        enabled = bool(enabled)
        if self._static_source != enabled:
            self._static_source = enabled
            self._invalidate_cache()

    def update(self):
        self._invalidate_cache()

    def setEnabled(self, enabled):
        enabled = bool(enabled)
        if not enabled:
            self._shadow_cache = None
        elif not self.isEnabled():
            self._cache_dirty = True
        super().setEnabled(enabled)

    def _invalidate_cache(self):
        self._cache_dirty = True
        super().update()

    def _build_shadow(self, source):
        dpr = max(1.0, float(source.devicePixelRatio()))
        spread = int(math.ceil((self._blur_radius + 2.0) * dpr))
        size = QSize(source.width() + spread * 2, source.height() + spread * 2)
        shadow = QPixmap(size)
        shadow.setDevicePixelRatio(dpr)
        shadow.fill(Qt.GlobalColor.transparent)
        painter = QPainter(shadow)
        painter.drawPixmap(QPointF(spread / dpr, spread / dpr), source)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(QRectF(0.0, 0.0, size.width() / dpr, size.height() / dpr), self._color)
        painter.end()
        if self._blur_radius > 0.0 and size.width() > 2 and size.height() > 2:
            factor = max(0.2, min(0.65, 1.0 / (1.0 + self._blur_radius / 4.0)))
            small_size = QSize(
                max(1, int(round(size.width() * factor))),
                max(1, int(round(size.height() * factor))),
            )
            shadow = shadow.scaled(
                small_size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ).scaled(
                size,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            shadow.setDevicePixelRatio(dpr)
        self._shadow_cache = shadow
        self._cache_dirty = False
        self._cache_source_size = QSize(source.size())
        self._cache_dpr = dpr
        return spread / dpr

    def draw(self, painter):
        use_device_coordinates = not self.sourceIsPixmap()
        source, source_offset = self.sourcePixmap(
            Qt.CoordinateSystem.DeviceCoordinates if use_device_coordinates else Qt.CoordinateSystem.LogicalCoordinates,
            QGraphicsEffect.PixmapPadMode.NoPad,
        )
        if source_offset is None:
            source_offset = QPoint()
        if source.isNull():
            return
        dpr = max(1.0, float(source.devicePixelRatio()))
        if (
            self._cache_dirty
            or self._shadow_cache is None
            or self._cache_source_size != source.size()
            or self._cache_dpr != dpr
        ):
            spread = self._build_shadow(source)
        else:
            spread = math.ceil((self._blur_radius + 2.0) * dpr) / dpr
        painter.save()
        if use_device_coordinates:
            painter.setWorldTransform(QTransform())
        painter.drawPixmap(
            QPointF(
                source_offset.x() + self._offset.x() - spread,
                source_offset.y() + self._offset.y() - spread,
            ),
            self._shadow_cache,
        )
        painter.drawPixmap(QPointF(source_offset), source)
        painter.restore()

def update_all_shadows(editor):
    mode = getattr(editor, 'drop_shadow_mode', "None")
    try:
        children = editor.findChildren(QWidget)
    except RuntimeError:
        return
    for child in children:
        try:
            effect = child.graphicsEffect()
            if isinstance(effect, FastDropShadowEffect):
                stype = child.property("shadow_type")
                if stype == "global":
                    enabled = mode == "All"
                    if "FileDropLabel" in str(type(child)) and child.property('state') == 'empty':
                        enabled = False
                elif stype == "manual":
                    enabled = mode in ("Specific", "All")
                else:
                    continue
                if effect.isEnabled() != enabled:
                    effect.setEnabled(enabled)
        except RuntimeError:
            continue

def schedule_shadow_update(editor):
    try:
        timer = getattr(editor, '_shadow_update_timer', None)
        if timer is None:
            timer = QTimer(editor)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: update_all_shadows(editor))
            editor._shadow_update_timer = timer
        timer.start(120)
    except RuntimeError:
        pass

def set_manual_shadow(widget, effect):
    effect.setStaticSource(True)
    widget.setGraphicsEffect(effect)
    widget.setProperty("shadow_type", "manual")
    curr = widget
    mode = "None"
    while curr:
        if hasattr(curr, 'drop_shadow_mode'):
            mode = curr.drop_shadow_mode
            break
        curr = curr.parent() if hasattr(curr, 'parent') else None
    effect.setEnabled(mode in ("Specific", "All"))

def apply_shadows_to_container(container):
    from PyQt6.QtWidgets import QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QWidget, QSlider, QScrollBar
    from PyQt6.QtGui import QColor
    types_to_shadow = (QPushButton, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, FileDropLabel)

    timeline_children = set()
    if hasattr(container, 'timeline'):
        for child in container.timeline.findChildren(QWidget):
            timeline_children.add(child)
        if hasattr(container, 'start_screen'):
            start_screen_children = set([container.start_screen] + container.start_screen.findChildren(QWidget))
            timeline_children = timeline_children - start_screen_children

    for child in container.findChildren(types_to_shadow):
        if isinstance(child, (QSlider, QScrollBar)):
            continue
        if child in timeline_children or (hasattr(container, 'timeline') and child == container.timeline):
            continue
        if child.objectName() == 'NoShadow':
            continue
        if child.graphicsEffect() is None:
            shadow = FastDropShadowEffect(child)
            shadow.setBlurRadius(12)
            shadow.setColor(QColor(0, 0, 0, 100))
            shadow.setOffset(0, 3)
            shadow.setStaticSource(True)
            child.setGraphicsEffect(shadow)
            child.setProperty("shadow_type", "global")
            
            curr = child
            mode = "None"
            while curr:
                if hasattr(curr, 'drop_shadow_mode'):
                    mode = curr.drop_shadow_mode
                    break
                curr = curr.parent() if hasattr(curr, 'parent') else None
            shadow.setEnabled(mode == "All")
            
            if isinstance(child, FileDropLabel) and child.property('state') == 'empty':
                shadow.setEnabled(False)

