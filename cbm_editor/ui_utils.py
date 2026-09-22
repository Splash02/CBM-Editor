from .models import *
import ctypes
import os
import sys
import uuid
from pathlib import Path

register_shared_globals(globals())

class _Guid(ctypes.Structure):
    _fields_ = (
        ("data1", ctypes.c_ulong),
        ("data2", ctypes.c_ushort),
        ("data3", ctypes.c_ushort),
        ("data4", ctypes.c_ubyte * 8),
    )

def _guid(value):
    return _Guid.from_buffer_copy(uuid.UUID(value).bytes_le)

def _com_method(pointer, index, result_type, *argument_types):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)(table[index])

def _release(pointer):
    if pointer:
        _com_method(pointer, 2, ctypes.c_ulong)(pointer)

def _raise_for_hresult(result, action):
    if result < 0:
        raise OSError(f"{action} failed with HRESULT 0x{result & 0xFFFFFFFF:08X}")

def select_native_folders(parent, title, start_directory):
    if not sys.platform.startswith("win"):
        raise OSError("Native multi-folder selection is only available on Windows")

    ole32 = ctypes.WinDLL("ole32")
    shell32 = ctypes.WinDLL("shell32")
    ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = ()
    ole32.CoCreateInstance.argtypes = (
        ctypes.POINTER(_Guid),
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.POINTER(_Guid),
        ctypes.POINTER(ctypes.c_void_p),
    )
    ole32.CoCreateInstance.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
    shell32.SHCreateItemFromParsingName.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.POINTER(_Guid),
        ctypes.POINTER(ctypes.c_void_p),
    )
    shell32.SHCreateItemFromParsingName.restype = ctypes.c_long

    initialization = ole32.CoInitializeEx(None, 2)
    should_uninitialize = initialization in (0, 1)
    if initialization < 0 and (initialization & 0xFFFFFFFF) != 0x80010106:
        _raise_for_hresult(initialization, "COM initialization")

    dialog = ctypes.c_void_p()
    results = ctypes.c_void_p()
    try:
        class_id = _guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")
        interface_id = _guid("D57C7288-D4AD-4768-BE02-9D969532D960")
        result = ole32.CoCreateInstance(
            ctypes.byref(class_id),
            None,
            1,
            ctypes.byref(interface_id),
            ctypes.byref(dialog),
        )
        _raise_for_hresult(result, "Creating the folder dialog")

        options = ctypes.c_uint()
        result = _com_method(
            dialog,
            10,
            ctypes.c_long,
            ctypes.POINTER(ctypes.c_uint),
        )(dialog, ctypes.byref(options))
        _raise_for_hresult(result, "Reading folder dialog options")
        options.value |= 0x20 | 0x40 | 0x200 | 0x800
        result = _com_method(dialog, 9, ctypes.c_long, ctypes.c_uint)(dialog, options.value)
        _raise_for_hresult(result, "Configuring the folder dialog")

        result = _com_method(dialog, 17, ctypes.c_long, ctypes.c_wchar_p)(dialog, title)
        _raise_for_hresult(result, "Setting the folder dialog title")

        initial_item = ctypes.c_void_p()
        initial_path = Path(start_directory) if start_directory else None
        if initial_path is not None and initial_path.is_dir():
            shell_item_id = _guid("43826D1E-E718-42EE-BC55-A1E261C37BFE")
            result = shell32.SHCreateItemFromParsingName(
                os.fspath(initial_path),
                None,
                ctypes.byref(shell_item_id),
                ctypes.byref(initial_item),
            )
            if result >= 0:
                try:
                    result = _com_method(dialog, 12, ctypes.c_long, ctypes.c_void_p)(dialog, initial_item)
                    _raise_for_hresult(result, "Setting the initial folder")
                finally:
                    _release(initial_item)

        owner = ctypes.c_void_p(int(parent.winId())) if parent is not None else None
        result = _com_method(dialog, 3, ctypes.c_long, ctypes.c_void_p)(dialog, owner)
        if (result & 0xFFFFFFFF) == 0x800704C7:
            return []
        _raise_for_hresult(result, "Showing the folder dialog")

        result = _com_method(
            dialog,
            27,
            ctypes.c_long,
            ctypes.POINTER(ctypes.c_void_p),
        )(dialog, ctypes.byref(results))
        _raise_for_hresult(result, "Reading selected folders")

        count = ctypes.c_uint()
        result = _com_method(
            results,
            7,
            ctypes.c_long,
            ctypes.POINTER(ctypes.c_uint),
        )(results, ctypes.byref(count))
        _raise_for_hresult(result, "Counting selected folders")

        folders = []
        for index in range(count.value):
            item = ctypes.c_void_p()
            result = _com_method(
                results,
                8,
                ctypes.c_long,
                ctypes.c_uint,
                ctypes.POINTER(ctypes.c_void_p),
            )(results, index, ctypes.byref(item))
            _raise_for_hresult(result, "Reading a selected folder")
            try:
                path_pointer = ctypes.c_void_p()
                result = _com_method(
                    item,
                    5,
                    ctypes.c_long,
                    ctypes.c_uint,
                    ctypes.POINTER(ctypes.c_void_p),
                )(item, 0x80058000, ctypes.byref(path_pointer))
                _raise_for_hresult(result, "Reading a selected folder path")
                try:
                    folders.append(Path(ctypes.wstring_at(path_pointer.value)))
                finally:
                    ole32.CoTaskMemFree(path_pointer)
            finally:
                _release(item)
        return folders
    finally:
        _release(results)
        _release(dialog)
        if should_uninitialize:
            ole32.CoUninitialize()

