import ctypes
import hashlib
import json
import math
import sys
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np

from .audio import AudioError
from .bass_audio import BassAudioEngine, _platform_key, _runtime_roots


FMOD_LOOP_OFF = 0x1
FMOD_CREATESAMPLE = 0x100
FMOD_OPENMEMORY = 0x800
FMOD_OPENONLY = 0x2000
FMOD_ACCURATETIME = 0x4000
FMOD_TIMEUNIT_PCM = 0x2
FMOD_TIMEUNIT_PCMBYTES = 0x4


class FmodError(AudioError):
    pass


class FmodCreateSoundInfo(ctypes.Structure):
    _fields_ = [
        ('cbsize', ctypes.c_int), ('length', ctypes.c_uint),
        ('fileoffset', ctypes.c_uint), ('numchannels', ctypes.c_int),
        ('defaultfrequency', ctypes.c_int), ('format', ctypes.c_int),
        ('decodebuffersize', ctypes.c_uint), ('initialsubsound', ctypes.c_int),
        ('numsubsounds', ctypes.c_int), ('inclusionlist', ctypes.c_void_p),
        ('inclusionlistnum', ctypes.c_int), ('pcmreadcallback', ctypes.c_void_p),
        ('pcmsetposcallback', ctypes.c_void_p), ('nonblockcallback', ctypes.c_void_p),
        ('dlsname', ctypes.c_void_p), ('encryptionkey', ctypes.c_void_p),
        ('maxpolyphony', ctypes.c_int), ('userdata', ctypes.c_void_p),
        ('suggestedsoundtype', ctypes.c_int), ('fileuseropen', ctypes.c_void_p),
        ('fileuserclose', ctypes.c_void_p), ('fileuserread', ctypes.c_void_p),
        ('fileuserseek', ctypes.c_void_p), ('fileuserasyncread', ctypes.c_void_p),
        ('fileuserasynccancel', ctypes.c_void_p), ('fileuserdata', ctypes.c_void_p),
        ('filebuffersize', ctypes.c_int), ('channelorder', ctypes.c_int),
        ('initialsoundgroup', ctypes.c_void_p), ('initialseekposition', ctypes.c_uint),
        ('initialseekpostype', ctypes.c_uint), ('ignoresetfilesystem', ctypes.c_int),
        ('audioqueuepolicy', ctypes.c_uint), ('minmidigranularity', ctypes.c_uint),
        ('nonblockthreadid', ctypes.c_int), ('fsbguid', ctypes.c_void_p),
    ]


def fmod_manifest():
    for root in _runtime_roots():
        path = root / 'vendor/fmod/manifest.json'
        if path.is_file():
            return path, json.loads(path.read_text(encoding='utf-8'))
    raise FmodError('The bundled FMOD manifest was not found.')


def fmod_available():
    try:
        path, manifest = fmod_manifest()
        entry = manifest['libraries'][_platform_key()]['core']
        return (path.parent / _platform_key() / entry['filename']).is_file()
    except (AudioError, OSError, ValueError, KeyError):
        return False


def pcm_float(raw, sample_format):
    if sample_format == 1:
        return np.frombuffer(raw, dtype=np.int8).astype(np.float32) / 128.0
    if sample_format == 2:
        return np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    if sample_format == 3:
        data = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        values = data[:, 0] | (data[:, 1] << 8) | (data[:, 2] << 16)
        return ((values ^ 0x800000) - 0x800000).astype(np.float32) / 8388608.0
    if sample_format == 4:
        return np.frombuffer(raw, dtype='<i4').astype(np.float32) / 2147483648.0
    if sample_format == 5:
        return np.frombuffer(raw, dtype='<f4').copy()
    raise FmodError(f'Unsupported FMOD PCM format {sample_format}.')


