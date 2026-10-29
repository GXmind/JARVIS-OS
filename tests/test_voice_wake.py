"""Deterministic wake/endpoint/one-command orchestration. No microphone/cloud required."""
from array import array
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
import tempfile,threading,unittest
from jarvis.domain.voice import WakeMatcher,VoiceEndpoint
from jarvis.domain.settings import Settings
from jarvis.bootstrap import create_state
from jarvis.infrastructure.persistence.sqlite import Store
from jarvis.infrastructure.system.paths import ROOT

def result(text="hi jarvis",conf=.95,final=True):
 return {"text" if final else "partial":text,"result" if final else "partial_result":[{"word":w,"conf":conf} for w in text.split()]}
class MatcherTests(unittest.TestCase):
 def test_final_confidence_and_cooldown(self):
  m=WakeMatcher();self.assertFalse(m.accept(result(conf=.3),0,True));self.assertTrue(m.accept(result(),1,True));self.assertFalse(m.accept(result(),2,True));self.assertTrue(m.accept(result("hey jarvis"),5,True))
 def test_partial_must_be_stable(self):
  m=WakeMatcher();self.assertFalse(m.accept(result(final=False),0));self.assertFalse(m.accept(result(final=False),.1));self.assertTrue(m.accept(result(final=False),.2))
 def test_substring_unrelated_or_unknown_never_wakes(self):
  for text in ("hi jarvison","jarvis","hello computer","[unk]","this is a test"):
   self.assertFalse(WakeMatcher().accept(result(text),0,True))
 def test_without_word_confidence_never_wakes(self):self.assertFalse(WakeMatcher().accept({"text":"hi jarvis"},0,True))
class EndpointTests(unittest.TestCase):
 def block(self,value):return array("h",[value]*1600).tobytes()
 def test_timeout_does_not_start_from_noise(self):
  e=VoiceEndpoint(16000,timeout=3)
  for i in range(31):decision=e.feed(self.block(70),i*.1)
  self.assertFalse(e.started);self.assertEqual(decision,"timeout")
 def test_speech_ends_after_silence(self):
  e=VoiceEndpoint(16000,silence=.7)
  self.assertEqual(e.feed(self.block(1500),.1),"start")
  for i in range(2,12):e.feed(self.block(1600),i*.1)
  self.assertEqual(e.feed(self.block(0),1.4),"speech");self.assertEqual(e.feed(self.block(0),1.9),"end")
 def test_maximum_bounds_continuous_audio(self):
  e=VoiceEndpoint(16000,maximum=2);e.feed(self.block(1500),0)
  self.assertEqual(e.feed(self.block(1500),2.1),"end")
class WakeSessionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT/"tmp");self.addCleanup(self.tmp.cleanup)
  self.state=create_state(Settings(ASR_MODE="api",ASR_MODEL="test-asr",ASR_BASE_URL="https://example.com/v1",ASR_API_KEY="local-test-key",AUTO_SPEAK="false"),Store(Path(self.tmp.name)/"voice.sqlite3"))
  self.audio=Mock();self.audio.command_recording.return_value=Path(self.tmp.name)/"command.wav"
  self.wake=Mock();self.gateway=Mock();self.gateway.transcribe.return_value="你好"
  self.state.audio=self.audio;self.state.wake=self.wake;self.state._reply=Mock()
  self.writer=Mock();self.state.services=replace(self.state.services,cloud_factory=Mock(return_value=self.gateway),save_settings=self.writer)
  self.addCleanup(self.state.close)
 def test_one_wake_one_command_then_resume(self):
  self.state.wake_detected();self.state.wait_workers(2)
  self.wake.pause.assert_called_once();self.wake.resume.assert_called_once();self.audio.wake_chime.assert_called_once()
  self.gateway.transcribe.assert_called_once_with(self.audio.command_recording.return_value);self.state._reply.assert_called_once_with("你好",self.state.settings)
  self.assertFalse(self.state.busy)
 def test_no_speech_never_calls_cloud(self):
  self.audio.command_recording.return_value=None;self.state.wake_detected();self.state.wait_workers(2);self.state.services.cloud_factory.assert_not_called();self.state._reply.assert_not_called()
 def test_missing_asr_produces_setting_hint(self):
  self.state.settings=replace(self.state.settings,ASR_MODE="off");self.state.wake_detected();self.audio.command_recording.assert_not_called();self.assertIn("F2",self.state.subtitle)
 def test_both_success_and_error_release_wake_pause(self):
  self.audio.command_recording.side_effect=RuntimeError("device");self.state.wake_detected();self.state.wait_workers(2);self.wake.resume.assert_called_once();self.assertFalse(self.state.busy)
 def test_busy_cannot_start_second_wake_command(self):
  self.state.busy=True;self.state.wake_detected();self.audio.command_recording.assert_not_called();self.state.busy=False
 def test_switch_is_saved_through_injected_writer(self):
  self.state.set_wake(False);self.assertEqual(self.writer.call_args.args[0].WAKE_ENABLED,"false")
 def test_close_stops_listener_before_audio(self):
  manager=Mock();manager.attach_mock(self.wake,"wake");manager.attach_mock(self.audio,"audio");self.state.close()
  names=[call[0] for call in manager.mock_calls];self.assertLess(names.index("wake.close"),names.index("audio.close"))
