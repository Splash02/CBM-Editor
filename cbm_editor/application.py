from .main_window import *
from datetime import datetime
import traceback

register_shared_globals(globals())

def record_startup(message):
    try:
        path = get_editor_data_directory(create=True) / "startup.log"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().astimezone().isoformat()} {message}\n")
    except OSError:
        pass


class StartupWorker(QThread):
    stage_changed = pyqtSignal(str)
    ready = pyqtSignal()
    failed = pyqtSignal(str)

    def run(self):
        try:
            for stage, action in (
                ("Starting audio...", get_audio_engine),
                ("Preparing editor files...", initialize_editor_storage),
            ):
                record_startup(stage)
                self.stage_changed.emit(stage)
                action()
            self.ready.emit()
        except Exception:
            error = traceback.format_exc()
            record_startup(error)
            self.failed.emit(error)


class InstallationRefreshWorker(QThread):
    def run(self):
        try:
            refresh_installation_registration()
        except Exception:
            record_startup(traceback.format_exc())


def main():
    global TARGET_FPS, launch_window
    launch_window = None
    refresh_registration = False
    if sys.platform.startswith('win'):
        import subprocess
        subprocess.CREATE_NO_WINDOW = 0x08000000
        _old_popen = subprocess.Popen.__init__
        
        def _new_popen(self, *args, **kwargs):
            kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
            _old_popen(self, *args, **kwargs)
        
        subprocess.Popen.__init__ = _new_popen
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings)
    fmt = QSurfaceFormat()
    fmt.setSwapInterval(1)
    fmt.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv)
    if sys.platform.startswith("linux"):
        app.setStyle("Fusion")
    install_application_fonts(app)
    
    tooltip_manager = CustomTooltipManager()
    app.installEventFilter(tooltip_manager)
    
    if TARGET_FPS == 0:
        try:
            screen = app.primaryScreen()
            if screen:
                set_target_fps(round(screen.refreshRate()))
            else:
                set_target_fps(60)
        except:
            set_target_fps(60)
    
    app.setStyleSheet(get_scaled_stylesheet(BASE_APP_STYLESHEET, 1.0))
    
    icon_path = None
    base_path = get_base_path()
    
    icon_name = "icon_pre.png" if PREVIEW_VERSION else "icon.png"
    paths_to_check = [
        os.path.join(base_path, icon_name),
        os.path.join(base_path, "sounds", icon_name),
        os.path.join(base_path, "icon.png"),
        os.path.join(base_path, "sounds", "icon.png")
    ]
    
    for p in paths_to_check:
        if os.path.exists(p):
            icon_path = p
            break

    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    arguments = set(sys.argv[1:])
    if installation_supported():
        if "--uninstall" in arguments:
            confirmed, remove_editor_data = show_uninstall_dialog()
            if confirmed:
                try:
                    begin_uninstallation(remove_editor_data)
                except Exception as error:
                    QMessageBox.critical(None, "Uninstall Failed", str(error))
            return
        if "--complete-install" in arguments:
            try:
                complete_installation("--create-desktop-shortcut" in arguments)
            except Exception as error:
                QMessageBox.critical(None, "Installation Failed", str(error))
                return
        elif is_installation_active():
            refresh_registration = True
        force_setup = "--setup" in arguments
        if force_setup or (is_packaged_application() and not setup_completed()):
            choice, portable_destination, create_desktop_shortcut = show_setup_dialog()
            if choice == "install":
                try:
                    if begin_installation(create_desktop_shortcut):
                        return
                except Exception as error:
                    QMessageBox.critical(None, "Installation Failed", str(error))
                    return
            elif choice == "portable":
                try:
                    if portable_destination and begin_portable_mode(portable_destination):
                        return
                    set_setup_completed(True)
                except Exception as error:
                    QMessageBox.critical(None, "Setup Failed", str(error))
                    return
            elif force_setup:
                return

    app.setStyleSheet("")

    saved_x = 100
    saved_y = 100
    
    try:
        config_path = get_chart_editor_resources_directory() / "editor_config.json"
        if config_path.exists():
            with open(config_path, 'r') as cf:
                config = json.load(cf)
                w_data = config.get("window", {})
                saved_x = w_data.get("x", 100)
                saved_y = w_data.get("y", 100)
    except:
        pass

    record_startup("Starting editor")
    splash = AnimatedSplashScreen(icon_path, saved_x, saved_y)
    splash.startup_ready = False
    splash.set_status("Starting audio...")
    startup_worker = StartupWorker(app)
    app._startup_worker = startup_worker
    app.aboutToQuit.connect(startup_worker.wait)
    app.aboutToQuit.connect(shutdown_audio_engine)
    main_window_shown = False

    def show_main_window():
        nonlocal main_window_shown
        if main_window_shown or launch_window is None:
            return
        main_window_shown = True
        launch_window._startup_splash_active = False
        fullscreen_requested = launch_window._startup_fullscreen_requested
        maximized_requested = launch_window._startup_maximized_requested
        launch_window._startup_fullscreen_requested = False
        launch_window._startup_maximized_requested = False
        if fullscreen_requested:
            launch_window._fullscreen_restore_geometry = launch_window.saveGeometry()
            launch_window._fullscreen_restore_maximized = maximized_requested
            launch_window.showFullScreen()
        elif maximized_requested:
            launch_window.showMaximized()
        else:
            launch_window.show()
        launch_window.raise_()
        launch_window.activateWindow()
        launch_window.installEventFilter(launch_window)
        record_startup("Main window shown")
        from .file_dialog import preload_folder_places
        QTimer.singleShot(250, preload_folder_places)
        if refresh_registration:
            registration_worker = InstallationRefreshWorker(app)
            app._registration_worker = registration_worker
            app.aboutToQuit.connect(registration_worker.wait)
            registration_worker.start()
        if fullscreen_requested or maximized_requested:
            QTimer.singleShot(0, launch_window.finish_startup_fullscreen)
        if sys.platform.startswith("win") and not MICROSOFT_STORE_BUILD:
            QTimer.singleShot(2000, complete_windows_update_cleanup)
            blocked_marker_found = consume_windows_update_blocked_marker()
            update_was_blocked = "--update-blocked" in arguments or blocked_marker_found
            if update_was_blocked:
                launch_window._update_checks_disabled_for_session = True
                launch_window.update_check_timer.stop()
                QTimer.singleShot(
                    700,
                    lambda: launch_window.show_update_blocked(
                        "Windows security software blocked the update installation."
                    ),
                )
        if PREVIEW_VERSION:
            QTimer.singleShot(
                1100,
                lambda: launch_window.save_toast.show_message(
                    "This is a preview version of CBM — bugs may occur",
                    duration=4.5,
                ),
            )

    def complete_splash_transition():
        splash.timer.stop()
        show_main_window()
        splash.hide()
        splash.close()
        if splash.boot_channel:
            try:
                splash.boot_channel.stop()
            except Exception:
                pass
            splash.boot_channel = None
        if splash.boot_sound:
            try:
                splash.boot_sound.free()
            except Exception:
                pass
            splash.boot_sound = None
        splash.deleteLater()

    def startup_failed(error):
        splash.timer.stop()
        splash.hide()
        detail = error.strip().splitlines()[-1]
        path = get_editor_data_directory() / "startup.log"
        QMessageBox.critical(None, "Startup Error", f"The editor could not start.\n\n{detail}\n\nDetails were saved to:\n{path}")
        app.exit(1)

    def build_main_window():
        global launch_window
        try:
            record_startup("Building main window")
            splash.set_status("Opening editor...")
            launch_window = MainWindow()
            launch_window._startup_splash_active = True
            record_startup("Preparing settings")
            settings = launch_window.ensure_settings_panel()
            settings.ensurePolished()
            settings.layout().activate()
            record_startup("Main window ready")
            record_startup("Preparing intro audio")
            splash.prepare_animation()
            splash.startup_ready = True
            splash.set_status("")
            QTimer.singleShot(0, start_splash)
        except Exception:
            error = traceback.format_exc()
            record_startup(error)
            startup_failed(error)

    def start_splash():
        splash.show()
        splash.start_animation()

    startup_worker.stage_changed.connect(splash.set_status)
    startup_worker.failed.connect(startup_failed)
    startup_worker.ready.connect(build_main_window)
    splash.finished.connect(complete_splash_transition)
    QTimer.singleShot(0, startup_worker.start)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
