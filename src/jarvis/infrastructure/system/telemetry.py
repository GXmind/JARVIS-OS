"""Actual Windows CPU/memory counters, sampled at most once per second."""
import ctypes as C
from ctypes import wintypes as W
import os
import time

class MemoryStatus(C.Structure):
    _fields_=[("length",W.DWORD),("load",W.DWORD),("total",C.c_ulonglong),("available",C.c_ulonglong),
              ("page_total",C.c_ulonglong),("page_available",C.c_ulonglong),
              ("virtual_total",C.c_ulonglong),("virtual_available",C.c_ulonglong),("extended",C.c_ulonglong)]

class Telemetry:
    def __init__(self):
        self.started=time.monotonic()
        self.previous=None
        self.last=0
        self.data={"cpu":None,"memory":None,"memory_used_gb":None,"memory_total_gb":None,
                   "uptime":0,"logical_cores":os.cpu_count()}
    def sample(self):
        now=time.monotonic()
        self.data["uptime"]=int(now-self.started)
        if now-self.last<1:return dict(self.data)
        self.last=now
        try:
            kernel=C.windll.kernel32
            idle,kernel_time,user=W.FILETIME(),W.FILETIME(),W.FILETIME()
            kernel.GetSystemTimes.argtypes=[C.POINTER(W.FILETIME)]*3
            if kernel.GetSystemTimes(C.byref(idle),C.byref(kernel_time),C.byref(user)):
                value=lambda t:(t.dwHighDateTime<<32)|t.dwLowDateTime
                current=(value(idle),value(kernel_time)+value(user))
                if self.previous and current[1]>self.previous[1]:
                    total=current[1]-self.previous[1]
                    used=total-(current[0]-self.previous[0])
                    self.data["cpu"]=round(max(0,min(100,used*100/total)),1)
                self.previous=current
            memory=MemoryStatus()
            memory.length=C.sizeof(memory)
            kernel.GlobalMemoryStatusEx.argtypes=[C.POINTER(MemoryStatus)]
            if kernel.GlobalMemoryStatusEx(C.byref(memory)):
                self.data.update(memory=int(memory.load),
                    memory_used_gb=round((memory.total-memory.available)/1024**3,1),
                    memory_total_gb=round(memory.total/1024**3,1))
        except (AttributeError,OSError):
            pass
        return dict(self.data)