class FmodAudioEngine:
    backend_name = 'FMOD'

    def __init__(self, max_voices=32):
        self.max_voices = max(1, int(max_voices))
        self.library_path = None
        self.version = 0
        self._lib = None
        self.system = ctypes.c_void_p()
        self._initialized = False
        self._lock = threading.RLock()
        self._sounds = set()
        self._streams = set()
        self._voices = deque()
        self._update_stop = threading.Event()
        self._update_thread = None
        self._converter = None
        self._update_error = None
        self.mixer_sample_rate = 0
        self.dsp_buffer_length = 0

    def _bind(self):
        p, u, i, f = ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_float
        pp, pu, pi, pf = (ctypes.POINTER(t) for t in (p, u, i, f))
        clock = ctypes.c_ulonglong
        pclock = ctypes.POINTER(clock)
        signatures = {
            'System_Create': [pp, u], 'System_Release': [p],
            'System_GetVersion': [p, pu], 'System_SetOutput': [p, i],
            'System_SetDSPBufferSize': [p, u, i],
            'System_GetDSPBufferSize': [p, pu, pi],
            'System_GetSoftwareFormat': [p, pi, pi, pi],
            'System_Init': [p, i, u, p], 'System_Update': [p],
            'System_CreateSound': [p, p, u, p, pp],
            'System_PlaySound': [p, p, p, i, pp],
            'Sound_GetFormat': [p, pi, pi, pi, pi],
            'Sound_GetDefaults': [p, pf, pi], 'Sound_GetLength': [p, pu, u],
            'Sound_ReadData': [p, p, u, pu], 'Sound_SeekData': [p, u],
            'Sound_Lock': [p, u, u, pp, pp, pu, pu],
            'Sound_Unlock': [p, p, p, u, u], 'Sound_Release': [p],
            'Channel_IsPlaying': [p, pi], 'Channel_Stop': [p],
            'Channel_SetVolume': [p, f], 'Channel_SetPan': [p, f],
            'Channel_SetFrequency': [p, f], 'Channel_SetPaused': [p, i],
            'Channel_SetPosition': [p, u, u], 'Channel_GetPosition': [p, pu, u],
            'Channel_GetDSPClock': [p, pclock, pclock],
            'Channel_SetDelay': [p, clock, clock, i],
        }
        for name, arguments in signatures.items():
            function = getattr(self._lib, 'FMOD_' + name)
            function.argtypes = arguments
            function.restype = ctypes.c_int
            setattr(self, '_' + name, function)

    @staticmethod
    def _check(result, operation):
        if result:
            raise FmodError(f'FMOD {operation} failed ({result}).')

    def initialize(self):
        with self._lock:
            if self._initialized:
                if self._update_error:
                    raise self._update_error
                return self
            manifest_path, manifest = fmod_manifest()
            platform_key = _platform_key()
            try:
                entry = manifest['libraries'][platform_key]['core']
            except KeyError as error:
                raise FmodError(f'FMOD is not bundled for {platform_key}.') from error
            self.library_path = manifest_path.parent / platform_key / entry['filename']
            if hashlib.sha256(self.library_path.read_bytes()).hexdigest() != entry['sha256'].lower():
                raise FmodError('The bundled FMOD library failed its integrity check.')
            try:
                loader = ctypes.WinDLL if sys.platform.startswith('win') else ctypes.CDLL
                self._lib = loader(str(self.library_path))
                self._bind()
                self._check(self._System_Create(ctypes.byref(self.system), manifest['header_version']), 'System_Create')
                version = ctypes.c_uint()
                self._check(self._System_GetVersion(self.system, ctypes.byref(version)), 'System_GetVersion')
                self.version = int(version.value)
                if self.version != manifest['header_version']:
                    raise FmodError('The FMOD runtime version does not match its manifest.')
                self._check(self._System_SetDSPBufferSize(self.system, 256, 4), 'System_SetDSPBufferSize')
                self._check(self._System_Init(self.system, self.max_voices + 8, 0, None), 'System_Init')
                sample_rate, buffer_length = ctypes.c_int(), ctypes.c_uint()
                self._check(self._System_GetSoftwareFormat(self.system, ctypes.byref(sample_rate), None, None), 'System_GetSoftwareFormat')
                self._check(self._System_GetDSPBufferSize(self.system, ctypes.byref(buffer_length), None), 'System_GetDSPBufferSize')
                self.mixer_sample_rate = int(sample_rate.value)
                self.dsp_buffer_length = int(buffer_length.value)
            except Exception:
                if self.system:
                    self._System_Release(self.system)
                    self.system = ctypes.c_void_p()
                self._lib = None
                raise
            self._initialized = True
            self._update_stop.clear()
            self._update_error = None
            self._update_thread = threading.Thread(target=self._update, name='FMOD Update', daemon=True)
            self._update_thread.start()
            return self

    def _update(self):
        while not self._update_stop.wait(0.005):
            with self._lock:
                if self.system:
                    result = self._System_Update(self.system)
                    if result:
                        self._update_error = FmodError(f'FMOD System_Update failed ({result}).')
                        return

    def _create_sound(self, path=None, data=None, decode=False):
        self.initialize()
        mode = FMOD_LOOP_OFF | FMOD_CREATESAMPLE | FMOD_ACCURATETIME
        if decode:
            mode |= FMOD_OPENONLY
        info = None
        if data is not None:
            if not data:
                raise FmodError('Cannot load an empty audio payload.')
            payload = ctypes.create_string_buffer(bytes(data))
            info = FmodCreateSoundInfo()
            info.cbsize = ctypes.sizeof(info)
            info.length = len(data)
            mode |= FMOD_OPENMEMORY
        else:
            payload = ctypes.create_string_buffer(str(Path(path).resolve()).encode('utf-8'))
        handle = ctypes.c_void_p()
        with self._lock:
            self._check(self._System_CreateSound(self.system, payload, mode, ctypes.byref(info) if info else None, ctypes.byref(handle)), 'System_CreateSound')
        return handle

    def _load(self, cls, path=None, data=None, decode=False):
        with self._lock:
            handle = self._create_sound(path, data, decode)
            try:
                sound = cls(self, handle, path) if path is not None and cls is not FmodSound else cls(self, handle)
                (self._sounds if cls is FmodSound else self._streams).add(sound)
                return sound
            except Exception:
                self._Sound_Release(handle)
                raise

    def load_sound(self, path):
        return self._load(FmodSound, path=path)

    def load_sound_bytes(self, data):
        return self._load(FmodSound, data=data)

    def load_stream(self, path, prescan=True):
        return self._load(FmodMusicStream, path=path)

    def load_decode_stream(self, path, prescan=False):
        return self._load(FmodDecodeStream, path=path, decode=True)

    def convert_audio(self, *args, **kwargs):
        with self._lock:
            if self._converter is None:
                self._converter = BassAudioEngine()
            converter = self._converter
        return converter.convert_audio(*args, **kwargs)

    def shutdown(self):
        self._update_stop.set()
        if self._update_thread is not None:
            self._update_thread.join()
            self._update_thread = None
        with self._lock:
            for stream in list(self._streams):
                stream.free()
            for sound in list(self._sounds):
                sound.free()
            self._voices.clear()
            if self.system:
                self._System_Release(self.system)
                self.system = ctypes.c_void_p()
            self._initialized = False
            self._lib = None
            if self._converter is not None:
                self._converter.shutdown()
                self._converter = None


