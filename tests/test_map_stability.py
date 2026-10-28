from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
import tempfile,threading,time,unittest
from jarvis.infrastructure.system.paths import ROOT
from jarvis.domain.settings import Settings
from jarvis.bootstrap import create_state, create_server
from jarvis.presentation.desktop.window import run
from jarvis.infrastructure.persistence.sqlite import Store

class MapStabilityTests(unittest.TestCase):
 def test_delayed_renderer_does_not_close_an_existing_window(self):
  class Closed:
   def __init__(self):self.calls=0
   def wait(self,_seconds):
    self.calls+=1
    return self.calls>=4
   def set(self):pass
  event=Closed()
  state=SimpleNamespace(closed=event,window_handle=123,connected=True,last_seen=0,
                        weather=SimpleNamespace(snapshot=lambda:None))
  server=MagicMock();server.origin="http://127.0.0.1:12345";server.port=12345
  process=MagicMock();process.pid=100
  with tempfile.TemporaryDirectory(dir=ROOT/"tmp") as folder:
   target=Path(folder);(target/"tmp").mkdir()
   with patch("jarvis.presentation.desktop.window.ROOT",target),patch("jarvis.presentation.desktop.window.browser_path",return_value=Path("test-browser.exe")),patch("jarvis.presentation.desktop.window.subprocess.Popen",return_value=process),patch("jarvis.presentation.desktop.window.time.monotonic",return_value=1000),patch("ctypes.windll.user32.IsWindow",return_value=1),patch("ctypes.windll.user32.PostMessageW"):
    self.assertEqual(run(state,server),0)
  self.assertEqual(event.calls,4,"An old heartbeat must not terminate a live window")
  server.close.assert_called_once()

 def test_worker_owns_audio_until_it_has_stopped(self):
  with tempfile.TemporaryDirectory(dir=ROOT/"tmp") as folder:
   state=create_state(Settings(),Store(Path(folder)/"test.sqlite3"))
   started=threading.Event()
   def work():
    started.set();state.audio.stop_event.wait(2)
   state.dispatch("record",work);self.assertTrue(started.wait(1))
   self.assertEqual(len(state.worker_threads),1)
   state.audio.stop();state.wait_workers(2)
   self.assertFalse(state.worker_threads)
   state.audio.close()

 def test_server_waits_for_audio_worker_before_releasing_audio(self):
  with tempfile.TemporaryDirectory(dir=ROOT/"tmp") as folder:
   state=create_state(Settings(),Store(Path(folder)/"test.sqlite3"))
   server=create_server(state);server.start()
   entered=threading.Event()
   def work():entered.set();state.audio.stop_event.wait(2)
   state.dispatch("record",work);self.assertTrue(entered.wait(1))
   with patch.object(state.audio,"close",side_effect=lambda:self.assertFalse(state.worker_threads)):
    server.close()
   state.audio.close()
