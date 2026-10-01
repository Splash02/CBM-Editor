import fnmatch
import json
import os
import re
import sys
import threading
from pathlib import Path
from xml.etree import ElementTree

from PyQt6.QtCore import (
    QAbstractTableModel, QCollator, QDateTime, QDir, QEventLoop, QFileInfo,
    QFileSystemWatcher, QLocale, QMimeDatabase, QModelIndex, QObject, QPointF,
    QProcess, QRectF, QRunnable, QSize, QStandardPaths, QStorageInfo, QThreadPool,
    QTimer, Qt, QUrl, pyqtSignal,
)
from PyQt6.QtGui import QColor, QFileSystemModel, QIcon, QKeySequence, QPainter, QPen, QPixmap, QPolygonF, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QAbstractItemView, QCompleter, QFileIconProvider, QHeaderView,
    QHBoxLayout, QLabel, QLineEdit, QListWidgetItem, QSizePolicy, QSplitter,
    QStyle, QVBoxLayout, QWidget,
)

from . import foundation as ui
from .foundation import QDialog, apply_layout_scale, fit_compact_popup, scale_stylesheet_dimensions, widget_global_scale
from .widgets import IgnoreWheelComboBox, QPushButton, SmoothListWidget, SmoothTreeView, widget_ui_brightness


class FolderScanSignals(QObject):
    finished = pyqtSignal(int, str, object, str)


class FolderScan(QRunnable):
    def __init__(self, generation, path, include_files=False):
        super().__init__()
        self.generation = generation
        self.path = path
        self.include_files = include_files
        self.cancelled = threading.Event()
        self.signals = FolderScanSignals()

    def run(self):
        entries = []
        error = ""
        try:
            with os.scandir(self.path) as iterator:
                for entry in iterator:
                    if self.cancelled.is_set():
                        return
                    if not sys.platform.startswith("win") and entry.name.startswith("."):
                        continue
                    try:
                        is_directory = entry.is_dir()
                        if not is_directory and not self.include_files:
                            continue
                        if not is_directory and not entry.is_file():
                            continue
                        info = entry.stat()
                        if getattr(info, "st_file_attributes", 0) & 6:
                            continue
                    except OSError:
                        continue
                    if self.include_files:
                        entries.append((entry.name, entry.path, info.st_mtime, is_directory, info.st_size if not is_directory else 0))
                    else:
                        entries.append((entry.name, entry.path, info.st_mtime))
        except OSError as exception:
            error = exception.strerror or str(exception)
        if not self.cancelled.is_set():
            self.signals.finished.emit(self.generation, self.path, entries, error)


