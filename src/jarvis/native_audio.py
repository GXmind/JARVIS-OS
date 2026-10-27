"""Dependency-free Windows MME fallback behind the raw-stream adapter interface.

waveIn uses four reusable buffers. waveOut writes bounded blocks. Both execute
outside the GUI thread. No ctypes callback enters Python from a driver thread.
"""
import ctypes as C
from ctypes import wintypes as W
import os
import threading
import time
from types import SimpleNamespace

from .api import ServiceError

DONE = 1
MAPPER = 0xFFFFFFFF

class WaveFormat(C.Structure):
    _pack_ = 1
    _fields_ = [("format", W.WORD), ("channels", W.WORD), ("rate", W.DWORD),
                ("byte_rate", W.DWORD), ("align", W.WORD), ("bits", W.WORD), ("extra", W.WORD)]

class Header(C.Structure):
    _fields_ = [("data", C.c_void_p), ("length", W.DWORD), ("recorded", W.DWORD),
                ("user", C.c_size_t), ("flags", W.DWORD), ("loops", W.DWORD),
                ("next", C.c_void_p), ("reserved", C.c_size_t)]

class InputCaps(C.Structure):
    _fields_ = [("manufacturer", W.WORD), ("product", W.WORD), ("version", W.DWORD),
                ("name", W.WCHAR * 32), ("formats", W.DWORD), ("channels", W.WORD), ("reserved", W.WORD)]

class OutputCaps(C.Structure):
    _fields_ = InputCaps._fields_ + [("support", W.DWORD)]

def check(code):
    if code:
        raise ServiceError(f"Windows 音频接口错误 {code}；请检查设备、麦克风权限和采样率。")

class WinMM:
    def __init__(self):
        if os.name != "nt":
            raise ServiceError("系统音频回退仅适用于 Windows。")
        self.lib = C.WinDLL("winmm.dll")
        for prefix in ("waveIn", "waveOut"):
            open_fn = getattr(self.lib, prefix + "Open")
            open_fn.argtypes = [C.POINTER(C.c_void_p), W.UINT, C.POINTER(WaveFormat), C.c_size_t, C.c_size_t, W.DWORD]
            open_fn.restype = W.UINT
            for suffix in ("PrepareHeader", "UnprepareHeader") + (("AddBuffer",) if prefix == "waveIn" else ("Write",)):
                fn = getattr(self.lib, prefix + suffix)
                fn.argtypes = [C.c_void_p, C.POINTER(Header), W.UINT]
                fn.restype = W.UINT
            for suffix in ("Reset", "Close") + (("Start", "Stop") if prefix == "waveIn" else ()):
                fn = getattr(self.lib, prefix + suffix)
                fn.argtypes = [C.c_void_p]
                fn.restype = W.UINT
            caps_type = InputCaps if prefix == "waveIn" else OutputCaps
            fn = getattr(self.lib, prefix + "GetDevCapsW")
            fn.argtypes = [C.c_size_t, C.POINTER(caps_type), W.UINT]
            fn.restype = W.UINT
            fn = getattr(self.lib, prefix + "GetNumDevs")
            fn.argtypes = []
            fn.restype = W.UINT
        self.rows = []
        default_ids = [-1, -1]
        for direction, prefix, caps_type in (("in", "waveIn", InputCaps), ("out", "waveOut", OutputCaps)):
            count = getattr(self.lib, prefix + "GetNumDevs")()
            if count:
                default_ids[0 if direction == "in" else 1] = len(self.rows)
                self.rows.append(self._row("系统默认麦克风" if direction == "in" else "系统默认扬声器",
                                           direction, MAPPER, 1 if direction == "in" else 2))
            for native_id in range(count):
                caps = caps_type()
                check(getattr(self.lib, prefix + "GetDevCapsW")(native_id, C.byref(caps), C.sizeof(caps)))
                self.rows.append(self._row(caps.name, direction, native_id, caps.channels))
        self.default = SimpleNamespace(device=tuple(default_ids))

    def _row(self, name, direction, native_id, channels):
        return {"name": name, "hostapi": 0, "max_input_channels": channels if direction == "in" else 0,
                "max_output_channels": channels if direction == "out" else 0,
                "default_samplerate": 44100, "native_id": native_id, "direction": direction}

    def query_devices(self):
        return self.rows

    def query_hostapis(self):
        return [{"name": "Windows MME 内置"}]

    def native_device(self, device, direction):
        if device is None:
            return MAPPER
        if not 0 <= device < len(self.rows) or self.rows[device]["direction"] != direction:
            raise ServiceError("设备编号不存在或方向错误，请刷新设备列表并重新选择。")
        return self.rows[device]["native_id"]

    def RawInputStream(self, **kwargs):
        return InputStream(self, **kwargs)

    def RawOutputStream(self, **kwargs):
        return OutputStream(self, **kwargs)

