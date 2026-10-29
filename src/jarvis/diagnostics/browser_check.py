"""Real Chromium rendering/keyboard check, using standard-library DevTools client."""
from dataclasses import replace
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
from urllib import request
from urllib.parse import urlsplit
import uuid
import traceback
from jarvis.domain.settings import Settings
from jarvis.bootstrap import create_state, create_server
from jarvis.presentation.desktop.window import browser_path
from jarvis.infrastructure.system.paths import ROOT
from jarvis.infrastructure.persistence.sqlite import Store

class DevTools:
    def __init__(self,url):
        parts=urlsplit(url)
        self.sock=socket.create_connection((parts.hostname,parts.port),timeout=8)
        self.sock.settimeout(8)
        key=base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {parts.path} HTTP/1.1\r\nHost: {parts.netloc}\r\n"
                           f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                           "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        self.buffer=b""
        while b"\r\n\r\n" not in self.buffer:
            self.buffer+=self.sock.recv(8192)
        headers,self.buffer=self.buffer.split(b"\r\n\r\n",1)
        if not headers.startswith(b"HTTP/1.1 101"):
            raise RuntimeError("DevTools handshake failed")
        self.counter=0

    def read(self,size):
        while len(self.buffer)<size:
            chunk=self.sock.recv(max(8192,size-len(self.buffer)))
            if not chunk:
                raise RuntimeError("DevTools connection closed")
            self.buffer+=chunk
        result,self.buffer=self.buffer[:size],self.buffer[size:]
        return result

    def send_frame(self,payload,opcode=1):
        mask=os.urandom(4)
        size=len(payload)
        header=bytes((0x80|opcode,0x80|(size if size<126 else 126 if size<65536 else 127)))
        if size>=65536:
            header+=struct.pack("!Q",size)
        elif size>=126:
            header+=struct.pack("!H",size)
        self.sock.sendall(header+mask+bytes(value^mask[i%4] for i,value in enumerate(payload)))

    def receive(self):
        while True:
            first,second=self.read(2)
            size=second&127
            if size==126:
                size=struct.unpack("!H",self.read(2))[0]
            elif size==127:
                size=struct.unpack("!Q",self.read(8))[0]
            mask=self.read(4) if second&128 else None
            data=self.read(size)
            if mask:
                data=bytes(value^mask[i%4] for i,value in enumerate(data))
            opcode=first&15
            if opcode==9:
                self.send_frame(data,10)
                continue
            if opcode==8:
                raise RuntimeError("DevTools closed")
            if opcode in (0,1):
                return json.loads(data)

    def call(self,method,params=None):
        self.counter+=1
        request_id=self.counter
        self.send_frame(json.dumps({"id":request_id,"method":method,"params":params or {}}).encode())
        while True:
            result=self.receive()
            if result.get("id")==request_id:
                if "error" in result:
                    raise RuntimeError(str(result["error"]))
                return result.get("result",{})

    def evaluate(self,expression):
        result=self.call("Runtime.evaluate",{"expression":expression,"returnByValue":True,"awaitPromise":True})
        if "exceptionDetails" in result:
            raise RuntimeError(str(result["exceptionDetails"]))
        return result.get("result",{}).get("value")

    def screenshot(self,path):
        data=self.call("Page.captureScreenshot",{"format":"png","captureBeyondViewport":False})
        path.write_bytes(base64.b64decode(data["data"]))

    def key(self,key,code=None):
        number={"Escape":27,"Enter":13,"F2":113,"F3":114,"F4":115,"F6":117,"F8":119,"F9":120,"F10":121}.get(key,0)
        params={"key":key,"code":code or key,"windowsVirtualKeyCode":number,"nativeVirtualKeyCode":number}
        self.call("Input.dispatchKeyEvent",{"type":"keyDown",**params})
        self.call("Input.dispatchKeyEvent",{"type":"keyUp",**params})

    def close(self):
        self.sock.close()

