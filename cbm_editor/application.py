from .main_window import *

register_shared_globals(globals())

def main():
    global TARGET_FPS, launch_window
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
            if show_uninstall_dialog():
                try:
                    begin_uninstallation()
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
            try:
                register_installation(get_application_executable_path())
            except Exception as error:
                QMessageBox.warning(None, "System Integration", str(error))
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

    try:
        get_audio_engine()
    except BassError as e:
        QMessageBox.critical(None, "BASS Audio Error", str(e))
        sys.exit(1)
    app.aboutToQuit.connect(shutdown_audio_engine)
    
    saved_x = 100
    saved_y = 100
    
    try:
        p_file = get_editor_data_directory() / "path.json"
        
        if p_file.exists():
            with open(p_file, 'r') as f:
                data = json.load(f)
                game_path = data.get("game_path")
                if game_path:
                    config_path = Path(game_path) / "ChartEditorResources" / "editor_config.json"
                    if config_path.exists():
                        with open(config_path, 'r') as cf:
                            config = json.load(cf)
                            w_data = config.get("window", {})
                            saved_x = w_data.get("x", 100)
                            saved_y = w_data.get("y", 100)
    except:
        pass
         
    launch_window = MainWindow()
    
    def show_main_window():
        global launch_window
        launch_window.show()
        launch_window.raise_()
        launch_window.activateWindow()
        launch_window.installEventFilter(launch_window)
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

    if icon_path:
        splash = AnimatedSplashScreen(icon_path, saved_x, saved_y)

        def complete_splash_transition():
            splash.timer.stop()
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
            QTimer.singleShot(150, show_main_window)

        splash.finished.connect(complete_splash_transition, Qt.ConnectionType.QueuedConnection)
        splash.show()
        splash.raise_()
        splash.activateWindow()
    else:
        show_main_window()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