class BaseStream:
    def __init__(self, backend, samplerate, channels, dtype, device=None, blocksize=1024, callback=None):
        if dtype != "int16" or channels not in (1, 2):
            raise ServiceError("Windows 内置音频仅接受 16 位 PCM 单声道/双声道。")
        self.backend, self.callback = backend, callback
        self.lib = backend.lib
        self.device = device
        self.rate, self.channels, self.blocksize = int(samplerate), channels, blocksize
        self.format = WaveFormat(1, channels, self.rate, self.rate * channels * 2, channels * 2, 16, 0)
        self.handle = C.c_void_p()

class InputStream(BaseStream):
    def __enter__(self):
        self.stopped = threading.Event()
        self.buffers = []
        self.failure = None
        self.thread = None
        check(self.lib.waveInOpen(C.byref(self.handle), self.backend.native_device(self.device, "in"),
                                 C.byref(self.format), 0, 0, 0))
        try:
            for _ in range(4):
                data = C.create_string_buffer(self.blocksize * self.channels * 2)
                header = Header()
                header.data = C.addressof(data)
                header.length = C.sizeof(data)
                check(self.lib.waveInPrepareHeader(self.handle, C.byref(header), C.sizeof(header)))
                self.buffers.append((data, header))
                check(self.lib.waveInAddBuffer(self.handle, C.byref(header), C.sizeof(header)))
            check(self.lib.waveInStart(self.handle))
            self.thread = threading.Thread(target=self._pump, daemon=True, name="jarvis-winmm-input")
            self.thread.start()
            return self
        except Exception:
            self._cleanup()
            raise

    def _pump(self):
        try:
            while not self.stopped.wait(0.004):
                for data, header in self.buffers:
                    if header.flags & DONE:
                        size = header.recorded
                        if size:
                            self.callback(data.raw[:size], size // (self.channels * 2), None, False)
                        header.recorded = 0
                        if not self.stopped.is_set():
                            check(self.lib.waveInAddBuffer(self.handle, C.byref(header), C.sizeof(header)))
        except Exception as exc:
            self.failure = exc
            self.stopped.set()

    def _cleanup(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=3)
        if self.handle:
            self.lib.waveInStop(self.handle)
            self.lib.waveInReset(self.handle)
            for data, header in self.buffers:
                if header.recorded and self.callback:
                    self.callback(data.raw[:header.recorded], header.recorded // (self.channels * 2), None, False)
                self.lib.waveInUnprepareHeader(self.handle, C.byref(header), C.sizeof(header))
            self.lib.waveInClose(self.handle)
            self.handle = C.c_void_p()

    def __exit__(self, kind, value, traceback):
        self._cleanup()
        if self.failure and kind is None:
            raise self.failure

class OutputStream(BaseStream):
    """Keep multiple buffers queued so Windows never starves between small writes."""
    def __enter__(self):
        self.pending=[]
        self.completed_frames=0
        check(self.lib.waveOutOpen(C.byref(self.handle), self.backend.native_device(self.device, "out"),
                                  C.byref(self.format), 0, 0, 0))
        return self

    @property
    def pending_frames(self):
        return sum(header.length//(self.channels*2) for _,header in self.pending)

    def _release_first(self,wait=False):
        if not self.pending:return
        data,header=self.pending[0]
        deadline=time.monotonic()+8
        while not header.flags & DONE:
            if not wait:return
            if time.monotonic()>deadline:raise ServiceError("Windows 音频设备播放超时。")
            time.sleep(.002)
        check(self.lib.waveOutUnprepareHeader(self.handle,C.byref(header),C.sizeof(header)))
        self.pending.pop(0)
        self.completed_frames+=header.length//(self.channels*2)

    def write(self,block):
        while self.pending and self.pending[0][1].flags & DONE:self._release_first()
        if len(self.pending)>=4:self._release_first(True)
        data=C.create_string_buffer(block,len(block));header=Header()
        header.data,header.length=C.addressof(data),len(block)
        check(self.lib.waveOutPrepareHeader(self.handle,C.byref(header),C.sizeof(header)))
        try:check(self.lib.waveOutWrite(self.handle,C.byref(header),C.sizeof(header)))
        except Exception:
            self.lib.waveOutUnprepareHeader(self.handle,C.byref(header),C.sizeof(header));raise
        self.pending.append((data,header))
        return False

    def drain(self,progress=None):
        while self.pending:
            self._release_first(True)
            if progress:progress(self.completed_frames/self.rate)

    def abort(self):
        if self.handle:self.lib.waveOutReset(self.handle)

    def __exit__(self,kind,value,traceback):
        try:
            if kind is None:self.drain()
            else:self.abort()
        finally:
            self.lib.waveOutReset(self.handle)
            for data,header in self.pending:
                self.lib.waveOutUnprepareHeader(self.handle,C.byref(header),C.sizeof(header))
            self.pending=[]
            self.lib.waveOutClose(self.handle)
            self.handle=C.c_void_p()
