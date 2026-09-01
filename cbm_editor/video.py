import ctypes
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import (
    QObject,
    QMetaObject,
    QRectF,
    QThread,
    QTimer,
    QUrl,
    Qt,
    pyqtSignal,
    pyqtSlot,
    qFormatLogMessage,
    qInstallMessageHandler,
)
from PyQt6.QtGui import QColor, QOffscreenSurface, QOpenGLContext, QPixmap, QTransform
from PyQt6.QtOpenGL import QOpenGLFunctions_2_0, QOpenGLShader, QOpenGLShaderProgram

from .foundation import get_base_path


VIDEO_EXTENSIONS = (".mp4", ".webm")
VIDEO_SETTINGS_NAME = "video_config.json"
VIDEO_MANIFEST_PATH = Path(get_base_path()) / "vendor" / "video" / "manifest.json"


def find_project_video(project_folder):
    if not project_folder:
        return None
    project_folder = Path(project_folder)
    for name in ("video.mp4", "video.webm"):
        path = project_folder / name
        if path.is_file():
            return path
    return None


def video_platform_key():
    if sys.platform.startswith("win") and platform.machine().lower() in ("amd64", "x86_64"):
        return "windows-x64"
    if sys.platform.startswith("linux") and platform.machine().lower() in ("amd64", "x86_64"):
        return "linux-x86_64"
    return ""


