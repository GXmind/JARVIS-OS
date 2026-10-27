import ctypes as C
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile,unittest,wave,time
from jarvis.desktop import DesktopState
from jarvis.storage import Store
from unittest.mock import patch
from jarvis.paths import ROOT,initialize
initialize()
from jarvis.native_audio import OutputStream,DONE
from jarvis.navigation import NavigationBridge,parse_navigation
from jarvis.presentation import lines_for_speech
from jarvis.city_data import parse_elements,validated_path
from jarvis.vector_city import varint,rings_of,decode_tile
from jarvis.weather import Weather
from jarvis.audio import Audio
from jarvis.config import Settings

class RevisionTests(unittest.TestCase):
    def test_default_trip_compares_modes(self):
        self.assertEqual(parse_navigation("我要去拙政园")["mode"],"compare")
    def test_explicit_transport_modes(self):
        for text,mode in (("我要去拙政园，步行导航","walking"),("我要去拙政园，公交导航","transit"),("我要去拙政园，打车导航","taxi")):
            self.assertEqual(parse_navigation(text)["mode"],mode)
            self.assertEqual(parse_navigation(text)["destination"],"拙政园")
    def test_navigation_end_with_wake_name_closes(self):
        b=NavigationBridge();b.accept("我要去拙政园","苏州","苏州站")
        self.assertEqual(b.accept("贾维斯，导航结束。","苏州")["action"],"cancel")
        self.assertIsNone(b.active)
    def test_unrelated_topic_emits_close_but_remains_normal_chat(self):
        b=NavigationBridge();b.accept("我要去拙政园","苏州","苏州站")
        self.assertIsNone(b.accept("给我讲个笑话","苏州"))
        self.assertEqual(b.snapshot()["action"],"close")
    def test_transport_followup_preserves_destination(self):
        b=NavigationBridge();b.accept("我要去拙政园","苏州","苏州站")
        result=b.accept("那公共交通怎么去","苏州")
        self.assertEqual((result["destination"],result["mode"]),("拙政园","transit"))
    def test_pending_origin_cleared_by_topic_change(self):
        b=NavigationBridge();b.accept("我要去拙政园","苏州")
        b.accept("今天虎丘天气如何","苏州")
        self.assertIsNone(b.pending)
    def test_caption_split_preserves_order_and_bounded_lines(self):
        text="第一句已经完成。第二句包含很多内容，"+"测试"*40+"。"
        lines=lines_for_speech(text)
        self.assertTrue(all(len(x)<=34 for x in lines))
        self.assertEqual("".join(lines),text)
        self.assertNotIn("\n",lines[0])
    def test_pcm_buffers_queue_before_waiting(self):
        class Driver:
            def __init__(self):self.headers=[];self.resets=0
            def waveOutOpen(self,handle,*args):handle._obj.value=1;return 0
            def waveOutPrepareHeader(self,handle,pointer,size):pointer._obj.flags=0;return 0
            def waveOutWrite(self,handle,pointer,size):self.headers.append(pointer._obj);return 0
            def waveOutUnprepareHeader(self,*args):return 0
            def waveOutReset(self,*args):
                self.resets+=1
                for header in self.headers:header.flags|=DONE
                return 0
            def waveOutClose(self,*args):return 0
            def advance(self,_):
                for header in self.headers:header.flags|=DONE
        driver=Driver()
        backend=SimpleNamespace(lib=driver,native_device=lambda _device,_direction:0)
        with patch("jarvis.native_audio.time.sleep",side_effect=driver.advance):
            with OutputStream(backend,samplerate=24000,channels=1,dtype="int16") as stream:
                for _ in range(4):stream.write(b"\0\0"*2048)
                self.assertEqual(len(driver.headers),4)
                self.assertEqual(driver.resets,0)
                self.assertEqual(stream.pending_frames,8192)
                progress=[];stream.drain(progress.append)
                self.assertEqual(stream.pending_frames,0)
                self.assertAlmostEqual(progress[-1],8192/24000)
    def test_city_path_validates_bounds_and_nonfinite(self):
        for values in ([],[[float("nan"),31]],[[500,31]]):
            with self.assertRaises(Exception):validated_path(values)
    def test_real_building_height_origin_is_explained(self):
        result=parse_elements({"elements":[{"id":1,"type":"way","tags":{"building":"yes"},"geometry":[
         {"lat":31.3,"lon":120.6},{"lat":31.3,"lon":120.601},{"lat":31.301,"lon":120.601},{"lat":31.3,"lon":120.6}]}]})
        self.assertEqual(result["buildings"][0]["height_source"],"estimated")
        self.assertEqual(result["license"],"ODbL")
    def test_pbf_reader_rejects_truncated_data(self):
        with self.assertRaises(ValueError):varint(b"\x80",0)
        with self.assertRaises(ValueError):rings_of(b"\x09")
    def test_huqiu_live_weather_is_not_replaced_by_model(self):
        weather=Weather("苏州虎丘区")
        weather.accept_live({"adcode":"320505","temperature":"19","humidity":"72","weather":"多云","windPower":"≤3","reporttime":"2026-10-27 00:00:00"})
        result=weather.snapshot(False)
        self.assertEqual(result["adcode"],"320505")
        self.assertIn("高德",result["source"])
        self.assertIsNone(result["wind"])
        self.assertEqual(result["wind_power"],"≤3")
    def test_other_district_live_weather_is_not_accepted(self):
        weather=Weather("苏州虎丘区");weather.data=None
        weather.accept_live({"adcode":"320508","temperature":"19","humidity":"72"})
        self.assertIsNone(weather.data)
    def test_new_text_interrupts_previous_line_presentation(self):
        with tempfile.TemporaryDirectory(dir=ROOT/"tmp") as temp:
            state=DesktopState(Settings(),Store(Path(temp)/"test.sqlite3"))
            with patch.object(state.conversation,"reply",side_effect=[("第一段。第二段要等待。",None),("新的回答。",None)]):
                state.send("第一条消息")
                deadline=time.monotonic()+2
                while not state.presenting and time.monotonic()<deadline:time.sleep(.01)
                self.assertTrue(state.presenting)
                state.send("换个话题")
                deadline=time.monotonic()+2
                while state.busy and time.monotonic()<deadline:time.sleep(.01)
                self.assertEqual(state.snapshot()["subtitle"],"新的回答。")
            state.audio.close()

    def test_minimal_real_vector_tile_building_decodes(self):
        def vi(value):
            out=bytearray()
            while value>127:out.append((value&127)|128);value>>=7
            out.append(value);return bytes(out)
        def field(n,value):
            return vi((n<<3)|2)+vi(len(value))+value
        # MoveTo(0,0), LineTo(100,0)(100,100)(0,100), ClosePath.
        geom=b"".join(vi(v) for v in (9,0,0,26,200,0,0,200,199,0,15))
        feature=vi(8)+vi(42)+vi(24)+vi(3)+field(4,geom)
        layer=field(1,b"building")+field(2,feature)+vi(40)+vi(4096)+vi(120)+vi(2)
        result=decode_tile(field(3,layer),13600,6690,14)
        self.assertEqual(len(result["buildings"]),1)
        self.assertEqual(len(result["buildings"][0]["footprint"]),5)
        self.assertGreater(result["buildings"][0]["height"],0)

    def test_camelcase_live_weather_timestamp(self):
        weather=Weather("苏州虎丘区")
        weather.accept_live({"adcode":"320505","temperature":"17","humidity":"84","reportTime":"2026-10-27 09:32:00"})
        self.assertEqual(weather.snapshot(False)["observation"],"2026-10-27 09:32:00")

    def test_expired_district_observation_is_marked_stale(self):
        weather=Weather("苏州虎丘区")
        weather.accept_live({"adcode":"320505","temperature":"17","humidity":"84"})
        weather.live_received-=901
        self.assertEqual(weather.snapshot(False)["status"],"stale")
