"""Window placement on actual Windows monitor work areas; no fullscreen mode."""
import ctypes as C
from ctypes import wintypes as W
import subprocess
import threading
import time
from jarvis.domain.errors import ServiceError
from jarvis.infrastructure.system.paths import ROOT
from jarvis.presentation.desktop.window import browser_path,find_window,style_window

MAP_TITLE="JARVIS · 地图"

def displays():
    class Info(C.Structure):
        _fields_=[("size",W.DWORD),("monitor",W.RECT),("work",W.RECT),("flags",W.DWORD)]
    result=[];user=C.windll.user32
    callback=C.WINFUNCTYPE(W.BOOL,W.HANDLE,W.HDC,C.POINTER(W.RECT),W.LPARAM)
    user.GetMonitorInfoW.argtypes=[W.HANDLE,C.POINTER(Info)]
    @callback
    def visit(handle,dc,rect,param):
        info=Info();info.size=C.sizeof(info)
        if user.GetMonitorInfoW(handle,C.byref(info)):
            r=info.work
            result.append({"id":len(result),"left":r.left,"top":r.top,"width":r.right-r.left,"height":r.bottom-r.top,"primary":bool(info.flags&1)})
        return True
    user.EnumDisplayMonitors(None,None,visit,0)
    return result

def find_map_window(origin=None,include_hidden=False):
    user=C.windll.user32;found=[]
    user.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,C.c_int]
    user.IsWindowVisible.argtypes=[W.HWND]
    callback=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    @callback
    def visit(handle,param):
        title=C.create_unicode_buffer(256);user.GetWindowTextW(handle,title,256)
        if (include_hidden or user.IsWindowVisible(handle)) and title.value.startswith(MAP_TITLE if origin is None else MAP_TITLE+" · "+origin.rsplit(":",1)[-1]):found.append(handle)
        return True
    user.EnumWindows(visit,0)
    return found[0] if found else None

def choose_display(items,target=None,direction=None,source_id=None):
    if not items:raise ServiceError("无法读取显示器信息。")
    if target is not None:
        if isinstance(target,bool) or not isinstance(target,int):raise ServiceError("目标显示器编号无效。")
        selected=next((m for m in items if m["id"]==target),None)
        if selected is None:raise ServiceError("目标显示器已断开。")
        return selected
    primary=next((m for m in items if m["id"]==source_id),None) or next((m for m in items if m["primary"]),items[0]);others=[m for m in items if m["id"]!=primary["id"]]
    if direction in ("left","right","up","down"):
        horizontal=direction in ("left","right");axis="left" if horizontal else "top";extent="width" if horizontal else "height"
        center=primary[axis]+primary[extent]/2;sign=1 if direction in ("right","down") else -1
        side=[m for m in others if (m[axis]+m[extent]/2-center)*sign>0]
        if side:return min(side,key=lambda m:abs(m[axis]+m[extent]/2-center))
    return others[0] if others else primary