class FileDropLabel(QLabel):
    fileDropped = pyqtSignal(str)
    filesDropped = pyqtSignal(list)
    
    def __init__(self, default_text, parent=None, dialog_title="Select File", file_filter="All Files (*)", allow_multiple=False):
        super().__init__(default_text, parent)
        self.setObjectName("FileDropLabel")
        self.setProperty("state", "empty")
        self.default_text = default_text
        self.dialog_title = dialog_title
        self.file_filter = file_filter
        self.allow_multiple = allow_multiple
        self.browse_press_position = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContentsMargins(0, 0, 0, 0)
        self.setIndent(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        scale = widget_ui_scale(self)
        self.setFixedHeight(max(20, int(round(40 * scale))))
        self.full_text = default_text
        
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.update_elided_text()
        if self.graphicsEffect():
            self.graphicsEffect().setEnabled(self.property("state") == "loaded")
        
    def showEvent(self, e):
        self.setFixedHeight(max(20, int(round(40 * widget_ui_scale(self)))))
        super().showEvent(e)

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
            if self.allow_multiple:
                self.filesDropped.emit(files)
            else:
                self.fileDropped.emit(files[0])
            e.acceptProposedAction()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.browse_press_position = QPointF(e.globalPosition())
        else:
            self.browse_press_position = None
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        press_position = self.browse_press_position
        self.browse_press_position = None
        distance = (
            (e.globalPosition() - press_position).manhattanLength()
            if press_position is not None
            else float("inf")
        )
        if (
            e.button() == Qt.MouseButton.LeftButton
            and self.isEnabled()
            and self.rect().contains(e.position().toPoint())
            and distance < QApplication.startDragDistance()
        ):
            if self.allow_multiple:
                file_paths, _ = QFileDialog.getOpenFileNames(self, self.dialog_title, "", self.file_filter)
                if file_paths:
                    self.filesDropped.emit(file_paths)
            else:
                file_path, _ = QFileDialog.getOpenFileName(self, self.dialog_title, "", self.file_filter)
                if file_path:
                    self.fileDropped.emit(file_path)
            e.accept()
            return
        super().mouseReleaseEvent(e)
            
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
    effect._ui_base_blur_radius = effect.blurRadius()
    effect._ui_base_offset = effect.offset()
    effect.setStaticSource(True)
    widget.setGraphicsEffect(effect)
    widget.setProperty("shadow_type", "manual")
    curr = widget
    mode = "None"
    scale = 1.0
    while curr:
        if hasattr(curr, 'drop_shadow_mode'):
            mode = curr.drop_shadow_mode
        if hasattr(curr, 'global_scale'):
            scale = max(0.1, float(curr.global_scale))
        if hasattr(curr, 'drop_shadow_mode') and hasattr(curr, 'global_scale'):
            break
        curr = curr.parent() if hasattr(curr, 'parent') else None
    effect.setBlurRadius(effect._ui_base_blur_radius * scale)
    effect.setOffset(effect._ui_base_offset.x() * scale, effect._ui_base_offset.y() * scale)
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
            shadow._ui_base_blur_radius = shadow.blurRadius()
            shadow._ui_base_offset = shadow.offset()
            shadow.setStaticSource(True)
            child.setGraphicsEffect(shadow)
            child.setProperty("shadow_type", "global")
            
            curr = child
            mode = "None"
            scale = 1.0
            while curr:
                if hasattr(curr, 'drop_shadow_mode'):
                    mode = curr.drop_shadow_mode
                if hasattr(curr, 'global_scale'):
                    scale = max(0.1, float(curr.global_scale))
                if hasattr(curr, 'drop_shadow_mode') and hasattr(curr, 'global_scale'):
                    break
                curr = curr.parent() if hasattr(curr, 'parent') else None
            shadow.setBlurRadius(shadow._ui_base_blur_radius * scale)
            shadow.setOffset(shadow._ui_base_offset.x() * scale, shadow._ui_base_offset.y() * scale)
            shadow.setEnabled(mode == "All")
            
            if isinstance(child, FileDropLabel) and child.property('state') == 'empty':
                shadow.setEnabled(False)

def update_shadow_scale(container, scale):
    scale = max(0.1, float(scale))
    widgets = [container] + container.findChildren(QWidget)
    for widget in widgets:
        effect = widget.graphicsEffect()
        if not isinstance(effect, FastDropShadowEffect):
            continue
        base_blur = getattr(effect, '_ui_base_blur_radius', effect.blurRadius())
        base_offset = getattr(effect, '_ui_base_offset', effect.offset())
        effect._ui_base_blur_radius = base_blur
        effect._ui_base_offset = base_offset
        effect.setBlurRadius(base_blur * scale)
        effect.setOffset(base_offset.x() * scale, base_offset.y() * scale)

