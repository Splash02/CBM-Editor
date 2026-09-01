from .ui_utils import *

WINDOWS_INSTALL_FOLDER = "CBM_Editor"
WINDOWS_INSTALL_FILENAME = "CBM_Editor.exe"
WINDOWS_SETUP_STATE_FILENAME = "setup_state.json"
WINDOWS_SHORTCUT_NAMES = ("CBM Editor.lnk", "CBM Editor -PREVIEW-.lnk")
WINDOWS_VENDOR_KEY = r"Software\Splash\CBM Editor"
WINDOWS_APP_PATH_KEY = r"Software\Microsoft\Windows\CurrentVersion\App Paths\CBM_Editor.exe"
WINDOWS_UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CBM Editor"


def _normalized_windows_path(path):
    return os.path.normcase(os.path.abspath(str(path)))


def _same_windows_path(first, second):
    return _normalized_windows_path(first) == _normalized_windows_path(second)


def _is_link_or_junction(path):
    candidate = Path(path)
    if candidate.is_symlink():
        return True
    checker = getattr(candidate, "is_junction", None)
    return bool(checker and checker())


def _resolved_existing_directory(path, label):
    candidate = Path(path)
    if not candidate.is_dir():
        raise RuntimeError(f"{label} does not exist.")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_dir():
        raise RuntimeError(f"{label} is invalid.")
    return resolved


def get_windows_local_appdata_root():
    if not sys.platform.startswith("win"):
        raise RuntimeError("Windows installation is unavailable on this platform.")
    value = os.environ.get("LOCALAPPDATA")
    if not value:
        raise RuntimeError("LOCALAPPDATA is unavailable.")
    return _resolved_existing_directory(value, "The local application data folder")


def get_windows_roaming_appdata_root():
    value = os.environ.get("APPDATA")
    if not value:
        raise RuntimeError("APPDATA is unavailable.")
    return _resolved_existing_directory(value, "The roaming application data folder")


def get_windows_install_directory(create=False):
    root = get_windows_local_appdata_root()
    path = root / WINDOWS_INSTALL_FOLDER
    if path.exists():
        if not path.is_dir() or _is_link_or_junction(path):
            raise RuntimeError("The CBM Editor installation folder is not a regular directory.")
        resolved = path.resolve(strict=True)
        expected = root / WINDOWS_INSTALL_FOLDER
        if not _same_windows_path(resolved, expected):
            raise RuntimeError("The CBM Editor installation folder redirects to another location.")
        return resolved
    if create:
        path.mkdir(mode=0o700)
        resolved = path.resolve(strict=True)
        if not _same_windows_path(resolved, root / WINDOWS_INSTALL_FOLDER):
            raise RuntimeError("The CBM Editor installation folder could not be verified.")
        return resolved
    return path


def get_windows_installed_executable(create_directory=False):
    return get_windows_install_directory(create_directory) / WINDOWS_INSTALL_FILENAME


def get_windows_process_temp_directory():
    root = get_windows_local_appdata_root()
    path = root / "Temp"
    if path.exists():
        if not path.is_dir() or _is_link_or_junction(path):
            raise RuntimeError("The Windows temporary directory is invalid.")
        resolved = path.resolve(strict=True)
        if not _same_windows_path(resolved, root / "Temp"):
            raise RuntimeError("The Windows temporary directory redirects to another location.")
        return resolved
    path.mkdir(mode=0o700)
    return path.resolve(strict=True)


def get_windows_helper_environment():
    environment = os.environ.copy()
    for name in tuple(environment):
        upper_name = name.upper()
        if upper_name.startswith("_PYI_") or upper_name.startswith("NUITKA_ONEFILE_"):
            environment.pop(name, None)
    temporary = get_windows_process_temp_directory()
    environment["TEMP"] = str(temporary)
    environment["TMP"] = str(temporary)
    environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return environment


