"""Assistant session orchestration; providers are injected via application ports."""
from dataclasses import asdict
import logging
import threading
import queue
import time
from jarvis.domain.errors import ServiceError
from jarvis.domain.settings import Settings, SECRET_FIELDS, map_config
from jarvis.domain.navigation import NavigationBridge
from jarvis.domain.map_workspace import MapWorkspace
from jarvis.domain.text import lines_for_speech,SpeechChunks
from jarvis.domain.center import intent as center_intent
from jarvis.application.center import SceneDesigner
from jarvis.application.conversation import Conversation
from jarvis.application.ports import SessionServices

LOG=logging.getLogger("jarvis")

class DesktopState:
    def __init__(self,settings: Settings,services: SessionServices):
        self.services=services
        self.settings=settings
        self.store=services.store
        sessions=self.store.sessions()
        self.sid=sessions[0][0] if sessions else self.store.new_session()
        self.conversation=Conversation(self.store,cloud_factory=services.cloud_factory)
        self.audio=services.audio
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
        self.weather=services.weather
        self.telemetry=services.telemetry
        self.counts={"memories":0,"messages":0}
        self.counts_updated=0.0
        self.navigation=NavigationBridge()
        self.map_workspace=MapWorkspace()
        self.wake=None
        self.center={"id":0,"build":0,"active":False}
        self.latency={}
        self.visual_cancel=threading.Event()

    def notify(self,text,error=False,seconds=18):
        with self.lock:
            self.subtitle=text
            self.subtitle_until=time.monotonic()+seconds
            self.error=error
            self.revision+=1

    def snapshot(self,center_since=None):
        with self.lock:
            self.last_seen=time.monotonic()
            self.connected=True
            if time.monotonic()-self.counts_updated>5:
                self.counts=self.store.counts(self.sid)
                self.counts_updated=time.monotonic()
            center=dict(self.center)
            if center_since==center["id"]:center.pop("plan",None);center["same"]=True
            return {
                "navigation":self.navigation.snapshot(),"presenting":self.presenting,"center":center,"latency":dict(self.latency),
                "wake":self.wake.snapshot() if self.wake else {"state":"disabled","phrase":"hi jarvis","local_only":True},
                "telemetry":self.telemetry.sample(),
                "counts":dict(self.counts),
                "modules":{"asr":self.settings.ASR_MODE,"tts":self.settings.TTS_MODE,"model":self.settings.API_MODEL,"auto_speak":self.settings.AUTO_SPEAK=="true"},
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
        if self.wake:self.wake.pause()
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
                if self.wake:self.wake.resume()
        thread=threading.Thread(target=worker,daemon=True,name="jarvis-space-"+kind)
        with self.lock:self.worker_threads.add(thread)
        thread.start()

    def wait_workers(self,seconds=2.0):
        deadline=time.monotonic()+seconds
        with self.lock:threads=list(self.worker_threads)
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(max(0,deadline-time.monotonic()))

    def _reply(self,text,settings,*,force_visual=False):
        detected=center_intent(text,self.center.get("active",False))
        visual={"action":"show","prompt":text,"edit":bool(detected and detected.get("edit"))} if force_visual else detected
        if visual:
            self.navigation.accept("绘制粒子场景",settings.AMAP_CITY,settings.AMAP_DEFAULT_ORIGIN)
            self.center_reply(text,visual,settings);return
        navigation=self.navigation.accept(text,settings.AMAP_CITY,settings.AMAP_DEFAULT_ORIGIN)
        if navigation:
            if navigation["action"] in ("route","open","cancel"):self.center={**self.center,"id":self.center["id"]+1,"active":False}
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
                answer="正在为您查询路线。"
            else:
                answer="正在打开高德地图。"
            self.store.add_message(self.sid,"assistant",answer)
            self._speak_answer(answer,settings)
            return
        if settings.CHAT_MODE=="api" and settings.CHAT_STREAM=="true":
            self.stream_reply(text,settings);return
        with self.lock:
            self.activity="thinking"
        answer,state=self.conversation.reply(self.sid,text,settings)
        self._speak_answer(answer,settings)

    def center_result(self,values):
        if not isinstance(values.get("ok"),bool):raise ServiceError("绘制结果无效。")
        with self.lock:
            if values.get("build")!=self.center["build"] or not self.center.get("active"):return
            if values["ok"]:self.center={**self.center,"rendered":True}
            else:self.close_center();self.notify("粒子绘制失败，已恢复能量体，请调整提示词重试。",True)

    def close_center(self):
        with self.lock:
            self.visual_cancel.set();self.center={**self.center,"id":self.center["id"]+1,"active":False,"pending":False}

    def center_reply(self,text,command,settings):
        action=command["action"]
        if action=="show":
            self.activity="modeling"
            version=self.center["id"]
            previous=self.center.get("plan") if command.get("edit") else None
            cancel=threading.Event()
            with self.lock:self.visual_cancel=cancel;self.center={**self.center,"pending":True}
            try:plan,source=SceneDesigner(self.services.cloud_factory).design(text,settings,previous,cancel)
            except ServiceError:
                if cancel.is_set():return
                raise
            finally:
                with self.lock:self.center={**self.center,"pending":False}
            with self.lock:
                if self.center["id"]!=version:return
                self.center={"id":self.center["id"]+1,"scene_id":self.center["id"]+1,"build":self.center["build"]+1,"active":True,"plan":plan,"source":source,"explode":0}
            answer=("当前为内置离线演示，完整提示词绘制需配置云端 API。" if source=="offline-demo" else "正在按完整提示词重组粒子：")+plan["title"]+"。可拖动旋转、滚轮缩放，也可以说散开、重组或收起模型。"
        elif action=="close":
            self.center={**self.center,"id":self.center["id"]+1,"active":False};answer="已收起粒子展示，恢复能量体。"
        else:
            if not self.center.get("active"):raise ServiceError("请先创建一个粒子模型。")
            plan={**self.center["plan"]}
            if "motion" in command:plan["motion"]=command["motion"]
            if "paused" in command:plan["paused"]=command["paused"]
            if "color" in command:plan["nodes"]=[{**node,"color":command["color"]} for node in plan["nodes"]]
            if "speed_factor" in command:plan["speed"]=max(.1,min(3,plan["speed"]*command["speed_factor"]))
            self.center={**self.center,"id":self.center["id"]+1,"build":self.center["build"]+(1 if "color" in command else 0),"plan":plan,"explode":command.get("explode",self.center.get("explode",0))};answer="已调整粒子表现。"
        self.store.add_message(self.sid,"user",text);self.store.add_message(self.sid,"assistant",answer);self._speak_answer(answer,settings)

    def stream_reply(self,text,settings):
        lines=queue.Queue(maxsize=24);ending=object();buffer=SpeechChunks();failure=[];started=time.monotonic();self.latency={};self.audio.prepare();self.presenting=True
        def put(value):
            while not self.audio.stop_event.is_set() and not self.closed.is_set():
                try:lines.put(value,timeout=.05);return
                except queue.Full:continue
        def chunk(value):
            if "first_token_ms" not in self.latency:self.latency["first_token_ms"]=round((time.monotonic()-started)*1000)
            for line in buffer.feed(value):put(line)
        def generate():
            try:
                self.conversation.reply(self.sid,text,settings,on_chunk=chunk,cancel=self.audio.stop_event)
                for line in buffer.feed("",True):put(line)
            except Exception as exc:failure.append(exc)
            finally:put(ending)
        def clauses():
            while not self.audio.stop_event.is_set() and not self.closed.is_set():
                try:item=lines.get(timeout=.05)
                except queue.Empty:continue
                if item is ending:return
                yield item
        producer=threading.Thread(target=generate,daemon=True,name="jarvis-stream-reply");producer.start()
        def show(line):
            self.activity="speaking";self.notify(line,seconds=30)
            if "first_presented_ms" not in self.latency:self.latency["first_presented_ms"]=round((time.monotonic()-started)*1000)
        try:
            if settings.AUTO_SPEAK=="true" and settings.TTS_MODE!="off":self.audio.speak_iter(clauses(),settings,on_line=show)
            else:
                for line in clauses():
                    show(line)
                    if self.audio.stop_event.wait(min(3,max(.5,len(line)/9))):break
            if failure:raise failure[0]
        finally:
            self.presenting=False
            if producer.is_alive():self.audio.stop()
            producer.join(.5)
            self.latency["total_ms"]=round((time.monotonic()-started)*1000)

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

    def send(self,text,*,visual=False):
        if not isinstance(visual,bool):raise ServiceError("绘制模式无效。")
        text=str(text).strip()
        if not text or len(text)>20000:
            raise ServiceError("输入长度需为 1–20000 字。")
        self._interrupt_presentation()
        settings=self.settings
        self.dispatch("reply",lambda:self._reply(text,settings,force_visual=True) if visual else self._reply(text,settings))

    def record(self):
        with self.lock:
            if self.busy and self.kind=="record":
                self.audio.stop()
                return
        self._interrupt_presentation()
        settings=self.settings
        if settings.ASR_MODE=="api":
            self.services.cloud_factory(settings).transcription_client()
        self.audio.prepare()
        def worker():
            self.last_record=self.audio.recording(settings)
            if settings.ASR_MODE=="api":
                with self.lock:
                    self.activity="transcribing"
                text=self.services.cloud_factory(settings).transcribe(self.last_record)
                self._reply(text,settings)
            else:
                self.notify("录音已保存。按 Enter 输入文字，或按 F2 配置语音识别。",seconds=12)
        self.dispatch("record",worker)

    def start_voice(self):
        if self.services.wake_factory and not self.wake:
            self.wake=self.services.wake_factory(audio=self.audio,settings_provider=lambda:self.settings,
                on_wake=self.wake_detected,can_listen=lambda:not self.busy and not self.presenting and not self.closed.is_set())
            self.wake.start()

    def set_wake(self,enabled):
        if not isinstance(enabled,bool):raise ServiceError("唤醒开关格式无效。")
        self.config_save({"WAKE_ENABLED":"true" if enabled else "false"})

    def wake_detected(self):
        settings=self.settings
        if settings.ASR_MODE!="api":
            self.notify("已听到 hi jarvis。请先在 F2 配置语音识别，再说出指令。",True,10);return
        def command():
            self.audio.prepare();self.audio.wake_chime(settings)
            self.notify("我在，请说您的指令。",seconds=20)
            self.last_record=self.audio.command_recording(settings)
            if self.last_record is None:self.notify("没有听到指令，已回到唤醒待机。",seconds=6);return
            self.activity="transcribing"
            text=self.services.cloud_factory(settings).transcribe(self.last_record).strip()
            if not text:self.notify("没有识别到有效指令，请再说 hi jarvis。",seconds=8);return
            self._reply(text,settings)
        try:self.dispatch("record",command)
        except ServiceError:pass

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
            self.services.save_settings(candidate)
            self.settings=candidate
            self.weather.reset(candidate.WEATHER_CITY)
            if candidate.AMAP_DEFAULT_ORIGIN and self.navigation.pending:
                self.navigation.accept("开始导航",candidate.AMAP_CITY,candidate.AMAP_DEFAULT_ORIGIN)
        if self.wake:self.wake.pause();self.wake.resume()
        self.notify("设置已保存。",seconds=5)


    def close(self):
        """Stop workers before releasing their audio resources."""
        self.closed.set()
        self.visual_cancel.set()
        if self.wake:self.wake.close()
        self.audio.stop()
        self.wait_workers(2.0)
        self.audio.close()
