import json
import os
import sys
import threading
from pathlib import Path


class AudioError(RuntimeError):
    pass


def audio_config_path():
    if sys.platform.startswith("win"):
        roaming = os.environ.get("APPDATA")
        root = Path(roaming).parent / "LocalLow" if roaming else Path.home() / "AppData/LocalLow"
    else:
        configured = Path(os.environ.get("XDG_CONFIG_HOME", "")).expanduser()
        root = configured if configured.is_absolute() else Path.home() / ".config"
    return root / "CBM_Editor/ChartEditorResources/editor_config.json"


def saved_audio_backend():
    from .fmod_audio import fmod_available
    default_backend = "FMOD" if fmod_available() else "BASS"
    try:
        data = json.loads(audio_config_path().read_text(encoding="utf-8"))
        backend = data.get("settings", {}).get("audio_backend", default_backend)
    except (OSError, ValueError, AttributeError):
        return default_backend
    return backend if backend in ("BASS", "FMOD") else default_backend


_engine = None
_engine_lock = threading.Lock()


def get_audio_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            backend = saved_audio_backend()
            if backend == "FMOD":
                from .fmod_audio import FmodAudioEngine
                candidate = FmodAudioEngine()
            else:
                from .bass_audio import BassAudioEngine
                candidate = BassAudioEngine()
            try:
                candidate.initialize()
            except Exception:
                candidate.shutdown()
                raise
            _engine = candidate
        return _engine


def shutdown_audio_engine():
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.shutdown()
            _engine = None
