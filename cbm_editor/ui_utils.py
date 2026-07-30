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


from PyQt6.QtWidgets import QGraphicsDropShadowEffect
class FastDropShadowEffect(QGraphicsDropShadowEffect):
    def setBlurRadius(self, radius):
        radius = float(radius)
        if self.blurRadius() != radius:
            super().setBlurRadius(radius)

    def setColor(self, color):
        if self.color() != color:
            super().setColor(color)

    def setOffset(self, dx, dy):
        offset = QPointF(float(dx), float(dy))
        if self.offset() != offset:
            super().setOffset(offset)

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