def get_setup_state_path():
    roaming = get_windows_roaming_appdata_root()
    local_low = roaming.parent / "LocalLow"
    local_low = _resolved_existing_directory(local_low, "The LocalLow application data folder")
    root = local_low / "CBM_Editor"
    if root.exists():
        if not root.is_dir() or _is_link_or_junction(root):
            raise RuntimeError("The CBM Editor data folder is not a regular directory.")
        resolved = root.resolve(strict=True)
        if not _same_windows_path(resolved, local_low / "CBM_Editor"):
            raise RuntimeError("The CBM Editor data folder redirects to another location.")
        root = resolved
    else:
        root.mkdir(mode=0o700)
    return root / WINDOWS_SETUP_STATE_FILENAME


def windows_setup_completed():
    if not sys.platform.startswith("win"):
        return True
    try:
        path = get_setup_state_path()
        if _is_link_or_junction(path):
            return False
        if not path.is_file():
            return False
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("setup_completed") is True
    except Exception:
        return False


def set_windows_setup_completed(completed):
    if not sys.platform.startswith("win"):
        return
    path = get_setup_state_path()
    temporary = path.with_name(f"{path.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        if temporary.is_dir() and not temporary.is_symlink():
            raise RuntimeError("The temporary setup state path is invalid.")
        temporary.unlink()
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump({"setup_completed": bool(completed)}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _validate_windows_executable(path):
    original = Path(path)
    if _is_link_or_junction(original):
        raise RuntimeError("The application executable redirects to another location.")
    candidate = original.resolve(strict=True)
    if not candidate.is_file():
        raise RuntimeError("The application executable does not exist.")
    if not _same_windows_path(original, candidate):
        raise RuntimeError("The application executable path could not be verified.")
    if candidate.stat().st_nlink != 1:
        raise RuntimeError("The application executable has multiple filesystem links.")
    with candidate.open("rb") as handle:
        if handle.read(2) != b"MZ":
            raise RuntimeError("The application file is not a Windows executable.")
    return candidate


def _read_registry_value(key_path, value_name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            return winreg.QueryValueEx(key, value_name)[0]
    except OSError:
        return None


def is_windows_installation_active():
    if not sys.platform.startswith("win") or not is_packaged_application():
        return False
    current = get_application_executable_path()
    if current is None:
        return False
    try:
        installed = get_windows_installed_executable(False)
    except RuntimeError:
        return False
    registered = _read_registry_value(WINDOWS_VENDOR_KEY, "ExecutablePath")
    return bool(registered and _same_windows_path(current, installed) and _same_windows_path(registered, installed))


def _start_menu_programs_directory():
    root = get_windows_roaming_appdata_root()
    programs = root / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return _resolved_existing_directory(programs, "The Start Menu programs folder")


def get_windows_shortcut_paths():
    programs = _start_menu_programs_directory()
    return tuple(programs / name for name in WINDOWS_SHORTCUT_NAMES)


def _remove_known_shortcuts():
    for shortcut in get_windows_shortcut_paths():
        if shortcut.is_file() or shortcut.is_symlink():
            shortcut.unlink()


def _create_windows_shortcut(executable, preview):
    executable = _validate_windows_executable(executable)
    shortcuts = get_windows_shortcut_paths()
    _remove_known_shortcuts()
    shortcut = shortcuts[1 if preview else 0]
    helper_env = get_windows_helper_environment()
    helper_env.update({
        "CBM_SHORTCUT_PATH": str(shortcut),
        "CBM_SHORTCUT_TARGET": str(executable),
        "CBM_SHORTCUT_WORKING_DIRECTORY": str(executable.parent),
        "CBM_SHORTCUT_DESCRIPTION": "CBM Editor -PREVIEW-" if preview else "CBM Editor",
    })
    script = (
        "$shell=New-Object -ComObject WScript.Shell; "
        "$shortcut=$shell.CreateShortcut($env:CBM_SHORTCUT_PATH); "
        "$shortcut.TargetPath=$env:CBM_SHORTCUT_TARGET; "
        "$shortcut.WorkingDirectory=$env:CBM_SHORTCUT_WORKING_DIRECTORY; "
        "$shortcut.IconLocation=($env:CBM_SHORTCUT_TARGET + ',0'); "
        "$shortcut.Description=$env:CBM_SHORTCUT_DESCRIPTION; "
        "$shortcut.Save()"
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-Command",
            script,
        ],
        env=helper_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
    )
    if result.returncode != 0 or not shortcut.is_file():
        raise RuntimeError("The Start Menu shortcut could not be created.")


def _write_registry_string(key, name, value):
    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, str(value))


def register_windows_installation(executable=None, preview=None, version=None):
    if not sys.platform.startswith("win"):
        return
    expected = get_windows_installed_executable(False)
    executable = _validate_windows_executable(executable or expected)
    if not _same_windows_path(executable, expected):
        raise RuntimeError("The registered executable is outside the CBM Editor installation folder.")
    preview = PREVIEW_VERSION if preview is None else bool(preview)
    display_name = "CBM Editor -PREVIEW-" if preview else "CBM Editor"
    display_version = str(VERSION_NUMBER if version is None else version).strip()
    if display_version.lower().startswith("v"):
        display_version = display_version[1:]
    uninstall_command = subprocess.list2cmdline([str(executable), "--uninstall"])
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, WINDOWS_VENDOR_KEY, 0, winreg.KEY_WRITE) as key:
        _write_registry_string(key, "InstallLocation", executable.parent)
        _write_registry_string(key, "ExecutablePath", executable)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, WINDOWS_APP_PATH_KEY, 0, winreg.KEY_WRITE) as key:
        _write_registry_string(key, "", executable)
        _write_registry_string(key, "Path", executable.parent)
        _write_registry_string(key, "ExecutablePath", executable)
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, WINDOWS_UNINSTALL_KEY, 0, winreg.KEY_WRITE) as key:
        _write_registry_string(key, "DisplayName", display_name)
        _write_registry_string(key, "DisplayVersion", display_version)
        _write_registry_string(key, "Publisher", "Splash!")
        _write_registry_string(key, "InstallLocation", executable.parent)
        _write_registry_string(key, "DisplayIcon", f"{executable},0")
        _write_registry_string(key, "UninstallString", uninstall_command)
        _write_registry_string(key, "ExecutablePath", executable)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    _create_windows_shortcut(executable, preview)
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass


