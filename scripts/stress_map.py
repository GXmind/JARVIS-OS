"""Synthetic map stability check: 500 buildings and 80 viewport replacements; no map credentials, mic or TTS."""
from dataclasses import replace
from pathlib import Path
from urllib import request
import json,os,re,subprocess,sys,time,uuid,wave
root=Path(r"F:\Javis_os")
sys.path.insert(0,str(root/"src"))
from jarvis.infrastructure.system.paths import initialize
initialize()
from jarvis.infrastructure.config.env_file import load_settings
from jarvis.bootstrap import create_state, create_server
from jarvis.presentation.desktop.window import browser_path
from jarvis.diagnostics.browser_check import DevTools
from jarvis.infrastructure.persistence.sqlite import Store
from jarvis.infrastructure.audio.service import Audio
from jarvis.domain.navigation import parse_navigation
from jarvis.domain.errors import ServiceError
settings=load_settings()
report={"ok":False,"center_only_revision":True}
state=create_state(replace(settings,CHAT_MODE="mock",ASR_MODE="off",AUTO_SPEAK="false",AMAP_JS_KEY="",AMAP_SECURITY_JSCODE=""),Store(root/"tmp"/("revision_live_"+uuid.uuid4().hex+".sqlite3")))
server=create_server(state);server.start()
profile=root/"tmp"/("revision_browser_"+uuid.uuid4().hex);profile.mkdir()
cdp=None;process=None
def wait_for(expression,seconds,label):
    deadline=time.monotonic()+seconds
    while not cdp.evaluate(expression):
        if time.monotonic()>deadline:raise RuntimeError(label)
        time.sleep(.15)
try:
    process=subprocess.Popen([str(browser_path()),"--headless=new","--no-first-run","--disable-extensions",
      "--remote-debugging-port=0","--user-data-dir="+str(profile),"--disk-cache-dir="+str(profile/"cache"),
      "--crash-dumps-dir="+str(root/"tmp"),"--window-size=1380,840",server.origin],
      cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    deadline=time.monotonic()+18
    while not (profile/"DevToolsActivePort").exists():
        if time.monotonic()>deadline:raise RuntimeError("Debug browser failed")
        time.sleep(.1)
    port=int((profile/"DevToolsActivePort").read_text().splitlines()[0])
    opener=request.build_opener(request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{port}/json/list",timeout=3) as response:targets=json.load(response)
    cdp=DevTools(next(t["webSocketDebuggerUrl"] for t in targets if t["type"]=="page"))
    cdp.call("Page.enable")
    wait_for("!!window.__sceneMetrics?.ready && !!window.__navigation",25,"Scene or data controller failed")

    cdp.evaluate("window.__mapErrors=[];addEventListener('error',e=>window.__mapErrors.push(e.message));addEventListener('unhandledrejection',e=>window.__mapErrors.push(String(e.reason?.message||e.reason)))")
    cdp.evaluate((root/"tests/navigation_sdk_fixture.js").read_text(encoding="utf-8"))
    cdp.evaluate("window.__navigation.setView('start')")
    wait_for("window.__sceneMetrics.mapMix===1 && window.__sceneMetrics.cityBuildings>0",12,"City did not start")
    cdp.evaluate("""(()=>{
      const n=window.__navigation,buildings=[];
      for(let y=0;y<20;y++)for(let x=0;x<25;x++){
       const lng=120.595+x*.00038,lat=31.306+y*.00038;
       buildings.push({height:6+(x+y)%9*4,footprint:[[lng,lat],[lng+.00015,lat],[lng+.00015,lat+.00016],[lng,lat+.00016],[lng,lat]]});
      }
      const context={status:'synthetic-stress-fixture',buildings,roads:[{kind:'primary',path:[[120.59,31.31],[120.62,31.31]]}]};
      n.state.cityScene={...n.state.cityScene,context};n.state.cityRevision++;
    })()""")
    time.sleep(.5)
    cdp.evaluate("""(()=>{
      const gl=document.getElementById('space').getContext('webgl2'),create=gl.createBuffer,remove=gl.deleteBuffer;
      window.__bufferPressure={created:0,deleted:0};
      gl.createBuffer=function(...a){window.__bufferPressure.created++;return create.apply(this,a)};
      gl.deleteBuffer=function(...a){window.__bufferPressure.deleted++;return remove.apply(this,a)};
    })()""")
    base_metric=cdp.evaluate("window.__sceneMetrics")
    report["baseline_gpu"]={k:base_metric.get(k) for k in ("gpuGeometries","gpuTextures","gpuPrograms")}
    report["pressure"]=[]
    for index in range(80):
        cdp.evaluate("(()=>{const n=window.__navigation;n.state.cityScene={...n.state.cityScene,focus:[120.60+"+str((index%10)*.00003)+",31.31]};n.state.cityRevision++;})()")
        time.sleep(.065)
        if index%10==0:
            metric=cdp.evaluate("window.__sceneMetrics")
            report["pressure"].append({k:metric.get(k) for k in ("frames","fps","gpuGeometries","gpuTextures","gpuPrograms","postPasses")})
    time.sleep(2)
    after=cdp.evaluate("window.__sceneMetrics")
    report["final_gpu"]={k:after.get(k) for k in ("gpuGeometries","gpuTextures","gpuPrograms")}
    report["buffer_allocations"]=cdp.evaluate("window.__bufferPressure")
    report["synthetic_buildings"]=after["cityBuildings"]
    report["particles"]=after["cityParticles"]
    assert after["cityBuildings"]>=400
    assert report["buffer_allocations"]["created"]<60,"Buffers are being reallocated for each view"
    assert after["gpuGeometries"]<=base_metric["gpuGeometries"]+2
    assert after["gpuTextures"]<=base_metric["gpuTextures"]+2
    assert after["frames"]>base_metric["frames"]+50
    assert after["postPasses"]==1
    assert not cdp.evaluate("window.__renderError")
    report["ok"]=True
except Exception as exc:
    report["error"]=str(exc)
    if cdp:
        try:report["navigation_status"]=cdp.evaluate("window.__navigation?.state.mapStatus || window.__renderError")
        except Exception:pass
finally:
    if cdp:
        try:cdp.call("Browser.close")
        except Exception:pass
        cdp.close()
    if process:
        try:process.wait(timeout=4)
        except subprocess.TimeoutExpired:process.terminate()
    server.close()
    text=json.dumps(report,ensure_ascii=False,indent=2)
    for secret in (settings.API_KEY,settings.ASR_API_KEY,settings.AMAP_JS_KEY,settings.AMAP_SECURITY_JSCODE):
        if secret:text=text.replace(secret,"[redacted]")
    (root/"logs/map_stability_pressure.json").write_text(text,encoding="utf-8")
    print(text,flush=True)
sys.exit(0 if report["ok"] else 1)