def file_sha256(path, progress=None, cancelled=None):
    path = Path(path)
    total = max(1, path.stat().st_size)
    processed = 0
    digest = hashlib.sha256()
    last_percent = -1
    with path.open("rb") as handle:
        while True:
            if cancelled and cancelled():
                raise InterruptedError
            chunk = handle.read(4 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            processed += len(chunk)
            percent = min(99, int(processed * 100 / total))
            if progress and percent != last_percent:
                last_percent = percent
                progress(percent)
    if progress:
        progress(100)
    return digest.hexdigest()


def load_video_manifest():
    try:
        with VIDEO_MANIFEST_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def resolve_video_tool():
    platform_key = video_platform_key()
    if not platform_key:
        return None, "Video processing is only available on Windows x64 and Linux x86-64."
    filename = "cbm_video_tool.exe" if platform_key == "windows-x64" else "cbm_video_tool"
    path = Path(get_base_path()) / "vendor" / "video" / platform_key / filename
    manifest = load_video_manifest()
    expected = str(manifest.get("artifacts", {}).get(platform_key, {}).get("sha256", "")).lower()
    if not path.is_file() or not expected:
        return None, "The verified cbm_video_tool is not installed for this platform."
    actual = file_sha256(path)
    if actual.lower() != expected:
        return None, "The bundled cbm_video_tool failed its integrity check."
    if platform_key == "linux-x86_64" and not path.stat().st_mode & 0o111:
        try:
            path.chmod(path.stat().st_mode | 0o755)
        except OSError:
            return None, "The bundled cbm_video_tool is not executable."
    return path, ""


def video_process_startup():
    startupinfo = None
    creationflags = 0
    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    return startupinfo, creationflags


def run_video_probe(path, tool_path=None):
    if tool_path is None:
        tool_path, error = resolve_video_tool()
        if not tool_path:
            raise RuntimeError(error)
    startupinfo, creationflags = video_process_startup()
    process = subprocess.run(
        [str(tool_path), "-hide_banner", "-i", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        startupinfo=startupinfo,
        creationflags=creationflags,
        check=False,
    )
    output = process.stdout or ""
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
    video_line = ""
    codec_match = None
    resolution_match = None
    for candidate in re.findall(r"^.*Video:.*$", output, re.IGNORECASE | re.MULTILINE):
        candidate_codec = re.search(r"Video:\s*([^,\s]+)", candidate, re.IGNORECASE)
        candidate_resolution = re.search(r"(?<!\d)(\d{2,})x(\d{2,})(?!\d)", candidate)
        if candidate_codec and candidate_resolution:
            video_line = candidate
            codec_match = candidate_codec
            resolution_match = candidate_resolution
            break
    if not codec_match or not resolution_match:
        raise RuntimeError("No supported video stream was found.")
    duration_ms = 0
    if duration_match:
        duration_ms = int(
            (
                int(duration_match.group(1)) * 3600
                + int(duration_match.group(2)) * 60
                + float(duration_match.group(3))
            )
            * 1000
        )
    fps_match = re.search(r",\s*([0-9.]+)\s*fps", video_line, re.IGNORECASE)
    stream_bitrate_match = re.search(r",\s*([0-9.]+)\s*kb/s", video_line, re.IGNORECASE)
    total_bitrate_match = re.search(r"bitrate:\s*([0-9.]+)\s*kb/s", output, re.IGNORECASE)
    duration_seconds = duration_ms / 1000.0
    measured_bitrate = int(Path(path).stat().st_size * 8 / duration_seconds) if duration_seconds > 0 else 0
    video_bitrate = int(float(stream_bitrate_match.group(1)) * 1000) if stream_bitrate_match else 0
    total_bitrate = int(float(total_bitrate_match.group(1)) * 1000) if total_bitrate_match else measured_bitrate
    if video_bitrate <= 0 and total_bitrate > 0:
        audio_bitrates = [
            int(float(match) * 1000)
            for line in re.findall(r"^.*Audio:.*$", output, re.IGNORECASE | re.MULTILINE)
            for match in re.findall(r",\s*([0-9.]+)\s*kb/s", line, re.IGNORECASE)
        ]
        video_bitrate = max(0, total_bitrate - sum(audio_bitrates))
    if video_bitrate <= 0:
        video_bitrate = measured_bitrate
    return {
        "path": str(Path(path)),
        "format": Path(path).suffix.lower().lstrip(".").upper(),
        "codec": codec_match.group(1).upper(),
        "width": int(resolution_match.group(1)),
        "height": int(resolution_match.group(2)),
        "fps": float(fps_match.group(1)) if fps_match else 0.0,
        "duration_ms": duration_ms,
        "size": Path(path).stat().st_size,
        "total_bitrate": total_bitrate,
        "video_bitrate": video_bitrate,
    }


def preview_video_bitrate(metadata, target_height=720):
    duration_seconds = max(0.001, float(metadata.get("duration_ms", 0)) / 1000.0)
    source_bitrate = int(metadata.get("total_bitrate", 0) or 0)
    if source_bitrate <= 0:
        source_bitrate = int(float(metadata.get("size", 0) or 0) * 8 / duration_seconds)
    if source_bitrate <= 0:
        source_bitrate = int(metadata.get("video_bitrate", 0) or 0)
    source_bitrate = max(1, source_bitrate)
    target_bitrate = int(source_bitrate * 0.9)
    minimum = min(source_bitrate, 16000)
    return max(minimum, min(source_bitrate, target_bitrate))


def load_video_settings(project_folder):
    defaults = {"offset_ms": 0}
    if not project_folder:
        return defaults
    path = Path(project_folder) / "cbm_files" / VIDEO_SETTINGS_NAME
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            defaults["offset_ms"] = int(loaded.get("offset_ms", 0) or 0)
    except Exception:
        pass
    return defaults


def save_video_settings(project_folder, data):
    directory = Path(project_folder) / "cbm_files"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / VIDEO_SETTINGS_NAME
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump({"offset_ms": int(data.get("offset_ms", 0) or 0)}, handle, indent=2)
    os.replace(temporary, path)


def find_video_backup(project_folder):
    directory = Path(project_folder) / "cbm_files"
    for name in ("video_backup.mp4", "video_backup.webm"):
        path = directory / name
        if path.is_file():
            return path
    return None


def format_file_size(size):
    value = float(size)
    units = ("B", "KB", "MB", "GB")
    unit = units[0]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            break
        value /= 1024.0
    return f"{value:.2f} {unit}"


def format_video_duration(duration_ms):
    total_seconds = max(0, int(round(duration_ms / 1000.0)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

_previous_qt_message_handler = None
_video_message_filter_installed = False


def _video_qt_message_handler(message_type, context, message):
    category = getattr(context, "category", "") or ""
    lowered = message.lower()
    if category.startswith("qt.multimedia") or any(
        marker in lowered
        for marker in (
            "qffmpeg::",
            "avhwframescontext",
            "thread_get_buffer()",
            "get_buffer() failed",
            "using qt multimedia with ffmpeg",
            "moov atom not found",
            "corrupted ctts atom",
            "error reading header",
        )
    ):
        return
    if (
        message.startswith(
            "QObject::disconnect: wildcard call disconnects from destroyed signal of QFFmpeg::"
        )
        and message.endswith("::unnamed")
    ):
        return
    if _previous_qt_message_handler is not None:
        _previous_qt_message_handler(message_type, context, message)
    else:
        sys.stderr.write(f"{qFormatLogMessage(message_type, context, message)}\n")


def install_video_message_filter():
    global _previous_qt_message_handler, _video_message_filter_installed
    if _video_message_filter_installed:
        return
    _previous_qt_message_handler = qInstallMessageHandler(_video_qt_message_handler)
    _video_message_filter_installed = True


class NV12FrameData:
    def __init__(self):
        self.width = 0
        self.height = 0
        self.y_stride = 0
        self.uv_stride = 0
        self.y_data = bytearray()
        self.uv_data = bytearray()
        self.coefficients = None
        self.serial = 0
        self.lock = threading.RLock()

    def clear(self):
        self.width = 0
        self.height = 0
        self.y_stride = 0
        self.uv_stride = 0
        self.y_data = bytearray()
        self.uv_data = bytearray()
        self.coefficients = None
        self.serial += 1

    def update(self, frame):
        if frame.pixelFormat().name != "Format_NV12":
            return False
        if frame.mirrored() or int(frame.rotation().value) != 0:
            return False
        if not frame.map(type(frame).MapMode.ReadOnly):
            return False
        try:
            with self.lock:
                y_size = frame.mappedBytes(0)
                uv_size = frame.mappedBytes(1)
                y_bits = frame.bits(0)
                uv_bits = frame.bits(1)
                if len(self.y_data) != y_size:
                    self.y_data = bytearray(y_size)
                if len(self.uv_data) != uv_size:
                    self.uv_data = bytearray(uv_size)
                ctypes.memmove(
                    ctypes.addressof(ctypes.c_ubyte.from_buffer(self.y_data)),
                    int(y_bits),
                    y_size,
                )
                ctypes.memmove(
                    ctypes.addressof(ctypes.c_ubyte.from_buffer(self.uv_data)),
                    int(uv_bits),
                    uv_size,
                )
                self.width = frame.width()
                self.height = frame.height()
                self.y_stride = frame.bytesPerLine(0)
                self.uv_stride = frame.bytesPerLine(1)
                try:
                    surface = frame.surfaceFormat()
                    color_space = surface.colorSpace().name
                    color_range = surface.colorRange().name
                except Exception:
                    color_space = "ColorSpace_BT709"
                    color_range = "ColorRange_Video"
                full = "Full" in color_range
                if "BT601" in color_space:
                    matrix = (1.4020, -0.3441, -0.7141, 1.7720) if full else (1.5960, -0.3918, -0.8130, 2.0172)
                elif "BT2020" in color_space:
                    matrix = (1.4746, -0.1646, -0.5714, 1.8814) if full else (1.6787, -0.1873, -0.6504, 2.1418)
                else:
                    matrix = (1.5748, -0.1873, -0.4681, 1.8556) if full else (1.7927, -0.2132, -0.5329, 2.1124)
                self.coefficients = (
                    0.0 if full else 16.0 / 255.0,
                    1.0 if full else 255.0 / 219.0,
                    matrix[0],
                    matrix[1],
                    matrix[2],
                    matrix[3],
                )
                self.serial += 1
            return True
        finally:
            frame.unmap()


class VideoFramePacket:
    def __init__(self):
        self.position_ms = None
        self.duration_us = 0
        self.nv12 = None
        self.nv12_serial = -1
        self.shared_textures = None
        self.video_size = None
        self.coefficients = None
        self.sync = None
        self.image = None


class VideoFrameWorker(QObject):
    frame_ready = pyqtSignal(object)

    def __init__(self, share_context=None, share_format=None, surface=None):
        super().__init__()
        self.nv12_enabled = True
        self.serial = 0
        self.buffers = None
        self.buffer_index = 0
        self.share_context = share_context
        self.share_format = share_format
        self.surface = surface
        self.upload_context = None
        self.functions = None
        self.textures = None
        self.texture_sizes = [None, None]
        self.active_texture = 0
        self.shared_failed = False
        self.native_gl = None
        self.upload_y_data = bytearray()
        self.upload_uv_data = bytearray()
        self.scrub_target_ms = None
        self.scrub_tolerance_ms = 50.0

    def _load_native_gl(self, context):
        factory = ctypes.WINFUNCTYPE if sys.platform.startswith("win") else ctypes.CFUNCTYPE

        def function(name, result, *arguments):
            address = context.getProcAddress(name.encode("ascii"))
            if not address:
                raise RuntimeError(name)
            return factory(result, *arguments)(int(address))

        uint = ctypes.c_uint
        integer = ctypes.c_int
        pointer = ctypes.c_void_p
        self.native_gl = {
            "active_texture": function("glActiveTexture", None, uint),
            "bind_texture": function("glBindTexture", None, uint, uint),
            "pixel_store": function("glPixelStorei", None, uint, integer),
            "tex_image": function(
                "glTexImage2D",
                None,
                uint,
                integer,
                integer,
                integer,
                integer,
                integer,
                uint,
                uint,
                pointer,
            ),
            "tex_sub_image": function(
                "glTexSubImage2D",
                None,
                uint,
                integer,
                integer,
                integer,
                integer,
                integer,
                uint,
                uint,
                pointer,
            ),
            "fence_sync": function("glFenceSync", pointer, uint, uint),
            "flush": function("glFlush", None),
        }

    def _ensure_shared_context(self):
        if self.shared_failed or self.share_context is None or self.surface is None:
            return False
        if self.upload_context is not None:
            return True
        try:
            context = QOpenGLContext()
            if self.share_format is not None:
                context.setFormat(self.share_format)
            context.setShareContext(self.share_context)
            if not context.create() or not context.makeCurrent(self.surface):
                self.shared_failed = True
                return False
            functions = QOpenGLFunctions_2_0()
            if not functions.initializeOpenGLFunctions():
                context.doneCurrent()
                self.shared_failed = True
                return False
            textures = functions.glGenTextures(4)
            if isinstance(textures, int):
                textures = (textures,)
            if not textures or len(textures) != 4:
                context.doneCurrent()
                self.shared_failed = True
                return False
            self.upload_context = context
            self.functions = functions
            self._load_native_gl(context)
            self.textures = tuple(textures)
            for texture in self.textures:
                functions.glBindTexture(0x0DE1, texture)
                functions.glTexParameteri(0x0DE1, 0x2801, 0x2601)
                functions.glTexParameteri(0x0DE1, 0x2800, 0x2601)
                functions.glTexParameteri(0x0DE1, 0x2802, 0x812F)
                functions.glTexParameteri(0x0DE1, 0x2803, 0x812F)
            functions.glBindTexture(0x0DE1, 0)
            context.doneCurrent()
            return True
        except Exception:
            self.shared_failed = True
            return False

    def _coefficients(self, frame):
        try:
            surface = frame.surfaceFormat()
            color_space = surface.colorSpace().name
            color_range = surface.colorRange().name
        except Exception:
            color_space = "ColorSpace_BT709"
            color_range = "ColorRange_Video"
        full = "Full" in color_range
        if "BT601" in color_space:
            matrix = (1.4020, -0.3441, -0.7141, 1.7720) if full else (1.5960, -0.3918, -0.8130, 2.0172)
        elif "BT2020" in color_space:
            matrix = (1.4746, -0.1646, -0.5714, 1.8814) if full else (1.6787, -0.1873, -0.6504, 2.1418)
        else:
            matrix = (1.5748, -0.1873, -0.4681, 1.8556) if full else (1.7927, -0.2132, -0.5329, 2.1124)
        return (
            0.0 if full else 16.0 / 255.0,
            1.0 if full else 255.0 / 219.0,
            matrix[0],
            matrix[1],
            matrix[2],
            matrix[3],
        )

    def _upload_shared(self, frame, packet):
        if (
            frame.pixelFormat().name != "Format_NV12"
            or frame.mirrored()
            or int(frame.rotation().value) != 0
            or not self._ensure_shared_context()
        ):
            return False
        if not frame.map(type(frame).MapMode.ReadOnly):
            return False
        try:
            width = frame.width()
            height = frame.height()
            size = (width, height)
            y_size = frame.mappedBytes(0)
            uv_size = frame.mappedBytes(1)
            y_stride = frame.bytesPerLine(0)
            uv_stride = frame.bytesPerLine(1)
            coefficients = self._coefficients(frame)
            if len(self.upload_y_data) != y_size:
                self.upload_y_data = bytearray(y_size)
            if len(self.upload_uv_data) != uv_size:
                self.upload_uv_data = bytearray(uv_size)
            ctypes.memmove(
                ctypes.addressof(ctypes.c_ubyte.from_buffer(self.upload_y_data)),
                int(frame.bits(0)),
                y_size,
            )
            ctypes.memmove(
                ctypes.addressof(ctypes.c_ubyte.from_buffer(self.upload_uv_data)),
                int(frame.bits(1)),
                uv_size,
            )
        finally:
            frame.unmap()
        current = False
        try:
            if not self.upload_context.makeCurrent(self.surface):
                self.shared_failed = True
                return False
            current = True
            y_data = ctypes.addressof(ctypes.c_ubyte.from_buffer(self.upload_y_data))
            uv_data = ctypes.addressof(ctypes.c_ubyte.from_buffer(self.upload_uv_data))
            target_texture = 1 - self.active_texture
            native = self.native_gl
            native["pixel_store"](0x0CF5, 1)
            native["active_texture"](0x84C0)
            native["bind_texture"](0x0DE1, self.textures[target_texture * 2])
            native["pixel_store"](0x0CF2, y_stride)
            if self.texture_sizes[target_texture] != size:
                native["tex_image"](0x0DE1, 0, 0x1909, width, height, 0, 0x1909, 0x1401, y_data)
            else:
                native["tex_sub_image"](0x0DE1, 0, 0, 0, width, height, 0x1909, 0x1401, y_data)
            native["active_texture"](0x84C1)
            native["bind_texture"](0x0DE1, self.textures[target_texture * 2 + 1])
            native["pixel_store"](0x0CF2, uv_stride // 2)
            if self.texture_sizes[target_texture] != size:
                native["tex_image"](0x0DE1, 0, 0x190A, width // 2, height // 2, 0, 0x190A, 0x1401, uv_data)
            else:
                native["tex_sub_image"](0x0DE1, 0, 0, 0, width // 2, height // 2, 0x190A, 0x1401, uv_data)
            native["pixel_store"](0x0CF2, 0)
            packet.sync = native["fence_sync"](0x9117, 0)
            native["flush"]()
            self.texture_sizes[target_texture] = size
            self.active_texture = target_texture
            self.serial += 1
            packet.shared_textures = (
                self.textures[target_texture * 2],
                self.textures[target_texture * 2 + 1],
            )
            packet.video_size = size
            packet.coefficients = coefficients
            packet.nv12_serial = self.serial
            return True
        except Exception:
            self.shared_failed = True
            return False
        finally:
            try:
                if self.native_gl is not None:
                    self.native_gl["pixel_store"](0x0CF2, 0)
            except Exception:
                pass
            if current:
                self.upload_context.doneCurrent()

    def process(self, frame):
        if not frame or not frame.isValid():
            return
        packet = VideoFramePacket()
        try:
            start_time = frame.startTime()
            if start_time >= 0:
                packet.position_ms = start_time / 1000.0
            packet.duration_us = max(0, frame.endTime() - start_time)
        except Exception:
            pass
        target_ms = self.scrub_target_ms
        if (
            target_ms is not None
            and packet.position_ms is not None
            and abs(packet.position_ms - target_ms) > self.scrub_tolerance_ms
        ):
            return
        try:
            if self.nv12_enabled and self._upload_shared(frame, packet):
                pass
            else:
                if self.buffers is None:
                    self.buffers = (NV12FrameData(), NV12FrameData())
                data = self.buffers[self.buffer_index]
                self.buffer_index = 1 - self.buffer_index
                if self.nv12_enabled and data.update(frame):
                    self.serial += 1
                    with data.lock:
                        data.serial = self.serial
                    packet.nv12 = data
                    packet.nv12_serial = self.serial
                else:
                    image = frame.toImage()
                    if image.isNull():
                        return
                    rotation = int(frame.rotation().value)
                    if rotation:
                        image = image.transformed(QTransform().rotate(rotation))
                    if frame.mirrored():
                        image = image.mirrored(True, False)
                    packet.image = image
        except Exception:
            return
        self.frame_ready.emit(packet)

    @pyqtSlot()
    def shutdown(self):
        context = self.upload_context
        if context is not None:
            try:
                if context.makeCurrent(self.surface):
                    if self.textures and self.functions:
                        self.functions.glDeleteTextures(4, self.textures)
                    context.doneCurrent()
            except Exception:
                pass
            try:
                sip.delete(context)
            except Exception:
                pass
        self.upload_context = None
        self.functions = None
        self.native_gl = None
        self.textures = None
        self.buffers = None
        self.upload_y_data = bytearray()
        self.upload_uv_data = bytearray()
        self.scrub_target_ms = None


class NV12VideoRenderer:
    def __init__(self):
        self.context = None
        self.functions = None
        self.program = None
        self.textures = None
        self.texture_sizes = [None, None]
        self.active_texture = 0
        self.uploaded_serial = -1
        self.active_size = None
        self.active_coefficients = None
        self.sync_gl = None
        self.failed = False

    def _load_sync_gl(self, context):
        factory = ctypes.WINFUNCTYPE if sys.platform.startswith("win") else ctypes.CFUNCTYPE

        def function(name, result, *arguments):
            address = context.getProcAddress(name.encode("ascii"))
            if not address:
                raise RuntimeError(name)
            return factory(result, *arguments)(int(address))

        pointer = ctypes.c_void_p
        uint = ctypes.c_uint
        uint64 = ctypes.c_uint64
        self.sync_gl = {
            "client_wait": function("glClientWaitSync", uint, pointer, uint, uint64),
            "delete": function("glDeleteSync", None, pointer),
        }

    def _initialize(self, allocate_textures=True):
        context = QOpenGLContext.currentContext()
        if context is None:
            return False
        if self.context is not context:
            self.context = context
            self.functions = None
            self.program = None
            self.textures = None
            self.texture_sizes = [None, None]
            self.active_texture = 0
            self.uploaded_serial = -1
            self.active_size = None
            self.active_coefficients = None
            self.sync_gl = None
            self.failed = False
        if self.failed:
            return False
        if self.program is not None and (not allocate_textures or self.textures is not None):
            return True
        try:
            self.functions = QOpenGLFunctions_2_0()
            if not self.functions.initializeOpenGLFunctions():
                self.failed = True
                return False
            self._load_sync_gl(context)
            if self.program is None:
                self.program = QOpenGLShaderProgram()
                if not self.program.addShaderFromSourceCode(
                    QOpenGLShader.ShaderTypeBit.Vertex,
                    "varying vec2 videoCoord; void main() { gl_Position = gl_Vertex; videoCoord = gl_MultiTexCoord0.xy; }",
                ):
                    self.failed = True
                    return False
                if not self.program.addShaderFromSourceCode(
                    QOpenGLShader.ShaderTypeBit.Fragment,
                    "uniform sampler2D textureY; uniform sampler2D textureUV; uniform float yOffset; uniform float yScale; uniform float redV; uniform float greenU; uniform float greenV; uniform float blueU; varying vec2 videoCoord; void main() { float y = (texture2D(textureY, videoCoord).r - yOffset) * yScale; vec4 uvSample = texture2D(textureUV, videoCoord); float u = uvSample.r - 0.5; float v = uvSample.a - 0.5; gl_FragColor = vec4(y + redV * v, y + greenU * u + greenV * v, y + blueU * u, 1.0); }",
                ):
                    self.failed = True
                    return False
                if not self.program.link():
                    self.failed = True
                    return False
            if not allocate_textures:
                return True
            textures = self.functions.glGenTextures(4)
            if isinstance(textures, int):
                textures = (textures,)
            if not textures or len(textures) != 4:
                self.failed = True
                return False
            self.textures = tuple(textures)
            for texture in self.textures:
                self.functions.glBindTexture(0x0DE1, texture)
                self.functions.glTexParameteri(0x0DE1, 0x2801, 0x2601)
                self.functions.glTexParameteri(0x0DE1, 0x2800, 0x2601)
                self.functions.glTexParameteri(0x0DE1, 0x2802, 0x812F)
                self.functions.glTexParameteri(0x0DE1, 0x2803, 0x812F)
            self.functions.glBindTexture(0x0DE1, 0)
            return True
        except Exception:
            self.failed = True
            return False

    def upload(self, data, expected_serial):
        if not self._initialize():
            return not self.failed
        try:
            with data.lock:
                if data.serial != expected_serial:
                    return self.active_size is not None
                if expected_serial == self.uploaded_serial:
                    return True
                if not data.width or data.coefficients is None:
                    return False
                gl = self.functions
                size = (data.width, data.height)
                target_texture = 1 - self.active_texture
                y_texture = self.textures[target_texture * 2]
                uv_texture = self.textures[target_texture * 2 + 1]
                gl.glPixelStorei(0x0CF5, 1)
                gl.glActiveTexture(0x84C0)
                gl.glBindTexture(0x0DE1, y_texture)
                gl.glPixelStorei(0x0CF2, data.y_stride)
                if self.texture_sizes[target_texture] != size:
                    gl.glTexImage2D(0x0DE1, 0, 0x1909, data.width, data.height, 0, 0x1909, 0x1401, data.y_data)
                else:
                    gl.glTexSubImage2D(0x0DE1, 0, 0, 0, data.width, data.height, 0x1909, 0x1401, data.y_data)
                gl.glActiveTexture(0x84C1)
                gl.glBindTexture(0x0DE1, uv_texture)
                gl.glPixelStorei(0x0CF2, data.uv_stride // 2)
                if self.texture_sizes[target_texture] != size:
                    gl.glTexImage2D(0x0DE1, 0, 0x190A, data.width // 2, data.height // 2, 0, 0x190A, 0x1401, data.uv_data)
                else:
                    gl.glTexSubImage2D(0x0DE1, 0, 0, 0, data.width // 2, data.height // 2, 0x190A, 0x1401, data.uv_data)
                gl.glPixelStorei(0x0CF2, 0)
                self.texture_sizes[target_texture] = size
                self.active_texture = target_texture
                self.uploaded_serial = expected_serial
                self.active_size = size
                self.active_coefficients = data.coefficients
                return True
        except Exception:
            self.failed = True
            return False

    def render(self, target_width, target_height):
        if self.failed or self.program is None or self.active_size is None:
            return False
        try:
            source_aspect = self.active_size[0] / max(1.0, self.active_size[1])
            target_aspect = target_width / max(1.0, target_height)
            if source_aspect > target_aspect:
                visible = target_aspect / source_aspect
                u0, u1 = (1.0 - visible) * 0.5, (1.0 + visible) * 0.5
                v0, v1 = 0.0, 1.0
            else:
                visible = source_aspect / target_aspect
                u0, u1 = 0.0, 1.0
                v0, v1 = (1.0 - visible) * 0.5, (1.0 + visible) * 0.5
            if not self.program.bind():
                return False
            y_offset, y_scale, red_v, green_u, green_v, blue_u = self.active_coefficients
            self.program.setUniformValue("textureY", 0)
            self.program.setUniformValue("textureUV", 1)
            self.program.setUniformValue("yOffset", float(y_offset))
            self.program.setUniformValue("yScale", float(y_scale))
            self.program.setUniformValue("redV", float(red_v))
            self.program.setUniformValue("greenU", float(green_u))
            self.program.setUniformValue("greenV", float(green_v))
            self.program.setUniformValue("blueU", float(blue_u))
            gl = self.functions
            gl.glDisable(0x0BE2)
            gl.glActiveTexture(0x84C0)
            gl.glBindTexture(0x0DE1, self.textures[self.active_texture * 2])
            gl.glActiveTexture(0x84C1)
            gl.glBindTexture(0x0DE1, self.textures[self.active_texture * 2 + 1])
            gl.glBegin(0x0005)
            gl.glTexCoord2f(u0, v1)
            gl.glVertex2f(-1.0, -1.0)
            gl.glTexCoord2f(u1, v1)
            gl.glVertex2f(1.0, -1.0)
            gl.glTexCoord2f(u0, v0)
            gl.glVertex2f(-1.0, 1.0)
            gl.glTexCoord2f(u1, v0)
            gl.glVertex2f(1.0, 1.0)
            gl.glEnd()
            gl.glActiveTexture(0x84C1)
            gl.glBindTexture(0x0DE1, 0)
            gl.glActiveTexture(0x84C0)
            gl.glBindTexture(0x0DE1, 0)
            self.program.release()
            return True
        except Exception:
            self.failed = True
            return False

    def render_shared(self, packet, target_width, target_height):
        if (
            packet is None
            or packet.shared_textures is None
            or packet.video_size is None
            or packet.coefficients is None
            or not self._initialize(False)
        ):
            return False
        self.active_size = packet.video_size
        self.active_coefficients = packet.coefficients
        try:
            source_aspect = self.active_size[0] / max(1.0, self.active_size[1])
            target_aspect = target_width / max(1.0, target_height)
            if source_aspect > target_aspect:
                visible = target_aspect / source_aspect
                u0, u1 = (1.0 - visible) * 0.5, (1.0 + visible) * 0.5
                v0, v1 = 0.0, 1.0
            else:
                visible = source_aspect / target_aspect
                u0, u1 = 0.0, 1.0
                v0, v1 = (1.0 - visible) * 0.5, (1.0 + visible) * 0.5
            if not self.program.bind():
                return False
            y_offset, y_scale, red_v, green_u, green_v, blue_u = self.active_coefficients
            self.program.setUniformValue("textureY", 0)
            self.program.setUniformValue("textureUV", 1)
            self.program.setUniformValue("yOffset", float(y_offset))
            self.program.setUniformValue("yScale", float(y_scale))
            self.program.setUniformValue("redV", float(red_v))
            self.program.setUniformValue("greenU", float(green_u))
            self.program.setUniformValue("greenV", float(green_v))
            self.program.setUniformValue("blueU", float(blue_u))
            gl = self.functions
            gl.glDisable(0x0BE2)
            gl.glActiveTexture(0x84C0)
            gl.glBindTexture(0x0DE1, packet.shared_textures[0])
            gl.glActiveTexture(0x84C1)
            gl.glBindTexture(0x0DE1, packet.shared_textures[1])
            gl.glBegin(0x0005)
            gl.glTexCoord2f(u0, v1)
            gl.glVertex2f(-1.0, -1.0)
            gl.glTexCoord2f(u1, v1)
            gl.glVertex2f(1.0, -1.0)
            gl.glTexCoord2f(u0, v0)
            gl.glVertex2f(-1.0, 1.0)
            gl.glTexCoord2f(u1, v0)
            gl.glVertex2f(1.0, 1.0)
            gl.glEnd()
            gl.glActiveTexture(0x84C1)
            gl.glBindTexture(0x0DE1, 0)
            gl.glActiveTexture(0x84C0)
            gl.glBindTexture(0x0DE1, 0)
            self.program.release()
            return True
        except Exception:
            self.failed = True
            return False

    def shared_packet_ready(self, packet):
        if packet is None or packet.sync is None:
            return True
        if not self._initialize(False) or self.sync_gl is None:
            return False
        try:
            status = self.sync_gl["client_wait"](packet.sync, 0, 0)
            if status in (0x911A, 0x911C):
                self.sync_gl["delete"](packet.sync)
                packet.sync = None
                return True
            if status == 0x911D:
                self.sync_gl["delete"](packet.sync)
                packet.sync = None
                return True
            return False
        except Exception:
            return False

    def release_shared_packet(self, packet):
        if packet is None or packet.sync is None:
            return
        try:
            if self._initialize(False) and self.sync_gl is not None:
                self.sync_gl["delete"](packet.sync)
        except Exception:
            pass
        packet.sync = None

    def release(self):
        try:
            if self.textures and self.functions and QOpenGLContext.currentContext() is self.context:
                self.functions.glDeleteTextures(4, self.textures)
        except Exception:
            pass
        self.context = None
        self.functions = None
        self.program = None
        self.textures = None
        self.texture_sizes = [None, None]
        self.active_texture = 0
        self.uploaded_serial = -1
        self.active_size = None
        self.active_coefficients = None
        self.sync_gl = None
        self.failed = False


class VideoPreviewController(QObject):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.source_path = None
        self.player = None
        self.sink = None
        self.frame_thread = None
        self.frame_worker = None
        self.frame_surface = None
        self.playback_source_path = None
        self.preview_worker = None
        self.preview_progress_dialog = None
        self.preview_generation_failed = False
        self.frame_pixmap = None
        self.shared_video_packet = None
        self.pending_shared_packet = None
        self.stale_shared_packets = []
        self.nv12_frame = NV12FrameData()
        self.nv12_serial = -1
        self.nv12_renderer = NV12VideoRenderer()
        self.frame_position_ms = None
        self.enabled = bool(getattr(editor, "video_preview_enabled", True))
        self.preview_offset_ms = 0
        self.preview_delay_mode = "black"
        self.before_start = False
        self.before_level_start = False
        self.after_end = False
        self.last_sync = 0.0
        self.pending_seek = None
        self.pending_seek_exact = False
        self.frame_rate = 30.0
        self.current_rate = None
        self.last_requested_position = None
        self.requested_frame_position = None
        self.active_seek_position = None
        self.seek_in_flight = False
        self.scrub_decoding = False
        self.continuous_scrub = False
        self.media_ready = False
        self.seek_timer = QTimer(self)
        self.seek_timer.setSingleShot(True)
        self.seek_timer.timeout.connect(self._flush_seek)

    def project_video(self):
        return find_project_video(getattr(self.editor, "project_folder", None))

    def load_project(self):
        path = self.project_video()
        if path == self.source_path:
            if self.enabled and path and self.player is None:
                self._ensure_player()
            return
        self.release()
        self.source_path = path
        if self.enabled and path:
            self._ensure_player()

    def set_configuration_source(self, source_path, offset_ms, delay_mode):
        source_path = Path(source_path) if source_path else self.project_video()
        if source_path != self.source_path:
            self.release()
            self.source_path = source_path
        self.preview_offset_ms = int(offset_ms)
        self.preview_delay_mode = "clone" if delay_mode == "clone" else "black"
        if self.enabled and self.source_path:
            self._ensure_player()
            self.sync_current(force=True)

    def restore_project_source(self):
        self.preview_offset_ms = 0
        self.preview_delay_mode = "black"
        self.release()
        self.load_project()
        self.sync_current(force=True)

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.editor.video_preview_enabled = self.enabled
        if self.enabled:
            self.source_path = self.project_video()
            if self.source_path:
                self._ensure_player()
                self.sync_current(force=True)
        else:
            self.release(keep_source=True)
        if hasattr(self.editor, "config_save_timer"):
            self.editor.config_save_timer.start()
        if hasattr(self.editor, "timeline"):
            self.editor.timeline.update()

    def toggle(self):
        self.set_enabled(not self.enabled)

    def set_preview_offset(self, offset_ms, delay_mode):
        self.preview_offset_ms = int(offset_ms)
        self.preview_delay_mode = "clone" if delay_mode == "clone" else "black"
        self.sync_current(force=True)

    def clear_preview_offset(self):
        self.preview_offset_ms = 0
        self.preview_delay_mode = "black"
        self.sync_current(force=True)

    def _ensure_player(self):
        if self.player is not None or not self.enabled or not self.source_path:
            return self.player is not None
        if self.playback_source_path is None:
            if self.preview_worker is None:
                self.preview_worker = VideoJobWorker(
                    "preview720",
                    getattr(self.editor, "project_folder", None),
                    self.source_path,
                    parent=self,
                )
                self.preview_worker.job_ready.connect(self._preview_ready)
                self.preview_worker.job_failed.connect(self._preview_failed)
                self.preview_worker.finished.connect(self._preview_finished)
                module = sys.modules.get(self.editor.__class__.__module__)
                dialog_class = getattr(module, "VideoProgressDialog", None)
                if dialog_class is not None:
                    self.preview_progress_dialog = dialog_class(
                        "Creating Cache",
                        self.editor,
                    )
                    self.preview_progress_dialog.cancel_button.clicked.connect(
                        self._cancel_preview_generation
                    )
                    self.preview_worker.progress_changed.connect(
                        self.preview_progress_dialog.set_progress
                    )
                self.preview_generation_failed = False
                self.preview_worker.start()
            return False
        try:
            install_video_message_filter()
            from PyQt6.QtMultimedia import QMediaPlayer, QVideoSink

            self.player = QMediaPlayer(self)
            self.sink = QVideoSink(self)
            self.frame_surface = None
            self.frame_thread = QThread(self)
            self.frame_worker = VideoFrameWorker()
            self.frame_worker.moveToThread(self.frame_thread)
            self.frame_thread.finished.connect(self.frame_worker.deleteLater)
            self.frame_worker.frame_ready.connect(self._frame_changed)
            self.sink.videoFrameChanged.connect(self.frame_worker.process)
            self.frame_thread.start(QThread.Priority.NormalPriority)
            self.player.setVideoSink(self.sink)
            self.player.mediaStatusChanged.connect(self._media_status_changed)
            self.player.setSource(QUrl.fromLocalFile(str(Path(self.playback_source_path).resolve())))
            self._apply_rate()
            return True
        except Exception as error:
            self.release(keep_source=True)
            QMessageBox = __import__("PyQt6.QtWidgets", fromlist=["QMessageBox"]).QMessageBox
            QMessageBox.warning(self.editor, "Video Preview", f"Video preview could not be started:\n{error}")
            return False

    def _cancel_preview_generation(self):
        self.set_enabled(False)

    def _preview_ready(self, result):
        if Path(result.get("source", "")) != Path(self.source_path or ""):
            return
        self.playback_source_path = Path(result["output"])
        if self.enabled and self._ensure_player():
            self.sync_current(force=True)

    def _preview_failed(self, message):
        self.preview_generation_failed = True
        if self.preview_progress_dialog is not None:
            self.preview_progress_dialog.show_error(message)
        if self.source_path:
            self.playback_source_path = Path(self.source_path)
            if self.enabled and self._ensure_player():
                self.sync_current(force=True)

    def _preview_finished(self):
        worker = self.preview_worker
        self.preview_worker = None
        dialog = self.preview_progress_dialog
        self.preview_progress_dialog = None
        if dialog is not None and not self.preview_generation_failed:
            dialog.finish()
        if worker is not None:
            worker.deleteLater()

    def _media_status_changed(self, status):
        if status.name not in ("LoadedMedia", "BufferedMedia") or self.media_ready:
            return
        self.media_ready = True
        self.seek_timer.stop()
        self.pending_seek = None
        self.pending_seek_exact = False
        self.seek_in_flight = False
        self.active_seek_position = None
        self.scrub_decoding = False
        self.continuous_scrub = False
        self.player.pause()
        QTimer.singleShot(0, lambda: self.sync_current(force=True))

    def _timeline_is_before_start(self):
        timeline = getattr(self.editor, "timeline", None)
        return bool(timeline is not None and float(timeline.current_time) < 0.0)

    def _frame_changed(self, packet):
        if not self.enabled or self.sink is None or packet is None:
            return
        if (
            not getattr(self.editor, "is_playing", False)
            and not self.scrub_decoding
            and not self.seek_in_flight
        ):
            return
        frame_position = packet.position_ms
        completed_seek = False
        if (
            (
                not getattr(self.editor, "is_playing", False)
                or self.scrub_decoding
            )
            and not self.continuous_scrub
            and self.seek_in_flight
            and self.active_seek_position is not None
        ):
            tolerance = max(2.0, 1000.0 / max(1.0, self.frame_rate))
            if (
                frame_position is not None
                and abs(frame_position - self.active_seek_position) > tolerance
            ):
                player_position = float(self.player.position())
                aligned_with_player = (
                    self.scrub_decoding
                    and abs(frame_position - player_position)
                    <= max(100.0, tolerance * 2.0)
                )
                if not aligned_with_player:
                    return
            self.seek_in_flight = False
            self.active_seek_position = None
            completed_seek = True
        if (
            (
                not getattr(self.editor, "is_playing", False)
                or self.scrub_decoding
            )
            and not self.continuous_scrub
            and self.requested_frame_position is not None
            and not completed_seek
        ):
            tolerance = max(2.0, 1000.0 / max(1.0, self.frame_rate))
            if (
                frame_position is not None
                and abs(frame_position - self.requested_frame_position) > tolerance
            ) or (frame_position is None and self.pending_seek is not None):
                if (
                    self.pending_seek is not None
                    and not self.seek_in_flight
                    and not self.seek_timer.isActive()
                ):
                    self.seek_timer.start(0)
                return
        if packet.duration_us > 0:
            self.frame_rate = max(1.0, min(240.0, 1000000.0 / packet.duration_us))
        try:
            if packet.nv12 is not None and not self.nv12_renderer.failed:
                if self.pending_shared_packet is not None:
                    self.stale_shared_packets.append(self.pending_shared_packet)
                self.nv12_frame = packet.nv12
                self.nv12_serial = packet.nv12_serial
                self.shared_video_packet = None
                self.pending_shared_packet = None
                self.frame_pixmap = None
            elif packet.shared_textures is not None and not self.nv12_renderer.failed:
                if self.pending_shared_packet is not None:
                    self.stale_shared_packets.append(self.pending_shared_packet)
                self.pending_shared_packet = packet
                self.nv12_serial = -1
                self.frame_pixmap = None
            elif packet.image is not None and not packet.image.isNull():
                if self.pending_shared_packet is not None:
                    self.stale_shared_packets.append(self.pending_shared_packet)
                self.frame_pixmap = QPixmap.fromImage(packet.image)
                self.nv12_frame = NV12FrameData()
                self.nv12_serial = -1
                self.shared_video_packet = None
                self.pending_shared_packet = None
            else:
                return
            self.frame_position_ms = frame_position
            if (
                self.requested_frame_position is None
                or frame_position is None
                or abs(frame_position - self.requested_frame_position)
                <= max(2.0, 1000.0 / max(1.0, self.frame_rate))
            ):
                self.requested_frame_position = None
        except Exception:
            return
        if completed_seek:
            if self.pending_seek is not None:
                if not self.seek_timer.isActive():
                    self.seek_timer.start(0)
            elif self.player is not None:
                if self.frame_worker is not None:
                    self.frame_worker.scrub_target_ms = None
                self.player.pause()
                self.scrub_decoding = False
        elif self.pending_seek is not None and not self.seek_timer.isActive():
            interval = (
                max(4, int(round(1000.0 / max(1.0, self.frame_rate))))
                if self.continuous_scrub and not self.pending_seek_exact
                else 0
            )
            self.seek_timer.start(interval)
        if hasattr(self.editor, "timeline") and not getattr(self.editor, "is_playing", False):
            self.editor.timeline.update()

    def _source_position(self, audio_ms):
        return float(audio_ms) - float(self.preview_offset_ms)

    def _apply_rate(self):
        if self.player is None:
            return
        rate = float(getattr(self.editor, "playback_speed", 1.0))
        if self.current_rate != rate:
            self.current_rate = rate
            self.player.setPlaybackRate(rate)

    def seek(self, audio_ms, exact=False):
        if not self.enabled or not self.source_path or not self._ensure_player():
            return
        source_ms = self._source_position(audio_ms)
        was_before_start = self.before_start
        self.before_level_start = self._timeline_is_before_start()
        self.before_start = source_ms < 0
        if was_before_start and not self.before_start:
            self.seek_timer.stop()
            self.pending_seek = None
            self.pending_seek_exact = False
            self.seek_in_flight = False
            self.active_seek_position = None
            self.requested_frame_position = None
            self.scrub_decoding = False
            self.continuous_scrub = False
        duration = self.player.duration()
        position = max(0, int(round(source_ms)))
        if duration > 0:
            position = min(position, max(0, duration - 1))
        self.after_end = duration > 0 and source_ms >= duration
        tolerance = max(2.0, 1000.0 / max(1.0, self.frame_rate))
        if (
            (
                self.shared_video_packet is not None
                or self.pending_shared_packet is not None
                or self.nv12_serial >= 0
                or self.frame_pixmap is not None
            )
            and self.frame_position_ms is not None
            and abs(self.frame_position_ms - position) <= tolerance
            and not self.seek_in_flight
        ):
            self.seek_timer.stop()
            self.pending_seek = None
            self.pending_seek_exact = False
            self.requested_frame_position = None
            if exact:
                self.player.pause()
                self.scrub_decoding = False
                self.continuous_scrub = False
                if self.frame_worker is not None:
                    self.frame_worker.scrub_target_ms = None
                self._apply_rate()
            return
        if self.seek_in_flight and self.active_seek_position == position:
            self.pending_seek = None
            self.requested_frame_position = position
            return
        self.requested_frame_position = position
        self.pending_seek = position
        self.pending_seek_exact = bool(exact)
        if not exact:
            self.requested_frame_position = None
        if self.before_start:
            self.player.pause()
        if not self.seek_in_flight and not self.seek_timer.isActive():
            interval = 0 if exact else max(
                4,
                int(round(1000.0 / max(1.0, self.frame_rate))),
            )
            self.seek_timer.start(interval)
        if exact and hasattr(self.editor, "timeline"):
            self.editor.timeline.update()

    def _flush_seek(self):
        if (
            self.player is None
            or self.pending_seek is None
            or self.seek_in_flight
        ):
            return
        position = self.pending_seek
        exact = self.pending_seek_exact
        self.pending_seek = None
        self.pending_seek_exact = False
        internal_decode = (
            not getattr(self.editor, "is_playing", False) or self.before_start
        )
        if internal_decode and not exact:
            if self.frame_thread is not None and self.frame_thread.isRunning():
                self.frame_thread.setPriority(QThread.Priority.NormalPriority)
            self.continuous_scrub = True
            self.scrub_decoding = True
            self.active_seek_position = None
            self.requested_frame_position = None
            if self.frame_worker is not None:
                self.frame_worker.scrub_target_ms = float(position)
                self.frame_worker.scrub_tolerance_ms = max(
                    50.0,
                    1500.0 / max(1.0, self.frame_rate),
                )
            self.last_requested_position = int(position)
            self.player.setPosition(int(position))
            self.player.setPlaybackRate(8.0)
            self.current_rate = 8.0
            self.player.play()
            return
        self.continuous_scrub = False
        self.active_seek_position = position
        self.seek_in_flight = True
        if internal_decode:
            if self.frame_thread is not None and self.frame_thread.isRunning():
                self.frame_thread.setPriority(QThread.Priority.NormalPriority)
            self.scrub_decoding = True
            if self.frame_worker is not None:
                self.frame_worker.scrub_target_ms = float(position)
                self.frame_worker.scrub_tolerance_ms = max(
                    50.0,
                    1500.0 / max(1.0, self.frame_rate),
                )
        if not self._set_position(position, True):
            self.seek_in_flight = False
            self.active_seek_position = None
            self.scrub_decoding = False
            if self.frame_worker is not None:
                self.frame_worker.scrub_target_ms = None
            return
        if internal_decode:
            self.player.setPlaybackRate(1.0)
            self.current_rate = 1.0
            self.player.play()

    def _set_position(self, position, force=False):
        if self.player is None:
            return False
        position = int(position)
        if not force and self.last_requested_position == position:
            return False
        if not getattr(self.editor, "is_playing", False) or self.scrub_decoding:
            self.requested_frame_position = position
        else:
            self.requested_frame_position = None
        self.last_requested_position = position
        self.player.setPosition(position)
        return True

    def play(self, audio_ms):
        if not self.enabled or not self.source_path or not self._ensure_player():
            return
        self.seek_timer.stop()
        self.pending_seek = None
        self.pending_seek_exact = False
        self.seek_in_flight = False
        self.active_seek_position = None
        self.scrub_decoding = False
        self.continuous_scrub = False
        if self.frame_worker is not None:
            self.frame_worker.scrub_target_ms = None
        if self.frame_thread is not None and self.frame_thread.isRunning():
            self.frame_thread.setPriority(QThread.Priority.LowPriority)
        self._apply_rate()
        source_ms = self._source_position(audio_ms)
        self.before_level_start = self._timeline_is_before_start()
        self.before_start = source_ms < 0
        duration = self.player.duration()
        position = max(0, int(round(source_ms)))
        if duration > 0:
            position = min(position, max(0, duration - 1))
        self._set_position(position, True)
        if self.before_start:
            self.player.pause()
            self.seek(audio_ms, exact=True)
        elif duration > 0 and source_ms >= duration:
            self.after_end = True
            self.player.pause()
        else:
            self.after_end = False
            self.player.play()
        self.last_sync = time.perf_counter()

    def pause(self, audio_ms=None):
        if self.player is None:
            return
        self.player.pause()
        if audio_ms is not None:
            self.seek(audio_ms, exact=True)

    def sync_current(self, force=False):
        timeline = getattr(self.editor, "timeline", None)
        if timeline is None:
            return
        audio_ms = timeline.visual_to_audio_ms(timeline.current_time)
        self.sync(audio_ms, getattr(self.editor, "is_playing", False), force)

    def sync(self, audio_ms, playing, force=False):
        if not self.enabled or not self.source_path or not self._ensure_player():
            return
        now = time.perf_counter()
        self._apply_rate()
        source_ms = self._source_position(audio_ms)
        self.before_level_start = self._timeline_is_before_start()
        before_start = source_ms < 0
        if before_start:
            self.before_start = True
            self.seek(audio_ms, exact=True)
            return
        if self.before_start:
            self.seek_timer.stop()
            self.pending_seek = None
            self.pending_seek_exact = False
            self.seek_in_flight = False
            self.active_seek_position = None
            self.requested_frame_position = None
            self.scrub_decoding = False
            self.continuous_scrub = False
            if self.frame_worker is not None:
                self.frame_worker.scrub_target_ms = None
            self.before_start = False
            self._set_position(max(0, int(round(source_ms))), True)
            if playing:
                self.player.play()
            now = time.perf_counter()
            self.last_sync = now
        duration = self.player.duration()
        if duration > 0 and source_ms >= duration:
            if not self.after_end or force:
                self.player.pause()
                last_position = max(0, duration - 1)
                self._set_position(last_position, force)
            self.after_end = True
            return
        self.after_end = False
        if not playing:
            self.pause(source_ms + self.preview_offset_ms)
            return
        if not force and now - self.last_sync < 1.0:
            return
        if self.player.playbackState().name != "PlayingState":
            self.player.play()
        self.last_sync = now
        threshold = max(200.0, 5000.0 / max(1.0, self.frame_rate))
        if force or abs(self.player.position() - source_ms) > threshold:
            self._set_position(max(0, int(round(source_ms))), force)

    def paint(self, painter, target):
        if not self.enabled or self.player is None:
            return
        if (
            self.before_start
            and not self.before_level_start
            and self.preview_delay_mode == "black"
        ):
            painter.fillRect(QRectF(target), QColor(0, 0, 0))
            return
        has_shared_video = (
            self.shared_video_packet is not None
            or self.pending_shared_packet is not None
            or bool(self.stale_shared_packets)
        )
        if has_shared_video and not self.nv12_renderer.failed:
            rendered = False
            try:
                painter.beginNativePainting()
                for stale_packet in self.stale_shared_packets:
                    self.nv12_renderer.release_shared_packet(stale_packet)
                self.stale_shared_packets.clear()
                if (
                    self.pending_shared_packet is not None
                    and self.nv12_renderer.shared_packet_ready(
                        self.pending_shared_packet
                    )
                ):
                    self.shared_video_packet = self.pending_shared_packet
                    self.pending_shared_packet = None
                if self.shared_video_packet is not None:
                    rendered = self.nv12_renderer.render_shared(
                        self.shared_video_packet,
                        float(target.width()),
                        float(target.height()),
                    )
            except Exception:
                rendered = False
            finally:
                try:
                    painter.endNativePainting()
                except Exception:
                    pass
            if rendered:
                return
            if self.pending_shared_packet is not None and self.shared_video_packet is None:
                return
            if self.nv12_renderer.failed and self.frame_worker is not None:
                self.frame_worker.nv12_enabled = False
        if self.nv12_serial >= 0 and not self.nv12_renderer.failed:
            rendered = False
            try:
                painter.beginNativePainting()
                if self.nv12_renderer.upload(
                    self.nv12_frame,
                    self.nv12_serial,
                ):
                    rendered = self.nv12_renderer.render(
                        float(target.width()),
                        float(target.height()),
                    )
            except Exception:
                rendered = False
            finally:
                try:
                    painter.endNativePainting()
                except Exception:
                    pass
            if rendered:
                return
            if self.nv12_renderer.failed and self.frame_worker is not None:
                self.frame_worker.nv12_enabled = False
        pixmap = self.frame_pixmap
        if pixmap is None or pixmap.isNull():
            return
        try:
            target_rect = QRectF(target)
            image_width = float(pixmap.width())
            image_height = float(pixmap.height())
            if image_width <= 0 or image_height <= 0:
                return
            scale = max(
                target_rect.width() / image_width,
                target_rect.height() / image_height,
            )
            source_width = target_rect.width() / scale
            source_height = target_rect.height() / scale
            source_rect = QRectF(
                (image_width - source_width) * 0.5,
                (image_height - source_height) * 0.5,
                source_width,
                source_height,
            )
            painter.drawPixmap(target_rect, pixmap, source_rect)
        except Exception:
            pass

    def release(self, keep_source=False):
        self.seek_timer.stop()
        self.pending_seek = None
        self.pending_seek_exact = False
        self.seek_in_flight = False
        self.active_seek_position = None
        self.scrub_decoding = False
        self.continuous_scrub = False
        preview_worker = self.preview_worker
        self.preview_worker = None
        if preview_worker is not None and preview_worker.isRunning():
            preview_worker.cancel()
            preview_worker.wait()
        if preview_worker is not None:
            preview_worker.deleteLater()
        if self.preview_progress_dialog is not None:
            self.preview_progress_dialog.finish()
            self.preview_progress_dialog = None
        player = self.player
        sink = self.sink
        frame_thread = self.frame_thread
        frame_worker = self.frame_worker
        frame_surface = self.frame_surface
        shared_packets = [
            packet
            for packet in (
                self.shared_video_packet,
                self.pending_shared_packet,
                *self.stale_shared_packets,
            )
            if packet is not None
        ]
        self.player = None
        self.sink = None
        self.frame_thread = None
        self.frame_worker = None
        self.frame_surface = None
        if sink is not None:
            try:
                if frame_worker is not None:
                    sink.videoFrameChanged.disconnect(frame_worker.process)
            except Exception:
                pass
            sink.blockSignals(True)
        if frame_worker is not None:
            try:
                frame_worker.frame_ready.disconnect(self._frame_changed)
            except Exception:
                pass
        if player is not None:
            try:
                player.blockSignals(True)
                player.stop()
                player.setVideoSink(None)
                player.setSource(QUrl())
            except Exception:
                pass
        if frame_thread is not None:
            if frame_worker is not None and frame_thread.isRunning():
                try:
                    QMetaObject.invokeMethod(
                        frame_worker,
                        "shutdown",
                        Qt.ConnectionType.BlockingQueuedConnection,
                    )
                except Exception:
                    pass
            frame_thread.quit()
            frame_thread.wait()
            try:
                sip.delete(frame_thread)
            except Exception:
                pass
        if player is not None:
            try:
                sip.delete(player)
            except Exception:
                pass
        if frame_surface is not None:
            try:
                sip.delete(frame_surface)
            except Exception:
                pass
        self.nv12_frame = NV12FrameData()
        self.nv12_serial = -1
        self.shared_video_packet = None
        self.pending_shared_packet = None
        self.stale_shared_packets.clear()
        timeline = getattr(self.editor, "timeline", None)
        try:
            if timeline is not None and timeline.isValid():
                timeline.makeCurrent()
                for packet in shared_packets:
                    self.nv12_renderer.release_shared_packet(packet)
                self.nv12_renderer.release()
                timeline.doneCurrent()
            else:
                self.nv12_renderer.release()
        except Exception:
            self.nv12_renderer.release()
        if sink is not None:
            try:
                sip.delete(sink)
            except Exception:
                pass
        self.frame_pixmap = None
        self.frame_position_ms = None
        self.current_rate = None
        self.last_requested_position = None
        self.requested_frame_position = None
        self.active_seek_position = None
        self.seek_in_flight = False
        self.scrub_decoding = False
        self.media_ready = False
        self.before_start = False
        self.before_level_start = False
        self.after_end = False
        if not keep_source:
            self.source_path = None
            self.playback_source_path = None
        if hasattr(self.editor, "timeline"):
            self.editor.timeline.update()

class VideoJobWorker(QThread):
    progress_changed = pyqtSignal(str, int)
    job_ready = pyqtSignal(object)
    job_failed = pyqtSignal(str)

    def __init__(self, operation, project_folder, source=None, options=None, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.project_folder = Path(project_folder)
        self.source = Path(source) if source else None
        self.options = dict(options or {})
        self.process = None
        self.temporary_paths = []
        self.passlog_paths = []
        self.last_progress = {}

    def cancel(self):
        self.requestInterruption()
        process = self.process
        if process and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass

            def force_kill():
                try:
                    if process.poll() is None:
                        process.kill()
                except Exception:
                    pass

            timer = threading.Timer(2.0, force_kill)
            timer.daemon = True
            timer.start()

    def emit_progress(self, phase, percent):
        percent = max(0, min(100, int(percent)))
        if percent <= self.last_progress.get(phase, -1):
            return
        self.last_progress[phase] = percent
        self.progress_changed.emit(phase, percent)

    def checked_tool(self):
        path, error = resolve_video_tool()
        if not path:
            raise RuntimeError(error)
        return path

    def probe(self, path):
        return run_video_probe(path, self.checked_tool())

    def run_process(self, arguments, phase, duration_ms, start_percent=0, end_percent=99):
        if self.isInterruptionRequested():
            raise InterruptedError
        tool = self.checked_tool()
        startupinfo, creationflags = video_process_startup()
        command = [str(tool), "-hide_banner", "-nostdin", "-y", *[str(value) for value in arguments]]
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
            startupinfo=startupinfo,
            creationflags=creationflags,
            preexec_fn=(lambda: os.nice(10)) if os.name != "nt" else None,
        )
        output_tail = []
        last_percent = -1
        duration_ms = max(1.0, float(duration_ms))
        for raw_line in self.process.stdout:
            if self.isInterruptionRequested():
                self.cancel()
                raise InterruptedError
            line = raw_line.strip()
            output_tail.append(line)
            if len(output_tail) > 80:
                output_tail.pop(0)
            current_ms = None
            if line.startswith("out_time_us="):
                try:
                    current_ms = float(line.split("=", 1)[1]) / 1000.0
                except ValueError:
                    pass
            elif line.startswith("out_time_ms="):
                try:
                    current_ms = float(line.split("=", 1)[1]) / 1000.0
                except ValueError:
                    pass
            elif line.startswith("out_time="):
                match = re.match(r"out_time=(\d+):(\d+):(\d+(?:\.\d+)?)", line)
                if match:
                    current_ms = (
                        int(match.group(1)) * 3600
                        + int(match.group(2)) * 60
                        + float(match.group(3))
                    ) * 1000.0
            if current_ms is not None:
                ratio = max(0.0, min(1.0, current_ms / duration_ms))
                percent = int(start_percent + ratio * (end_percent - start_percent))
                if percent != last_percent:
                    last_percent = percent
                    self.emit_progress(phase, percent)
        return_code = self.process.wait()
        self.process = None
        if return_code != 0:
            details = "\n".join(line for line in output_tail if line)
            raise RuntimeError(details[-4000:] or f"cbm_video_tool exited with code {return_code}.")
        self.emit_progress(phase, end_percent)
        return "\n".join(output_tail)

    def copy_file(self, source, destination, phase):
        source = Path(source)
        destination = Path(destination)
        total = max(1, source.stat().st_size)
        copied = 0
        last_percent = -1
        with source.open("rb") as src, destination.open("wb") as dst:
            while True:
                if self.isInterruptionRequested():
                    raise InterruptedError
                chunk = src.read(4 * 1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
                copied += len(chunk)
                percent = min(99, int(copied * 100 / total))
                if percent != last_percent:
                    last_percent = percent
                    self.emit_progress(phase, percent)
            dst.flush()
            os.fsync(dst.fileno())
        shutil.copystat(source, destination)

    def make_temp_path(self, suffix, label):
        path = self.project_folder / f".video-{label}-{time.time_ns()}{suffix}"
        self.temporary_paths.append(path)
        return path

    def remove_temp_path(self, path):
        try:
            if path.exists():
                path.unlink()
        except OSError:
            return
        try:
            self.temporary_paths.remove(path)
        except ValueError:
            pass

    def cleanup_temp_paths(self, keep=()):
        keep = {Path(path) for path in keep if path}
        for path in tuple(self.temporary_paths):
            if path in keep:
                continue
            self.remove_temp_path(path)

    def make_passlog_path(self, label):
        prefix = f"{label}-" if label else ""
        path = self.project_folder / f".video-{prefix}pass-{time.time_ns()}"
        self.passlog_paths.append(path)
        return path

    def cleanup_passlog_path(self, passlog):
        passlog = Path(passlog)
        for path in passlog.parent.glob(f"{passlog.name}*"):
            try:
                path.unlink()
            except OSError:
                pass
        try:
            self.passlog_paths.remove(passlog)
        except ValueError:
            pass

    def cleanup_passlogs(self):
        for passlog in tuple(self.passlog_paths):
            self.cleanup_passlog_path(passlog)

    def cleanup_orphan_passlogs(self):
        for pattern in (
            ".video-pass-*",
            ".video-correction-pass-*",
            ".video-offset-pass-*",
            ".video-offset-correction-pass-*",
        ):
            for path in self.project_folder.glob(pattern):
                try:
                    path.unlink()
                except OSError:
                    pass

    def ensure_backup(self, source):
        cbm_directory = self.project_folder / "cbm_files"
        cbm_directory.mkdir(parents=True, exist_ok=True)
        existing = find_video_backup(self.project_folder)
        if existing:
            return existing
        backup = cbm_directory / f"video_backup{source.suffix.lower()}"
        temporary = backup.with_name(f".{backup.name}.{time.time_ns()}.tmp")
        self.temporary_paths.append(temporary)
        self.copy_file(source, temporary, "Creating original video backup...")
        os.replace(temporary, backup)
        self.temporary_paths.remove(temporary)
        for other_extension in (".mp4", ".webm"):
            other = cbm_directory / f"video_backup{other_extension}"
            if other != backup and other.is_file():
                other.unlink()
        self.emit_progress("Creating original video backup...", 100)
        return backup

    def import_video(self):
        source = self.source
        if not source or not source.is_file() or source.suffix.lower() not in (".mp4", ".webm"):
            raise RuntimeError("Only MP4 and WebM video files are supported.")
        metadata = self.probe(source)
        output = self.make_temp_path(source.suffix.lower(), "import")
        self.run_process(
            [
                "-i",
                source,
                "-map",
                "0:v:0",
                "-c:v",
                "copy",
                "-an",
                "-progress",
                "pipe:1",
                "-nostats",
                output,
            ],
            "Importing video...",
            metadata["duration_ms"],
        )
        validated = self.probe(output)
        if validated["duration_ms"] <= 0 or validated["width"] <= 0 or validated["height"] <= 0:
            raise RuntimeError("The imported video could not be validated.")
        self.emit_progress("Importing video...", 100)
        cbm_directory = self.project_folder / "cbm_files"
        cbm_directory.mkdir(parents=True, exist_ok=True)
        backup = cbm_directory / f".video-backup-import-{time.time_ns()}{output.suffix.lower()}"
        self.temporary_paths.append(backup)
        self.copy_file(output, backup, "Creating original video backup...")
        self.emit_progress("Creating original video backup...", 100)
        return {
            "operation": "import",
            "output": str(output),
            "backup_output": str(backup),
            "extension": output.suffix.lower(),
            "metadata": validated,
            "settings": {"offset_ms": 0},
        }

    def sample_ranges(self, duration_ms):
        duration_seconds = duration_ms / 1000.0
        if duration_seconds <= 30.0:
            return [(0.0, duration_seconds)]
        ranges = []
        for ratio in (0.10, 0.30, 0.50, 0.70, 0.90):
            start = max(0.0, min(duration_seconds - 4.0, duration_seconds * ratio - 2.0))
            end = min(duration_seconds, start + 4.0)
            if ranges and start <= ranges[-1][1]:
                ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
            else:
                ranges.append((start, end))
        return [(start, end - start) for start, end in ranges if end > start]

    def analyze_mp4(self, source, metadata, bitrate, resize_height=0):
        ranges = self.sample_ranges(metadata["duration_ms"])
        total_duration = sum(duration for _, duration in ranges)
        scores = []
        processed = 0.0
        for index, (start, duration) in enumerate(ranges):
            if self.isInterruptionRequested():
                raise InterruptedError
            candidate = self.make_temp_path(".mp4", f"sample-{index}")
            phase = "Analyzing MP4 quality..."
            start_percent = int(processed * 50.0 / max(0.001, total_duration))
            end_percent = int((processed + duration) * 50.0 / max(0.001, total_duration))
            self.run_process(
                [
                    "-ss",
                    f"{start:.6f}",
                    "-t",
                    f"{duration:.6f}",
                    "-i",
                    source,
                    "-map",
                    "0:v:0",
                    "-an",
                    *(
                        ["-vf", f"scale=-2:{resize_height},format=yuv420p"]
                        if resize_height > 0 and resize_height != metadata["height"]
                        else []
                    ),
                    "-c:v",
                    "libx264",
                    "-b:v",
                    str(bitrate),
                    "-preset",
                    "medium",
                    "-pix_fmt",
                    "yuv420p",
                    "-progress",
                    "pipe:1",
                    "-nostats",
                    candidate,
                ],
                phase,
                duration * 1000.0,
                start_percent,
                end_percent,
            )
            tool = self.checked_tool()
            startupinfo, creationflags = video_process_startup()
            comparison_filter = "ssim"
            if resize_height > 0 and resize_height != metadata["height"]:
                comparison_filter = (
                    f"[0:v]scale=-2:{resize_height},format=yuv420p[reference];"
                    "[reference][1:v]ssim"
                )
            process = subprocess.Popen(
                [
                    str(tool),
                    "-hide_banner",
                    "-nostdin",
                    "-ss",
                    f"{start:.6f}",
                    "-t",
                    f"{duration:.6f}",
                    "-i",
                    str(source),
                    "-i",
                    str(candidate),
                    "-lavfi",
                    comparison_filter,
                    "-an",
                    "-progress",
                    "pipe:1",
                    "-nostats",
                    "-f",
                    "null",
                    os.devnull,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                startupinfo=startupinfo,
                creationflags=creationflags,
                preexec_fn=(lambda: os.nice(10)) if os.name != "nt" else None,
            )
            self.process = process
            output = []
            for line in process.stdout:
                if self.isInterruptionRequested():
                    self.cancel()
                    raise InterruptedError
                output.append(line)
                stripped = line.strip()
                current_ms = None
                if stripped.startswith("out_time_us=") or stripped.startswith("out_time_ms="):
                    try:
                        current_ms = float(stripped.split("=", 1)[1]) / 1000.0
                    except ValueError:
                        pass
                if current_ms is not None:
                    current_seconds = min(duration, max(0.0, current_ms / 1000.0))
                    self.emit_progress(
                        phase,
                        50
                        + int(
                            (processed + current_seconds)
                            * 50.0
                            / max(0.001, total_duration)
                        ),
                    )
            return_code = process.wait()
            self.process = None
            if return_code != 0:
                raise RuntimeError("".join(output)[-4000:] or "SSIM analysis failed.")
            matches = re.findall(r"All:([0-9.]+)", "".join(output))
            if not matches:
                raise RuntimeError("The MP4 quality score could not be calculated.")
            scores.append(float(matches[-1]))
            processed += duration
            self.emit_progress(
                phase,
                50 + int(processed * 50.0 / max(0.001, total_duration)),
            )
            self.remove_temp_path(candidate)
        average = sum(scores) / len(scores)
        worst = min(scores)
        return {
            "average_ssim": average,
            "minimum_ssim": worst,
            "viable": average >= 0.92 and worst >= 0.88,
            "sample_count": len(scores),
            "sample_duration_seconds": total_duration,
        }

    def filter_chain(self, offset_frames, resize_height=0):
        filters = []
        if offset_frames > 0:
            mode = "clone" if self.options.get("delay_mode") == "clone" else "add"
            filters.append(f"tpad=start={offset_frames}:start_mode={mode}")
        elif offset_frames < 0:
            filters.append(f"trim=start_frame={abs(offset_frames)}")
        filters.append("setpts=PTS-STARTPTS")
        if resize_height > 0:
            filters.append(f"scale=-2:{resize_height}")
        filters.append("format=yuv420p")
        return ",".join(filters)

    def resolve_offset(self, metadata):
        fps = float(metadata.get("fps", 0.0))
        if fps <= 0:
            raise RuntimeError("The video frame rate could not be determined.")
        if "offset_frames" in self.options:
            offset_frames = int(self.options.get("offset_frames", 0))
        else:
            offset_frames = int(round(float(self.options.get("offset_ms", 0)) * fps / 1000.0))
        return offset_frames, int(round(offset_frames * 1000.0 / fps))

    def encode_once(self, source, output, metadata, codec, bitrate, phase, pass_number=None, passlog=None):
        offset_frames, offset_ms = self.resolve_offset(metadata)
        resize_height = int(self.options.get("resize_height", 0) or 0)
        duration_ms = max(1, metadata["duration_ms"] + offset_ms)
        arguments = [
            "-i",
            source,
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            self.filter_chain(offset_frames, resize_height),
            "-c:v",
            codec,
        ]
        if bitrate:
            arguments.extend(["-b:v", str(int(bitrate))])
        if codec == "libx264":
            arguments.extend(["-preset", "medium", "-pix_fmt", "yuv420p"])
        else:
            arguments.extend(["-deadline", "good", "-cpu-used", "2", "-pix_fmt", "yuv420p"])
        if pass_number:
            arguments.extend(["-pass", str(pass_number), "-passlogfile", str(passlog)])
        arguments.extend(["-progress", "pipe:1", "-nostats"])
        if pass_number == 1:
            arguments.extend(["-f", "null", os.devnull])
        else:
            if output.suffix.lower() == ".mp4":
                arguments.extend(["-movflags", "+faststart"])
            arguments.append(output)
        self.run_process(arguments, phase, duration_ms)

    def apply_video(self):
        current = find_project_video(self.project_folder)
        if not current:
            raise RuntimeError("No project video exists.")
        backup = self.ensure_backup(current)
        metadata = self.probe(backup)
        offset_frames, offset_ms = self.resolve_offset(metadata)
        final_duration_ms = metadata["duration_ms"] + offset_ms
        if final_duration_ms <= 0:
            raise RuntimeError("The negative offset removes the entire video.")
        compression = bool(self.options.get("compress", False))
        resize_height = int(self.options.get("resize_height", 0) or 0)
        if resize_height <= 0:
            resize_height = int(metadata["height"])
        resize_needed = resize_height != int(metadata["height"])
        mp4_test = None
        target_mb = None
        if compression:
            target_mb = float(self.options.get("target_mb", 0))
            if target_mb <= 0:
                raise RuntimeError("The target size must be greater than zero.")
            target_bytes = int(target_mb * 1024 * 1024)
            bitrate = int(target_bytes * 8 * 0.96 / max(0.001, final_duration_ms / 1000.0))
            if bitrate < 16000:
                raise RuntimeError("The target size is too small for this video duration.")
            mp4_test = self.analyze_mp4(backup, metadata, bitrate, resize_height)
            output_extension = ".mp4" if mp4_test["viable"] else ".webm"
            codec = "libx264" if mp4_test["viable"] else "libvpx-vp9"
            output = self.make_temp_path(output_extension, "processed")
            passlog = self.make_passlog_path("")
            self.encode_once(
                backup,
                output,
                metadata,
                codec,
                bitrate,
                "Compressing video — Pass 1 of 2...",
                1,
                passlog,
            )
            final_phase = "Compressing video — Pass 2 of 2..."
            self.encode_once(
                backup,
                output,
                metadata,
                codec,
                bitrate,
                "Compressing video — Pass 2 of 2...",
                2,
                passlog,
            )
            self.cleanup_passlog_path(passlog)
            actual_size = output.stat().st_size
            if actual_size > target_bytes:
                corrected = max(16000, int(bitrate * target_bytes / actual_size * 0.985))
                correction = self.make_temp_path(output_extension, "correction")
                correction_log = self.make_passlog_path("correction")
                self.encode_once(
                    backup,
                    correction,
                    metadata,
                    codec,
                    corrected,
                    "Correcting video size — Pass 1 of 2...",
                    1,
                    correction_log,
                )
                final_phase = "Correcting video size — Pass 2 of 2..."
                self.encode_once(
                    backup,
                    correction,
                    metadata,
                    codec,
                    corrected,
                    "Correcting video size — Pass 2 of 2...",
                    2,
                    correction_log,
                )
                self.cleanup_passlog_path(correction_log)
                if correction.stat().st_size > target_bytes:
                    raise RuntimeError("The requested size cannot be reached without changing the resolution.")
                try:
                    output.unlink()
                except OSError:
                    pass
                self.temporary_paths.remove(output)
                output = correction
        else:
            output_extension = current.suffix.lower()
            codec = "libx264" if output_extension == ".mp4" else "libvpx-vp9"
            output = self.make_temp_path(output_extension, "offset")
            if offset_frames == 0 and not resize_needed:
                self.copy_file(backup, output, "Applying video offset...")
                final_phase = "Applying video offset..."
            else:
                action = str(self.options.get("action", "offset"))
                phase_name = "Resizing video" if action == "resize" else "Applying video offset"
                source_duration_ms = max(1, int(metadata["duration_ms"]))
                target_bytes = max(
                    1,
                    int(backup.stat().st_size * final_duration_ms / source_duration_ms),
                )
                bitrate = max(
                    1000,
                    int(
                        target_bytes
                        * 8
                        * 0.985
                        / max(0.001, final_duration_ms / 1000.0)
                    ),
                )
                passlog = self.make_passlog_path("offset")
                self.encode_once(
                    backup,
                    output,
                    metadata,
                    codec,
                    bitrate,
                    f"{phase_name} — Pass 1 of 2...",
                    1,
                    passlog,
                )
                final_phase = f"{phase_name} — Pass 2 of 2..."
                self.encode_once(
                    backup,
                    output,
                    metadata,
                    codec,
                    bitrate,
                    final_phase,
                    2,
                    passlog,
                )
                self.cleanup_passlog_path(passlog)
                if output.stat().st_size > int(target_bytes * 1.03):
                    corrected_bitrate = max(
                        1000,
                        int(bitrate * target_bytes / output.stat().st_size * 0.985),
                    )
                    correction = self.make_temp_path(
                        output_extension,
                        "offset-correction",
                    )
                    correction_log = self.make_passlog_path("offset-correction")
                    self.encode_once(
                        backup,
                        correction,
                        metadata,
                        codec,
                        corrected_bitrate,
                        "Correcting video offset size — Pass 1 of 2...",
                        1,
                        correction_log,
                    )
                    final_phase = "Correcting video offset size — Pass 2 of 2..."
                    self.encode_once(
                        backup,
                        correction,
                        metadata,
                        codec,
                        corrected_bitrate,
                        final_phase,
                        2,
                        correction_log,
                    )
                    self.cleanup_passlog_path(correction_log)
                    output.unlink()
                    self.temporary_paths.remove(output)
                    output = correction

        validated = self.probe(output)
        source_aspect = metadata["width"] / max(1, metadata["height"])
        output_aspect = validated["width"] / max(1, validated["height"])
        if (
            validated["duration_ms"] <= 0
            or validated["height"] != resize_height
            or abs(output_aspect - source_aspect) > 0.01
        ):
            raise RuntimeError("The processed video failed validation.")
        source_fps = float(metadata.get("fps", 0.0))
        output_fps = float(validated.get("fps", 0.0))
        if source_fps > 0 and output_fps > 0 and abs(output_fps - source_fps) > max(0.01, source_fps * 0.001):
            raise RuntimeError("The processed video frame rate changed unexpectedly.")
        if compression and output.stat().st_size > int(target_mb * 1024 * 1024):
            raise RuntimeError("The processed video exceeds the requested maximum size.")
        self.emit_progress(final_phase, 100)
        return {
            "operation": "apply",
            "output": str(output),
            "extension": output_extension,
            "metadata": validated,
            "mp4_test": mp4_test,
            "settings": {"offset_ms": offset_ms},
        }

    def restore_video(self):
        backup = find_video_backup(self.project_folder)
        if not backup:
            raise RuntimeError("No original video backup exists.")
        output = self.make_temp_path(backup.suffix.lower(), "restore")
        self.copy_file(backup, output, "Restoring original video...")
        validated = self.probe(output)
        if validated["duration_ms"] <= 0:
            raise RuntimeError("The restored video failed validation.")
        self.emit_progress("Restoring original video...", 100)
        return {
            "operation": "restore",
            "output": str(output),
            "extension": backup.suffix.lower(),
            "metadata": validated,
            "settings": {"offset_ms": 0},
        }

    def probe_video(self):
        source = self.source or find_project_video(self.project_folder)
        if not source:
            raise RuntimeError("No project video exists.")
        return {"operation": "probe", "metadata": self.probe(source)}

    def create_preview_720(self):
        source = self.source or find_project_video(self.project_folder)
        if not source or not source.is_file():
            raise RuntimeError("No project video exists.")
        metadata = self.probe(source)
        if metadata["height"] <= 720:
            return {
                "operation": "preview720",
                "source": str(source),
                "output": str(source),
                "metadata": metadata,
            }
        stat = source.stat()
        source_bitrate = int(metadata.get("total_bitrate", 0) or 0)
        if source_bitrate <= 0:
            duration_seconds = max(0.001, float(metadata["duration_ms"]) / 1000.0)
            source_bitrate = int(stat.st_size * 8 / duration_seconds)
        if source_bitrate <= 0:
            source_bitrate = int(metadata.get("video_bitrate", 0) or 0)
        source_bitrate = max(1, source_bitrate)
        target_bitrate = preview_video_bitrate(metadata, 720)
        cache_directory = self.project_folder / "cbm_files"
        cache_directory.mkdir(parents=True, exist_ok=True)
        for stale_path in cache_directory.glob("video_preview_720_*.mp4"):
            try:
                stale_path.unlink()
            except OSError:
                pass
        cache_path = cache_directory / "previewcache.mp4"
        if cache_path.is_file() and cache_path.stat().st_mtime_ns >= stat.st_mtime_ns:
            cached_metadata = self.probe(cache_path)
            if cached_metadata["height"] == 720:
                return {
                    "operation": "preview720",
                    "source": str(source),
                    "output": str(cache_path),
                    "metadata": cached_metadata,
                }
        temporary = self.make_temp_path(".mp4", "preview-720")
        self.run_process(
            [
                "-i",
                source,
                "-map",
                "0:v:0",
                "-vf",
                "scale=-2:720",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-b:v",
                str(target_bitrate),
                "-maxrate",
                str(target_bitrate),
                "-bufsize",
                str(max(32000, target_bitrate * 2)),
                "-pix_fmt",
                "yuv420p",
                "-an",
                "-movflags",
                "+faststart",
                "-progress",
                "pipe:1",
                "-nostats",
                temporary,
            ],
            "Creating Cache",
            metadata["duration_ms"],
        )
        cached_metadata = self.probe(temporary)
        if cached_metadata["height"] != 720 or cached_metadata["duration_ms"] <= 0:
            raise RuntimeError("The 720p video preview failed validation.")
        if int(cached_metadata.get("video_bitrate", 0) or 0) > source_bitrate:
            raise RuntimeError("The 720p video preview exceeds the source video bitrate.")
        os.replace(temporary, cache_path)
        self.temporary_paths.remove(temporary)
        self.emit_progress("Creating Cache", 100)
        return {
            "operation": "preview720",
            "source": str(source),
            "output": str(cache_path),
            "metadata": cached_metadata,
        }

    def run(self):
        succeeded = False
        try:
            self.cleanup_orphan_passlogs()
            if self.operation == "import":
                result = self.import_video()
            elif self.operation == "apply":
                result = self.apply_video()
            elif self.operation == "restore":
                result = self.restore_video()
            elif self.operation == "probe":
                result = self.probe_video()
            elif self.operation == "preview720":
                result = self.create_preview_720()
            else:
                raise RuntimeError("Unknown video operation.")
            if not self.isInterruptionRequested():
                self.cleanup_temp_paths((result.get("output"), result.get("backup_output")))
                self.job_ready.emit(result)
                succeeded = True
        except InterruptedError:
            pass
        except Exception as error:
            if not self.isInterruptionRequested():
                self.job_failed.emit(str(error))
        finally:
            self.cleanup_passlogs()
            if not succeeded or self.operation == "probe":
                self.cleanup_temp_paths()


def commit_video_result(project_folder, result):
    project_folder = Path(project_folder)
    output = Path(result["output"])
    extension = result["extension"]
    destination = project_folder / f"video{extension}"
    backup_output = result.get("backup_output")
    if backup_output:
        backup_output = Path(backup_output)
        backup_directory = project_folder / "cbm_files"
        backup_directory.mkdir(parents=True, exist_ok=True)
        backup_destination = backup_directory / f"video_backup{backup_output.suffix.lower()}"
        os.replace(backup_output, backup_destination)
        for other_extension in (".mp4", ".webm"):
            other_backup = backup_directory / f"video_backup{other_extension}"
            if other_backup != backup_destination and other_backup.is_file():
                other_backup.unlink()
    os.replace(output, destination)
    for other_extension in (".mp4", ".webm"):
        other = project_folder / f"video{other_extension}"
        if other != destination and other.is_file():
            other.unlink()
    return destination