class FmodChannel:
    def __init__(self, engine, handle):
        self.engine = engine
        self.handle = handle

    def get_busy(self):
        with self.engine._lock:
            if not self.handle or not self.engine.system:
                return False
            playing = ctypes.c_int()
            result = self.engine._Channel_IsPlaying(self.handle, ctypes.byref(playing))
            return result == 0 and bool(playing.value)

    def stop(self):
        with self.engine._lock:
            if self.handle and self.engine.system:
                self.engine._Channel_Stop(self.handle)
            self.handle = ctypes.c_void_p()

    def set_volume(self, left, right=None):
        if right is None:
            return self.set_volume_pan(left)
        left, right = max(0.0, float(left)), max(0.0, float(right))
        volume = max(left, right)
        pan = (1.0 - left / right if right >= left else right / left - 1.0) if volume else 0.0
        self.set_volume_pan(volume, pan)

    def set_volume_pan(self, volume, pan=0.0):
        with self.engine._lock:
            if not self.handle or not self.engine.system:
                return
            self.engine._check(self.engine._Channel_SetVolume(self.handle, max(0.0, float(volume))), 'Channel_SetVolume')
            self.engine._check(self.engine._Channel_SetPan(self.handle, max(-1.0, min(1.0, float(pan)))), 'Channel_SetPan')