def _delete_owned_registry_key(key_path, executable):
    registered = _read_registry_value(key_path, "ExecutablePath")
    if not registered or not _same_windows_path(registered, executable):
        return
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
    except FileNotFoundError:
        pass


def unregister_windows_installation(executable=None):
    if not sys.platform.startswith("win"):
        return
    expected = get_windows_installed_executable(False)
    executable = Path(executable or expected)
    if not _same_windows_path(executable, expected):
        raise RuntimeError("The unregister target is outside the CBM Editor installation folder.")
    _remove_known_shortcuts()
    _delete_owned_registry_key(WINDOWS_APP_PATH_KEY, expected)
    _delete_owned_registry_key(WINDOWS_UNINSTALL_KEY, expected)
    _delete_owned_registry_key(WINDOWS_VENDOR_KEY, expected)
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    except Exception:
        pass


def _launch_hidden_powershell(script, environment):
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-Command",
            script,
        ],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        close_fds=True,
    )


def begin_windows_installation():
    if not sys.platform.startswith("win") or not is_packaged_application():
        raise RuntimeError("Installation is only available from a built Windows executable.")
    source = _validate_windows_executable(get_application_executable_path())
    target = get_windows_installed_executable(True)
    if _same_windows_path(source, target):
        register_windows_installation(target)
        set_windows_setup_completed(True)
        return False
    temporary = target.with_name("CBM_Editor.installing.exe")
    if target.exists() and not _same_windows_path(source, target):
        _validate_windows_executable(target)
    if temporary.exists() or temporary.is_symlink():
        if temporary.is_dir() and not temporary.is_symlink():
            raise RuntimeError("The temporary installation target is invalid.")
        temporary.unlink()
    shutil.copy2(source, temporary)
    copied = _validate_windows_executable(temporary)
    if copied.stat().st_size != source.stat().st_size:
        copied.unlink(missing_ok=True)
        raise RuntimeError("The copied application file is incomplete.")
    helper_env = get_windows_helper_environment()
    helper_env.update({
        "CBM_INSTALL_SOURCE": str(source),
        "CBM_INSTALL_TEMPORARY": str(copied),
        "CBM_INSTALL_TARGET": str(target),
        "CBM_INSTALL_PID": str(os.getpid()),
    })
    helper_script = (
        "$source=$env:CBM_INSTALL_SOURCE; $temporary=$env:CBM_INSTALL_TEMPORARY; "
        "$target=$env:CBM_INSTALL_TARGET; $processId=[int]$env:CBM_INSTALL_PID; "
        "Wait-Process -Id $processId -ErrorAction SilentlyContinue; "
        "$deadline=[DateTime]::UtcNow.AddSeconds(60); $installed=$false; "
        "while (-not $installed -and [DateTime]::UtcNow -lt $deadline) { "
        "if (Test-Path -LiteralPath $temporary -PathType Leaf) { "
        "try { Move-Item -LiteralPath $temporary -Destination $target -Force -ErrorAction Stop; $installed=$true } "
        "catch { Start-Sleep -Milliseconds 100 } } else { break } }; "
        "if ($installed) { Start-Process -FilePath $target -ArgumentList '--complete-install' "
        "-WorkingDirectory (Split-Path -LiteralPath $target); "
        "while ((Test-Path -LiteralPath $source -PathType Leaf) -and [DateTime]::UtcNow -lt $deadline) { "
        "try { Remove-Item -LiteralPath $source -Force -ErrorAction Stop } "
        "catch { Start-Sleep -Milliseconds 100 } } }"
    )
    _launch_hidden_powershell(helper_script, helper_env)
    return True


