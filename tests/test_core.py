"""Offline tests: no real credentials, microphone, cloud charges or production DB."""
from dataclasses import replace
import http.server
import json
import logging
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

from jarvis.infrastructure.system.paths import ROOT, initialize, local_path
initialize()
from jarvis.infrastructure.http.openai_compatible import CloudAPI
from jarvis.domain.errors import ServiceError
from jarvis.infrastructure.audio.service import Audio
from jarvis.domain.settings import Settings, api_base
from jarvis.infrastructure.config.env_file import load_settings, save_settings
from jarvis.domain.emotion import RuleEmotion
from jarvis.infrastructure.system.logging import SecretFilter
from jarvis.application.conversation import Conversation
from jarvis.infrastructure.persistence.sqlite import Store

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tmp")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.store = Store(self.path / "test.sqlite3")

    def test_paths_reject_escape(self):
        self.assertEqual(local_path(ROOT / "tmp"), ROOT / "tmp")
        with self.assertRaises(ValueError):
            local_path(ROOT / "../outside.txt")

    def test_all_temporary_files_under_root(self):
        self.assertTrue(Path(tempfile.gettempdir()).is_relative_to(ROOT))

    def test_config_round_trip_secrets_and_unicode(self):
        path = self.path / ".env"
        secret = 'test-secret-$()#你好"\\literal'
        settings = Settings(API_KEY=secret)
        save_settings(settings, path)
        self.assertEqual(load_settings(path).API_KEY, secret)

    def test_bad_config_stays_untouched(self):
        path = self.path / ".env"
        original = 'API_KEY="unfinished\n'
        path.write_text(original, encoding="utf-8")
        with self.assertRaises(ValueError):
            load_settings(path)
        self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_endpoint_validation(self):
        self.assertEqual(api_base("https://example.com/v1/chat/completions/"), "https://example.com/v1")
        for url in ("http://example.com/v1", "https://user:key@example.com/v1",
                    "https://example.com/v1?key=secret", "file:///tmp", "https://example.com:bad"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                api_base(url)

    def test_cloud_requires_explicit_configuration(self):
        for cfg in (Settings(CHAT_MODE="api"), Settings(ASR_MODE="api"), Settings(TTS_MODE="api")):
            with self.assertRaises(ValueError):
                cfg.validated()

    def test_invalid_device_and_duration(self):
        for cfg in (Settings(INPUT_DEVICE="-1"), Settings(MAX_RECORD_SECONDS="999"),
                    Settings(REQUEST_TIMEOUT="nope"), Settings(AUTO_SPEAK="yes")):
            with self.assertRaises(ValueError):
                cfg.validated()

    def test_sqlite_sessions_and_persistence(self):
        first, second = self.store.new_session(), self.store.new_session()
        self.store.add_message(first, "user", "你好")
        self.store.add_message(first, "assistant", "收到")
        self.store.add_message(second, "user", "另一会话")
        reopened = Store(self.path / "test.sqlite3")
        self.assertEqual([item["content"] for item in reopened.history(first)], ["你好", "收到"])
        self.assertEqual(len(reopened.history(second)), 1)

    def test_sqlite_rollback_and_foreign_key(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.add_message("missing", "user", "orphan")

    def test_explicit_memory_and_delete(self):
        sid = self.store.new_session()
        service = Conversation(self.store,cloud_factory=CloudAPI)
        service.reply(sid, "我喜欢咖啡", Settings())
        self.assertEqual(self.store.memories(), [])
        service.reply(sid, "/记住 我喜欢咖啡", Settings())
        memories = self.store.memories()
        self.assertEqual(memories[0][1], "我喜欢咖啡")
        self.assertEqual(self.store.recall("咖啡"), ["我喜欢咖啡"])
        self.store.forget(memories[0][0])
        self.assertEqual(self.store.memories(), [])

    def test_emotion_explained_and_not_trained(self):
        state = RuleEmotion().infer("谢谢，今天很开心")
        self.assertEqual(state.label, "积极")
        self.assertIn("开心", state.reason)
        self.assertFalse(state.trained_model)
        self.assertEqual(RuleEmotion().infer("明天的安排").label, "中性")

    def test_mock_never_calls_cloud(self):
        sid = self.store.new_session()
        with patch.object(CloudAPI, "chat", side_effect=AssertionError("No cloud")):
            reply, state = Conversation(self.store,cloud_factory=CloudAPI).reply(sid, "你好", Settings())
        self.assertIn("模拟", reply)
        self.assertEqual(len(self.store.history(sid)), 2)

    def test_cloud_context_contains_explicit_memory(self):
        sid = self.store.new_session()
        self.store.remember("用户喜欢喝咖啡")
        cfg = Settings(API_BASE_URL="https://example.com/v1", API_KEY="test-only", API_MODEL="test-model", CHAT_MODE="api")
        with patch.object(CloudAPI, "chat", return_value="好的") as call:
            answer, _ = Conversation(self.store,cloud_factory=CloudAPI).reply(sid, "咖啡", cfg)
        self.assertEqual(answer, "好的")
        messages = call.call_args.args[0]
        self.assertIn("咖啡", messages[1]["content"])
        self.assertEqual(messages[-1], {"role": "user", "content": "咖啡"})

    def test_api_failure_keeps_user_history(self):
        sid = self.store.new_session()
        cfg = Settings(API_BASE_URL="https://example.com/v1", API_KEY="test-only", API_MODEL="test-model", CHAT_MODE="api")
        with patch.object(CloudAPI, "chat", side_effect=ServiceError("测试错误")):
            with self.assertRaises(ServiceError):
                Conversation(self.store,cloud_factory=CloudAPI).reply(sid, "请回复", cfg)
        self.assertEqual(self.store.history(sid), [{"role": "user", "content": "请回复"}])

    def test_secret_log_redaction(self):
        record = logging.LogRecord("jarvis", logging.INFO, "", 0, "Bearer abc123 sk-test-secret", (), None)
        SecretFilter().filter(record)
        self.assertNotIn("abc123", record.getMessage())
        self.assertNotIn("sk-test-secret", record.getMessage())

    def test_missing_audio_is_actionable(self):
        from jarvis.infrastructure.audio.service import sounddevice
        import builtins
        real_import = builtins.__import__
        def no_sd(name, *args, **kwargs):
            if name == "sounddevice":
                raise ImportError()
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=no_sd), patch("jarvis.infrastructure.audio.winmm.WinMM", side_effect=OSError()), self.assertRaisesRegex(ServiceError, "文字"):
            sounddevice()

    def test_native_fallback_without_optional_package(self):
        import builtins
        from jarvis.infrastructure.audio.service import sounddevice
        real_import = builtins.__import__
        marker = object()
        def no_sd(name, *args, **kwargs):
            if name == "sounddevice":
                raise ImportError()
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=no_sd), patch("jarvis.infrastructure.audio.winmm.WinMM", return_value=marker):
            self.assertIs(sounddevice(), marker)

    def test_native_device_mapping_rejects_wrong_direction(self):
        from jarvis.infrastructure.audio.winmm import WinMM, MAPPER
        backend = object.__new__(WinMM)
        backend.rows = [{"native_id": 7, "direction": "in"}]
        self.assertEqual(backend.native_device(None, "out"), MAPPER)
        self.assertEqual(backend.native_device(0, "in"), 7)
        with self.assertRaises(ServiceError):
            backend.native_device(0, "out")
        with self.assertRaises(ServiceError):
            backend.native_device(100, "in")

    def test_native_windows_structure_sizes(self):
        import ctypes
        from jarvis.infrastructure.audio.winmm import WaveFormat, Header, InputCaps, OutputCaps
        self.assertEqual(ctypes.sizeof(WaveFormat), 18)
        self.assertEqual(ctypes.sizeof(Header), 48 if ctypes.sizeof(ctypes.c_void_p) == 8 else 32)
        self.assertEqual(ctypes.sizeof(InputCaps), 80)
        self.assertEqual(ctypes.sizeof(OutputCaps), 84)

    def test_playback_uses_selected_output_and_stop(self):
        path = self.path / "audio.wav"
        with wave.open(str(path), "wb") as file:
            file.setnchannels(1)
            file.setsampwidth(2)
            file.setframerate(16000)
            file.writeframes(b"\x00\x00" * 2000)
        class Stream:
            kwargs = None
            writes = 0
            def __init__(self, **kwargs):
                Stream.kwargs = kwargs
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def write(self, block):
                Stream.writes += 1
        class FakeSD:
            RawOutputStream = Stream
        audio = Audio()
        with patch("jarvis.infrastructure.audio.service.sounddevice", return_value=FakeSD):
            audio.play(path, Settings(OUTPUT_DEVICE="3"))
        self.assertEqual(Stream.kwargs["device"], 3)
        self.assertGreater(Stream.writes, 0)
        audio.stop()
        Stream.writes = 0
        with patch("jarvis.infrastructure.audio.service.sounddevice", return_value=FakeSD):
            audio.play(path, Settings())
        self.assertEqual(Stream.writes, 0)

    def test_recording_uses_device_and_wav(self):
        class Stream:
            kwargs = None
            def __init__(self, **kwargs):
                Stream.kwargs = kwargs
                self.callback = kwargs["callback"]
            def __enter__(self):
                self.callback(b"\x01\x00" * 4000, 4000, None, False)
                audio.stop()
                return self
            def __exit__(self, *args):
                pass
        class FakeSD:
            RawInputStream = Stream
        audio = Audio()
        with patch("jarvis.infrastructure.audio.service.sounddevice", return_value=FakeSD):
            output = audio.recording(Settings(INPUT_DEVICE="2"))
        self.addCleanup(output.unlink)
        with wave.open(str(output)) as file:
            self.assertEqual(file.getnframes(), 4000)
            self.assertEqual(file.getframerate(), 16000)
        self.assertEqual(Stream.kwargs["device"], 2)