class FmodPcmSound:
    def __init__(self, engine, handle):
        self.engine = engine
        self.handle = handle
        sound_type, sample_format, channels, bits = (ctypes.c_int() for _ in range(4))
        engine._check(engine._Sound_GetFormat(handle, ctypes.byref(sound_type), ctypes.byref(sample_format), ctypes.byref(channels), ctypes.byref(bits)), 'Sound_GetFormat')
        frequency, priority = ctypes.c_float(), ctypes.c_int()
        engine._check(engine._Sound_GetDefaults(handle, ctypes.byref(frequency), ctypes.byref(priority)), 'Sound_GetDefaults')
        self.sample_rate = int(round(frequency.value))
        self.original_frequency = float(frequency.value)
        self.channels = int(channels.value)
        self.sample_format = int(sample_format.value)
        self.bytes_per_sample = int(bits.value) // 8
        if self.sample_rate <= 0 or self.channels <= 0 or self.bytes_per_sample != {1: 1, 2: 2, 3: 3, 4: 4, 5: 4}.get(self.sample_format):
            raise FmodError('FMOD returned an unsupported PCM format.')
        length = ctypes.c_uint()
        engine._check(engine._Sound_GetLength(handle, ctypes.byref(length), FMOD_TIMEUNIT_PCM), 'Sound_GetLength')
        self.frame_length = int(length.value)

    def get_length_ms(self):
        return self.frame_length * 1000.0 / self.sample_rate

    def free(self):
        with self.engine._lock:
            if self.handle and self.engine.system:
                self.engine._Sound_Release(self.handle)
            self.handle = ctypes.c_void_p()
            self.engine._sounds.discard(self)
            self.engine._streams.discard(self)


class FmodSound(FmodPcmSound):
    def __init__(self, engine, handle, pitch_ratio=1.0, owner=None):
        super().__init__(engine, handle)
        self.volume = 1.0
        self.pitch_ratio = max(0.01, float(pitch_ratio))
        self.owner = owner

    def set_volume(self, volume):
        self.volume = max(0.0, float(volume))

    def play(self, offset_ms=0.0, dsp_start=None, dsp_end=0):
        with self.engine._lock:
            if not self.handle or not self.engine.system or (self.owner is not None and not self.owner.handle):
                return None
            self.engine._voices = deque(voice for voice in self.engine._voices if voice.get_busy())
            while len(self.engine._voices) >= self.engine.max_voices:
                self.engine._voices.popleft().stop()
            handle = ctypes.c_void_p()
            self.engine._check(self.engine._System_PlaySound(self.engine.system, self.handle, None, 1, ctypes.byref(handle)), 'System_PlaySound')
            channel = FmodChannel(self.engine, handle)
            try:
                channel.set_volume(self.volume)
                self.engine._check(self.engine._Channel_SetFrequency(handle, self.original_frequency * self.pitch_ratio), 'Channel_SetFrequency')
                frame = max(0, int(round(float(offset_ms) * self.sample_rate / 1000.0)))
                if frame >= self.frame_length:
                    channel.stop()
                    return None
                self.engine._check(self.engine._Channel_SetPosition(handle, frame, FMOD_TIMEUNIT_PCM), 'Channel_SetPosition')
                if dsp_start is not None:
                    self.engine._check(self.engine._Channel_SetDelay(handle, max(0, int(dsp_start)), max(0, int(dsp_end)), 1), 'Channel_SetDelay')
                self.engine._check(self.engine._Channel_SetPaused(handle, 0), 'Channel_SetPaused')
            except Exception:
                channel.stop()
                raise
            self.engine._voices.append(channel)
            return channel

    def create_variant(self, pitch_ratio):
        with self.engine._lock:
            variant = FmodSound(self.engine, self.handle, pitch_ratio, self.owner or self)
            variant.volume = self.volume
            return variant

    def free(self):
        if self.owner is None:
            super().free()
        else:
            self.handle = ctypes.c_void_p()


