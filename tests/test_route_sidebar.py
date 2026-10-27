from dataclasses import replace
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from jarvis.paths import ROOT,initialize
initialize()
from jarvis.navigation import NavigationBridge,parse_navigation
from jarvis.config import Settings
from jarvis.desktop import DesktopState
from jarvis.storage import Store
from jarvis.api import CloudAPI

class RouteSidebarTests(unittest.TestCase):
    def test_exact_reported_taxi_phrase(self):
        command=parse_navigation("帮我规划从苏州工业园区站到虎丘景区的路线，打车前往","苏州","另一个默认起点")
        self.assertEqual((command["origin"],command["destination"],command["mode"]),("苏州工业园区站","虎丘景区","taxi"))
        self.assertEqual(command["origin_source"],"explicit")

    def test_implicit_start_uses_saved_f2_address(self):
        for text in ("我要去虎丘景区","导航到虎丘景区","去虎丘景区","到虎丘景区怎么走","帮我规划去虎丘景区"):
            with self.subTest(text=text):
                command=parse_navigation(text,"苏州","F2 常用地址")
                self.assertEqual((command["origin"],command["destination"]),("F2 常用地址","虎丘景区"))
                self.assertEqual(command["origin_source"],"saved")

    def test_explicit_origin_does_not_overwrite_next_default(self):
        bridge=NavigationBridge()
        bridge.accept("帮我规划从苏州站到虎丘景区的路线","苏州","F2 地址")
        result=bridge.accept("我要去拙政园","苏州","F2 地址")
        self.assertEqual(result["origin"],"F2 地址")

    def test_transport_suffix_never_becomes_part_of_destination(self):
        for suffix in ("，打车前往","，坐公交车前往","，乘坐公共交通前往","，自驾过去","，步行前往"):
            with self.subTest(suffix=suffix):
                command=parse_navigation("帮我规划从苏州站到虎丘景区的路线"+suffix)
                self.assertEqual(command["destination"],"虎丘景区")

    def test_exact_bug_phrase_bypasses_chat_model(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"tmp") as folder:
            cfg=Settings(API_BASE_URL="https://api.deepseek.com",API_KEY="unit-test",API_MODEL="deepseek-flash",CHAT_MODE="api",AMAP_DEFAULT_ORIGIN="F2 地址")
            state=DesktopState(cfg,Store(Path(folder)/"test.sqlite3"))
            with patch.object(CloudAPI,"chat",side_effect=AssertionError("Navigation must not go to chat")),patch.object(state,"_speak_answer"):
                state._reply("帮我规划从苏州工业园区站到虎丘景区的路线，打车前往",cfg)
            self.assertEqual(state.navigation.snapshot()["destination"],"虎丘景区")
            self.assertEqual(state.navigation.snapshot()["mode"],"taxi")

    def test_saving_unrelated_setting_does_not_close_active_route(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"tmp") as folder:
            state=DesktopState(Settings(AMAP_DEFAULT_ORIGIN="F2 地址"),Store(Path(folder)/"test.sqlite3"))
            state.navigation.accept("我要去虎丘景区","苏州","F2 地址")
            before=state.navigation.snapshot()
            with patch("jarvis.desktop.save_settings"):
                state.config_save({"WEATHER_CITY":"苏州虎丘区"})
            self.assertEqual(state.navigation.snapshot(),before)