class FolderListingModel(QAbstractTableModel):
    directoryLoaded = pyqtSignal(str)
    directoryFailed = pyqtSignal(str, str)

    def __init__(self, icon_provider, parent=None, include_files=False):
        super().__init__(parent)
        self._icon = icon_provider.icon(icon_provider.IconType.Folder)
        self._file_icon = icon_provider.icon(icon_provider.IconType.File)
        self._folder_type = icon_provider.type(QFileInfo(str(Path.home())))
        self._include_files = include_files
        self._name_filters = ["*"]
        self._mime_database = QMimeDatabase()
        self._file_types = {}
        self._entries = []
        self._rows = {}
        self._path = ""
        self._generation = 0
        self._scan = None
        self._sort_column = 3
        self._sort_order = Qt.SortOrder.DescendingOrder
        self._collator = QCollator()
        self._collator.setNumericMode(True)
        self._collator.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._cache = {}
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self.directory_changed)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(lambda: self.setRootPath(self._path, refresh=True))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent=QModelIndex()):
        return 4

    def index(self, row, column=0, parent=QModelIndex()):
        if isinstance(row, str):
            row = self._rows.get(os.path.normcase(os.path.abspath(row)), -1)
        return super().index(row, column, parent)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._entries):
            return None
        entry = self._entries[index.row()]
        name, path, modified = entry[:3]
        is_directory = self.entry_is_directory(entry)
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return name
            if index.column() == 1 and not is_directory:
                return QLocale().formattedDataSize(entry[4])
            if index.column() == 2:
                return self.entry_type(entry)
            if index.column() == 3:
                return QLocale().toString(QDateTime.fromSecsSinceEpoch(int(modified)), QLocale.FormatType.ShortFormat)
            return ""
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            return self._icon if is_directory else self._file_icon
        if role == Qt.ItemDataRole.ToolTipRole:
            return path
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole and 0 <= section < 4:
            return ("Name", "Size", "Type", "Date Modified")[section]
        return None

    def filePath(self, index):
        return self._entries[index.row()][1] if index.isValid() else self._path

    def fileName(self, index):
        return self._entries[index.row()][0] if index.isValid() else Path(self._path).name

    def entry_is_directory(self, entry):
        return len(entry) == 3 or entry[3]

    def isDir(self, index):
        return not index.isValid() or self.entry_is_directory(self._entries[index.row()])

    def entry_type(self, entry):
        if self.entry_is_directory(entry):
            return self._folder_type
        extension = Path(entry[0]).suffix.casefold()
        if extension not in self._file_types:
            mime = self._mime_database.mimeTypeForFile(entry[0], QMimeDatabase.MatchMode.MatchExtension)
            self._file_types[extension] = mime.comment() or (f"{extension[1:].upper()} file" if extension else "File")
        return self._file_types[extension]

    def matches_filters(self, name):
        return any(pattern in ("*", "*.*") or fnmatch.fnmatchcase(name.casefold(), pattern.casefold()) for pattern in self._name_filters)

    def setNameFilters(self, patterns):
        self._name_filters = list(patterns) or ["*"]
        self.beginResetModel()
        self._entries = self.sorted_entries(self._cache.get(self._path, []))
        self.update_rows()
        self.endResetModel()

    def sorted_entries(self, entries):
        entries = [entry for entry in entries if self.entry_is_directory(entry) or self.matches_filters(entry[0])]
        entries = sorted(entries, key=lambda entry: self._collator.sortKey(entry[0]))
        descending = self._sort_order == Qt.SortOrder.DescendingOrder
        if self._sort_column == 3:
            entries.sort(key=lambda entry: entry[2], reverse=descending)
        elif self._sort_column == 0 and descending:
            entries.reverse()
        elif self._sort_column == 1:
            entries.sort(key=lambda entry: entry[4] if len(entry) > 3 else 0, reverse=descending)
        elif self._sort_column == 2:
            entries.sort(key=lambda entry: self._collator.sortKey(self.entry_type(entry)), reverse=descending)
        return entries

    def update_rows(self):
        self._rows = {os.path.normcase(entry[1]): row for row, entry in enumerate(self._entries)}

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        self._sort_column = column
        self._sort_order = order
        self.layoutAboutToBeChanged.emit()
        persistent = self.persistentIndexList()
        paths = [self.filePath(index) for index in persistent]
        self._entries = self.sorted_entries(self._entries)
        self.update_rows()
        self.changePersistentIndexList(persistent, [self.index(path, index.column()) for path, index in zip(paths, persistent)])
        self.layoutChanged.emit()

    def setRootPath(self, path, refresh=False):
        path = os.path.abspath(path) if path else self._path
        if not path:
            return QModelIndex()
        self._refresh_timer.stop()
        if self._scan is not None:
            self._scan.cancelled.set()
        self._generation += 1
        changed = os.path.normcase(path) != os.path.normcase(self._path)
        self._path = path
        if changed or refresh:
            self.beginResetModel()
            self._entries = self.sorted_entries(self._cache.get(path, []))
            self.update_rows()
            self.endResetModel()
        if path in self._cache and not refresh:
            self.directoryLoaded.emit(path)
            return QModelIndex()
        scan = FolderScan(self._generation, path, self._include_files)
        self._scan = scan
        scan.signals.finished.connect(self.scan_finished)
        self.destroyed.connect(scan.cancelled.set)
        QThreadPool.globalInstance().start(scan)
        return QModelIndex()

    def scan_finished(self, generation, path, entries, error):
        if generation != self._generation or path != self._path:
            return
        self._scan = None
        if error:
            self.directoryFailed.emit(path, error)
            return
        self._cache[path] = entries
        if path not in self._watcher.directories() and Path(path).is_dir():
            self._watcher.addPath(path)
        if len(self._cache) > 24:
            oldest = next(iter(self._cache))
            self._cache.pop(oldest)
            if oldest in self._watcher.directories():
                self._watcher.removePath(oldest)
        self.beginResetModel()
        self._entries = self.sorted_entries(entries)
        self.update_rows()
        self.endResetModel()
        self.directoryLoaded.emit(path)

    def directory_changed(self, path):
        self._cache.pop(path, None)
        if path == self._path:
            self._refresh_timer.start(100)


class FolderBrowserIconProvider(QFileIconProvider):
    def __init__(self):
        super().__init__()
        self.setOptions(QFileIconProvider.Option.DontUseCustomDirectoryIcons)
        self._folder_icon = super().icon(QFileIconProvider.IconType.Folder)
        self._file_icon = super().icon(QFileIconProvider.IconType.File)
        self._folder_type = super().type(QFileInfo(QDir.homePath()))

    def icon(self, info):
        if isinstance(info, QFileInfo):
            return self._folder_icon if info.isDir() else self._file_icon
        return super().icon(info)

    def type(self, info):
        return self._folder_type if info.isDir() else ""


