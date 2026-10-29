"""Offline wake-only recognizer. Ambient PCM is never saved or uploaded."""
import json
import queue
import threading
import time
from pathlib import Path
from jarvis.domain.voice import WakeMatcher
from jarvis.infrastructure.audio.service import sounddevice,device_id
from jarvis.infrastructure.system.paths import ROOT

class WakeListener:
    def __init__(self,*,audio,settings_provider,on_wake,can_listen):
        self.audio=audio;self.settings_provider=settings_provider;self.on_wake=on_wake;self.can_listen=can_listen
        self.stopped=threading.Event();self.paused=threading.Event();self.released=threading.Event();self.released.set()
        self.thread=None;self.lock=threading.Lock();self.state="starting";self.message="";self.model=None;self.decoder_class=None;self.matcher=WakeMatcher()
    def status(self,state,message=""):
        with self.lock:self.state=state;self.message=message
    def snapshot(self):
        with self.lock:return {"state":self.state,"message":self.message,"phrase":"hi jarvis","local_only":True}
    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True,name="jarvis-local-wake");self.thread.start()
    def pause(self):self.paused.set();self.released.wait(1.5)
    def resume(self):self.paused.clear()
    def close(self):
        self.stopped.set();self.paused.set()
        if self.thread and self.thread is not threading.current_thread():self.thread.join(2)
    def ready(self):
        if self.model is not None:return
        self.status("loading","正在准备本机唤醒词")
        import vosk
        vosk.SetLogLevel(-1)
        path=ROOT/"cache/wake/vosk-model-small-en-us-0.15"
        if not (path/"am/final.mdl").is_file():raise RuntimeError("请先运行 scripts/install_wake.cmd 安装唤醒组件。")
        self.model=vosk.Model(str(path));self.decoder_class=vosk.KaldiRecognizer
    def available(self):
        return not self.stopped.is_set() and not self.paused.is_set() and self.settings_provider().WAKE_ENABLED=="true" and self.can_listen()
    def run(self):
        while not self.stopped.is_set():
            settings=self.settings_provider()
            if settings.WAKE_ENABLED!="true":self.status("disabled");self.stopped.wait(.2);continue
            if not self.available():self.status("paused");self.stopped.wait(.08);continue
            try:
                self.ready()
                if not self.audio.lock.acquire(timeout=.15):continue
                detected=False;self.released.clear()
                try:
                    if not self.available():continue
                    blocks=queue.Queue(maxsize=8)
                    def receive(data,*_args):
                        try:blocks.put_nowait(bytes(data))
                        except queue.Full:
                            try:blocks.get_nowait()
                            except queue.Empty:pass
                    recognizer=self.decoder_class(self.model,16000,json.dumps(["hi jarvis","hey jarvis","high jarvis","[unk]"]))
                    recognizer.SetWords(True);recognizer.SetPartialWords(True)
                    with sounddevice().RawInputStream(samplerate=16000,blocksize=1600,channels=1,dtype="int16",device=device_id(settings.INPUT_DEVICE),callback=receive):
                        self.status("waiting")
                        while self.available():
                            try:block=blocks.get(timeout=.12)
                            except queue.Empty:continue
                            final=recognizer.AcceptWaveform(block)
                            result=json.loads(recognizer.Result() if final else recognizer.PartialResult())
                            if self.matcher.accept(result,time.monotonic(),bool(final)):
                                detected=True;self.status("awakened");break
                finally:self.audio.lock.release();self.released.set()
                if detected and not self.stopped.is_set():self.on_wake();self.stopped.wait(.4)
            except Exception as exc:
                self.released.set()
                message="请先运行 scripts/install_wake.cmd 安装唤醒组件。" if isinstance(exc,ImportError) else str(exc) if isinstance(exc,RuntimeError) else "麦克风唤醒暂不可用，请检查输入设备和权限。"
                self.status("error",message);self.stopped.wait(5)