class FmodPlaybackClock:
    def __init__(self):
        self.reset(0.0, 0.0)

    def reset(self, position_ms, now):
        self.position_ms = float(position_ms)
        self.last_tick = float(now)
        self.last_raw_ms = float(position_ms)
        self.last_raw_tick = float(now)

    def advance(self, raw_position_ms, now, speed):
        elapsed_ms = max(0.0, (now - self.last_tick) * 1000.0)
        advance_ms = elapsed_ms * speed
        position_ms = self.position_ms + advance_ms
        if raw_position_ms != self.last_raw_ms:
            observation_ms = max(0.0, (now - self.last_raw_tick) * 1000.0)
            weight = -math.expm1(-observation_ms / 200.0)
            correction_ms = (raw_position_ms - position_ms) * weight
            limit_ms = advance_ms * 0.1
            position_ms += max(-limit_ms, min(limit_ms, correction_ms))
            self.last_raw_ms = raw_position_ms
            self.last_raw_tick = now
        position_ms = min(position_ms, raw_position_ms + 50.0 * speed)
        self.position_ms = max(self.position_ms, position_ms)
        self.last_tick = now
        return self.position_ms


class FmodMusicStream(FmodPcmSound):
    def __init__(self, engine, handle, path):
        super().__init__(engine, handle)
        self.path = Path(path)
        self.volume = 1.0
        self.speed = 1.0
        self.channel = None
        self._position_frame = 0
        self._playback_clock = FmodPlaybackClock()
        self._dsp_start = 0
        self._dsp_position_ms = 0.0
        self._note_channels = []

    def _get_parent_clock(self):
        parent_clock = ctypes.c_ulonglong()
        self.engine._check(self.engine._Channel_GetDSPClock(self.channel.handle, None, ctypes.byref(parent_clock)), 'Channel_GetDSPClock')
        return int(parent_clock.value)

    def _schedule_start(self):
        self._dsp_start = self._get_parent_clock() + self.engine.dsp_buffer_length * 2
        self._dsp_position_ms = self._position_frame * 1000.0 / self.sample_rate
        self.engine._check(self.engine._Channel_SetDelay(self.channel.handle, self._dsp_start, 0, 1), 'Channel_SetDelay')

    def play_sound_at(self, sound, position_ms, end_position_ms=None, offset_ms=0.0):
        with self.engine._lock:
            if not self.get_busy():
                return None
            ticks_per_ms = self.engine.mixer_sample_rate / (1000.0 * self.speed)
            start = self._dsp_start + int(round((float(position_ms) - self._dsp_position_ms) * ticks_per_ms))
            end = 0 if end_position_ms is None else self._dsp_start + int(round((float(end_position_ms) - self._dsp_position_ms) * ticks_per_ms))
            parent_clock = self._get_parent_clock()
            if end_position_ms is not None and end <= parent_clock:
                return None
            late_ms = max(0, parent_clock - start) * 1000.0 / self.engine.mixer_sample_rate
            offset_ms += late_ms * sound.pitch_ratio
            channel = sound.play(offset_ms=offset_ms, dsp_start=max(start, parent_clock), dsp_end=end)
            self._note_channels = [voice for voice in self._note_channels if voice.get_busy()]
            if channel:
                self._note_channels.append(channel)
            return channel

    def set_volume(self, volume):
        with self.engine._lock:
            self.volume = max(0.0, float(volume))
            if self.channel and self.channel.get_busy():
                self.channel.set_volume(self.volume)

    def set_speed(self, speed):
        speed = float(speed)
        if speed <= 0:
            raise ValueError('speed must be greater than zero')
        with self.engine._lock:
            position_ms = self.get_playback_position_ms()
            if self.channel and self.channel.get_busy():
                parent_clock = self._get_parent_clock()
                self._dsp_position_ms += max(0, parent_clock - self._dsp_start) * 1000.0 * self.speed / self.engine.mixer_sample_rate
                self._dsp_start = max(self._dsp_start, parent_clock)
                self.engine._check(self.engine._Channel_SetFrequency(self.channel.handle, self.original_frequency * speed), 'Channel_SetFrequency')
                for voice in self._note_channels:
                    voice.stop()
                self._note_channels.clear()
            self.speed = speed
            self._playback_clock.reset(position_ms, time.perf_counter())

    def seek_ms(self, position_ms):
        with self.engine._lock:
            if not self.handle or not self.engine.system:
                return False
            frame = max(0, int(round(float(position_ms) * self.sample_rate / 1000.0)))
            self._position_frame = min(frame, self.frame_length)
            if frame >= self.frame_length:
                self.stop()
                self._position_frame = self.frame_length
                return False
            if self.channel and self.channel.get_busy():
                for voice in self._note_channels:
                    voice.stop()
                self._note_channels.clear()
                self.engine._check(self.engine._Channel_SetPaused(self.channel.handle, 1), 'Channel_SetPaused')
                self.engine._check(self.engine._Channel_SetPosition(self.channel.handle, frame, FMOD_TIMEUNIT_PCM), 'Channel_SetPosition')
                self._schedule_start()
                self.engine._check(self.engine._Channel_SetPaused(self.channel.handle, 0), 'Channel_SetPaused')
            self._playback_clock.reset(frame * 1000.0 / self.sample_rate, time.perf_counter())
            return True

    def play_from_ms(self, position_ms=0.0):
        with self.engine._lock:
            self.stop()
            if not self.seek_ms(position_ms):
                return False
            handle = ctypes.c_void_p()
            self.engine._check(self.engine._System_PlaySound(self.engine.system, self.handle, None, 1, ctypes.byref(handle)), 'System_PlaySound')
            self.channel = FmodChannel(self.engine, handle)
            try:
                self.channel.set_volume(self.volume)
                self.engine._check(self.engine._Channel_SetFrequency(handle, self.original_frequency * self.speed), 'Channel_SetFrequency')
                self.engine._check(self.engine._Channel_SetPosition(handle, self._position_frame, FMOD_TIMEUNIT_PCM), 'Channel_SetPosition')
                self._schedule_start()
                self.engine._check(self.engine._Channel_SetPaused(handle, 0), 'Channel_SetPaused')
                self._playback_clock.reset(self._position_frame * 1000.0 / self.sample_rate, time.perf_counter())
            except Exception:
                self.stop()
                raise
            return True

    def stop(self):
        with self.engine._lock:
            for voice in self._note_channels:
                voice.stop()
            self._note_channels.clear()
            if self.channel:
                self._position_frame = int(round(self.get_position_ms() * self.sample_rate / 1000.0))
                self.channel.stop()
                self.channel = None

    def get_busy(self):
        with self.engine._lock:
            return self.channel is not None and self.channel.get_busy()

    def get_position_ms(self):
        with self.engine._lock:
            if self.channel and self.channel.get_busy():
                frame = ctypes.c_uint()
                if self.engine._Channel_GetPosition(self.channel.handle, ctypes.byref(frame), FMOD_TIMEUNIT_PCM) == 0:
                    self._position_frame = int(frame.value)
            elif self.channel is not None:
                self._position_frame = self.frame_length
            return self._position_frame * 1000.0 / self.sample_rate

    def get_playback_position_ms(self):
        with self.engine._lock:
            raw_position_ms = self.get_position_ms()
            now = time.perf_counter()
            if not self.get_busy():
                self._playback_clock.reset(raw_position_ms, now)
                return raw_position_ms
            position_ms = self._playback_clock.advance(raw_position_ms, now, self.speed)
            return min(self.get_length_ms(), position_ms)

    def get_visualizer_snapshot(self, duration=0.031, include_rms=True):
        with self.engine._lock:
            if not self.handle or not self.engine.system or not self.get_busy():
                return None
            position = int(round(self.get_position_ms() * self.sample_rate / 1000.0))
            frame_count = max(2048, int(self.sample_rate * max(0.001, float(duration))))
            start = max(0, position - frame_count)
            count = min(frame_count, self.frame_length - start)
            if count <= 0:
                return None
            frame_size = self.channels * self.bytes_per_sample
            sample_format = self.sample_format
            channels = self.channels
            frequency = self.original_frequency
            first, second = ctypes.c_void_p(), ctypes.c_void_p()
            first_size, second_size = ctypes.c_uint(), ctypes.c_uint()
            self.engine._check(self.engine._Sound_Lock(self.handle, start * frame_size, count * frame_size, ctypes.byref(first), ctypes.byref(second), ctypes.byref(first_size), ctypes.byref(second_size)), 'Sound_Lock')
            try:
                raw = ctypes.string_at(first, first_size.value)
                if second_size.value:
                    raw += ctypes.string_at(second, second_size.value)
            finally:
                self.engine._Sound_Unlock(self.handle, first, second, first_size, second_size)
        mono = pcm_float(raw, sample_format).reshape(-1, channels).mean(axis=1, dtype=np.float32)
        window = np.zeros(2048, dtype=np.float32)
        count = min(2048, mono.size)
        window[-count:] = mono[-count:]
        window -= window.mean()
        spectrum = (np.abs(np.fft.rfft(window))[:1024] / 1024.0).astype(np.float32)
        rms = float(np.sqrt(np.mean(mono * mono))) if include_rms else 0.0
        return spectrum.tobytes(), frequency, rms

    def get_fft(self):
        snapshot = self.get_visualizer_snapshot(include_rms=False)
        return np.frombuffer(snapshot[0], dtype=np.float32) if snapshot else None

    def get_rms_level(self, duration=0.031):
        snapshot = self.get_visualizer_snapshot(duration)
        return snapshot[2] if snapshot else 0.0

    def free(self):
        with self.engine._lock:
            self.stop()
            super().free()