class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.received = []
        cls.mode = "ok"
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                cls.received.append((self.path, self.headers, body))
                if cls.mode == "unauthorized":
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b"secret-provider-error")
                    return
                if cls.mode == "redirect":
                    self.send_response(307)
                    self.send_header("Location", "/redirect-target")
                    self.end_headers()
                    return
                self.send_response(200)
                self.end_headers()
                if cls.mode == "malformed":
                    self.wfile.write(b"not-json")
                elif self.path.endswith("/audio/transcriptions"):
                    self.wfile.write(json.dumps({"text": "测试语音"}).encode())
                elif self.path.endswith("/audio/speech"):
                    import io
                    buffer = io.BytesIO()
                    with wave.open(buffer, "wb") as wav:
                        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
                        wav.writeframes(b"\0\0" * 100)
                    self.wfile.write(buffer.getvalue())
                else:
                    self.wfile.write(json.dumps({"choices": [{"message": {"content": "模拟云端"}}]}).encode())
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        type(self).mode = "ok"
        type(self).received.clear()
        self.cfg = Settings(API_BASE_URL=f"http://127.0.0.1:{self.server.server_port}/v1",
                            API_MODEL="test-model", ASR_MODEL="test-asr", TTS_MODEL="test-tts",
                            API_KEY="unit-test-not-a-real-key", CHAT_MODE="api")
        self.api = CloudAPI(self.cfg)

    def test_chat_wire_contract(self):
        self.assertEqual(self.api.chat([{"role": "user", "content": "你好"}]), "模拟云端")
        path, headers, body = self.received[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer unit-test-not-a-real-key")
        self.assertEqual(json.loads(body)["model"], "test-model")
        self.assertFalse(json.loads(body)["stream"])

    def test_http_error_does_not_leak_server_body(self):
        type(self).mode = "unauthorized"
        with self.assertRaises(ServiceError) as context:
            self.api.chat([])
        self.assertIn("401", str(context.exception))
        self.assertNotIn("secret-provider", str(context.exception))
        self.assertNotIn(self.cfg.API_KEY, str(context.exception))

    def test_malformed_response(self):
        type(self).mode = "malformed"
        with self.assertRaisesRegex(ServiceError, "JSON"):
            self.api.chat([])

    def test_redirect_never_forwards_token(self):
        type(self).mode = "redirect"
        with self.assertRaises(ServiceError):
            self.api.chat([])
        self.assertEqual(len(self.received), 1)

    def test_audio_upload_contract(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as temp:
            file = Path(temp) / "input.wav"
            file.write_bytes(b"RIFF-test-fixture")
            self.assertEqual(self.api.transcribe(file), "测试语音")
        path, headers, body = self.received[0]
        self.assertEqual(path, "/v1/audio/transcriptions")
        self.assertIn("multipart/form-data", headers["Content-Type"])
        self.assertIn(b'filename="recording.wav"', body)
        self.assertIn(b"test-asr", body)

    def test_speech_wav_saved_locally(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as temp:
            file = Path(temp) / "out.wav"
            self.api.synthesize("测试", file)
            with wave.open(str(file)) as wav:
                self.assertEqual(wav.getframerate(), 16000)
        self.assertEqual(self.received[0][0], "/v1/audio/speech")

if __name__ == "__main__":
    unittest.main()