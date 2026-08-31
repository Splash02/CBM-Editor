import ctypes
import hashlib
import json
import os
import platform
import sys
import threading
from collections import deque
from pathlib import Path

BASS_OK = 0
BASS_ERROR_UNKNOWN = -1
BASS_CONFIG_BUFFER = 0
BASS_CONFIG_UPDATEPERIOD = 1
BASS_CONFIG_CURVE_VOL = 7
BASS_CONFIG_CURVE_PAN = 8
BASS_DEVICE_STEREO = 0x8000
BASS_SAMPLE_FLOAT = 0x100
BASS_SAMPLE_OVER_POS = 0x20000
BASS_STREAM_PRESCAN = 0x20000
BASS_STREAM_DECODE = 0x200000
BASS_UNICODE = 0x80000000
BASS_MIXER_END = 0x10000
BASS_MIXER_NONSTOP = 0x20000
BASS_MIXER_CHAN_DOWNMIX = 0x400000
BASS_MIXER_CHAN_NORAMPIN = 0x800000
BASS_ENCODE_FP_16BIT = 4
BASS_ENCODE_DITHER = 0x8000
BASS_ENCODE_STOP_WAIT = 2
BASS_ATTRIB_FREQ = 1
BASS_ATTRIB_VOL = 2
BASS_ATTRIB_PAN = 3
BASS_ATTRIB_SRC = 8
BASS_ACTIVE_STOPPED = 0
BASS_ACTIVE_PLAYING = 1
BASS_ACTIVE_STALLED = 2
BASS_ACTIVE_PAUSED = 3
BASS_ACTIVE_PAUSED_DEVICE = 4
BASS_POS_BYTE = 0
BASS_FILE_NAME = 0
BASS_FILE_MEM = 1
BASS_DATA_FFT2048 = 0x80000003
BASS_DATA_FFT_NOWINDOW = 0x20
BASS_DATA_FFT_REMOVEDC = 0x40
BASS_LEVEL_MONO = 1
BASS_LEVEL_RMS = 4
BASS_API_VERSION = 0x0204


ERROR_NAMES = {
    0: "OK",
    1: "MEM",
    2: "FILEOPEN",
    3: "DRIVER",
    4: "BUFLOST",
    5: "HANDLE",
    6: "FORMAT",
    7: "POSITION",
    8: "INIT",
    9: "START",
    10: "SSL",
    11: "REINIT",
    13: "TRACK",
    14: "ALREADY",
    17: "NOTAUDIO",
    18: "NOCHAN",
    19: "ILLTYPE",
    20: "ILLPARAM",
    21: "NO3D",
    22: "NOEAX",
    23: "DEVICE",
    24: "NOPLAY",
    25: "FREQ",
    27: "NOTFILE",
    29: "NOHW",
    31: "EMPTY",
    32: "NONET",
    33: "CREATE",
    34: "NOFX",
    37: "NOTAVAIL",
    38: "DECODE",
    39: "DX",
    40: "TIMEOUT",
    41: "FILEFORM",
    42: "SPEAKER",
    43: "VERSION",
    44: "CODEC",
    45: "ENDED",
    46: "BUSY",
    47: "UNSTREAMABLE",
    48: "PROTOCOL",
    49: "DENIED",
    50: "FREEING",
    51: "CANCEL",
    -1: "UNKNOWN",
}


class BASS_CHANNELINFO(ctypes.Structure):
    _fields_ = [
        ("freq", ctypes.c_uint32),
        ("chans", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("ctype", ctypes.c_uint32),
        ("origres", ctypes.c_uint32),
        ("plugin", ctypes.c_uint32),
        ("sample", ctypes.c_uint32),
        ("filename", ctypes.c_void_p),
    ]


class BassError(RuntimeError):
    def __init__(self, operation, code=BASS_ERROR_UNKNOWN, detail=None):
        self.operation = operation
        self.code = int(code)
        self.name = ERROR_NAMES.get(self.code, f"CODE_{self.code}")
        message = f"{operation} failed: BASS_ERROR_{self.name} ({self.code})"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)


def _is_frozen_runtime():
    return bool(getattr(sys, "frozen", False) or globals().get("__compiled__"))


