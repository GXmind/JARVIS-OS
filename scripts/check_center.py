"""Real WebGL two-window and local WASM check. Optional --camera/--native-window.
Uses synthetic routes, no saved provider credentials, no audio and no image recordings.
"""
from pathlib import Path
import argparse,json,math,os,subprocess,sys,time,uuid
from dataclasses import replace
from urllib import request
ROOT=Path(r"F:\Javis_os");sys.path.insert(0,str(ROOT/"src"))
from jarvis.bootstrap import create_state,create_server
from jarvis.domain.settings import Settings
from jarvis.infrastructure.persistence.sqlite import Store
from jarvis.presentation.desktop.window import browser_path
from jarvis.presentation.desktop.map_windows import displays,find_map_window
from jarvis.diagnostics.browser_check import DevTools

parser=argparse.ArgumentParser();parser.add_argument("--live-chat",action="store_true");parser.add_argument("--live-model",action="store_true");parser.add_argument("--audio",action="store_true");parser.add_argument("--live-drawing",action="store_true");args=parser.parse_args()
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


state=create_state(Settings(TTS_MODE="off"),Store(ROOT/"tmp"/("center_check_"+uuid.uuid4().hex+".sqlite3")));server=create_server(state);server.start()
state._speak_answer=lambda answer,settings:state.notify(answer)
report={"ok":False,"cloud_calls":False,"checks":[],"models":[]};folder=ROOT/"logs/center-preview";folder.mkdir(exist_ok=True)
try:
 b=Browser(server.origin);b.wait("window.__sceneMetrics?.ready&&!!window.__navigation",25)
 for activity in ("idle","listening","transcribing","thinking","speaking","modeling"):
  state.busy=activity!="idle";state.activity=activity
  b.wait("window.__sceneMetrics.visualActivity==='"+activity+"'",6);time.sleep(.5);b.cdp.screenshot(folder/(activity+".png"))
 state.busy=False;state.activity="idle";report["checks"].append("six actual WebGL activity forms and galaxy palette")
 for text in ("生成一个太阳系","创建一个火箭","画一辆汽车","展示DNA双螺旋模型","生成一个爱心","用粒子写出‘你好’"):
  state.send(text);deadline=time.monotonic()+5
  while state.busy and time.monotonic()<deadline:time.sleep(.05)
  if state.error:raise RuntimeError(state.subtitle)
  build=state.center["build"];b.wait("window.__sceneMetrics.centerBuild==="+str(build)+"&&window.__sceneMetrics.centerMix===1&&window.__sceneMetrics.centerMorph===1&&!window.__sceneMetrics.centerLoading",10)
  model=b.cdp.evaluate("({title:window.__sceneMetrics.centerTitle,particles:window.__sceneMetrics.centerParticles,fps:window.__sceneMetrics.fps,error:window.__sceneMetrics.centerError})")
  assert model["particles"] in (12000,20000) and not model.get("error"),model;report["models"].append(model)
  b.cdp.screenshot(folder/("model_"+str(build)+".png"))
 report["checks"].append("natural-language scene dispatch, bounded worker sampling, model morph and text glyphs")
 state.send("暂停动画");state.wait_workers(2);assert state.center["plan"]["paused"]
 b.wait("window.__sceneMetrics.centerPaused===true");paused=b.cdp.evaluate("window.__sceneMetrics.centerAnimationTime");time.sleep(.25);assert b.cdp.evaluate("window.__sceneMetrics.centerAnimationTime")==paused
 state.send("让它散开");state.wait_workers(2);assert state.center["explode"]==1
 state.send("重新汇聚");state.wait_workers(2);assert state.center["explode"]==0
 state.send("把它改成粉色");state.wait_workers(2);assert state.center["plan"]["nodes"][0]["color"]=="rose"
 b.cdp.key("Escape");b.wait("window.__sceneMetrics.centerMix===0",8);assert not state.center["active"]

 # Exercise all freeform surfaces plus per-part keyframes through the real renderer.
 free_nodes=[{"shape":"curve","points":[[-1,-1,0],[0,1,0],[1,0,0]],"radius":.04,"color":"#88aaff","position":[0,0,0],"scale":[1,1,1]},
 {"shape":"patch","control":[[i%4/3-1,i//4/3-.5,math.sin(i)*.1] for i in range(16)],"position":[0,0,.4],"scale":[1,1,1],"color":"#aa66ff","pivot":[0,0,0],"frames":[{"t":0,"turn":[0,0,-.3]},{"t":1,"turn":[0,0,.3]},{"t":2,"turn":[0,0,-.3]}]},
 {"shape":"lathe","profile":[[0,-1],[.3,-.6],[.5,.4],[.2,1]],"position":[1,0,0],"scale":[.4,.7,.4],"color":"#ff77bb"},
 {"shape":"mesh","vertices":[[-1,0,0],[0,1,0],[1,0,0],[0,0,1]],"faces":[[0,1,2],[0,1,3],[1,2,3],[0,2,3]],"position":[-.8,0,0],"scale":[.4,.4,.4],"color":"#ffe08a"}]
 from jarvis.domain.center import validate_plan
 state.center={"id":state.center["id"]+1,"build":state.center["build"]+1,"active":True,"plan":validate_plan({"title":"自由曲面与关键帧测试","nodes":free_nodes,"motion":"none"}),"explode":0}
 b.wait("window.__sceneMetrics.centerBuild==="+str(state.center["build"])+"&&window.__sceneMetrics.centerMorph===1&&window.__sceneMetrics.centerMix===1",12)
 assert not b.cdp.evaluate("window.__sceneMetrics.centerError||window.__renderError")
 b.cdp.screenshot(folder/"free_surface_animation.png");state.close_center();b.wait("window.__sceneMetrics.centerMix===0",6)
 report["checks"].append("free curves, Bezier surfaces, meshes, lathed profiles and per-part keyframes render without shader errors")
 report["checks"].append("pause, explosion, reassembly, palette update and independent model close")

 # F4 must send the exact prompt without requiring "draw/create" or any object keyword.
 old_settings=state.settings;old_services=state.services;received=[]
 class PromptGateway:
  def chat(self,messages):
   received.append(messages[-1]["content"])
   return json.dumps({"title":"自由输入验证","motion":"none","nodes":[{"shape":"drawing","paths":[{"d":"M 30 200 Q 180 20 340 200 Q 200 400 30 200 Z","color":"#66aaff","fill":False}]}]})
 state.settings=Settings(CHAT_MODE="api",API_BASE_URL="https://example.com/v1",API_MODEL="local-scene-fixture",API_KEY="local-fixture",TTS_MODE="off")
 state.services=replace(state.services,cloud_factory=lambda cfg:PromptGateway())
 prompt="紫色星海里游动的鲸鱼，三颗星星"
 b.cdp.key("F4");b.wait("!document.getElementById('command').hidden")
 b.cdp.evaluate("document.getElementById('thought').value="+json.dumps(prompt)+";document.getElementById('command').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))")
 b.wait("window.__sceneMetrics.centerTitle==='自由输入验证'&&window.__sceneMetrics.centerMorph===1&&!window.__sceneMetrics.centerLoading",12)
 assert received[-1]==prompt and state.center["source"]=="cloud"
 report["checks"].append("F4 arbitrary prompt reaches an injected scene gateway unchanged, with no intent keywords")
 state.close_center();b.wait("window.__sceneMetrics.centerMix===0",6);state.settings=old_settings;state.services=old_services
 b.cdp.evaluate((ROOT/"tests/navigation_sdk_fixture.js").read_text(encoding="utf-8"));b.wait("window.__sceneMetrics.mapMix===1&&window.__sceneMetrics.cityGeometryReady",15)
 assert b.cdp.evaluate("window.__sceneMetrics.visualActivity==='dedicated'&&window.__sceneMetrics.centerMix===0")
 report["checks"].append("map keeps dedicated shape and is not replaced by dialogue forms")
 assert not b.cdp.evaluate("window.__renderError||window.__handCheckErrors?.length")
 if args.live_chat or args.live_model or args.audio or args.live_drawing:
  from jarvis.infrastructure.config.env_file import load_settings
  from jarvis.infrastructure.http.openai_compatible import CloudAPI
  from jarvis.application.center import SceneDesigner
  from jarvis.infrastructure.audio.service import Audio
  from jarvis.domain.text import SpeechChunks
  cfg=replace(load_settings(),REQUEST_TIMEOUT="120")
  if args.live_model:
   class PublicModelAPI(CloudAPI):
    def chat_stream(self,messages,cancel=None):
     pieces=[]
     try:
      for piece in super().chat_stream(messages,cancel):pieces.append(piece);yield piece
     finally:(ROOT/"logs/free_model_public_raw.txt").write_text("".join(pieces),encoding="utf-8")
   t=time.monotonic();plan,source=SceneDesigner(PublicModelAPI).design("请创建一个三维概念模型：一朵不对称弯曲花瓣组成的机械花，花瓣绕花根缓慢开合，底座保持不动。至少一片花瓣使用patch自由曲面并配置frames局部动画。必须有立体深度，不用二维drawing代替。",cfg);report["live_model"]={"source":source,"nodes":len(plan["nodes"]),"ms":round((time.monotonic()-t)*1000)};report["cloud_calls"]=source=="cloud"
   b.cdp.evaluate("window.__navigation.close()");state.center={"id":state.center["id"]+1,"build":state.center["build"]+1,"active":True,"plan":plan,"source":source,"explode":0}
   b.wait("window.__sceneMetrics.centerBuild==="+str(state.center["build"])+"&&window.__sceneMetrics.centerMorph===1&&window.__sceneMetrics.centerMix===1",12);b.cdp.screenshot(folder/"cloud_free_model.png");report["live_model"]["rendered"]=True;report["live_model"]["free_surface_nodes"]=sum(n["shape"] in ("curve","patch","mesh","lathe") for n in plan["nodes"]);report["live_model"]["animated_nodes"]=sum(bool(n.get("frames")) for n in plan["nodes"]);(ROOT/"logs/free_model_public_scene.json").write_text(json.dumps(plan,ensure_ascii=False),encoding="utf-8");assert report["live_model"]["free_surface_nodes"]>0 and report["live_model"]["animated_nodes"]>0
  if args.live_drawing:
   prompt="绘制一幅自由二维粒子图景：一只蓝色鲸鱼游在紫色星河中，尾巴朝右，鲸鱼上方有三颗金色五角星。请用自由曲线路径体现鲸鱼的身体、尾鳍、眼睛和星星，不用任何内置对象或文字代替。"
   class PublicPromptAPI(CloudAPI):
    def chat_stream(self,messages,cancel=None):
     pieces=[]
     try:
      for piece in super().chat_stream(messages,cancel):pieces.append(piece);yield piece
     finally:(ROOT/"logs/free_prompt_public_raw.txt").write_text("".join(pieces),encoding="utf-8")
   t=time.monotonic();plan,source=SceneDesigner(PublicPromptAPI).design(prompt,cfg);report["live_drawing"]={"source":source,"shapes":[n["shape"] for n in plan["nodes"]],"ms":round((time.monotonic()-t)*1000)};report["cloud_calls"]=True
   b.cdp.evaluate("window.__navigation.close()");state.center={"id":state.center["id"]+1,"build":state.center["build"]+1,"active":True,"plan":plan,"source":source,"explode":0}
   b.wait("window.__sceneMetrics.centerBuild==="+str(state.center["build"])+"&&window.__sceneMetrics.centerMorph===1&&window.__sceneMetrics.centerMix===1&&!window.__sceneMetrics.centerLoading",18);assert not b.cdp.evaluate("window.__sceneMetrics.centerError")
   b.cdp.screenshot(folder/"free_prompt_whale.png");(ROOT/"logs/free_prompt_whale_scene.json").write_text(json.dumps(plan,ensure_ascii=False),encoding="utf-8");report["live_drawing"]["rendered"]=True
  if args.live_chat:
   t=time.monotonic();first=None;chunks=[]
   for piece in CloudAPI(cfg).chat_stream([{"role":"user","content":"请用两句简短中文欢迎我，每句不超过十二字。"}]):
    if first is None:first=round((time.monotonic()-t)*1000)
    chunks.append(piece)
   report["live_chat"]={"first_token_ms":first,"total_ms":round((time.monotonic()-t)*1000),"characters":len("".join(chunks))};report["cloud_calls"]=True
  if args.audio:
   audio=Audio();audio.warmup(cfg);time.sleep(.8);audio.prepare();audio.speak("第一句连续播报。第二句连续播报。",replace(cfg,TTS_MODE="windows"));report["audio"]={**audio.speech_metrics,"human_quality":"requires listening confirmation"};audio.close()
 report["ok"]=True
except Exception as exc:
 report["error"]=str(exc)
 if browsers:
  try:report["debug"]=browsers[0].cdp.evaluate("({metrics:window.__sceneMetrics,error:window.__renderError,errors:window.__handCheckErrors})")
  except Exception:pass
finally:
 for b in reversed(browsers):
  try:b.close()
  except Exception:pass
 server.close();(ROOT/"logs/center_actions_check.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(report,ensure_ascii=True))
sys.exit(0 if report["ok"] else 1)