def run(check_audio=False):
    store=Store(ROOT/"tmp"/("space_check_"+uuid.uuid4().hex+".sqlite3"))
    settings=Settings(MAX_RECORD_SECONDS="1")
    state=create_state(settings,store)
    server=create_server(state)
    server.start()
    profile=ROOT/"tmp"/("space_render_"+uuid.uuid4().hex)
    profile.mkdir()
    process=None
    cdp=None
    result={"ok":False,"checks":[],"window":"ordinary; no fullscreen flag"}
    try:
        process=subprocess.Popen([
            str(browser_path()),"--headless=new","--no-first-run","--no-default-browser-check",
            "--disable-extensions","--disable-background-networking",
            "--remote-debugging-port=0","--remote-allow-origins=http://localhost",
            "--user-data-dir="+str(profile),"--disk-cache-dir="+str(profile/"cache"),
            "--crash-dumps-dir="+str(ROOT/"tmp"),"--window-size=1380,840",server.origin,
        ],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+20
        active_port=profile/"DevToolsActivePort"
        while not active_port.exists():
            if time.monotonic()>deadline:
                raise RuntimeError("Renderer DevTools did not start")
            time.sleep(.1)
        port=int(active_port.read_text().splitlines()[0])
        local=request.build_opener(request.ProxyHandler({}))
        target=None
        while not target:
            with local.open(f"http://127.0.0.1:{port}/json/list",timeout=3) as response:
                targets=json.load(response)
            target=next((item for item in targets if item.get("type")=="page" and item.get("url","").startswith(server.origin)),None)
            if time.monotonic()>deadline:
                raise RuntimeError("Renderer page did not load")
            if not target:
                time.sleep(.1)
        cdp=DevTools(target["webSocketDebuggerUrl"])
        cdp.call("Page.enable")
        deadline=time.monotonic()+30
        while not cdp.evaluate("!!window.__sceneMetrics && window.__sceneMetrics.ready && window.__sceneMetrics.frames>20"):
            render_error=cdp.evaluate("window.__renderError || null")
            if render_error:
                raise RuntimeError(render_error)
            if time.monotonic()>deadline:
                raise RuntimeError("Animation failed to start")
            time.sleep(.1)
        result["checks"].append("Actual WebGL2 shader rendering and frame loop")
        assert cdp.evaluate("document.querySelectorAll('#command:not([hidden]),#exitLayer:not([hidden]),#settingsLayer:not([hidden])').length")==0
        assert cdp.evaluate("!!document.querySelector('canvas') && !document.querySelector('textarea,nav')")
        result["checks"].append("No persistent conversation panel or menu")
        cdp.evaluate("document.getElementById('hints').classList.remove('visible')")
        cdp.screenshot(ROOT/"docs/space_initial.png")
        state.dialogue_until=time.monotonic()+10
        state.activity="speaking"
        state.audio.level=.28
        time.sleep(1.7)
        assert cdp.evaluate("window.__sceneMetrics.phase")=="dialogue"
        cdp.screenshot(ROOT/"docs/space_dialogue.png")
        result["checks"].append("Initial/dialogue morph rendered")
        state.audio.level=0
        state.activity="idle"
        cdp.key("Escape")
        assert cdp.evaluate("!document.getElementById('exitLayer').hidden")
        assert not state.closed.is_set()
        time.sleep(.45)
        cdp.screenshot(ROOT/"docs/space_exit.png")
        cdp.key("Escape")
        assert cdp.evaluate("document.getElementById('exitLayer').hidden")
        result["checks"].append("Escape opens exit layer; second Escape returns")
        cdp.key("Enter")
        assert cdp.evaluate("!document.getElementById('command').hidden")
        cdp.evaluate("document.getElementById('thought').value='你好，星海'")
        cdp.evaluate("document.getElementById('command').requestSubmit()")
        deadline=time.monotonic()+6
        while len(store.history(state.sid))<2:
            if time.monotonic()>deadline:
                raise RuntimeError("Text interaction failed")
            time.sleep(.1)
        assert "模拟" in store.history(state.sid)[-1]["content"]
        deadline=time.monotonic()+15
        while state.busy:
            if time.monotonic()>deadline:raise RuntimeError("Line presentation did not finish")
            time.sleep(.05)
        result["checks"].append("Optional Enter input sends through real Python service")
        if check_audio:
            cdp.key("F8")
            deadline=time.monotonic()+8
            while state.busy or state.last_record is None:
                if time.monotonic()>deadline:
                    raise RuntimeError("Microphone interaction did not finish")
                time.sleep(.1)
            result["checks"].append("F8 microphone recording")
        cdp.key("F2")
        deadline=time.monotonic()+6
        while not cdp.evaluate("!document.getElementById('settingsLayer').hidden && !!document.getElementById('cfg-WEATHER_CITY')"):
            if time.monotonic()>deadline:raise RuntimeError("Connection settings did not open")
            time.sleep(.1)
        assert cdp.evaluate("document.getElementById('cfg-WEATHER_CITY').value")=="苏州虎丘区"
        assert cdp.evaluate("document.getElementById('cfg-API_KEY').value")==""
        assert cdp.evaluate("document.getElementById('cfg-ASR_API_KEY').type")=="password"
        assert cdp.evaluate("document.getElementById('cfg-ASR_BASE_URL').value")==""
        assert "语音识别" in cdp.evaluate("document.getElementById('configNote').textContent")
        cdp.key("Escape")
        result["checks"].append("F2 settings, Suzhou city and secret masking")
        result["normal_renderer"]=cdp.evaluate("window.__sceneMetrics")
        cdp.key("F3")
        deadline=time.monotonic()+6
        while not cdp.evaluate("!!window.__navigation && window.__navigation.isOpen && !!window.__navigation.config"):
            if time.monotonic()>deadline:raise RuntimeError("Map view did not open")
            time.sleep(.1)
        assert cdp.evaluate("document.getElementById('mapStage').hidden && !window.__navigation.state.mapReady")
        assert cdp.evaluate("window.__navigation.map===null")
        assert not cdp.evaluate("!!document.getElementById('mapTrigger')")
        time.sleep(.4)
        assert cdp.evaluate("window.__sceneMetrics.mapMix")<.01
        cdp.screenshot(ROOT/"docs/amap_pending_credentials.png")
        cdp.key("Escape")
        assert cdp.evaluate("!window.__navigation.isOpen && document.getElementById('exitLayer').hidden")
        result["checks"].append("Missing credentials retain the energy body; no independent map panel or fabricated map")
        cdp.key("Enter")
        cdp.evaluate("document.getElementById('thought').value='贾维斯，我要去拙政园，帮我规划路线';document.getElementById('command').requestSubmit()")
        deadline=time.monotonic()+5
        while not cdp.evaluate("window.__navigation.isOpen && window.__navigation.command?.destination==='拙政园'"):
            if time.monotonic()>deadline:raise RuntimeError("Conversation navigation intent did not reach central scene")
            time.sleep(.1)
        assert state.navigation.snapshot()["action"]=="await_origin"
        assert "起点" not in state.navigation.snapshot()["origin"]
        assert cdp.evaluate("document.getElementById('mapStage').hidden")
        cdp.key("Enter")
        assert cdp.evaluate("!document.getElementById('command').hidden")
        cdp.evaluate("document.getElementById('thought').value='从苏州站出发';document.getElementById('command').requestSubmit()")
        deadline=time.monotonic()+5
        while state.navigation.snapshot().get("origin")!="苏州站":
            if time.monotonic()>deadline:raise RuntimeError("Follow-up departure did not resume route")
            time.sleep(.1)
        result["checks"].append("Jarvis destination phrase and follow-up departure handled without chat model or separate map form")
        cdp.key("Escape")
        cdp.key("F2")
        deadline=time.monotonic()+5
        while not cdp.evaluate("!!document.getElementById('cfg-AMAP_DEFAULT_ORIGIN') && !document.getElementById('settingsLayer').hidden"):
            if time.monotonic()>deadline:raise RuntimeError("Common departure setting missing")
            time.sleep(.1)
        assert cdp.evaluate("document.getElementById('cfg-AMAP_DEFAULT_ORIGIN').value")==""
        cdp.key("Escape")
        result["checks"].append("F2 provides an initially empty common departure setting")
        # Synthetic SDK fixture tests lifecycle/projection in real Chromium, never live AMap data.
        cdp.evaluate((ROOT/"tests/navigation_sdk_fixture.js").read_text(encoding="utf-8"))
        assert cdp.evaluate("window.__navigation.state.mapReady && !document.getElementById('mapStage').hidden")
        time.sleep(.65)
        assert .05 < cdp.evaluate("window.__sceneMetrics.mapMix") < .9
        assert cdp.evaluate("window.__sceneMetrics.morphDirection")=="city"
        assert cdp.evaluate("window.__sceneMetrics.cityRoadSegments")>0
        cdp.screenshot(ROOT/"docs/city_fixture_transition.png")
        time.sleep(2.4)
        assert cdp.evaluate("window.__sceneMetrics.mapMix")>.99
        assert cdp.evaluate("window.__sceneMetrics.cityView")=="overview"
        assert cdp.evaluate("window.__sceneMetrics.cityEndpointCount")==2
        assert cdp.evaluate("window.__sceneMetrics.cityEndpointProjection.every(p=>p.visible)")
        cdp.evaluate("window.__navigation.setView('start')")
        deadline=time.monotonic()+6
        while not cdp.evaluate("window.__sceneMetrics.cityView==='start' && window.__sceneMetrics.cityBuildings===2"):
            if time.monotonic()>deadline:raise RuntimeError("Local detailed street view failed")
            time.sleep(.1)
        assert cdp.evaluate("window.__sceneMetrics.cityParticles")>100
        assert cdp.evaluate("window.__navigation.options.length")==4
        assert cdp.evaluate("document.getElementById('travelOptions').children.length")==4
        assert cdp.evaluate("!document.getElementById('amapContainer') && !window.__navigation.map")
        assert cdp.evaluate("!!document.getElementById('travelOptions').closest('.left-rail') && !document.getElementById('travelPanel').hidden")
        assert cdp.evaluate("document.getElementById('travelOptions').getBoundingClientRect().right < innerWidth*.28")

        cdp.evaluate("document.querySelector('[data-mode=transit]').click()")
        assert cdp.evaluate("window.__navigation.selected")=="transit"
        assert cdp.evaluate("window.__navigation.path===window.__navigation.options.find(o=>o.id==='transit').route.path")
        cdp.evaluate("document.querySelector('[data-mode=walking]').scrollIntoView({block:'nearest'});document.querySelector('[data-mode=walking]').click()")
        assert cdp.evaluate("window.__navigation.selected")=="walking"
        assert cdp.evaluate("document.querySelector('[data-mode=walking]').getAttribute('aria-pressed')")== "true"

        # Reproduce a real ambiguity while a backend caption is still being presented.
        state.presenting=True
        cdp.evaluate((ROOT/"tests/navigation_choice_fixture.js").read_text(encoding="utf-8"))
        deadline=time.monotonic()+6
        while not cdp.evaluate("window.__navigation.state.mapStage==='await_choice'"):
            if time.monotonic()>deadline:raise RuntimeError("Ambiguous-place prompt missing")
            time.sleep(.1)
        time.sleep(.4)
        assert cdp.evaluate("document.getElementById('coreCaption').textContent.includes('左侧选择终点')")
        assert cdp.evaluate("document.getElementById('subtitle').textContent.includes('左侧选择终点')")
        assert not cdp.evaluate("window.__navigation.routeBusy")
        cdp.evaluate("document.getElementById('travelOptions').children[0].click()")
        deadline=time.monotonic()+6
        while not cdp.evaluate("window.__navigation.state.mapReady"):
            if time.monotonic()>deadline:raise RuntimeError("Selected POI did not resume planning")
            time.sleep(.1)
        state.presenting=False
        time.sleep(2.8)
        result["checks"].append("Ambiguous POI is visibly awaiting a choice, overrides stale backend captions, and resumes on selection")

        cdp.key("Escape");time.sleep(.7)
        assert cdp.evaluate("window.__sceneMetrics.morphDirection")=="energy"
        assert .05 < cdp.evaluate("window.__sceneMetrics.mapMix") < .95
        time.sleep(2.2)
        assert cdp.evaluate("!window.__navigation.state.mapReady && window.__sceneMetrics.mapMix<.02")
        assert cdp.evaluate("document.getElementById('exitLayer').hidden")
        result["checks"].append("Synthetic fixture: 3D geometry, four left-sidebar travel choices, switching paths, no flat map, Esc restoration")
        # A failed config request must leave a visible error instead of an old loading caption.
        cdp.evaluate("window.__savedNavApi=window.__navigation.api;window.__navigation.api=async()=>{throw new Error('测试连接失败')};void window.__navigation.open({action:'route',origin:'测试起点',destination:'测试终点'})")
        time.sleep(.4)
        assert cdp.evaluate("window.__navigation.state.mapStage==='error'")
        assert cdp.evaluate("document.getElementById('coreCaption').textContent.includes('测试连接失败')")
        assert cdp.evaluate("document.getElementById('subtitle').classList.contains('error')")
        cdp.evaluate("window.__navigation.close();window.__navigation.api=window.__savedNavApi")
        result["checks"].append("Failed navigation displays the actual error and retry guidance in the central status")
        result["amap_live_verified"]=False
        result["amap_live_limit"]="This isolated test uses no saved credentials; separate live provider check is recorded independently"
        weather=cdp.evaluate("document.getElementById('temperature').textContent")
        result["weather_display"]=weather
        result["renderer"]=cdp.evaluate("window.__sceneMetrics")
        cdp.evaluate("document.getElementById('quit').click()")
        deadline=time.monotonic()+3
        while not state.closed.is_set() and time.monotonic()<deadline:
            time.sleep(.1)
        assert state.closed.is_set()
        result["checks"].append("Exit command closes Python service")
        result["ok"]=True
        return 0
    except Exception as exc:
        result["error"]=str(exc)
        result["traceback"]=traceback.format_exc()
        return 1
    finally:
        if cdp:
            try:
                cdp.call("Browser.close")
            except Exception:
                pass
            cdp.close()
        if process:
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.terminate()
        server.close()
        (ROOT/"logs/space_render_check.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(result,ensure_ascii=False,indent=2))