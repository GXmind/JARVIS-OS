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

class DesktopServer:
    def __init__(self,state,services):
        self.services=services
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
                        body,mime=outer.services.fetch_proxy(path,urlsplit(self.path).query,outer.state.settings,outer.origin)
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
                            self.respond(200,outer.services.devices())
                        except ServiceError as exc:
                            self.respond(400,{"error":str(exc)})
                    else:
                        self.respond(404,{"error":"Not found"})
                    return
                asset=read_asset(path)
                if asset is None:
                    self.respond(404,{"error":"Not found"})
                    return
                body,mime,is_index=asset
                if is_index:body=body.replace("__TOKEN__",outer.token)
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
        self.state.close()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)