class FolderPlacesCache(QObject):
    loaded = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.entries = []
        self.ready = False
        self._refresh_pending = False
        self.process = QProcess(self)
        self.process.finished.connect(self.finish_loading)
        self.process.errorOccurred.connect(self.loading_failed)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.process.kill)
        self.watcher = QFileSystemWatcher(self)
        recent = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "Microsoft/Windows/Recent/AutomaticDestinations"
        self._pins_file = recent / "f01b4d95cf55d32a.automaticDestinations-ms"
        if recent.is_dir():
            self.watcher.addPath(str(recent))
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(lambda: self.start(refresh=True))
        self.watcher.directoryChanged.connect(self.schedule_refresh)
        self.watcher.fileChanged.connect(self.schedule_refresh)
        self.watch_pins_file()
        parent.aboutToQuit.connect(self.process.kill)

    def start(self, refresh=False):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self._refresh_pending |= refresh
            return
        if self.ready and not refresh:
            return
        self.ready = False
        script = """
            $ErrorActionPreference = 'Stop'
            [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
            $shell = New-Object -ComObject Shell.Application
            $folder = $shell.Namespace('shell:::{679f85cb-0220-4080-b29b-5540cc05aab6}')
            $items = @($folder.Items() | Where-Object {
                $_.IsFolder -and $_.IsFileSystem -and ($_.ExtendedProperty('System.Home.Grouping') -eq 1)
            } | ForEach-Object { @{name = $_.Name; path = $_.Path} })
            ConvertTo-Json -InputObject $items -Compress
        """
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        self.timer.start(6000)
        self.process.start(str(executable), ["-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script])

    def finish_loading(self, exit_code, exit_status):
        self.timer.stop()
        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            try:
                entries = json.loads(bytes(self.process.readAllStandardOutput()).decode("utf-8-sig"))
                self.entries = [(entry["name"], entry["path"]) for entry in entries if entry.get("path")]
            except (ValueError, KeyError, TypeError, UnicodeError):
                pass
        self.ready = True
        self.loaded.emit()
        if self._refresh_pending:
            self._refresh_pending = False
            QTimer.singleShot(0, lambda: self.start(refresh=True))

    def watch_pins_file(self):
        path = str(self._pins_file)
        if self._pins_file.is_file() and path not in self.watcher.files():
            self.watcher.addPath(path)

    def schedule_refresh(self, path):
        self.watch_pins_file()
        self.refresh_timer.start(200)

    def loading_failed(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.finish_loading(-1, QProcess.ExitStatus.CrashExit)

    def get(self, refresh=False):
        self.start(refresh)
        if not self.ready:
            loop = QEventLoop()
            self.loaded.connect(loop.quit)
            loop.exec()
            self.loaded.disconnect(loop.quit)
        return list(self.entries)


def folder_places_cache():
    app = QApplication.instance()
    cache = getattr(app, "_folder_places_cache", None)
    if cache is None:
        cache = FolderPlacesCache(app)
        app._folder_places_cache = cache
    return cache


def preload_folder_places():
    if sys.platform.startswith("win"):
        folder_places_cache().start()

def system_bookmarks():
    config = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericConfigLocation))
    entries = []
    for source in (config / "gtk-3.0/bookmarks", config / "gtk-4.0/bookmarks", Path.home() / ".gtk-bookmarks"):
        try:
            lines = source.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        for line in lines:
            address, _, label = line.partition(" ")
            url = QUrl(address)
            if url.isLocalFile():
                path = url.toLocalFile()
                entries.append((label.strip() or Path(path).name or path, path))
    data = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation))
    try:
        root = ElementTree.parse(data / "user-places.xbel").getroot()
        for bookmark in root.findall("bookmark"):
            url = QUrl(bookmark.get("href", ""))
            if url.isLocalFile() and not any(node.text == "true" for node in bookmark.iter("isHidden")):
                path = url.toLocalFile()
                entries.append((bookmark.findtext("title") or Path(path).name or path, path))
    except (OSError, ElementTree.ParseError):
        pass
    return entries


class NewProjectFolderDialog(QDialog):
    def __init__(self, parent, directory, project_folder=True):
        super().__init__(parent)
        self.directory = Path(directory)
        self.created_path = None
        self.setWindowTitle("New Project Folder" if project_folder else "New Folder")
        self.setModal(True)
        scale = widget_global_scale(self)
        self.setStyleSheet(ui.get_scaled_stylesheet(ui.BASE_WINDOW_STYLESHEET, scale, widget_ui_brightness(self)))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("What should the project folder be called?" if project_folder else "What should the folder be called?", self))
        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Enter project folder name" if project_folder else "Enter folder name")
        self.name_input.setAccessibleName("Project folder name" if project_folder else "Folder name")
        self.name_input.returnPressed.connect(self.accept)
        layout.addWidget(self.name_input)
        self.message = QLabel(self)
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.message.hide()
        buttons = QHBoxLayout()
        self.create_button = QPushButton("Create", self)
        self.create_button.setAutoDefault(False)
        self.create_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.create_button, 1)
        buttons.addWidget(self.cancel_button, 1)
        layout.addLayout(buttons)
        for widget in self.findChildren(QWidget):
            widget.setProperty("noShadow", True)
        fit_compact_popup(self, width=420, scale=scale)

    def showEvent(self, event):
        super().showEvent(event)
        self.name_input.setFocus()

    def show_error(self, text):
        self.message.setText(text)
        self.message.show()
        fit_compact_popup(self, width=420)
        self.name_input.setFocus()

    def accept(self):
        name = self.name_input.text().strip()
        if not name or name in (".", "..") or "/" in name or "\\" in name or (sys.platform.startswith("win") and any(character in name for character in '<>:"|?*')):
            self.show_error("Enter a folder name without path separators.")
            return
        path = self.directory / name
        try:
            path.mkdir()
        except FileExistsError:
            self.show_error("A folder or file with this name already exists.")
            return
        except OSError as error:
            self.show_error(f"Could not create the folder: {error.strerror or error}")
            return
        self.created_path = str(path)
        super().accept()


