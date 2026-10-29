"""Real WebGL two-window and local WASM check. Optional --camera/--native-window.
Uses synthetic routes, no saved provider credentials, no audio and no image recordings.
"""
from pathlib import Path
import argparse,json,os,subprocess,sys,time,uuid
from dataclasses import replace
from urllib import request
ROOT=Path(r"F:\Javis_os");sys.path.insert(0,str(ROOT/"src"))
from jarvis.bootstrap import create_state,create_server
from jarvis.domain.settings import Settings
from jarvis.infrastructure.persistence.sqlite import Store
from jarvis.presentation.desktop.window import browser_path
from jarvis.presentation.desktop.map_windows import displays,find_map_window
from jarvis.diagnostics.browser_check import DevTools

parser=argparse.ArgumentParser();parser.add_argument("--camera",action="store_true");parser.add_argument("--native-window",action="store_true");args=parser.parse_args()
opener=request.build_opener(request.ProxyHandler({}));browsers=[]
class Browser:
    def __init__(self,url):
        profile=ROOT/"tmp"/("hand_browser_"+uuid.uuid4().hex);profile.mkdir()
        self.process=subprocess.Popen([str(browser_path()),"--headless=new","--no-first-run","--disable-extensions","--use-fake-ui-for-media-stream",
            "--remote-debugging-port=0","--user-data-dir="+str(profile),"--disk-cache-dir="+str(profile/"cache"),
            "--crash-dumps-dir="+str(ROOT/"tmp"),"--window-size=1380,840","about:blank"],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        browsers.append(self);self.cdp=None
        deadline=time.monotonic()+20
        while not (profile/"DevToolsActivePort").exists():
            if time.monotonic()>deadline:raise RuntimeError("Browser debugging did not start")
            time.sleep(.1)
        port=int((profile/"DevToolsActivePort").read_text().splitlines()[0])
        with opener.open(f"http://127.0.0.1:{port}/json/list",timeout=3) as response:targets=json.load(response)
        self.cdp=DevTools(next(t["webSocketDebuggerUrl"] for t in targets if t["type"]=="page"))
        self.events=[];original_receive=self.cdp.receive
        def receive():
            value=original_receive()
            if value.get("method") in ("Log.entryAdded","Runtime.exceptionThrown"):self.events.append(value)
            return value
        self.cdp.receive=receive
        self.cdp.call("Log.enable");self.cdp.call("Runtime.enable");self.cdp.call("Page.enable")
        self.cdp.call("Page.addScriptToEvaluateOnNewDocument",{"source":"window.__handCheckErrors=[];addEventListener('error',e=>window.__handCheckErrors.push(e.message));addEventListener('unhandledrejection',e=>window.__handCheckErrors.push(String(e.reason?.message||e.reason)))"})
        self.cdp.evaluate("window.__handCheckErrors=[];addEventListener('error',e=>window.__handCheckErrors.push(e.message));addEventListener('unhandledrejection',e=>window.__handCheckErrors.push(String(e.reason?.message||e.reason)))")
        self.cdp.call("Page.navigate",{"url":url})
    def wait(self,expression,seconds=15):
        deadline=time.monotonic()+seconds
        while not self.cdp.evaluate(expression):
            if time.monotonic()>deadline:
                raise RuntimeError("Timed out: "+expression+"; errors="+str(self.cdp.evaluate("window.__handCheckErrors")))
            time.sleep(.12)
    def close(self):
        if self.cdp:
            try:self.cdp.call("Browser.close")
            except Exception:pass
            self.cdp.close();self.cdp=None
        try:self.process.wait(timeout=4)
        except subprocess.TimeoutExpired:self.process.terminate()

class WindowFixture:
    def displays(self):return displays()
    def open(self,*args):return {"multiple_displays":False,"display":{"id":0}}
    def reveal(self):return {"visible":True}
    def close(self):pass
    def status(self):return {"error":""}

def fixture_context(points,overview=False):
    return {"status":"synthetic-independent-fixture","buildings":[
        {"footprint":[[120.602,31.312],[120.603,31.312],[120.603,31.313],[120.602,31.313],[120.602,31.312]],"height":36},
        {"footprint":[[120.606,31.315],[120.608,31.315],[120.608,31.316],[120.606,31.316],[120.606,31.315]],"height":58}],
        "roads":[{"path":[[120.60,31.31],[120.61,31.31],[120.61,31.32]]}]}

state=create_state(Settings(TTS_MODE="off"),Store(ROOT/"tmp"/("hand_check_"+uuid.uuid4().hex+".sqlite3")))
server=create_server(state);native=server.services.map_windows
server.services=replace(server.services,map_windows=WindowFixture(),city_context=fixture_context);server.start()
report={"ok":False,"route_source":"synthetic fixture","recordings_saved":False,"cloud_calls":False,"checks":[]}
try:
    main=Browser(server.origin);main.wait("!!window.__sceneMetrics?.ready&&!!window.__navigation")
    main.cdp.evaluate("""(()=>{
      const w=window.__workerCheck=new Worker('/features/hand/worker.js');window.__workerResult={stage:'starting'};
      w.onmessage=async e=>{if(e.data.type==='ready'){const c=new OffscreenCanvas(480,360);c.getContext('2d').fillRect(0,0,480,360);const bitmap=await createImageBitmap(c);w.postMessage({type:'frame',bitmap,timestamp:performance.now()},[bitmap]);}
      else{window.__workerResult=e.data;if(e.data.type==='result')w.postMessage({type:'close'});if(e.data.type==='error')w.terminate();}};
      w.onerror=e=>window.__workerResult={type:'error',message:e.message};w.postMessage({type:'init'});
    })()""")
    main.wait("['result','error'].includes(window.__workerResult?.type)",30)
    worker=main.cdp.evaluate("window.__workerResult")
    if worker["type"]!="result":raise RuntimeError("Real hand runtime: "+worker.get("message",""))
    report["worker"]={"real_model":True,"blank_frame_landmarks":len(worker["landmarks"]),"inference_ms":round(worker["milliseconds"],1),"backend":worker.get("backend")}
    report["checks"].append("real local model and WASM inference in background worker")
    main.cdp.evaluate((ROOT/"tests/navigation_sdk_fixture.js").read_text(encoding="utf-8"))
    main.wait("window.__sceneMetrics.mapMix===1&&window.__navigation.state.mapReady&&window.__sceneMetrics.cityGeometryReady")
    main.cdp.evaluate("void window.__mapWorkspace.detach('right')")
    main.wait("!window.__mapWorkspace.opening")
    replica=Browser(server.origin+"/map");replica.wait("window.__sceneMetrics?.ready&&window.__mapReplica?.state.mapReady",40)
    main.wait("window.__sceneMetrics.transferPhase==='depart'",8)
    report["departure_direction"]=main.cdp.evaluate("window.__sceneMetrics.transferDirection")
    assert replica.cdp.evaluate("document.body.classList.contains('transfer-staging')"),"Secondary must remain hidden during primary departure"
    assert state.map_workspace.stage=="departing"
    main.cdp.screenshot(ROOT/"docs/hand_transfer_depart.png")
    replica.wait("window.__sceneMetrics.transferPhase==='arrive'",12)
    replica.wait("window.__sceneMetrics.assemblyParticles>100",5)
    report["assembly_particles"]=replica.cdp.evaluate("window.__sceneMetrics.assemblyParticles")
    report["source_first_ordering"]=True
    replica.cdp.screenshot(ROOT/"docs/hand_transfer_arrive.png")
    main.wait("window.__sceneMetrics.mapMix===0&&window.__sceneMetrics.transferPhase==='idle'",12)
    replica.wait("window.__sceneMetrics.mapMix===1&&window.__sceneMetrics.transferPhase==='idle'&&document.body.classList.contains('map-independent')",12)
    assert main.cdp.evaluate("!window.__navigation.isOpen")
    assert replica.cdp.evaluate("document.getElementById('voiceTrigger')===null && document.getElementById('command')===null")
    report["checks"].append("directional particle departure and destination assembly; primary returns to energy")
    replica.cdp.evaluate("document.querySelector('[data-mode=walking]').click()")
    replica.wait("window.__navigation.selected==='walking'")
    assert main.cdp.evaluate("window.__navigation.selected!=='walking'&&!window.__navigation.isOpen")
    replica.cdp.evaluate("document.querySelector('[data-city-view=start]').click()")
    replica.wait("window.__sceneMetrics.cityView==='start'&&window.__sceneMetrics.cityBuildings===2")
    replica.cdp.call("Input.dispatchMouseEvent",{"type":"mousePressed","x":700,"y":380,"button":"right","buttons":2,"clickCount":1})
    replica.cdp.call("Input.dispatchMouseEvent",{"type":"mouseMoved","x":850,"y":420,"button":"right","buttons":2})
    replica.cdp.call("Input.dispatchMouseEvent",{"type":"mouseReleased","x":850,"y":420,"button":"right","buttons":0,"clickCount":1})
    replica.wait("window.__navigation.state.cityYaw>.5")
    assert main.cdp.evaluate("window.__navigation.state.cityYaw===0")
    report["checks"].append("secondary independently chooses transport, loads geographic districts and rotates")
    state.send("你好，继续主屏对话")
    deadline=time.monotonic()+8
    while state.busy and time.monotonic()<deadline:time.sleep(.1)
    assert not state.busy
    assert replica.cdp.evaluate("window.__navigation.command.id===888&&window.__navigation.selected==='walking'")
    main.cdp.evaluate("void window.__navigation.open({id:889,action:'route',origin:'测试起点',destination:'另一测试终点',city:'苏州',mode:'driving'})")
    main.wait("window.__navigation.state.mapReady&&window.__navigation.command.id===889")
    assert replica.cdp.evaluate("window.__navigation.command.id===888&&window.__navigation.selected==='walking'")
    main.cdp.evaluate("window.__navigation.close()")
    main.wait("window.__sceneMetrics.mapMix===0")
    assert replica.cdp.evaluate("window.__navigation.isOpen&&window.__navigation.command.id===888")
    report["checks"].append("primary conversation, new route and navigation close do not change or close secondary map")
    main.cdp.evaluate("void window.__mapWorkspace.gesture({type:'orbit',dx:.06,dy:.02})")
    replica.wait("window.__mapReplica.state.cityYaw>1")
    assert main.cdp.evaluate("window.__sceneMetrics.mapMix===0")
    report["checks"].append("explicit camera target sends hand actions to independent secondary only")
    if args.camera:
        main.cdp.evaluate("void window.__handCamera.start()")
        main.wait("!window.__handCamera.active||window.__handCamera.lastFrame>0",35)
        if main.cdp.evaluate("window.__handCamera.active"):
            time.sleep(2)
            report["camera"]={"opened":True,"local_frames_processed":True,"human_gesture_accuracy":"requires user hand demonstration", "primary_fps":main.cdp.evaluate("window.__sceneMetrics.fps"),"secondary_fps":replica.cdp.evaluate("window.__sceneMetrics.fps"),"runtime":main.cdp.evaluate("window.__handCamera.metrics")}
        else:report["camera"]={"opened":False,"reason":main.cdp.evaluate("document.getElementById('handStatus').textContent")}
        main.cdp.evaluate("window.__handCamera.stop()")
        assert main.cdp.evaluate("!window.__handCamera.stream&&!window.__handCamera.worker")
    replica.cdp.key("F8");assert not state.audio.capture_active
    replica.cdp.key("Escape");main.wait("!window.__mapWorkspace.remote.requested")
    assert not state.closed.is_set();assert main.cdp.evaluate("window.__sceneMetrics.mapMix===0&&!window.__navigation.isOpen")
    report["checks"].append("secondary F8 cannot record; secondary Esc closes itself without restoring or changing primary")
    replica.close();report["monitors"]=len(displays())
    if args.native_window:
        server.services=replace(server.services,map_windows=native)
        main.cdp.evaluate("void window.__navigation.open({id:890,action:'route',origin:'测试起点',destination:'测试终点',city:'苏州',mode:'driving'})")
        main.wait("window.__navigation.state.mapReady&&window.__sceneMetrics.mapMix===1")
        main.cdp.evaluate("void window.__mapWorkspace.detach('right')")
        main.wait("window.__mapWorkspace.remote.stage==='departing'",45)
        assert not native.visible,"Destination must stay hidden until source departure ends"
        main.wait("window.__mapWorkspace.remote.stage==='independent'&&window.__sceneMetrics.mapMix===0",50)
        assert native.visible
        handle=find_map_window(server.origin);assert handle
        report["native_window"]={"ok":True,"physical_monitor_count":report["monitors"],"fullscreen":False}
        native._close(handle)
        main.wait("!window.__mapWorkspace.remote.requested",12)
        assert main.cdp.evaluate("!window.__navigation.isOpen&&window.__sceneMetrics.mapMix===0")
        report["checks"].append("native map window places on detected display and Windows X-close is independent")
    for browser in browsers:
        if browser.cdp:
            assert not browser.cdp.evaluate("(window.__handCheckErrors||[]).length"),browser.cdp.evaluate("window.__handCheckErrors")
            assert not browser.cdp.evaluate("window.__renderError||null"),browser.cdp.evaluate("window.__renderError")
    report["ok"]=True
except Exception as exc:
    report["error"]=str(exc);report["debug"]=[]
    for browser in browsers:
        if browser.cdp:
            try:
                report["debug"].append({"events":browser.events})
                browser.cdp.evaluate("void import('/map.js').then(()=>window.__importStatus='ok').catch(e=>window.__importStatus=String(e.stack||e))" ) if browser.cdp.evaluate("location.pathname==='/map'") else None
                time.sleep(1)
                report["debug"].append(browser.cdp.evaluate("({moduleStatus:window.__importStatus,doc:document.readyState,resources:performance.getEntriesByType('resource').map(e=>e.name.split('/').slice(3).join('/')).slice(-12),url:location.pathname,ready:window.__sceneMetrics?.ready,mapReady:window.__navigation?.state.mapReady,status:document.getElementById('replicaStatus')?.textContent,remote:window.__mapWorkspace?.remote,lastError:window.__mapWorkspace?.lastError,renderError:window.__renderError,errors:window.__handCheckErrors})"))
            except Exception:pass
finally:
    for browser in reversed(browsers):
        try:browser.close()
        except Exception:pass
    server.close()
    (ROOT/"logs/hand_workspace_check.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False),flush=True)
sys.exit(0 if report["ok"] else 1)
