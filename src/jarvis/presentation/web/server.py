"""Loopback HTTP transport. Services are wired only in bootstrap.py."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit
import json
import logging
import secrets
import threading
from jarvis.domain.errors import ServiceError
from jarvis.domain.settings import map_config
from jarvis.presentation.web.security import proxy_authorized

LOG=logging.getLogger("jarvis")
from jarvis.presentation.web.assets import read_asset

@dataclass(frozen=True)
class HttpServices:
    fetch_proxy: Callable
    city_context: Callable
    devices: Callable
    drag: Callable
    map_windows: object = None
    hand_status: Callable = lambda: {"ready":False,"message":"手势运行库尚未安装。"}
    hand_asset: Callable = lambda path: None

class DesktopServer:
    def __init__(self,state,services):
        self.services=services
        self.state=state
        self.token=secrets.token_urlsafe(32)
        self.map_token=secrets.token_urlsafe(32)
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
                page_token=outer.map_token if urlsplit(self.path).path=="/map" else outer.token
                self.send_header("Permissions-Policy","microphone=(), camera="+("()" if urlsplit(self.path).path=="/map" else "(self)"))
                amap=map_config(outer.state.settings)["configured"]
                if amap:
                    csp=("default-src 'self'; "
                         "img-src 'self' data: blob: https://*.amap.com https://*.autonavi.com http://*.amap.com http://*.autonavi.com; "
                         "style-src 'self' 'unsafe-inline' https://webapi.amap.com https://a.amap.com; "
                         "script-src 'self' 'unsafe-eval' 'nonce-"+page_token+"' https://webapi.amap.com https://a.amap.com; "
                         # AMap creates inline bootstrap code and loads WebGLRender from this SDK host.
                         # Restrict external script elements to these provider hosts; event handlers remain forbidden.
                         "script-src-elem 'self' 'unsafe-inline' https://webapi.amap.com https://a.amap.com https://jsapi-service.amap.com https://jsapi.amap.com https://mapplugin.amap.com; "
                         "script-src-attr 'none'; "
                         "connect-src 'self' https://*.amap.com https://*.autonavi.com http://*.amap.com http://*.autonavi.com; "
                         "worker-src 'self' blob:; font-src 'self' data: https://*.amap.com; frame-ancestors 'none'")
                else:
                    csp=("default-src 'self'; img-src 'self' data:; style-src 'self'; "
                         "script-src 'self' 'wasm-unsafe-eval' 'nonce-"+page_token+"'; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'")
                self.send_header("Content-Security-Policy",csp)
                if urlsplit(self.path).path=="/":
                    self.send_header("Set-Cookie","jarvis_map_gate="+outer.token+"; HttpOnly; SameSite=Strict; Path=/_AMapService")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):
                    pass
            def role(self):
                origin=self.headers.get("Origin")
                if (origin and origin!=outer.origin) or self.headers.get("Host")!=f"127.0.0.1:{outer.port}":return None
                token=self.headers.get("X-Jarvis-Token")
                if token==outer.token:return "primary"
                if token==outer.map_token:return "map"
                return None
            def authorized(self):
                role=self.role()
                if role=="primary":return True
                allowed={"GET":{"/api/map/workspace"},"POST":{"/api/map/ready","/api/map/arrive","/api/map/complete","/api/map/close","/api/city/context"}}
                return role=="map" and urlsplit(self.path).path in allowed.get(self.command,set())
            def do_GET(self):
                path=urlsplit(self.path).path
                if path.startswith("/_AMapService/"):
                    if not proxy_authorized(self.headers,outer.token,outer.origin,outer.port):
                        self.respond(403,{"error":"Forbidden"})
                        return
                    try:
                        body,mime=outer.services.fetch_proxy(path,urlsplit(self.path).query,outer.state.settings,outer.origin)
                        self.respond(200,body,mime)
                    except (ServiceError,ValueError) as exc:
                        self.respond(400,{"error":str(exc)})
                    return
                if path.startswith("/api/"):
                    if not self.authorized():
                        self.respond(403,{"error":"Forbidden"})
                        return
                    if path=="/api/map/workspace":
                        from urllib.parse import parse_qs
                        query=parse_qs(urlsplit(self.path).query)
                        try:
                            value=int(query.get("since" if self.role()=="map" else "after",["-1" if self.role()=="map" else "0"])[0])
                            after=int(query.get("after",["0"])[0]) if self.role()=="map" else 0
                        except ValueError:self.respond(400,{"error":"Invalid revision"});return
                        workspace=outer.state.map_workspace
                        data=workspace.replica_poll(value,after) if self.role()=="map" else workspace.primary_poll(value)
                        if outer.services.map_windows:
                            data["window"]=outer.services.map_windows.status()
                            if data["window"].get("closed") and data["requested"]:
                                workspace.close_map();data.update(workspace.metadata())
                        self.respond(200,data)
                    elif path=="/api/displays":
                        self.respond(200,outer.services.map_windows.displays() if outer.services.map_windows else [])
                    elif path=="/api/hand/status":
                        self.respond(200,outer.services.hand_status())
                    elif path=="/api/state":
                        self.respond(200,outer.state.snapshot())
                    elif path=="/api/weather":
                        self.respond(200,outer.state.weather.snapshot())
                    elif path=="/api/map/config":
                        self.respond(200,map_config(outer.state.settings))
                    elif path=="/api/config":
                        self.respond(200,outer.state.config_public())
                    elif path=="/api/devices":
                        try:
                            self.respond(200,outer.services.devices())
                        except ServiceError as exc:
                            self.respond(400,{"error":str(exc)})
                    else:
                        self.respond(404,{"error":"Not found"})
                    return
                if path.startswith("/runtime/hand/"):
                    asset=outer.services.hand_asset(path)
                    if asset is None:self.respond(404,{"error":"Hand runtime not installed"})
                    else:self.respond(200,*asset)
                    return
                asset=read_asset(path)
                if asset is None:
                    self.respond(404,{"error":"Not found"})
                    return
                body,mime,is_index=asset
                if is_index:body=body.replace("__TOKEN__",outer.map_token if path=="/map" else outer.token)
                if is_index and path=="/map":body=body.replace("<title>JARVIS · 地图</title>",f"<title>JARVIS · 地图 · {outer.port}</title>")
                self.respond(200,body,mime)
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
                    limit=4_100_000 if urlsplit(self.path).path=="/api/map/publish" and self.role()=="primary" else 100000
                    if not 0<size<=limit:
                        raise ValueError("Invalid request size")
                    values=json.loads(self.rfile.read(size))
                    if not isinstance(values,dict):
                        raise ValueError("Invalid request")
                    action=urlsplit(self.path).path
                    if action=="/api/map/publish":
                        result=outer.state.map_workspace.publish(values)
                        self.respond(200,result);return
                    elif action=="/api/map/view":
                        self.respond(200,outer.state.map_workspace.patch_view(values));return
                    elif action=="/api/map/detach":
                        if not outer.services.map_windows:raise ServiceError("当前环境不支持独立地图窗口。")
                        outer.state.map_workspace.request_detach(values.get("direction"))
                        try:result=outer.services.map_windows.open(outer.origin,values.get("display"),values.get("direction"))
                        except Exception:
                            outer.state.map_workspace.close_map();raise
                        outer.state.map_workspace.set_direction(result.get("direction"))
                        self.respond(200,result);return
                    elif action=="/api/map/ready":
                        self.respond(200,outer.state.map_workspace.replica_ready(values.get("epoch"),values.get("revision")));return
                    elif action in ("/api/map/depart","/api/map/dispatch","/api/map/arrive","/api/map/complete"):
                        event=action.rsplit("/",1)[-1]
                        if self.role()=="map" and event not in ("arrive","complete"):raise ServiceError("此窗口不能发送该阶段。")
                        result=outer.state.map_workspace.transition(values.get("epoch"),event)
                        if event=="dispatch" and outer.services.map_windows:outer.services.map_windows.reveal()
                        self.respond(200,result);return
                    elif action=="/api/map/gesture":
                        self.respond(200,outer.state.map_workspace.enqueue(values));return
                    elif action=="/api/map/close":
                        if self.role()=="map" and values.get("epoch")!=outer.state.map_workspace.epoch:raise ServiceError("地图窗口已过期。")
                        outer.state.map_workspace.close_map()
                        if outer.services.map_windows:outer.services.map_windows.close()
                    elif action=="/api/wake":
                        outer.state.set_wake(values.get("enabled"))
                    elif action=="/api/send":
                        outer.state.send(values.get("text",""))
                    elif action=="/api/record":
                        outer.state.record()
                    elif action=="/api/stop":
                        outer.state.audio.stop()
                    elif action=="/api/city/context":
                        result=outer.services.city_context(values.get("path",[]),overview=values.get("overview") is True)
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
                            outer.services.drag(outer.state.window_handle)
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
        if self.services.map_windows:self.services.map_windows.close()
        self.state.close()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)