def _runtime_roots():
    roots = []
    if _is_frozen_runtime():
        roots.append(Path(sys.executable).resolve().parent)
    if getattr(sys, "_MEIPASS", None):
        roots.append(Path(sys._MEIPASS))
    module_root = Path(__file__).resolve().parent
    roots.extend((module_root, module_root.parent))
    if os.path.exists("/.flatpak-info") or os.environ.get("FLATPAK_ID"):
        roots.extend((Path("/app/share/cbm-editor"), Path("/app/lib/cbm-editor")))
    unique = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def _platform_key():
    machine = platform.machine().lower()
    if machine not in {"amd64", "x86_64"}:
        raise BassError("platform detection", detail=f"unsupported architecture {machine}")
    if sys.platform.startswith("win"):
        return "win-x64"
    if sys.platform.startswith("linux"):
        return "linux-x86_64"
    raise BassError("platform detection", detail=f"unsupported platform {sys.platform}")


def _find_manifest():
    for root in _runtime_roots():
        candidate = root / "vendor" / "bass" / "manifest.json"
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(root) for root in _runtime_roots())
    raise BassError("BASS manifest lookup", detail=f"manifest.json not found under {searched}")


def _verify_library(name):
    platform_key = _platform_key()
    if name == "mp3_encoder" and _is_frozen_runtime():
        external_name = "bassenc_mp3.dll" if platform_key == "win-x64" else "libbassenc_mp3.so"
        external_path = Path(sys.executable).resolve().parent / external_name
        if external_path.is_file():
            return external_path
    manifest_path = _find_manifest()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entry = manifest["libraries"][platform_key][name]
        filename = entry["filename"]
        expected = entry["sha256"].lower()
    except Exception as exc:
        raise BassError("BASS manifest read", detail=str(exc)) from exc
    library_path = manifest_path.parent / platform_key / filename
    if not library_path.is_file():
        raise BassError("BASS library lookup", detail=str(library_path))
    digest = hashlib.sha256(library_path.read_bytes()).hexdigest()
    if digest.lower() != expected:
        raise BassError("BASS integrity check", detail=f"{library_path} SHA-256 {digest} != {expected}")
    return library_path


