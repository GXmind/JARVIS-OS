"""Local desktop renderer: Python services + installed Chromium app window.

Only loopback is exposed. All API secrets remain in Python/.env.
"""
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import secrets
import subprocess
import threading
import time
from urllib.parse import urlsplit

from .api import CloudAPI, ServiceError
from .audio import Audio, devices
from .config import Settings, load_settings, save_settings
from .paths import ROOT
from .service import Conversation
from .storage import Store
from .weather import Weather
from .telemetry import Telemetry
from .presentation import lines_for_speech
from .city_data import city_context
from .navigation import NavigationBridge,map_config,fetch_proxy,proxy_authorized,SECRET_FIELDS

LOG=logging.getLogger("jarvis")
UI=Path(__file__).parent/"space_ui"

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

class DesktopState:
    def __init__(self,settings,store=None):
        self.settings=settings
        self.store=store or Store()
        sessions=self.store.sessions()
        self.sid=sessions[0][0] if sessions else self.store.new_session()
        self.conversation=Conversation(self.store)
        self.audio=Audio()
        self.lock=threading.RLock()
        self.busy=False
        self.activity="idle"
        self.kind=""
        self.subtitle=""
        self.presenting=False
        self.subtitle_until=0.0
        self.dialogue_until=0.0
        self.error=False
        self.closed=threading.Event()
        self.last_seen=time.monotonic()
        self.connected=False
        self.last_record=None
        self.revision=0
        self.window_handle=None
        self.worker_threads=set()
        self.weather=Weather(settings.WEATHER_CITY)
        self.telemetry=Telemetry()
        self.counts={"memories":0,"messages":0}
        self.counts_updated=0.0
        self.navigation=NavigationBridge()

    def notify(self,text,error=False,seconds=18):
        with self.lock:
            self.subtitle=text
            self.subtitle_until=time.monotonic()+seconds
            self.error=error
            self.revision+=1

    def snapshot(self):
        with self.lock:
            self.last_seen=time.monotonic()
            self.connected=True
            if time.monotonic()-self.counts_updated>5:
                with self.store.connect() as db:
                    self.counts={"memories":db.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
                                 "messages":db.execute("SELECT COUNT(*) FROM messages WHERE session_id=?",(self.sid,)).fetchone()[0]}
                self.counts_updated=time.monotonic()
            return {
                "navigation":self.navigation.snapshot(),"presenting":self.presenting,
                "telemetry":self.telemetry.sample(),
                "counts":dict(self.counts),
                "modules":{"asr":self.settings.ASR_MODE,"tts":self.settings.TTS_MODE,"model":self.settings.API_MODEL},
                "phase":"dialogue" if self.busy or time.monotonic()<self.dialogue_until else "initial",
                "activity":"listening" if self.audio.capture_active else self.activity,
                "level":self.audio.level,
                "capturing":self.audio.capture_active,
                "busy":self.busy,
                "subtitle":self.subtitle if time.monotonic()<self.subtitle_until else "",
                "error":self.error if time.monotonic()<self.subtitle_until else False,
                "mock":self.settings.CHAT_MODE=="mock",
                "revision":self.revision,
            }

    def dispatch(self,kind,fn):
        with self.lock:
            if self.busy:
                raise ServiceError("当前任务正在进行，请稍候；F8 可停止录音。")
            self.busy=True
            self.kind=kind
            self.activity="thinking" if kind=="reply" else "listening" if kind=="record" else "speaking"
            self.dialogue_until=time.monotonic()+20
        def worker():
            try:
                fn()
            except (ServiceError,ValueError) as exc:
                self.notify(str(exc),True)
            except Exception as exc:
                LOG.error("space_worker_failed category=%s",type(exc).__name__)
                self.notify("操作失败，请查看项目 logs 目录。",True)
            finally:
                with self.lock:
                    self.busy=False
                    self.activity="idle"
                    self.kind=""
                    self.dialogue_until=time.monotonic()+8
                    self.worker_threads.discard(threading.current_thread())
        thread=threading.Thread(target=worker,daemon=True,name="jarvis-space-"+kind)
        with self.lock:self.worker_threads.add(thread)
        thread.start()

    def wait_workers(self,seconds=2.0):
        deadline=time.monotonic()+seconds
        with self.lock:threads=list(self.worker_threads)
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(max(0,deadline-time.monotonic()))

    def _reply(self,text,settings):
        navigation=self.navigation.accept(text,settings.AMAP_CITY,settings.AMAP_DEFAULT_ORIGIN)
        if navigation:
            self.store.add_message(self.sid,"user",text)
            if navigation["action"]=="cancel":
                answer="已取消路线规划。"
            elif navigation["action"]=="await_origin":
                answer="您从哪里出发？可以说“从苏州站出发”，或在 F2 设置中保存常用出发地。"
                if not map_config(settings)["configured"]:
                    answer+=" 高德凭证也需在 F2 设置中填写。"
            elif not map_config(settings)["configured"]:
                answer="已收到地图请求。高德地图尚未配置；请在 F2 设置中填写 JS API Key 和配套安全密钥。"
            elif navigation["action"]=="route":
                answer="正在为您查询高德路线，中心能量体会在地图加载后展开。"
            else:
                answer="正在打开高德地图。"
            self.store.add_message(self.sid,"assistant",answer)
            self._speak_answer(answer,settings)
            return
        with self.lock:
            self.activity="thinking"
        answer,state=self.conversation.reply(self.sid,text,settings)
        self._speak_answer(answer,settings)

    def _speak_answer(self,answer,settings):
        self.presenting=True
        try:
            if settings.AUTO_SPEAK=="true" and settings.TTS_MODE!="off":
                with self.lock:self.activity="speaking"
                self.audio.prepare()
                try:self.audio.speak(answer,settings,on_line=lambda line:self.notify(line,seconds=30))
                except ServiceError:
                    if not self.audio.stop_event.is_set():raise
            else:
                self.audio.prepare()
                lines=lines_for_speech(answer)
                for i,line in enumerate(lines):
                    self.notify(line,seconds=20)
                    if i+1<len(lines) and self.audio.stop_event.wait(min(4,max(.7,len(line)/7))):break
        finally:self.presenting=False

    def navigation_result(self,values):
        event_id=int(values.get("id",0))
        text=str(values.get("text",""))[:1800]
        if not text:return
        def deliver():
            deadline=time.monotonic()+35
            while time.monotonic()<deadline:
                current=self.navigation.snapshot()
                if current["id"]!=event_id or current["action"] in ("close","cancel"):return
                with self.lock:
                    if not self.busy:
                        self.store.add_message(self.sid,"assistant",text)
                        self.dispatch("route-result",lambda:self._speak_answer(text,self.settings))
                        return
                if self.closed.wait(.15):return
        threading.Thread(target=deliver,daemon=True,name="jarvis-route-result").start()

    def _interrupt_presentation(self):
        with self.lock:interrupt=self.busy and self.presenting
        if not interrupt:return
        self.audio.stop()
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            with self.lock:
                if not self.busy:return
            if self.closed.wait(.025):return

    def send(self,text):
        text=str(text).strip()
        if not text or len(text)>20000:
            raise ServiceError("输入长度需为 1–20000 字。")
        self._interrupt_presentation()
        settings=self.settings
        self.dispatch("reply",lambda:self._reply(text,settings))

    def record(self):
        with self.lock:
            if self.busy and self.kind=="record":
                self.audio.stop()
                return
        self._interrupt_presentation()
        settings=self.settings
        if settings.ASR_MODE=="api":
            CloudAPI(settings).transcription_client()
        self.audio.prepare()
        def worker():
            self.last_record=self.audio.recording(settings)
            if settings.ASR_MODE=="api":
                with self.lock:
                    self.activity="thinking"
                text=CloudAPI(settings).transcribe(self.last_record)
                self._reply(text,settings)
            else:
                self.notify("录音已保存。按 Enter 输入文字，或按 F2 配置语音识别。",seconds=12)
        self.dispatch("record",worker)

    def config_public(self):
        values=asdict(self.settings)
        for secret in SECRET_FIELDS:
            values[secret]=""
        values["ASR_API_KEY_PRESENT"]=bool(self.settings.ASR_API_KEY)
        values["AMAP_JS_KEY_PRESENT"]=bool(self.settings.AMAP_JS_KEY)
        values["AMAP_SECURITY_JSCODE_PRESENT"]=bool(self.settings.AMAP_SECURITY_JSCODE)
        values["KEY_PRESENT"]=bool(self.settings.API_KEY)
        return values

    def config_save(self,values):
        with self.lock:
            if self.busy:
                raise ServiceError("请先结束当前录音或请求，再保存设置。")
            current=asdict(self.settings)
            for key in current:
                if key in values:
                    current[key]=str(values[key]).strip()
            for secret in SECRET_FIELDS:
                if not current[secret]:
                    current[secret]=getattr(self.settings,secret)
            candidate=Settings(**current).validated()
            save_settings(candidate)
            self.settings=candidate
            self.weather.reset(candidate.WEATHER_CITY)
            if candidate.AMAP_DEFAULT_ORIGIN and self.navigation.pending:
                self.navigation.accept("开始导航",candidate.AMAP_CITY,candidate.AMAP_DEFAULT_ORIGIN)
        self.notify("设置已保存。",seconds=5)

