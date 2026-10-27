from pathlib import Path
import json
import tempfile
import threading
import time
import unittest
from urllib import request,error
from unittest.mock import patch

from jarvis.paths import ROOT,initialize
initialize()
from jarvis.config import Settings
from jarvis.desktop import DesktopState,DesktopServer
from jarvis.storage import Store

class SpaceDesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/"tmp")
        self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/"space.sqlite3")
        self.state=DesktopState(Settings(API_KEY="test-local-secret"),self.store)
        self.server=DesktopServer(self.state)
        self.server.start()
        self.addCleanup(self.server.close)
        self.opener=request.build_opener(request.ProxyHandler({}))

    def get(self,path,token=True):
        headers={"X-Jarvis-Token":self.server.token} if token else {}
        return self.opener.open(request.Request(self.server.origin+path,headers=headers),timeout=3)

    def post(self,path,data,origin=None):
        headers={"X-Jarvis-Token":self.server.token,"Content-Type":"application/json"}
        if origin:
            headers["Origin"]=origin
        return self.opener.open(request.Request(self.server.origin+path,
            data=json.dumps(data).encode(),headers=headers),timeout=3)

    def test_requires_per_run_token(self):
        with self.assertRaises(error.HTTPError) as ctx:
            self.get("/api/state",False)
        self.assertEqual(ctx.exception.code,403)
        ctx.exception.close()

    def test_rejects_cross_origin_commands(self):
        with self.assertRaises(error.HTTPError) as ctx:
            self.post("/api/send",{"text":"cross-origin"},"https://example.com")
        self.assertEqual(ctx.exception.code,403)
        ctx.exception.close()
        self.assertFalse(self.state.busy)

    def test_secret_never_returned_to_renderer(self):
        with self.get("/api/config") as response:
            values=json.load(response)
        self.assertEqual(values["API_KEY"],"")
        self.assertTrue(values["KEY_PRESENT"])
        self.assertNotIn("test-local-secret",json.dumps(values))

    def test_static_paths_cannot_read_config(self):
        with self.assertRaises(error.HTTPError) as ctx:
            self.get("/config/.env")
        self.assertEqual(ctx.exception.code,404)
        ctx.exception.close()

    def test_text_dispatch_history_and_morph_state(self):
        started,release=threading.Event(),threading.Event()
        original=self.state.conversation.reply
        def delayed(*args):
            started.set();release.wait(3);return original(*args)
        with patch.object(self.state.conversation,"reply",side_effect=delayed):
            with self.post("/api/send",{"text":"你好"}):
                pass
            self.assertTrue(started.wait(1))
            self.assertEqual(self.state.snapshot()["phase"],"dialogue")
            self.assertEqual(self.state.snapshot()["activity"],"thinking")
            release.set()
            deadline=time.monotonic()+3
            while self.state.busy and time.monotonic()<deadline:
                time.sleep(.02)
        self.assertEqual(len(self.store.history(self.state.sid)),2)
        self.assertTrue(self.state.snapshot()["subtitle"])
        self.assertLessEqual(len(self.state.snapshot()["subtitle"]),34)

    def test_microphone_stop_routes_to_existing_capture(self):
        self.state.busy=True
        self.state.kind="record"
        self.state.audio.capture_active=True
        with self.post("/api/record",{}):
            pass
        self.assertTrue(self.state.audio.stop_event.is_set())

    def test_close_action_stops_main_loop(self):
        with self.post("/api/close",{}):
            pass
        self.assertTrue(self.state.closed.is_set())

    def test_empty_key_preserves_saved_secret(self):
        with patch("jarvis.desktop.save_settings") as save:
            self.state.config_save({"API_KEY":"","CHAT_MODE":"mock"})
        self.assertEqual(save.call_args.args[0].API_KEY,"test-local-secret")