class BassAudioEngine:
    def __init__(self, max_voices=32):
        self.max_voices = max(1, int(max_voices))
        self.library_path = None
        self.version = 0
        self._lib = None
        self._mix = None
        self._enc = None
        self._enc_mp3 = None
        self._plugins = []
        self._dll_directory = None
        self._initialized = False
        self._sounds = set()
        self._streams = set()
        self._voices = deque()
        self._lock = threading.RLock()

    def initialize(self):
        with self._lock:
            if self._initialized:
                return self
            self.library_path = _verify_library("core")
            try:
                if sys.platform.startswith("win"):
                    self._dll_directory = os.add_dll_directory(str(self.library_path.parent))
                    self._lib = ctypes.WinDLL(str(self.library_path))
                else:
                    self._lib = ctypes.CDLL(str(self.library_path), mode=ctypes.RTLD_GLOBAL)
            except OSError as exc:
                raise BassError("BASS library load", detail=f"{self.library_path}: {exc}") from exc
            self._bind()
            self.version = int(self._lib.BASS_GetVersion())
            if (self.version >> 16) != BASS_API_VERSION:
                raise BassError("BASS version check", detail=f"0x{self.version:08X}")
            self._check(self._lib.BASS_SetConfig(BASS_CONFIG_CURVE_VOL, 0), "BASS_SetConfig(CURVE_VOL)")
            self._check(self._lib.BASS_SetConfig(BASS_CONFIG_CURVE_PAN, 0), "BASS_SetConfig(CURVE_PAN)")
            self._check(self._lib.BASS_SetConfig(BASS_CONFIG_UPDATEPERIOD, 10), "BASS_SetConfig(UPDATEPERIOD)")
            self._check(self._lib.BASS_SetConfig(BASS_CONFIG_BUFFER, 100), "BASS_SetConfig(BUFFER)")
            self._check(self._lib.BASS_Init(-1, 44100, BASS_DEVICE_STEREO, None, None), "BASS_Init")
            self._load_components()
            self._initialized = True
            return self

    def _bind(self):
        lib = self._lib
        lib.BASS_GetVersion.argtypes = []
        lib.BASS_GetVersion.restype = ctypes.c_uint32
        lib.BASS_ErrorGetCode.argtypes = []
        lib.BASS_ErrorGetCode.restype = ctypes.c_int
        lib.BASS_SetConfig.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        lib.BASS_SetConfig.restype = ctypes.c_int
        lib.BASS_Init.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
        lib.BASS_Init.restype = ctypes.c_int
        lib.BASS_Free.argtypes = []
        lib.BASS_Free.restype = ctypes.c_int
        lib.BASS_PluginLoad.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        lib.BASS_PluginLoad.restype = ctypes.c_uint32
        lib.BASS_PluginFree.argtypes = [ctypes.c_uint32]
        lib.BASS_PluginFree.restype = ctypes.c_int
        lib.BASS_SampleLoad.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
        lib.BASS_SampleLoad.restype = ctypes.c_uint32
        lib.BASS_SampleFree.argtypes = [ctypes.c_uint32]
        lib.BASS_SampleFree.restype = ctypes.c_int
        lib.BASS_SampleGetChannel.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        lib.BASS_SampleGetChannel.restype = ctypes.c_uint32
        lib.BASS_StreamCreateFile.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint32]
        lib.BASS_StreamCreateFile.restype = ctypes.c_uint32
        lib.BASS_StreamFree.argtypes = [ctypes.c_uint32]
        lib.BASS_StreamFree.restype = ctypes.c_int
        lib.BASS_ChannelPlay.argtypes = [ctypes.c_uint32, ctypes.c_int]
        lib.BASS_ChannelPlay.restype = ctypes.c_int
        lib.BASS_ChannelStart.argtypes = [ctypes.c_uint32]
        lib.BASS_ChannelStart.restype = ctypes.c_int
        lib.BASS_ChannelStop.argtypes = [ctypes.c_uint32]
        lib.BASS_ChannelStop.restype = ctypes.c_int
        lib.BASS_ChannelIsActive.argtypes = [ctypes.c_uint32]
        lib.BASS_ChannelIsActive.restype = ctypes.c_uint32
        lib.BASS_ChannelGetInfo.argtypes = [ctypes.c_uint32, ctypes.POINTER(BASS_CHANNELINFO)]
        lib.BASS_ChannelGetInfo.restype = ctypes.c_int
        lib.BASS_ChannelGetData.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
        lib.BASS_ChannelGetData.restype = ctypes.c_uint32
        lib.BASS_ChannelGetLevelEx.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_float), ctypes.c_float, ctypes.c_uint32]
        lib.BASS_ChannelGetLevelEx.restype = ctypes.c_int
        lib.BASS_ChannelGetAttribute.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_float)]
        lib.BASS_ChannelGetAttribute.restype = ctypes.c_int
        lib.BASS_ChannelSetAttribute.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_float]
        lib.BASS_ChannelSetAttribute.restype = ctypes.c_int
        lib.BASS_ChannelSetPosition.argtypes = [ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint32]
        lib.BASS_ChannelSetPosition.restype = ctypes.c_int
        lib.BASS_ChannelGetPosition.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        lib.BASS_ChannelGetPosition.restype = ctypes.c_uint64
        lib.BASS_ChannelGetLength.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        lib.BASS_ChannelGetLength.restype = ctypes.c_uint64
        lib.BASS_ChannelSeconds2Bytes.argtypes = [ctypes.c_uint32, ctypes.c_double]
        lib.BASS_ChannelSeconds2Bytes.restype = ctypes.c_uint64
        lib.BASS_ChannelBytes2Seconds.argtypes = [ctypes.c_uint32, ctypes.c_uint64]
        lib.BASS_ChannelBytes2Seconds.restype = ctypes.c_double

    def _load_dynamic_library(self, name):
        path = _verify_library(name)
        try:
            if sys.platform.startswith("win"):
                return ctypes.WinDLL(str(path))
            return ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)
        except OSError as exc:
            raise BassError(f"{name} library load", detail=f"{path}: {exc}") from exc

    def _load_components(self):
        for name in ("flac", "opus", "alac"):
            path = _verify_library(name)
            keeper, pointer, flags = self._path_pointer(path)
            handle = int(self._lib.BASS_PluginLoad(pointer, flags))
            if not handle:
                raise BassError("BASS_PluginLoad", self._error_code(), str(path))
            self._plugins.append(handle)
        self._mix = self._load_dynamic_library("mixer")
        self._enc = self._load_dynamic_library("encoder")
        self._enc_mp3 = self._load_dynamic_library("mp3_encoder")
        self._bind_components()

    def _bind_components(self):
        self._mix.BASS_Mixer_GetVersion.argtypes = []
        self._mix.BASS_Mixer_GetVersion.restype = ctypes.c_uint32
        self._mix.BASS_Mixer_StreamCreate.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
        self._mix.BASS_Mixer_StreamCreate.restype = ctypes.c_uint32
        self._mix.BASS_Mixer_StreamAddChannelEx.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint64,
            ctypes.c_uint64,
        ]
        self._mix.BASS_Mixer_StreamAddChannelEx.restype = ctypes.c_int
        self._enc.BASS_Encode_StartPCMFile.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        self._enc.BASS_Encode_StartPCMFile.restype = ctypes.c_uint32
        self._enc.BASS_Encode_GetVersion.argtypes = []
        self._enc.BASS_Encode_GetVersion.restype = ctypes.c_uint32
        self._enc.BASS_Encode_StopEx.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        self._enc.BASS_Encode_StopEx.restype = ctypes.c_int
        self._enc_mp3.BASS_Encode_MP3_StartFile.argtypes = [
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        self._enc_mp3.BASS_Encode_MP3_StartFile.restype = ctypes.c_uint32
        self._enc_mp3.BASS_Encode_MP3_GetVersion.argtypes = []
        self._enc_mp3.BASS_Encode_MP3_GetVersion.restype = ctypes.c_uint32
        versions = (
            ("BASSmix", int(self._mix.BASS_Mixer_GetVersion())),
            ("BASSenc", int(self._enc.BASS_Encode_GetVersion())),
            ("BASSenc_MP3", int(self._enc_mp3.BASS_Encode_MP3_GetVersion())),
        )
        for name, version in versions:
            if (version >> 16) != BASS_API_VERSION:
                raise BassError(f"{name} version check", detail=f"0x{version:08X}")

    def _error_code(self):
        if self._lib is None:
            return BASS_ERROR_UNKNOWN
        return int(self._lib.BASS_ErrorGetCode())

    def _check(self, result, operation):
        if not result:
            raise BassError(operation, self._error_code())
        return result

    def _path_pointer(self, path):
        if sys.platform.startswith("win"):
            value = ctypes.c_wchar_p(str(path))
            return value, ctypes.cast(value, ctypes.c_void_p), BASS_UNICODE
        encoded = ctypes.c_char_p(os.fsencode(path))
        return encoded, ctypes.cast(encoded, ctypes.c_void_p), 0

    def load_sound(self, path):
        self.initialize()
        keeper, pointer, flags = self._path_pointer(Path(path))
        handle = int(self._lib.BASS_SampleLoad(BASS_FILE_NAME, pointer, 0, 0, self.max_voices, flags | BASS_SAMPLE_OVER_POS))
        if not handle:
            raise BassError("BASS_SampleLoad", self._error_code(), str(path))
        sound = BassSound(self, handle)
        with self._lock:
            self._sounds.add(sound)
        return sound

    def load_sound_bytes(self, data):
        self.initialize()
        payload = bytes(data)
        if not payload:
            raise BassError("BASS_SampleLoad(memory)", detail="empty payload")
        buffer = ctypes.create_string_buffer(payload)
        handle = int(self._lib.BASS_SampleLoad(BASS_FILE_MEM, ctypes.cast(buffer, ctypes.c_void_p), 0, len(payload), self.max_voices, BASS_SAMPLE_OVER_POS))
        if not handle:
            raise BassError("BASS_SampleLoad(memory)", self._error_code())
        sound = BassSound(self, handle)
        with self._lock:
            self._sounds.add(sound)
        return sound

    def load_stream(self, path, prescan=True):
        self.initialize()
        keeper, pointer, flags = self._path_pointer(Path(path))
        stream_flags = flags | (BASS_STREAM_PRESCAN if prescan else 0)
        handle = int(self._lib.BASS_StreamCreateFile(BASS_FILE_NAME, pointer, 0, 0, stream_flags))
        if not handle:
            raise BassError("BASS_StreamCreateFile", self._error_code(), str(path))
        stream = BassMusicStream(self, handle, Path(path))
        with self._lock:
            self._streams.add(stream)
        return stream

    def load_decode_stream(self, path):
        self.initialize()
        keeper, pointer, flags = self._path_pointer(Path(path))
        handle = int(self._lib.BASS_StreamCreateFile(
            BASS_FILE_NAME,
            pointer,
            0,
            0,
            flags | BASS_STREAM_DECODE | BASS_SAMPLE_FLOAT
        ))
        if not handle:
            raise BassError("BASS_StreamCreateFile(decode)", self._error_code(), str(path))
        stream = BassDecodeStream(self, handle, Path(path))
        with self._lock:
            self._streams.add(stream)
        return stream

    def convert_audio(
        self,
        source_path,
        output_path,
        output_format="mp3",
        progress_callback=None,
        cancel_callback=None,
        leading_silence_ms=0,
        trim_start_ms=0,
        target_sample_rate=None,
        target_channels=None,
    ):
        self.initialize()
        source_path = Path(source_path)
        output_path = Path(output_path)
        output_format = str(output_format).lower()
        if output_format not in {"mp3", "wav"}:
            raise ValueError(f"unsupported output format: {output_format}")
        source = None
        mixer_handle = 0
        encoder_handle = 0
        completed = False
        output_path.parent.mkdir(parents=True, exist_ok=True)

        def emit_progress(value):
            if progress_callback:
                progress_callback(int(value))

        try:
            source = self.load_decode_stream(source_path)
            sample_rate = 44100 if output_format == "mp3" else int(target_sample_rate or source.sample_rate)
            channels = 2 if output_format == "mp3" else int(target_channels or min(2, source.channels))
            sample_rate = max(8000, sample_rate)
            channels = max(1, min(2, channels))
            source_length = source.get_length_ms()
            trim_ms = max(0.0, float(trim_start_ms))
            silence_ms = max(0.0, float(leading_silence_ms))
            remaining_ms = max(0.0, source_length - trim_ms)
            if remaining_ms <= 0.0:
                silence_ms = max(silence_ms, 100.0)
            if remaining_ms > 0.0 and trim_ms > 0 and not source.seek_ms(trim_ms):
                raise BassError("BASS_ChannelSetPosition", self._error_code(), str(source_path))

            mixer_handle = int(self._mix.BASS_Mixer_StreamCreate(
                sample_rate,
                channels,
                BASS_STREAM_DECODE
                | BASS_SAMPLE_FLOAT
                | (BASS_MIXER_END if remaining_ms > 0.0 else BASS_MIXER_NONSTOP),
            ))
            if not mixer_handle:
                raise BassError("BASS_Mixer_StreamCreate", self._error_code())

            if remaining_ms > 0.0:
                start_position = int(self._lib.BASS_ChannelSeconds2Bytes(mixer_handle, silence_ms / 1000.0))
                self._check(
                    self._mix.BASS_Mixer_StreamAddChannelEx(
                        mixer_handle,
                        source.handle,
                        BASS_MIXER_CHAN_DOWNMIX | BASS_MIXER_CHAN_NORAMPIN,
                        start_position,
                        0,
                    ),
                    "BASS_Mixer_StreamAddChannelEx",
                )

            output_keeper, output_pointer, output_flags = self._path_pointer(output_path)
            if output_format == "mp3":
                options_keeper, options_pointer, options_flags = self._path_pointer("-b 192 -q 2 -m j")
                encoder_handle = int(self._enc_mp3.BASS_Encode_MP3_StartFile(
                    mixer_handle,
                    options_pointer,
                    output_flags | options_flags,
                    output_pointer,
                ))
            else:
                encoder_handle = int(self._enc.BASS_Encode_StartPCMFile(
                    mixer_handle,
                    output_flags | BASS_ENCODE_FP_16BIT | BASS_ENCODE_DITHER,
                    output_pointer,
                ))
            if not encoder_handle:
                raise BassError("BASS encoder start", self._error_code(), str(output_path))

            expected_frames = max(1, int(round((silence_ms + remaining_ms) * sample_rate / 1000.0)))
            expected_bytes = expected_frames * channels * ctypes.sizeof(ctypes.c_float)
            buffer = (ctypes.c_float * (65536 * channels))()
            processed_bytes = 0
            last_progress = -1
            emit_progress(0)
            last_progress = 0

            while True:
                if cancel_callback and cancel_callback():
                    raise InterruptedError("audio conversion cancelled")
                request_bytes = ctypes.sizeof(buffer)
                if remaining_ms <= 0.0:
                    request_bytes = min(request_bytes, expected_bytes - processed_bytes)
                    if request_bytes <= 0:
                        break
                result = int(self._lib.BASS_ChannelGetData(
                    mixer_handle,
                    ctypes.cast(buffer, ctypes.c_void_p),
                    request_bytes,
                ))
                if result == 0xFFFFFFFF:
                    if self._error_code() == 45:
                        break
                    raise BassError("BASS_ChannelGetData(conversion)", self._error_code())
                if result <= 0:
                    break
                processed_bytes += result
                current_progress = min(99, int(processed_bytes * 100 // expected_bytes))
                while last_progress < current_progress:
                    last_progress += 1
                    emit_progress(last_progress)

            self._check(
                self._enc.BASS_Encode_StopEx(encoder_handle, BASS_ENCODE_STOP_WAIT),
                "BASS_Encode_StopEx",
            )
            encoder_handle = 0
            completed = True
            while last_progress < 100:
                last_progress += 1
                emit_progress(last_progress)
            return {
                "sample_rate": sample_rate,
                "channels": channels,
                "bitrate_kbps": 192 if output_format == "mp3" else None,
                "format": output_format,
            }
        finally:
            if encoder_handle and self._enc is not None:
                self._enc.BASS_Encode_StopEx(encoder_handle, BASS_ENCODE_STOP_WAIT)
            if mixer_handle and self._lib is not None:
                self._lib.BASS_StreamFree(mixer_handle)
            if source:
                source.free()
            if not completed:
                try:
                    output_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _reserve_voice(self):
        with self._lock:
            active = deque()
            while self._voices:
                voice = self._voices.popleft()
                if voice.get_busy():
                    active.append(voice)
            self._voices = active
            while len(self._voices) >= self.max_voices:
                self._voices.popleft().stop()

    def _register_voice(self, voice):
        with self._lock:
            self._voices.append(voice)

    def shutdown(self):
        with self._lock:
            if not self._initialized:
                return
            for voice in list(self._voices):
                voice.stop()
            self._voices.clear()
            for stream in list(self._streams):
                stream.free()
            for sound in list(self._sounds):
                sound.free()
            for plugin in self._plugins:
                self._lib.BASS_PluginFree(plugin)
            self._plugins.clear()
            self._lib.BASS_Free()
            self._initialized = False
            self._lib = None
            self._mix = None
            self._enc = None
            self._enc_mp3 = None
            if self._dll_directory is not None:
                self._dll_directory.close()
                self._dll_directory = None


class BassChannel:
    def __init__(self, engine, handle):
        self.engine = engine
        self.handle = int(handle)

    def get_busy(self):
        if not self.handle or self.engine._lib is None:
            return False
        return int(self.engine._lib.BASS_ChannelIsActive(self.handle)) in {
            BASS_ACTIVE_PLAYING,
            BASS_ACTIVE_STALLED,
            BASS_ACTIVE_PAUSED,
            BASS_ACTIVE_PAUSED_DEVICE,
        }

    def stop(self):
        if self.handle and self.engine._lib is not None:
            self.engine._lib.BASS_ChannelStop(self.handle)

    def set_volume(self, left, right=None):
        if right is None:
            self.set_volume_pan(float(left), 0.0)
            return
        left = max(0.0, float(left))
        right = max(0.0, float(right))
        volume = max(left, right)
        if volume <= 0:
            pan = 0.0
        elif right >= left:
            pan = 1.0 - left / right if right else 0.0
        else:
            pan = right / left - 1.0
        self.set_volume_pan(volume, pan)

    def set_volume_pan(self, volume, pan=0.0):
        if not self.handle or self.engine._lib is None:
            return
        volume = max(0.0, float(volume))
        pan = max(-1.0, min(1.0, float(pan)))
        self.engine._check(self.engine._lib.BASS_ChannelSetAttribute(self.handle, BASS_ATTRIB_VOL, volume), "BASS_ChannelSetAttribute(VOL)")
        self.engine._check(self.engine._lib.BASS_ChannelSetAttribute(self.handle, BASS_ATTRIB_PAN, pan), "BASS_ChannelSetAttribute(PAN)")


class BassSound:
    def __init__(self, engine, handle, pitch_ratio=1.0, owns_handle=True):
        self.engine = engine
        self.handle = int(handle)
        self.volume = 1.0
        self.pitch_ratio = max(0.01, float(pitch_ratio))
        self.owns_handle = bool(owns_handle)

    def set_volume(self, volume):
        self.volume = max(0.0, float(volume))

    def play(self, offset_ms=0.0):
        if not self.handle or self.engine._lib is None:
            return None
        self.engine._reserve_voice()
        handle = int(self.engine._lib.BASS_SampleGetChannel(self.handle, 0))
        if not handle:
            return None
        channel = BassChannel(self.engine, handle)
        try:
            channel.set_volume_pan(self.volume, 0.0)
            if self.pitch_ratio != 1.0:
                frequency = ctypes.c_float()
                self.engine._check(
                    self.engine._lib.BASS_ChannelGetAttribute(handle, BASS_ATTRIB_FREQ, ctypes.byref(frequency)),
                    "BASS_ChannelGetAttribute(FREQ)",
                )
                self.engine._check(
                    self.engine._lib.BASS_ChannelSetAttribute(
                        handle,
                        BASS_ATTRIB_FREQ,
                        ctypes.c_float(float(frequency.value) * self.pitch_ratio),
                    ),
                    "BASS_ChannelSetAttribute(FREQ)",
                )
            if offset_ms > 0:
                position = int(self.engine._lib.BASS_ChannelSeconds2Bytes(handle, float(offset_ms) / 1000.0))
                if not self.engine._lib.BASS_ChannelSetPosition(handle, position, BASS_POS_BYTE):
                    return None
            self.engine._check(self.engine._lib.BASS_ChannelStart(handle), "BASS_ChannelStart")
        except BassError:
            channel.stop()
            raise
        self.engine._register_voice(channel)
        return channel

    def create_variant(self, pitch_ratio):
        sound = BassSound(self.engine, self.handle, pitch_ratio=pitch_ratio, owns_handle=False)
        sound.volume = self.volume
        return sound

    def free(self):
        if not self.handle:
            return
        if self.owns_handle and self.engine._lib is not None:
            self.engine._lib.BASS_SampleFree(self.handle)
        self.handle = 0
        self.engine._sounds.discard(self)


class BassMusicStream:
    def __init__(self, engine, handle, path):
        self.engine = engine
        self.handle = int(handle)
        self.path = Path(path)
        self.volume = 1.0
        self._fft_buffer = (ctypes.c_float * 1024)()
        self._rms_level = ctypes.c_float()
        frequency = ctypes.c_float()
        self.engine._check(
            self.engine._lib.BASS_ChannelGetAttribute(self.handle, BASS_ATTRIB_FREQ, ctypes.byref(frequency)),
            "BASS_ChannelGetAttribute(FREQ)"
        )
        self.original_frequency = float(frequency.value)
        self.engine._check(
            self.engine._lib.BASS_ChannelSetAttribute(self.handle, BASS_ATTRIB_SRC, ctypes.c_float(4.0)),
            "BASS_ChannelSetAttribute(SRC)"
        )

    def set_volume(self, volume):
        self.volume = max(0.0, float(volume))
        if self.handle and self.engine._lib is not None:
            self.engine._check(self.engine._lib.BASS_ChannelSetAttribute(self.handle, BASS_ATTRIB_VOL, self.volume), "BASS_ChannelSetAttribute(VOL)")

    def set_speed(self, speed):
        if not self.handle or self.engine._lib is None:
            return
        speed = float(speed)
        if speed <= 0:
            raise ValueError("speed must be greater than zero")
        frequency = self.original_frequency * speed
        self.engine._check(
            self.engine._lib.BASS_ChannelSetAttribute(self.handle, BASS_ATTRIB_FREQ, ctypes.c_float(frequency)),
            "BASS_ChannelSetAttribute(FREQ)"
        )

    def get_fft(self):
        if not self.handle or self.engine._lib is None:
            return None
        result = int(self.engine._lib.BASS_ChannelGetData(
            self.handle,
            ctypes.cast(self._fft_buffer, ctypes.c_void_p),
            BASS_DATA_FFT2048 | BASS_DATA_FFT_NOWINDOW | BASS_DATA_FFT_REMOVEDC
        ))
        if result == 0xFFFFFFFF:
            return None
        return self._fft_buffer

    def get_rms_level(self, duration=0.031):
        if not self.handle or self.engine._lib is None:
            return 0.0
        result = self.engine._lib.BASS_ChannelGetLevelEx(
            self.handle,
            ctypes.byref(self._rms_level),
            ctypes.c_float(max(0.001, float(duration))),
            BASS_LEVEL_MONO | BASS_LEVEL_RMS
        )
        if not result:
            return 0.0
        return max(0.0, float(self._rms_level.value))

    def seek_ms(self, position_ms):
        if not self.handle or self.engine._lib is None:
            return False
        seconds = max(0.0, float(position_ms) / 1000.0)
        position = int(self.engine._lib.BASS_ChannelSeconds2Bytes(self.handle, seconds))
        return bool(self.engine._lib.BASS_ChannelSetPosition(self.handle, position, BASS_POS_BYTE))

    def play_from_ms(self, position_ms=0.0):
        if not self.handle or self.engine._lib is None:
            return False
        if not self.seek_ms(position_ms):
            return False
        self.set_volume(self.volume)
        self.engine._check(self.engine._lib.BASS_ChannelPlay(self.handle, 0), "BASS_ChannelPlay")
        return True

    def stop(self):
        if self.handle and self.engine._lib is not None:
            self.engine._lib.BASS_ChannelStop(self.handle)

    def get_busy(self):
        if not self.handle or self.engine._lib is None:
            return False
        return int(self.engine._lib.BASS_ChannelIsActive(self.handle)) in {
            BASS_ACTIVE_PLAYING,
            BASS_ACTIVE_STALLED,
            BASS_ACTIVE_PAUSED,
            BASS_ACTIVE_PAUSED_DEVICE,
        }

    def get_position_ms(self):
        if not self.handle or self.engine._lib is None:
            return 0.0
        position = int(self.engine._lib.BASS_ChannelGetPosition(self.handle, BASS_POS_BYTE))
        return float(self.engine._lib.BASS_ChannelBytes2Seconds(self.handle, position) * 1000.0)

    def get_length_ms(self):
        if not self.handle or self.engine._lib is None:
            return 0.0
        length = int(self.engine._lib.BASS_ChannelGetLength(self.handle, BASS_POS_BYTE))
        return float(self.engine._lib.BASS_ChannelBytes2Seconds(self.handle, length) * 1000.0)

    def free(self):
        if not self.handle:
            return
        if self.engine._lib is not None:
            self.engine._lib.BASS_StreamFree(self.handle)
        self.handle = 0
        self._fft_buffer = None
        self._rms_level = None
        self.engine._streams.discard(self)


class BassDecodeStream:
    def __init__(self, engine, handle, path):
        self.engine = engine
        self.handle = int(handle)
        self.path = Path(path)
        info = BASS_CHANNELINFO()
        self.engine._check(
            self.engine._lib.BASS_ChannelGetInfo(self.handle, ctypes.byref(info)),
            "BASS_ChannelGetInfo"
        )
        self.sample_rate = int(info.freq)
        self.channels = int(info.chans)

    def read_float_frames(self, frame_count):
        if not self.handle or self.engine._lib is None:
            return None, 0
        sample_count = max(1, int(frame_count)) * self.channels
        if not hasattr(self, '_float_buffer') or getattr(self, '_float_buffer_size', 0) < sample_count:
            self._float_buffer_type = ctypes.c_float * sample_count
            self._float_buffer = self._float_buffer_type()
            self._float_buffer_size = sample_count
        samples = self._float_buffer
        byte_size = sample_count * ctypes.sizeof(ctypes.c_float)
        result = int(self.engine._lib.BASS_ChannelGetData(
            self.handle,
            ctypes.cast(samples, ctypes.c_void_p),
            byte_size
        ))
        if result == 0xFFFFFFFF:
            if self.engine._error_code() == 45:
                return None, 0
            raise BassError("BASS_ChannelGetData", self.engine._error_code())
        return samples, result // ctypes.sizeof(ctypes.c_float)

    def seek_ms(self, position_ms):
        if not self.handle or self.engine._lib is None:
            return False
        position = int(self.engine._lib.BASS_ChannelSeconds2Bytes(
            self.handle,
            max(0.0, float(position_ms)) / 1000.0,
        ))
        return bool(self.engine._lib.BASS_ChannelSetPosition(self.handle, position, BASS_POS_BYTE))

    def get_length_ms(self):
        if not self.handle or self.engine._lib is None:
            return 0.0
        length = int(self.engine._lib.BASS_ChannelGetLength(self.handle, BASS_POS_BYTE))
        return float(self.engine._lib.BASS_ChannelBytes2Seconds(self.handle, length) * 1000.0)

    def free(self):
        if not self.handle:
            return
        if self.engine._lib is not None:
            self.engine._lib.BASS_StreamFree(self.handle)
        self.handle = 0
        self._float_buffer = None
        self._float_buffer_type = None
        self._float_buffer_size = 0
        self.engine._streams.discard(self)


_engine = None
_engine_lock = threading.Lock()


def get_audio_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = BassAudioEngine()
        return _engine.initialize()


def shutdown_audio_engine():
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.shutdown()
            _engine = None
