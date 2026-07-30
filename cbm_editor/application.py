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
    app = QApplication(sys.argv)
    try:
        get_audio_engine()
    except BassError as e:
        QMessageBox.critical(None, "BASS Audio Error", str(e))
        sys.exit(1)
    app.aboutToQuit.connect(shutdown_audio_engine)
    
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
    
    fmt = QSurfaceFormat()
    fmt.setSwapInterval(1)
    fmt.setSwapBehavior(QSurfaceFormat.SwapBehavior.TripleBuffer)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)

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
    
    saved_x = 100
    saved_y = 100
    
    try:
        if sys.platform.startswith("win"):
            app_data = os.getenv('APPDATA')
            if app_data:
                p_file = Path(app_data).parent / "LocalLow" / "CBM_Editor" / "path.json"
            else:
                p_file = Path.home() / "AppData" / "LocalLow" / "CBM_Editor" / "path.json"
        else:
            p_file = Path.home() / ".config" / "CBM_Editor" / "path.json"
        
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
         
    launch_window = None
    
    def show_main_window():
        global launch_window
        launch_window = MainWindow()
        launch_window.show()
        launch_window.raise_()
        launch_window.activateWindow()
        launch_window.installEventFilter(launch_window)
        if PREVIEW_VERSION:
            def show_preview_dialog():
                dlg = QDialog(launch_window)
                dlg.setWindowTitle("PREVIEW")
                dlg.setMinimumWidth(300)
                layout = QVBoxLayout(dlg)
                
                lbl = QLabel("this is a preview version of CBM, bugs may occur")
                lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                lbl.setWordWrap(True)
                layout.addWidget(lbl)
                
                btn = QPushButton("Okay")
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn.clicked.connect(dlg.accept)
                layout.addWidget(btn)
                
                dlg.adjustSize()
                dlg.move(launch_window.geometry().center() - dlg.rect().center())
                dlg.raise_()
                dlg.activateWindow()
                dlg.exec()
            
            QTimer.singleShot(100, show_preview_dialog)

    if icon_path:
        splash = AnimatedSplashScreen(icon_path, saved_x, saved_y)
        splash.finished.connect(show_main_window)
        splash.show()
        splash.raise_()
        splash.activateWindow()
    else:
        show_main_window()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
