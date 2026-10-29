"""Installed Chromium window and Windows lifecycle; no business orchestration."""
import logging
import os
from pathlib import Path
import subprocess
import time
import json
from jarvis.domain.errors import ServiceError
from jarvis.infrastructure.system.paths import ROOT

LOG=logging.getLogger("jarvis")

def browser_path():
    candidates=[
        Path(os.environ.get("PROGRAMFILES(X86)",r"C:\Program Files (x86)"))/"Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES",r"C:\Program Files"))/"Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES",r"C:\Program Files"))/"Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ServiceError("需要已安装的 Microsoft Edge 或 Chrome 才能打开星空界面。")


def native_drag(handle):
    import ctypes
    from ctypes import wintypes as W
    user=ctypes.windll.user32
    user.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
    user.ReleaseCapture()
    user.PostMessageW(handle,0x00A1,2,0)


def find_window():
    import ctypes as C
    from ctypes import wintypes as W
    user=C.windll.user32
    user.GetWindowTextW.argtypes=[W.HWND,W.LPWSTR,C.c_int]
    user.IsWindowVisible.argtypes=[W.HWND]
    found=[]
    callback=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    @callback
    def visit(handle,param):
        text=C.create_unicode_buffer(256)
        user.GetWindowTextW(handle,text,256)
        if user.IsWindowVisible(handle) and text.value.startswith("JARVIS · 星海"):
            found.append(handle)
        return True
    user.EnumWindows(visit,0)
    return found[0] if found else None


def style_window(handle):
    import ctypes as C
    from ctypes import wintypes as W
    user=C.windll.user32
    user.GetWindowLongW.argtypes=[W.HWND,C.c_int]
    user.GetWindowLongW.restype=C.c_long
    user.SetWindowLongW.argtypes=[W.HWND,C.c_int,C.c_long]
    user.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
    style=user.GetWindowLongW(handle,-16)
    user.SetWindowLongW(handle,-16,style & ~0x00C00000)
    user.SetWindowPos(handle,None,0,0,0,0,0x0027)
    try:
        dwm=C.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes=[W.HWND,W.DWORD,C.c_void_p,W.DWORD]
        # Chromium draws part of its own frame; --force-dark-mode handles it.
        # Windows 11 additionally supports suppressing the DWM outline. Older
        # systems return E_INVALIDARG and keep the normal resizable frame.
        for attribute,value in ((20,1),(34,0xFFFFFFFE),(35,0x00100703)):
            color=W.DWORD(value)
            dwm.DwmSetWindowAttribute(handle,attribute,C.byref(color),C.sizeof(color))
    except Exception:
        pass


def run(state,server,config_error=None):
    if config_error:
        state.notify("配置无效，暂以模拟模式启动。按 F2 修正设置。",True,20)
    server.start()
    profile=ROOT/"cache/space-browser"
    profile.mkdir(parents=True,exist_ok=True)
    process=None
    try:
        command=[str(browser_path()),"--app="+server.origin,
                 "--user-data-dir="+str(profile),"--disk-cache-dir="+str(profile/"disk-cache"),
                 "--crash-dumps-dir="+str(ROOT/"tmp"),"--no-first-run","--no-default-browser-check",
                 "--disable-background-mode","--force-dark-mode","--disable-extensions","--disable-session-crashed-bubble",
                 "--disable-features=msEdgeSidebarV2,msEdgeShoppingAssistant",
                 "--window-size=1380,840","--window-position=100,70"]
        process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        (ROOT/"tmp/space_process.json").write_text(json.dumps({"python":os.getpid(),"browser":process.pid,"port":server.port}),encoding="utf-8")
        state.weather.snapshot()
        LOG.info("space_desktop_started")
        launched=time.monotonic()
        while not state.closed.wait(.2):
            if not state.window_handle:
                state.window_handle=find_window()
                if state.window_handle:
                    style_window(state.window_handle)
            if state.window_handle:
                import ctypes
                if not ctypes.windll.user32.IsWindow(state.window_handle):
                    replacement=find_window()
                    if replacement:state.window_handle=replacement
                    else:
                        LOG.info("space_exit_reason window_closed")
                        break
            if not state.connected and time.monotonic()-launched>60:
                raise ServiceError("星空窗口未能连接，请检查已安装的 Edge。")
        return 0
    finally:
        state.closed.set()
        if state.window_handle:
            import ctypes
            ctypes.windll.user32.PostMessageW(state.window_handle,0x0010,0,0)
        if process:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
        server.close()
        LOG.info("space_desktop_closed")