class MapWindows:
    def __init__(self):
        self.lock=threading.RLock();self.generation=0;self.handle=None;self.closed=False;self.error="";self.worker=None;self.origin=None;self.missing_since=None;self.target=None;self.visible=False
    def displays(self):return displays()
    def open(self,origin,target=None,direction=None):
        items=displays();source_id=None;handle=find_window()
        if handle:
            rect=W.RECT();user=C.windll.user32;user.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)]
            if user.GetWindowRect(handle,C.byref(rect)):
                def overlap(m):return max(0,min(rect.right,m["left"]+m["width"])-max(rect.left,m["left"]))*max(0,min(rect.bottom,m["top"]+m["height"])-max(rect.top,m["top"]))
                if items:source_id=max(items,key=overlap)["id"]
        selected=choose_display(items,target,direction,source_id)
        with self.lock:
            self.closed=False;self.generation+=1;generation=self.generation;self.error="";self.origin=origin;self.missing_since=None;self.target=selected;self.visible=False
        def launch():
            try:
                handle=find_map_window(origin,include_hidden=True)
                if not handle:
                    # Dark mode is a process-wide Chromium flag. A separate profile
                    # avoids reusing an older light-mode map process while its
                    # independently owned windows may still be open.
                    profile=ROOT/"cache/map-browser-dark";profile.mkdir(parents=True,exist_ok=True)
                    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
                    subprocess.Popen([str(browser_path()),"--app="+origin+"/map","--user-data-dir="+str(profile),
                        "--disk-cache-dir="+str(profile/"disk-cache"),"--crash-dumps-dir="+str(ROOT/"tmp"),
                        "--no-first-run","--no-default-browser-check","--disable-extensions","--disable-session-crashed-bubble","--disable-background-mode","--force-dark-mode","--window-size=1280,820","--window-position=-32000,-32000",
                        "--disable-background-timer-throttling","--disable-renderer-backgrounding","--disable-features=CalculateNativeWinOcclusion"],
                        cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,startupinfo=startup)
                    deadline=time.monotonic()+18
                    while not handle and time.monotonic()<deadline:
                        with self.lock:
                            if self.closed or generation!=self.generation:return
                        time.sleep(.1);handle=find_map_window(origin,include_hidden=True)
                if not handle:raise ServiceError("独立地图窗口未能打开。")
                style_window(handle)
                with self.lock:
                    if self.closed or generation!=self.generation:
                        self._close(handle);return
                    self.handle=handle
                # Keep the prepared browser off all monitors until the source has dispatched its particles.
                user=C.windll.user32;user.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
                user.SetWindowPos(handle,None,-32000,-32000,min(selected["width"],1280),min(selected["height"],820),0x0014)
            except Exception as exc:
                with self.lock:self.error=str(exc) if isinstance(exc,ServiceError) else "独立地图窗口启动失败。"
        self.worker=threading.Thread(target=launch,daemon=True,name="jarvis-map-window");self.worker.start()
        source=next((m for m in items if m["id"]==source_id),None) or next((m for m in items if m["primary"]),items[0])
        dx=selected["left"]+selected["width"]/2-source["left"]-source["width"]/2
        dy=selected["top"]+selected["height"]/2-source["top"]-source["height"]/2
        length=max(1,(dx*dx+dy*dy)**.5)
        vector={"x":dx/length,"y":-dy/length} if dx or dy else {"x":0 if direction in ("up","down") else -1 if direction=="left" else 1,"y":1 if direction=="up" else -1 if direction=="down" else 0}
        return {"display":selected,"multiple_displays":len(items)>1,"direction":vector}
    def reveal(self):
        with self.lock:
            handle=find_map_window(self.origin,include_hidden=True) if self.origin else None
            if handle:self.handle=handle
            if not self.handle or not self.target:raise ServiceError("目标屏幕尚未准备好。")
            m=self.target;user=C.windll.user32
            user.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
            user.ShowWindow.argtypes=[W.HWND,C.c_int];user.ShowWindow(self.handle,9)
            width=min(m["width"],max(640,int(m["width"]*.92)));height=min(m["height"],max(480,int(m["height"]*.90)))
            user.SetWindowPos(self.handle,None,m["left"]+(m["width"]-width)//2,m["top"]+(m["height"]-height)//2,width,height,0x0040)
            self.visible=True

    def status(self):
        with self.lock:
            user=C.windll.user32;user.IsWindow.argtypes=[W.HWND]
            if self.handle and not user.IsWindow(self.handle):
                replacement=find_map_window(self.origin,include_hidden=True)
                if replacement:self.handle=replacement;self.missing_since=None
                elif self.missing_since is None:self.missing_since=time.monotonic()
            else:self.missing_since=None
            return {"visible":self.visible,"error":self.error,"closed":self.missing_since is not None and time.monotonic()-self.missing_since>2}
    @staticmethod
    def _close(handle):
        user=C.windll.user32;user.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
        user.PostMessageW(handle,0x0010,0,0)
    def close(self):
        with self.lock:
            self.closed=True;self.generation+=1;handle=self.handle;self.handle=None
        if self.origin:handle=find_map_window(self.origin,include_hidden=True) or handle
        if handle:self._close(handle)