def complete_windows_installation():
    if not sys.platform.startswith("win") or not is_packaged_application():
        raise RuntimeError("The installation cannot be completed by this application.")
    current = _validate_windows_executable(get_application_executable_path())
    target = get_windows_installed_executable(False)
    if not _same_windows_path(current, target):
        raise RuntimeError("The application was not started from the installation folder.")
    register_windows_installation(current)
    set_windows_setup_completed(True)


def begin_windows_uninstallation():
    if not sys.platform.startswith("win") or not is_packaged_application():
        raise RuntimeError("Uninstallation is unavailable from this application.")
    target = get_windows_installed_executable(False)
    current = _validate_windows_executable(get_application_executable_path())
    if not _same_windows_path(current, target):
        raise RuntimeError("Only the installed CBM Editor executable can uninstall the application.")
    registered = _read_registry_value(WINDOWS_VENDOR_KEY, "ExecutablePath")
    if not registered or not _same_windows_path(registered, target):
        raise RuntimeError("This executable is not registered as the installed CBM Editor application.")
    unregister_windows_installation(target)
    set_windows_setup_completed(False)
    install_directory = get_windows_install_directory(False)
    helper_env = get_windows_helper_environment()
    helper_env.update({
        "CBM_UNINSTALL_TARGET": str(target),
        "CBM_UNINSTALL_DIRECTORY": str(install_directory),
        "CBM_UNINSTALL_PID": str(os.getpid()),
    })
    helper_script = (
        "$target=$env:CBM_UNINSTALL_TARGET; $directory=$env:CBM_UNINSTALL_DIRECTORY; "
        "$processId=[int]$env:CBM_UNINSTALL_PID; Wait-Process -Id $processId -ErrorAction SilentlyContinue; "
        "$deadline=[DateTime]::UtcNow.AddSeconds(60); "
        "while ((Test-Path -LiteralPath $target -PathType Leaf) -and [DateTime]::UtcNow -lt $deadline) { "
        "try { Remove-Item -LiteralPath $target -Force -ErrorAction Stop } "
        "catch { Start-Sleep -Milliseconds 100 } }; "
        "if (-not (Test-Path -LiteralPath $target)) { "
        "try { Remove-Item -LiteralPath $directory -ErrorAction Stop } catch {} }"
    )
    _launch_hidden_powershell(helper_script, helper_env)


class WindowsSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.choice = None
        self.setWindowTitle("CBM Editor Setup")
        self.setModal(True)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowCloseButtonHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        title = QLabel("How do you want to run CBM Editor?")
        title_font = title.font()
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        description = QLabel("Install adds CBM Editor to Windows. Portable runs this file without Windows integration.")
        description.setWordWrap(True)
        layout.addWidget(description)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.install_button = QPushButton("Install")
        self.portable_button = QPushButton("Run Portable")
        self.install_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.portable_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if not is_packaged_application():
            self.install_button.setText("Install [BLOCKED]")
            self.install_button.setEnabled(False)
        self.install_button.clicked.connect(self.choose_install)
        self.portable_button.clicked.connect(self.choose_portable)
        buttons.addWidget(self.install_button)
        buttons.addWidget(self.portable_button)
        layout.addLayout(buttons)
        apply_shadows_to_container(self)
        self.ui_animation_timer = QTimer(self)
        self.ui_animation_timer.timeout.connect(update_ui_animations)
        self.ui_animation_timer.start(16)
        self.setFixedSize(self.sizeHint())

    def choose_install(self):
        self.choice = "install"
        self.accept()

    def choose_portable(self):
        self.choice = "portable"
        self.accept()

    def reject(self):
        if self.choice is not None:
            super().reject()

    def closeEvent(self, event):
        if self.choice is None:
            event.ignore()
            return
        super().closeEvent(event)


def show_windows_setup_dialog(parent=None):
    dialog = WindowsSetupDialog(parent)
    dialog.exec()
    return dialog.choice


class WindowsUninstallDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.confirmed = False
        self.decision = None
        self.setWindowTitle("Uninstall CBM Editor")
        self.setModal(True)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowCloseButtonHint
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setMinimumWidth(390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)
        content = QHBoxLayout()
        content.setSpacing(14)
        icon = QLabel()
        icon.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning).pixmap(36, 36))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        content.addWidget(icon)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(10)
        title = QLabel("Uninstall CBM Editor?")
        description = QLabel("The application will be removed. Projects and settings will be kept.")
        description.setWordWrap(True)
        text_layout.addWidget(title)
        text_layout.addWidget(description)
        content.addLayout(text_layout, 1)
        layout.addLayout(content)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.uninstall_button = QPushButton("Uninstall")
        self.cancel_button = QPushButton("Cancel")
        self.uninstall_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cancel_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.uninstall_button.clicked.connect(self.confirm_uninstall)
        self.cancel_button.clicked.connect(self.cancel_uninstall)
        buttons.addWidget(self.uninstall_button, 1)
        buttons.addWidget(self.cancel_button, 1)
        layout.addLayout(buttons)
        apply_shadows_to_container(self)
        self.ui_animation_timer = QTimer(self)
        self.ui_animation_timer.timeout.connect(update_ui_animations)
        self.ui_animation_timer.start(16)
        size_hint = self.sizeHint()
        self.setFixedSize(max(390, size_hint.width()), size_hint.height())

    def confirm_uninstall(self):
        self.confirmed = True
        self.decision = "uninstall"
        self.accept()

    def cancel_uninstall(self):
        self.decision = "cancel"
        super().reject()

    def reject(self):
        if self.decision is not None:
            super().reject()

    def closeEvent(self, event):
        if self.decision is None:
            event.ignore()
            return
        super().closeEvent(event)


def show_windows_uninstall_dialog(parent=None):
    dialog = WindowsUninstallDialog(parent)
    dialog.exec()
    return dialog.confirmed
