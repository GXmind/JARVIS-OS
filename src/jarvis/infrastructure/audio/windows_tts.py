"""One reusable system synthesizer process. Text is data sent through JSON, never shell code."""
import json,queue,subprocess,threading,time
from pathlib import Path
from jarvis.domain.errors import ServiceError
from jarvis.infrastructure.system.paths import ROOT,local_path
class WindowsSynthesizer:
 def __init__(self):self.process=None;self.responses=queue.Queue();self.lock=threading.Lock();self.guard=threading.Lock();self.closed=threading.Event()
 def _stop(self):
  with self.guard:
   process=self.process;self.process=None
   if process and process.poll() is None:
    process.kill()
    try:process.wait(timeout=2)
    except subprocess.TimeoutExpired:pass
 def _start(self):
  if self.closed.is_set():raise ServiceError("语音引擎已关闭。")
  if self.process and self.process.poll() is None:return
  self.responses=queue.Queue();responses=self.responses
  process=subprocess.Popen(["powershell.exe","-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",str(Path(__file__).with_name("tts_worker.ps1"))],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding="utf-8",creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
  self.process=process
  if self.closed.is_set():self._stop();raise ServiceError("语音引擎已关闭。")
  def read():
   try:
    for line in process.stdout:
     try:responses.put(json.loads(line))
     except ValueError:continue
   finally:responses.put({"error":True})
  threading.Thread(target=read,daemon=True,name="jarvis-system-voice-reader").start()
  try:message=responses.get(timeout=15)
  except queue.Empty:self._stop();raise ServiceError("Windows 语音引擎准备超时。") from None
  if not message.get("ready"):self._stop();raise ServiceError("Windows 语音引擎不可用，请检查中文语音包。")
 def warmup(self):
  with self.lock:self._start()
 def synthesize(self,text,output,stop,closed):
  with self.lock:
   if stop.is_set() or closed.is_set():return
   self._start();process=self.process
   try:
    process.stdin.write(json.dumps({"text":str(text)[:2000],"output":str(local_path(output))},ensure_ascii=False)+"\n");process.stdin.flush()
    deadline=time.monotonic()+45
    while True:
     if stop.is_set() or closed.is_set() or time.monotonic()>deadline:self._stop();raise ServiceError("语音生成已停止或超时。")
     try:message=self.responses.get(timeout=.05);break
     except queue.Empty:continue
    if not message.get("ok") or not output.is_file():raise ServiceError("Windows 语音生成失败，请检查中文语音包。")
   except (BrokenPipeError,OSError):self._stop();raise ServiceError("系统语音连接中断，请重试。") from None
 def close(self):self.closed.set();self._stop()