class DesktopServer:
    def __init__(self,state):
        self.state=state
        self.token=secrets.token_urlsafe(32)
        outer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass
            def respond(self,*args,**kwargs):
                try:return self._respond(*args,**kwargs)
                except (ConnectionError,OSError):
                    self.close_connection=True
            def _respond(self,status,body,mime="application/json; charset=utf-8"):
                if isinstance(body,(dict,list)):
                    body=json.dumps(body,ensure_ascii=False).encode("utf-8")
                elif isinstance(body,str):
                    body=body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type",mime)
                self.send_header("Content-Length",str(len(body)))
                self.send_header("Cache-Control","no-store")
                self.send_header("X-Content-Type-Options","nosniff")
                self.send_header("X-Frame-Options","DENY")
                amap=map_config(outer.state.settings)["configured"]
                if amap:
                    csp=("default-src 'self'; "
                         "img-src 'self' data: blob: https://*.amap.com https://*.autonavi.com http://*.amap.com http://*.autonavi.com; "
                         "style-src 'self' 'unsafe-inline' https://webapi.amap.com https://a.amap.com; "
                         "script-src 'self' 'unsafe-eval' 'nonce-"+outer.token+"' https://webapi.amap.com https://a.amap.com; "
                         # AMap creates inline bootstrap code and loads WebGLRender from this SDK host.
                         # Restrict external script elements to these provider hosts; event handlers remain forbidden.
                         "script-src-elem 'self' 'unsafe-inline' https://webapi.amap.com https://a.amap.com https://jsapi-service.amap.com https://jsapi.amap.com https://mapplugin.amap.com; "
                         "script-src-attr 'none'; "
                         "connect-src 'self' https://*.amap.com https://*.autonavi.com http://*.amap.com http://*.autonavi.com; "
                         "worker-src 'self' blob:; font-src 'self' data: https://*.amap.com; frame-ancestors 'none'")
                else:
                    csp=("default-src 'self'; img-src 'self' data:; style-src 'self'; "
                         "script-src 'self' 'nonce-"+outer.token+"'; connect-src 'self'; frame-ancestors 'none'")
                self.send_header("Content-Security-Policy",csp)
                if urlsplit(self.path).path=="/":
                    self.send_header("Set-Cookie","jarvis_map_gate="+outer.token+"; HttpOnly; SameSite=Strict; Path=/_AMapService")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):
                    pass
            def authorized(self):
                origin=self.headers.get("Origin")
                return (self.headers.get("X-Jarvis-Token")==outer.token
                        and (not origin or origin==outer.origin)
                        and self.headers.get("Host")==f"127.0.0.1:{outer.port}")
            def do_GET(self):
                path=urlsplit(self.path).path
                if path.startswith("/_AMapService/"):
                    if not proxy_authorized(self.headers,outer.token,outer.origin,outer.port):
                        self.respond(403,{"error":"Forbidden"})
                        return
                    try:
                        body,mime=fetch_proxy(path,urlsplit(self.path).query,outer.state.settings,outer.origin)
                        self.respond(200,body,mime)
                    except (ServiceError,ValueError) as exc:
                        self.respond(400,{"error":str(exc)})
                    return
                if path.startswith("/api/"):
                    if not self.authorized():
                        self.respond(403,{"error":"Forbidden"})
                        return
                    if path=="/api/state":
                        self.respond(200,outer.state.snapshot())
                    elif path=="/api/weather":
                        self.respond(200,outer.state.weather.snapshot())
                    elif path=="/api/map/config":
                        self.respond(200,map_config(outer.state.settings))
                    elif path=="/api/config":
                        self.respond(200,outer.state.config_public())
                    elif path=="/api/devices":
                        try:
                            self.respond(200,devices())
                        except ServiceError as exc:
                            self.respond(400,{"error":str(exc)})
                    else:
                        self.respond(404,{"error":"Not found"})
                    return
                files={"/":("index.html","text/html; charset=utf-8"),
                       "/scene.js":("scene.js","text/javascript; charset=utf-8"),
                       "/style.css":("style.css","text/css; charset=utf-8"),
                       "/visual.js":("visual.js","text/javascript; charset=utf-8"),
                       "/navigation.js":("navigation.js","text/javascript; charset=utf-8"),
                       "/city.js":("city.js","text/javascript; charset=utf-8"),
                       "/map_controls.js":("map_controls.js","text/javascript; charset=utf-8"),
                       "/places.js":("places.js","text/javascript; charset=utf-8")}
                if path.startswith("/vendor/"):
                    vendor=(UI/path.lstrip("/")).resolve()
                    allowed=(UI/"vendor").resolve()
                    if vendor.is_relative_to(allowed) and vendor.is_file() and vendor.suffix in (".js",".txt"):
                        self.respond(200,vendor.read_bytes(),"text/javascript; charset=utf-8" if vendor.suffix==".js" else "text/plain")
                    else:
                        self.respond(404,{"error":"Not found"})
                    return
                if path not in files:
                    self.respond(404,{"error":"Not found"})
                    return
                name,mime=files[path]
                text=(UI/name).read_text(encoding="utf-8")
                if name=="index.html":
                    text=text.replace("__TOKEN__",outer.token)
                self.respond(200,text,mime)
            def do_POST(self):
                if not self.authorized():
                    # Consume a bounded request body before closing so Windows does not reset the 403 response.
                    try:
                        size=int(self.headers.get("Content-Length","0"))
                        if 0<size<=100000:
                            self.connection.settimeout(2)
                            self.rfile.read(size)
                    except (ValueError,OSError):
                        pass
                    self.respond(403,{"error":"Forbidden"})
                    return
                try:
                    size=int(self.headers.get("Content-Length","0"))
                    if not 0<size<=100000:
                        raise ValueError("Invalid request size")
                    values=json.loads(self.rfile.read(size))
                    if not isinstance(values,dict):
                        raise ValueError("Invalid request")
                    action=urlsplit(self.path).path
                    if action=="/api/send":
                        outer.state.send(values.get("text",""))
                    elif action=="/api/record":
                        outer.state.record()
                    elif action=="/api/stop":
                        outer.state.audio.stop()
                    elif action=="/api/city/context":
                        result=city_context(values.get("path",[]),overview=values.get("overview") is True)
                        self.respond(200,result);return
                    elif action=="/api/navigation/result":
                        outer.state.navigation_result(values)
                    elif action=="/api/weather/live":
                        outer.state.weather.accept_live(values)
                    elif action=="/api/config":
                        outer.state.config_save(values)
                    elif action=="/api/close":
                        outer.state.closed.set()
                    elif action=="/api/drag":
                        if outer.state.window_handle:
                            native_drag(outer.state.window_handle)
                    else:
                        self.respond(404,{"error":"Not found"})
                        return
                    self.respond(200,{"ok":True})
                except (ServiceError,ValueError) as exc:
                    self.respond(400,{"error":str(exc)})
                except Exception as exc:
                    LOG.error("space_http_error category=%s",type(exc).__name__)
                    self.respond(500,{"error":"操作失败，请查看 logs 目录。"})
        self.http=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        self.http.daemon_threads=True
        self.port=self.http.server_port
        self.origin=f"http://127.0.0.1:{self.port}"
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True,name="jarvis-space-server")

    def start(self):
        self.thread.start()

    def close(self):
        self.state.closed.set()
        self.state.audio.stop()
        self.state.wait_workers(2.0)
        self.state.audio.close()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)

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
        dark=C.c_int(1)
        C.windll.dwmapi.DwmSetWindowAttribute(handle,20,C.byref(dark),C.sizeof(dark))
    except Exception:
        pass

def run(settings,config_error=None):
    state=DesktopState(settings)
    if config_error:
        state.notify("配置无效，暂以模拟模式启动。按 F2 修正设置。",True,20)
    server=DesktopServer(state)
    server.start()
    profile=ROOT/"cache/space-browser"
    profile.mkdir(parents=True,exist_ok=True)
    process=None
    try:
        command=[str(browser_path()),"--app="+server.origin,
                 "--user-data-dir="+str(profile),"--disk-cache-dir="+str(profile/"disk-cache"),
                 "--crash-dumps-dir="+str(ROOT/"tmp"),"--no-first-run","--no-default-browser-check",
                 "--disable-background-mode","--disable-extensions","--disable-session-crashed-bubble",
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