class FmodDecodeStream(FmodPcmSound):
    def __init__(self, engine, handle, path):
        super().__init__(engine, handle)
        self.path = Path(path)
        self.finished = False

    def read_float_frames(self, frame_count):
        with self.engine._lock:
            if self.finished or not self.handle or not self.engine.system:
                return None, 0
            frame_size = self.channels * self.bytes_per_sample
            byte_count = max(1, int(frame_count)) * frame_size
            buffer = ctypes.create_string_buffer(byte_count)
            read = ctypes.c_uint()
            result = self.engine._Sound_ReadData(self.handle, buffer, byte_count, ctypes.byref(read))
            if result not in (0, 16, 17):
                self.engine._check(result, 'Sound_ReadData')
            if read.value > byte_count or read.value % frame_size:
                raise FmodError('FMOD returned incomplete PCM frames.')
            self.finished = result != 0 or read.value == 0
            if not read.value:
                return None, 0
            samples = pcm_float(memoryview(buffer).cast('B')[:read.value], self.sample_format)
            return samples, int(samples.size)

    def seek_ms(self, position_ms):
        with self.engine._lock:
            if not self.handle or not self.engine.system:
                return False
            frame = max(0, int(round(float(position_ms) * self.sample_rate / 1000.0)))
            if frame >= self.frame_length:
                self.finished = True
                return False
            self.engine._check(self.engine._Sound_SeekData(self.handle, frame), 'Sound_SeekData')
            self.finished = False
            return True