class ProjectFolderDialog(QDialog):
    def __init__(self, parent=None, title="Select Project Folder(s)", directory="", mode="directories"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setProperty("adaptive_popup", True)
        self.setObjectName("ProjectFolderDialog")
        self.scale = widget_global_scale(self)
        self.mode = mode
        self._file_mode = mode in ("open", "multiple", "save")
        self._history = []
        self._history_index = -1
        self._selected = []
        self._pins = [] if sys.platform.startswith("win") else system_bookmarks()
        self._project_path = getattr(parent, "game_custom_maps_path", None)
        self._current_path = str(Path.home())
        self._icon_provider = QFileIconProvider()
        self._shortcuts = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.back_button = self.navigation_button("Back", QStyle.StandardPixmap.SP_ArrowBack, lambda: self.step_history(-1))
        self.forward_button = self.navigation_button("Forward", QStyle.StandardPixmap.SP_ArrowForward, lambda: self.step_history(1))
        self.up_button = self.navigation_button("Up one folder", QStyle.StandardPixmap.SP_ArrowUp, self.go_up)
        for button in (self.back_button, self.forward_button, self.up_button):
            toolbar.addWidget(button)
        self.path_input = QLineEdit(self)
        self.path_input.setObjectName("FolderPath")
        self.path_input.setAccessibleName("Folder path")
        self.path_input.setPlaceholderText("Enter a folder path")
        self.path_input.setClearButtonEnabled(True)
        self.path_input.returnPressed.connect(self.enter_path)
        toolbar.addWidget(self.path_input, 1)
        toolbar.addWidget(self.navigation_button("Refresh", QStyle.StandardPixmap.SP_BrowserReload, self.refresh))
        layout.addLayout(toolbar)

        actions = QHBoxLayout()
        self.folder_count = QLabel("Folders", self)
        self.folder_count.setObjectName("FolderMuted")
        actions.addWidget(self.folder_count, 1)
        self.new_folder_button = QPushButton("New folder", self)
        self.new_folder_button.setAutoDefault(False)
        self.new_folder_button.setMinimumSize(int(round(140 * self.scale)), int(round(42 * self.scale)))
        self.new_folder_button.clicked.connect(self.show_new_folder)
        actions.addWidget(self.new_folder_button)
        layout.addLayout(actions)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.sidebar = SmoothListWidget(self.splitter)
        self.sidebar.setObjectName("FolderPlaces")
        self.sidebar.setMinimumWidth(int(round(140 * self.scale)))
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.sidebar.setIconSize(QSize(int(round(20 * self.scale)), int(round(20 * self.scale))))
        self.sidebar.itemClicked.connect(self.open_place)
        self.sidebar.itemActivated.connect(self.open_place)

        self._browser_icon_provider = FolderBrowserIconProvider()
        self.model = FolderListingModel(self._browser_icon_provider, self, include_files=self._file_mode)
        self.model.directoryLoaded.connect(self.directory_loaded)
        self.model.directoryFailed.connect(self.directory_failed)
        self.model.rowsInserted.connect(self.update_folder_count)
        self.model.rowsRemoved.connect(self.update_folder_count)
        self.model.modelReset.connect(self.update_folder_count)
        self.completion_model = QFileSystemModel(self)
        self.completion_model.setOption(QFileSystemModel.Option.DontUseCustomDirectoryIcons, True)
        self.completion_model.setOption(QFileSystemModel.Option.DontResolveSymlinks, True)
        self.completion_model.setOption(QFileSystemModel.Option.DontWatchForChanges, True)
        self.completion_model.setFilter(QDir.Filter.Dirs | QDir.Filter.NoDotAndDotDot)
        self.completion_model.setRootPath("")
        completer = QCompleter(self.completion_model, self.path_input)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive if sys.platform.startswith("win") else Qt.CaseSensitivity.CaseSensitive)
        self.path_input.setCompleter(completer)
        self.tree = SmoothTreeView(self.splitter)
        self.tree.setObjectName("FolderDetails")
        self.tree.setModel(self.model)
        self.tree.setRootIsDecorated(False)
        self.tree.setItemsExpandable(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setIconSize(QSize(int(round(18 * self.scale)), int(round(18 * self.scale))))
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection if mode in ("directories", "multiple") else QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        self.tree.setColumnHidden(1, not self._file_mode)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.moveSection(header.visualIndex(3), 1)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.tree.setColumnWidth(2, int(round(110 * self.scale)))
        self.tree.setColumnWidth(3, int(round(165 * self.scale)))
        self.tree.setColumnWidth(1, int(round(85 * self.scale)))
        self.tree.activated.connect(self.activate_entry)
        self.tree.selectionModel().selectionChanged.connect(self.update_selection)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([int(round(205 * self.scale)), int(round(610 * self.scale))])
        layout.addWidget(self.splitter, 1)

        self.message = QLabel(self)
        self.message.setObjectName("FolderMuted")
        self.message.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.message)
        self.message.hide()
        if self._file_mode:
            self.build_file_controls(layout)
        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.selection_label = QLabel(self)
        self.selection_label.setObjectName("FolderSelection")
        self.selection_label.setMinimumWidth(0)
        self.selection_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        footer.addWidget(self.selection_label, 1)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        self.choose_button = QPushButton("Select folder", self)
        self.choose_button.setObjectName("FolderChoose")
        self.choose_button.setAutoDefault(False)
        self.choose_button.clicked.connect(self.accept)
        for button in (self.cancel_button, self.choose_button):
            button.setMinimumWidth(int(round(115 * self.scale)))
            footer.addWidget(button)
        layout.addLayout(footer)
        for widget in self.findChildren(QWidget):
            widget.setProperty("noShadow", True)
        self.apply_style()
        apply_layout_scale(self, self.scale)
        self.setMinimumSize(int(round(480 * self.scale)), int(round(310 * self.scale)))
        self.resize(int(round(1240 * self.scale)), int(round(820 * self.scale)))
        for sequence, callback in (("Alt+Left", lambda: self.step_history(-1)), ("Alt+Right", lambda: self.step_history(1)), ("Alt+Up", self.go_up), ("Ctrl+L", self.focus_path), ("Ctrl+R", self.refresh), ("Ctrl+Return", self.accept)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        if sys.platform.startswith("win"):
            self.load_windows_places()
        self.navigate(directory or str(Path.home()))
        if not self._history:
            self.navigate(str(Path.home()))
        self.rebuild_places()

    def navigation_button(self, label, icon, callback):
        button = QPushButton(self)
        button.setObjectName("FolderNavigation")
        button.setToolTip(label)
        button.setAccessibleName(label)
        size = max(12, int(round(18 * self.scale)))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#333333" if widget_ui_brightness(self) > 180 else "#dddddd")
        painter.setPen(QPen(color, max(1.2, 1.5 * self.scale), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        points = {
            QStyle.StandardPixmap.SP_ArrowBack: ((0.62, 0.22), (0.34, 0.5), (0.62, 0.78)),
            QStyle.StandardPixmap.SP_ArrowForward: ((0.38, 0.22), (0.66, 0.5), (0.38, 0.78)),
            QStyle.StandardPixmap.SP_ArrowUp: ((0.22, 0.62), (0.5, 0.34), (0.78, 0.62)),
        }
        if icon in points:
            painter.drawPolyline(QPolygonF([QPointF(x * size, y * size) for x, y in points[icon]]))
        else:
            painter.drawArc(QRectF(size * 0.2, size * 0.2, size * 0.6, size * 0.6), 45 * 16, 285 * 16)
            painter.drawPolyline(QPolygonF([QPointF(size * 0.52, size * 0.2), QPointF(size * 0.75, size * 0.2), QPointF(size * 0.75, size * 0.43)]))
        painter.end()
        button.setIcon(QIcon(pixmap))
        button.setAutoDefault(False)
        button.setFixedSize(int(round(34 * self.scale)), int(round(36 * self.scale)))
        button.clicked.connect(callback)
        return button

    def apply_style(self):
        brightness = widget_ui_brightness(self)
        surface = ui.get_ui_background_brightness(brightness)
        light = brightness > 180
        text = "#202020" if light else "#ededed"
        muted = "#606060" if light else "#aaaaaa"
        border = "#b4b4b4" if light else "#3d3d3d"
        panel = QColor(*([max(0, surface - 5)] * 3)).name()
        hover = QColor(*([min(255, surface + 18)] * 3)).name()
        accent = QColor(ui.ACCENT_COLOR)
        selected = QColor(accent)
        selected.setAlpha(45)
        style = f"""
            QDialog#ProjectFolderDialog {{ background: {QColor(*([surface] * 3)).name()}; color: {text}; }}
            QTreeView#FolderDetails, QListWidget#FolderPlaces {{
                background: {panel}; color: {text}; border: 1px solid {border};
                border-radius: 8px; outline: none; padding: 4px;
                selection-background-color: {selected.name(QColor.NameFormat.HexArgb)};
                selection-color: {text};
            }}
            QTreeView#FolderDetails::item, QListWidget#FolderPlaces::item {{
                min-height: 32px; padding: 2px 6px; border: none;
            }}
            QTreeView#FolderDetails::item:hover, QListWidget#FolderPlaces::item:hover {{ background: {hover}; }}
            QTreeView#FolderDetails::item:selected, QListWidget#FolderPlaces::item:selected {{
                background: {selected.name(QColor.NameFormat.HexArgb)}; color: {text};
            }}
            QHeaderView::section {{
                background: {panel}; color: {muted}; border: none;
                border-bottom: 1px solid {border}; padding: 8px; font-weight: 600;
            }}
            QPushButton#FolderNavigation {{ padding: 0px; min-height: 0px; }}
            QPushButton#FolderNavigation:pressed {{ padding-top: 3px; }}
            QLabel#FolderMuted {{ color: {muted}; font-size: 9pt; }}
            QLabel#FolderSelection {{ color: {text}; }}
            QSplitter::handle {{ background: transparent; width: 10px; }}
        """
        shared_style = ui.get_scaled_stylesheet(ui.BASE_WINDOW_STYLESHEET, self.scale, brightness)
        self.setStyleSheet(shared_style + scale_stylesheet_dimensions(style, self.scale))

    def rebuild_places(self):
        self.sidebar.sc_reset_to_native()
        self.sidebar.clear()
        seen = set()

        def group(title, entries):
            items = []
            for label, path in entries:
                if not path:
                    continue
                path = os.path.normpath(path)
                key = os.path.normcase(path)
                if key in seen:
                    continue
                seen.add(key)
                items.append((label, path))
            if not items:
                return
            heading = QListWidgetItem(title, self.sidebar)
            heading.setFlags(Qt.ItemFlag.NoItemFlags)
            font = heading.font()
            font.setBold(True)
            heading.setFont(font)
            for label, path in items:
                item = QListWidgetItem(self._icon_provider.icon(QFileInfo(path)), label, self.sidebar)
                item.setData(Qt.ItemDataRole.UserRole, path)
                item.setToolTip(QDir.toNativeSeparators(path))

        group("Quick access" if sys.platform.startswith("win") else "Bookmarks", self._pins)
        locations = [("Home", str(Path.home()))]
        for label, location in (("Desktop", "DesktopLocation"), ("Documents", "DocumentsLocation"), ("Downloads", "DownloadLocation"), ("Pictures", "PicturesLocation"), ("Music", "MusicLocation"), ("Videos", "MoviesLocation")):
            path = QStandardPaths.writableLocation(getattr(QStandardPaths.StandardLocation, location))
            if path and Path(path).is_dir():
                locations.append((label, path))
        project_path = self._project_path
        if project_path and Path(project_path).is_dir():
            locations.append(("Project folders", str(project_path)))
        group("Places", locations)
        drives = []
        for volume in QStorageInfo.mountedVolumes():
            if not volume.isValid() or not volume.isReady():
                continue
            path = volume.rootPath()
            if not sys.platform.startswith("win") and path != "/" and not path.startswith(("/media/", "/mnt/", "/run/media/")):
                continue
            label = volume.displayName() or volume.name() or path
            if sys.platform.startswith("win"):
                label = f"{label} ({QDir.toNativeSeparators(path)})" if label != path else QDir.toNativeSeparators(path)
            elif path == "/":
                label = "File system"
            drives.append((label, path))
        group("This PC" if sys.platform.startswith("win") else "Devices", drives)
        self.mark_current_place()

    def load_windows_places(self, refresh=False):
        self._pins = folder_places_cache().get(refresh)

    def open_place(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.navigate(path)

    def mark_current_place(self):
        self.sidebar.clearSelection()
        self.sidebar.setCurrentRow(-1)
        for row in range(self.sidebar.count()):
            item = self.sidebar.item(row)
            path = item.data(Qt.ItemDataRole.UserRole)
            if path and os.path.normcase(path) == os.path.normcase(self._current_path):
                self.sidebar.setCurrentItem(item)
                break

    def navigate(self, path, record=True):
        path = os.path.expandvars(os.path.expanduser(str(path).strip().strip('"')))
        if not os.path.isabs(path):
            path = os.path.join(self._current_path, path)
        path = os.path.abspath(path)
        if not os.path.isdir(path) or not os.access(path, os.R_OK | os.X_OK):
            self.set_message("This folder is unavailable or cannot be opened.")
            self.path_input.setText(QDir.toNativeSeparators(path))
            return False
        if record and (not self._history or os.path.normcase(path) != os.path.normcase(self._current_path)):
            self._history = self._history[:self._history_index + 1] + [path]
            self._history_index = len(self._history) - 1
        self._current_path = path
        self.path_input.setText(QDir.toNativeSeparators(path))
        self.tree.sc_reset_to_native()
        self.tree.setRootIndex(self.model.setRootPath(path))
        self.tree.clearSelection()
        self.tree.sc_reset_to_native()
        self.back_button.setEnabled(self._history_index > 0)
        self.forward_button.setEnabled(self._history_index + 1 < len(self._history))
        self.up_button.setEnabled(os.path.dirname(path) != path)
        self.mark_current_place()
        self.update_selection()
        self.update_folder_count()
        return True

    def enter_path(self):
        if self.navigate(self.path_input.text()):
            self.tree.setFocus()

    def activate_entry(self, index):
        self.navigate(self.model.filePath(index))

    def focus_path(self):
        self.path_input.setFocus()
        self.path_input.selectAll()

    def step_history(self, direction):
        position = self._history_index + direction
        if 0 <= position < len(self._history):
            old_position = self._history_index
            self._history_index = position
            if not self.navigate(self._history[position], record=False):
                self._history_index = old_position

    def go_up(self):
        self.navigate(os.path.dirname(self._current_path))

    def refresh(self):
        self.navigate(self._current_path, record=False)
        self.model.setRootPath(self._current_path, refresh=True)
        if sys.platform.startswith("win"):
            self.load_windows_places(refresh=True)
        else:
            self._pins = system_bookmarks()
        self.rebuild_places()

    def directory_loaded(self, path):
        if os.path.normcase(path) == os.path.normcase(self._current_path):
            self.update_folder_count()

    def directory_failed(self, path, error):
        if os.path.normcase(path) == os.path.normcase(self._current_path):
            self.set_message(f"Could not open this folder: {error}")

    def update_folder_count(self, *args):
        count = self.model.rowCount(self.tree.rootIndex())
        noun = "item" if self._file_mode else "folder"
        self.folder_count.setText(f"{count} {noun}{'s' if count != 1 else ''}")

    def selected_directories(self):
        return list(self._selected)

    def current_selection(self):
        return [os.path.normpath(self.model.filePath(index)) for index in self.tree.selectionModel().selectedRows(0)] or [self._current_path]

    def update_selection(self, *args):
        paths = self.current_selection()
        count = len(paths)
        label = (Path(paths[0]).name or paths[0]) if count == 1 else f"{count} folders selected"
        self.selection_label.setText(label)
        self.selection_label.setToolTip("\n".join(QDir.toNativeSeparators(path) for path in paths))
        self.choose_button.setText("Select folder" if count == 1 else f"Select {count} folders")
        self.set_message("")

    def set_message(self, text):
        self.message.setText(text)
        self.message.setToolTip(text)
        self.message.setVisible(bool(text))

    def show_new_folder(self):
        dialog = NewProjectFolderDialog(self, self._current_path, project_folder=self.mode == "directories")
        result = dialog.exec()
        path = dialog.created_path
        if not ui.sip.isdeleted(dialog):
            dialog.deleteLater()
        if result == QDialog.DialogCode.Accepted and path:
            self.navigate(path)

    def accept(self):
        if os.path.normcase(self.path_input.text()) != os.path.normcase(QDir.toNativeSeparators(self._current_path)):
            if not self.navigate(self.path_input.text()):
                return
        paths = self.current_selection()
        if not all(os.path.isdir(path) for path in paths):
            self.set_message("A selected folder is no longer available. Refresh and select it again.")
            return
        self._selected = paths
        super().accept()


def initial_file_location(directory, mode):
    downloads = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
    fallback = downloads if downloads and os.path.isdir(downloads) else str(Path.home())
    if not directory:
        return fallback, ""
    path = os.path.expandvars(os.path.expanduser(str(directory)))
    if os.path.isdir(path):
        return os.path.abspath(path), ""
    parent = os.path.dirname(path)
    if parent and os.path.isdir(parent):
        return os.path.abspath(parent), os.path.basename(path) if mode != "directory" else ""
    return fallback, os.path.basename(path) if mode == "save" else ""


def parse_file_filters(file_filter):
    filters = []
    for label in file_filter.split(";;"):
        label = label.strip()
        if not label:
            continue
        match = re.search(r"\(([^()]*)\)\s*$", label)
        patterns = match.group(1).split() if match else ["*"]
        filters.append((label, patterns or ["*"]))
    return filters or [("All Files (*)", ["*"])]


class FileSelectionDialog(ProjectFolderDialog):
    def __init__(self, parent=None, title="", directory="", file_filter="", mode="open"):
        self._file_filters = parse_file_filters(file_filter)
        self._editing_filename = False
        start, filename = initial_file_location(directory, mode)
        default_title = {"open": "Select File", "multiple": "Select Files", "save": "Save File", "directory": "Select Folder"}[mode]
        super().__init__(parent, title or default_title, start, mode=mode)
        if self._file_mode:
            self.model.setNameFilters(self._file_filters[0][1])
            if filename:
                self.filename_input.setText(filename)
                self.choose_button.setEnabled(True)

    def build_file_controls(self, layout):
        row = QHBoxLayout()
        label = QLabel("File name", self)
        label.setFixedWidth(int(round(70 * self.scale)))
        self.filename_input = QLineEdit(self)
        self.filename_input.setAccessibleName("File name")
        self.filename_input.setPlaceholderText("Enter a file name" if self.mode == "save" else "Select a file or enter its name")
        label.setBuddy(self.filename_input)
        self.filename_input.returnPressed.connect(self.accept)
        self.filename_input.textEdited.connect(self.edit_filename)
        row.addWidget(label)
        row.addWidget(self.filename_input, 1)
        layout.addLayout(row)
        self.filter_input = IgnoreWheelComboBox(self)
        self.filter_input.setAccessibleName("File type")
        self.filter_input.setSizeAdjustPolicy(self.filter_input.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.filter_input.setMinimumContentsLength(12)
        for label, patterns in self._file_filters:
            self.filter_input.addItem(label, patterns)
        self.filter_input.setToolTip(self._file_filters[0][0])
        self.filter_input.currentIndexChanged.connect(self.change_filter)
        row = QHBoxLayout()
        label = QLabel("File type", self)
        label.setFixedWidth(int(round(70 * self.scale)))
        label.setBuddy(self.filter_input)
        row.addWidget(label)
        row.addWidget(self.filter_input, 1)
        layout.addLayout(row)

    def change_filter(self, index):
        self.filter_input.setToolTip(self._file_filters[index][0])
        self.tree.sc_reset_to_native()
        self.model.setNameFilters(self._file_filters[index][1])
        self.tree.sc_reset_to_native()
        self.update_selection()

    def edit_filename(self, text):
        self._editing_filename = True
        self.tree.clearSelection()
        self._editing_filename = False
        self.choose_button.setEnabled(bool(text.strip()))
        self.set_message("")

    def selectedFiles(self):
        return list(self._selected)

    def current_selection(self):
        if not self._file_mode:
            return super().current_selection()
        return [os.path.normpath(self.model.filePath(index)) for index in self.tree.selectionModel().selectedRows(0) if not self.model.isDir(index)]

    def update_selection(self, *args):
        if not self._file_mode:
            return super().update_selection(*args)
        if self._editing_filename:
            return
        paths = self.current_selection()
        if paths:
            names = [Path(path).name for path in paths]
            self.filename_input.setText(names[0] if len(names) == 1 else " ".join(f'"{name}"' for name in names))
        elif self.mode != "save":
            self.filename_input.clear()
        count = len(paths)
        self.selection_label.setText(Path(paths[0]).name if count == 1 else f"{count} files selected" if count else "")
        self.selection_label.setToolTip("\n".join(QDir.toNativeSeparators(path) for path in paths))
        self.choose_button.setText("Save" if self.mode == "save" else f"Open {count} files" if count > 1 else "Open")
        self.choose_button.setEnabled(bool(paths or self.filename_input.text().strip() or self.tree.selectionModel().selectedRows(0)))
        self.set_message("")

    def enter_path(self):
        path = self.resolve_path(self.path_input.text())
        if self._file_mode and os.path.isfile(path):
            if self.navigate(os.path.dirname(path)):
                self.filename_input.setText(os.path.basename(path))
                self.choose_button.setEnabled(True)
                self.filename_input.setFocus()
            return
        super().enter_path()

    def activate_entry(self, index):
        if self.model.isDir(index):
            self.navigate(self.model.filePath(index))
        else:
            self.filename_input.setText(self.model.fileName(index))
            self.accept()

    def resolve_path(self, text):
        path = os.path.expandvars(os.path.expanduser(text.strip().strip('"')))
        return os.path.abspath(path if os.path.isabs(path) else os.path.join(self._current_path, path))

    def accept(self):
        if not self._file_mode:
            return super().accept()
        if os.path.normcase(self.path_input.text()) != os.path.normcase(QDir.toNativeSeparators(self._current_path)):
            self.enter_path()
            return
        paths = self.current_selection()
        text = self.filename_input.text().strip()
        if self.mode == "save" or not paths:
            if not text:
                folders = self.tree.selectionModel().selectedRows(0)
                if folders:
                    self.navigate(self.model.filePath(folders[0]))
                else:
                    self.set_message("Select a file or enter a file name.")
                return
            path = self.resolve_path(text)
            if os.path.isdir(path):
                self.navigate(path)
                return
            if self.mode == "save":
                patterns = self.filter_input.currentData()
                suffix = re.fullmatch(r"\*\.([A-Za-z0-9.]+)", patterns[0])
                if not Path(path).suffix and suffix:
                    path += "." + suffix.group(1)
                name = os.path.basename(path)
                if not name or (os.name == "nt" and (any(character in name for character in '<>:"|?*') or name.endswith((".", " ")))):
                    self.set_message("Enter a valid file name.")
                    return
                parent = os.path.dirname(path)
                if not os.path.isdir(parent) or not os.access(parent, os.W_OK):
                    self.set_message("The destination folder is unavailable or cannot be written to.")
                    return
            paths = [path]
        if self.mode != "save":
            if not all(os.path.isfile(path) for path in paths):
                self.set_message("A selected file is unavailable. Refresh or check the file name.")
                return
            if not all(self.model.matches_filters(os.path.basename(path)) for path in paths):
                self.set_message("Select a file that matches the chosen file type.")
                return
        self._selected = paths
        QDialog.accept(self)
