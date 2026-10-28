"""Speech provider routing tests; only loopback traffic, never user recordings or keys."""
from dataclasses import replace
from pathlib import Path
import http.server
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
from jarvis.infrastructure.system.paths import ROOT, initialize
initialize()
from jarvis.infrastructure.http.openai_compatible import CloudAPI
from jarvis.domain.errors import ServiceError
from jarvis.domain.settings import Settings
from jarvis.infrastructure.config.env_file import load_settings, save_settings
from jarvis.bootstrap import create_state
from jarvis.infrastructure.persistence.sqlite import Store

class SpeechProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests=[]
        cls.status=200
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=self.rfile.read(int(self.headers.get("Content-Length","0")))
                cls.requests.append((self.path,self.headers.get("Authorization"),body))
                self.send_response(cls.status);self.end_headers()
                if cls.status!=200:
                    self.wfile.write(b"private-provider-error-body")
                elif self.path.endswith("/audio/transcriptions"):
                    self.wfile.write(json.dumps({"text":"我要去拙政园"}).encode())
                else:
                    self.wfile.write(json.dumps({"choices":[{"message":{"content":"收到"}}]}).encode())
        cls.server=http.server.ThreadingHTTPServer(("127.0.0.1",0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=3)

    def setUp(self):
        type(self).status=200;self.requests.clear()
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/"tmp")
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)
        self.wav=self.path/"fixture.wav";self.wav.write_bytes(b"RIFF-test-fixture")
        self.origin=f"http://127.0.0.1:{self.server.server_port}"
        self.settings=Settings(API_BASE_URL=self.origin+"/chat/v1",API_KEY="chat-key-test",
                               API_MODEL="test-chat",CHAT_MODE="api",
                               ASR_MODE="api",ASR_BASE_URL=self.origin+"/speech/v1",
                               ASR_API_KEY="speech-key-test",ASR_MODEL="test-transcriber")

    def test_chat_and_speech_use_separate_endpoints_and_credentials(self):
        cfg=self.settings.validated()
        api=CloudAPI(cfg)
        self.assertEqual(api.chat([{"role":"user","content":"你好"}]),"收到")
        self.assertEqual(api.transcribe(self.wav),"我要去拙政园")
        chat,speech=self.requests
        self.assertEqual(chat[:2],("/chat/v1/chat/completions","Bearer chat-key-test"))
        self.assertEqual(speech[:2],("/speech/v1/audio/transcriptions","Bearer speech-key-test"))
        self.assertIn(b"test-transcriber",speech[2])
        self.assertNotIn(b"test-chat",speech[2])

    def test_speech_only_configuration_does_not_require_chat_service(self):
        cfg=Settings(ASR_MODE="api",ASR_BASE_URL=self.origin+"/v1",
                     ASR_API_KEY="speech-key-test",ASR_MODEL="test-transcriber").validated()
        self.assertEqual(CloudAPI(cfg).transcribe(self.wav),"我要去拙政园")

    def test_chat_key_never_falls_back_to_explicit_speech_provider(self):
        cfg=replace(self.settings,ASR_API_KEY="")
        with self.assertRaisesRegex(ValueError,"独立识别密钥"):cfg.validated()
        with self.assertRaises(ServiceError):CloudAPI(cfg).transcribe(self.wav)
        self.assertEqual(self.requests,[])

    def test_existing_single_provider_configuration_remains_compatible(self):
        cfg=replace(self.settings,ASR_BASE_URL="",ASR_API_KEY="")
        self.assertEqual(CloudAPI(cfg).transcribe(self.wav),"我要去拙政园")
        self.assertEqual(self.requests[0][:2],("/chat/v1/audio/transcriptions","Bearer chat-key-test"))

    def test_pasted_full_transcription_endpoint_is_normalized(self):
        cfg=replace(self.settings,ASR_BASE_URL=self.origin+"/v1/audio/transcriptions/")
        CloudAPI(cfg).transcribe(self.wav)
        self.assertEqual(self.requests[0][0],"/v1/audio/transcriptions")

    def test_deepseek_speech_rejected_before_network_or_file_access(self):
        cfg=Settings(API_BASE_URL="https://api.deepseek.com",API_MODEL="deepseek-flash",
                     API_KEY="chat-test",CHAT_MODE="api",ASR_MODE="api",ASR_MODEL="deepseek-flash")
        # Keep existing settings loadable so valid text chat is not lost.
        cfg.validated()
        with patch.object(CloudAPI,"_post",side_effect=AssertionError("No cloud upload")):
            with self.assertRaisesRegex(ServiceError,"不提供录音转文字"):
                CloudAPI(cfg).transcribe(self.path/"nonexistent.wav")

    def test_deepseek_record_button_reports_configuration_before_capture(self):
        cfg=replace(self.settings,ASR_BASE_URL="https://api.deepseek.com",ASR_MODEL="deepseek-flash")
        state=create_state(cfg,Store(self.path/"test.sqlite3"))
        with patch.object(state.audio,"prepare") as prepare,patch.object(state.audio,"recording") as recording:
            with self.assertRaisesRegex(ServiceError,"F2"):state.record()
        prepare.assert_not_called();recording.assert_not_called()

    def test_transcription_404_identifies_speech_stage_without_secret_body(self):
        type(self).status=404
        with self.assertRaises(ServiceError) as caught:
            CloudAPI(self.settings).transcribe(self.wav)
        text=str(caught.exception)
        self.assertIn("语音识别",text);self.assertIn("/audio/transcriptions",text)
        self.assertNotIn("private-provider",text);self.assertNotIn("speech-key-test",text)

    def test_independent_key_is_masked_and_empty_save_preserves_it(self):
        state=create_state(self.settings,Store(self.path/"test.sqlite3"))
        config=state.config_public()
        self.assertEqual(config["ASR_API_KEY"],"")
        self.assertTrue(config["ASR_API_KEY_PRESENT"])
        self.assertNotIn("speech-key-test",json.dumps(config))
        with patch("jarvis.bootstrap.save_settings") as save:
            state.config_save({"ASR_API_KEY":""})
        self.assertEqual(save.call_args.args[0].ASR_API_KEY,"speech-key-test")

    def test_speech_configuration_roundtrip(self):
        path=self.path/".env"
        save_settings(self.settings,path)
        loaded=load_settings(path)
        self.assertEqual((loaded.ASR_BASE_URL,loaded.ASR_API_KEY),
                         (self.settings.ASR_BASE_URL,self.settings.ASR_API_KEY))

    def test_speech_key_control_characters_rejected(self):
        with self.assertRaises(ValueError):
            replace(self.settings,ASR_API_KEY="invalid\nkey").validated()

    def test_speech_provider_insecure_remote_url_rejected(self):
        with self.assertRaises(ValueError):
            replace(self.settings,ASR_BASE_URL="http://example.com/v1").validated()