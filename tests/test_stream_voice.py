import io,json,tempfile,threading,time,unittest,wave
from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from jarvis.infrastructure.audio.service import Audio
from jarvis.infrastructure.audio.sequence import trim_padding
from jarvis.infrastructure.http.openai_compatible import CloudAPI
from jarvis.domain.settings import Settings
from jarvis.domain.text import SpeechChunks
from jarvis.domain.errors import ServiceError
class SpeechRules(unittest.TestCase):
 def test_chunk_split_never_waits_for_full_answer(self):
  c=SpeechChunks();self.assertEqual(c.feed("你好"),[]);self.assertEqual(c.feed("。下一"),["你好。"]);self.assertEqual(c.feed("句。"),["下一句。"]);self.assertEqual(c.feed("尾句",True),["尾句"])
 def test_no_punctuation_is_bounded(self):
  c=SpeechChunks();out=c.feed("字"*130);out+=c.feed("",True);self.assertEqual("".join(out),"字"*130);self.assertTrue(all(len(x)<=48 for x in out))
 def test_trim_preserves_non_silent_samples_and_short_tail(self):
  pcm=array("h",[0]*4800+[1000]*2400+[0]*9600).tobytes();out=array("h",trim_padding(pcm,24000,1));self.assertEqual(sum(x==1000 for x in out),2400);self.assertEqual(len(out),600+2400+2400)
class StreamingAPI(unittest.TestCase):
 def gateway(self,data,mime="text/event-stream"):
  g=CloudAPI(Settings(API_BASE_URL="http://127.0.0.1:1/v1",API_KEY="test-key"));response=io.BytesIO(data);response.headers={"Content-Type":mime};g.opener=Mock();g.opener.open.return_value=response;return g
 def test_only_content_not_reasoning_is_exposed(self):
  events=[{"choices":[{"index":0,"delta":{"reasoning_content":"hidden"}}]},{"choices":[{"index":0,"delta":{"content":"你好"}}]},{"choices":[{"index":0,"delta":{"content":"先生。"},"finish_reason":"stop"}]}]
  raw=b"".join(b"data: "+json.dumps(e,ensure_ascii=False).encode()+b"\n\n" for e in events)+b"data: [DONE]\n\n";g=self.gateway(raw)
  self.assertEqual(list(g.chat_stream([])),["你好","先生。"])
 def test_incomplete_stream_is_not_success(self):
  raw=b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
  with self.assertRaises(ServiceError):list(self.gateway(raw).chat_stream([]))
 def test_json_provider_can_ignore_stream_flag(self):
  g=self.gateway(json.dumps({"choices":[{"message":{"content":"你好"}}]}).encode(),"application/json");self.assertEqual(list(g.chat_stream([])),["你好"])
 def test_cancel_suppresses_future_chunks(self):
  e=threading.Event();e.set();self.assertEqual(list(self.gateway(b'data: [DONE]\n').chat_stream([],e)),[])
class ContinuousOutput(unittest.TestCase):
 def test_first_clip_plays_before_later_text_and_one_device_opens(self):
  audio=Audio();settings=Settings(TTS_MODE="windows");release=threading.Event();opened=threading.Event();writes=[];lines=[];opens=[]
  class Stream:
   pending_frames=0
   def __init__(self,**kwargs):opens.append(kwargs)
   def __enter__(self):opened.set();release.set();return self
   def write(self,pcm):writes.append(pcm)
   def drain(self,progress):pass
   def __exit__(self,*args):pass
  def synth(text,path,*args):
   value=1000 if text=="第一句。" else 2000
   with wave.open(str(path),"wb") as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(array("h",[value]*4800).tobytes())
  def chunks():
   yield "第一句。"
   if not release.wait(2):raise RuntimeError("Playback waited for complete answer")
   yield "第二句。"
  audio._tts=SimpleNamespace(synthesize=synth,close=lambda:None)
  with patch("jarvis.infrastructure.audio.service.sounddevice",return_value=SimpleNamespace(RawOutputStream=Stream)):audio.speak_iter(chunks(),settings,lines.append)
  self.assertTrue(opened.is_set());self.assertEqual(len(opens),1);self.assertEqual(lines,["第一句。","第二句。"]);self.assertEqual(audio.speech_metrics["device_opens"],1);self.assertFalse(audio.lock.locked());audio.close()
 def test_generation_failure_releases_output_lock(self):
  a=Audio();a._tts=SimpleNamespace(synthesize=Mock(side_effect=ServiceError("failure")),close=lambda:None)
  with self.assertRaises(ServiceError):a.speak_iter(iter(["测试"]),Settings(TTS_MODE="windows"))
  self.assertFalse(a.lock.locked());a.close()

class StreamCancellation(unittest.TestCase):
 def test_cancel_unblocks_a_waiting_socket(self):
  from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
  started=threading.Event();finish=threading.Event();stop=threading.Event();errors=[]
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_POST(self):
    self.rfile.read(int(self.headers["Content-Length"]));self.send_response(200);self.send_header("Content-Type","text/event-stream");self.end_headers()
    self.wfile.write(b'data: {"choices":[{"delta":{"content":"ready"}}]}\n\n');self.wfile.flush();finish.wait(3)
  server=ThreadingHTTPServer(("127.0.0.1",0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
  gateway=CloudAPI(Settings(API_BASE_URL="http://127.0.0.1:"+str(server.server_port),API_KEY="local-test"))
  def consume():
   try:
    for chunk in gateway.chat_stream([],stop):started.set()
   except Exception as exc:errors.append(exc)
  thread=threading.Thread(target=consume,daemon=True);thread.start()
  try:self.assertTrue(started.wait(1));stop.set();thread.join(1.5);self.assertFalse(thread.is_alive());self.assertFalse(errors)
  finally:finish.set();server.shutdown();server.server_close()

class ResponseMode(unittest.TestCase):
 def test_fast_mode_disables_deepseek_default_reasoning(self):
  g=CloudAPI(Settings(API_BASE_URL="https://api.deepseek.com",API_MODEL="deepseek-flash"));self.assertEqual(g.chat_payload([],True)["thinking"],{"type":"disabled"})
 def test_other_providers_do_not_receive_deepseek_parameters(self):
  g=CloudAPI(Settings(API_BASE_URL="https://example.com/v1",API_MODEL="custom"));self.assertNotIn("thinking",g.chat_payload([],True));self.assertNotIn("reasoning_effort",g.chat_payload([],False))
 def test_provider_default_can_be_preserved(self):
  g=CloudAPI(Settings(API_BASE_URL="https://api.deepseek.com",API_MODEL="deepseek-flash",RESPONSE_MODE="provider"));self.assertNotIn("thinking",g.chat_payload([],True))
