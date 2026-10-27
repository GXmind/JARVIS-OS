import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from urllib import request,error,parse
from unittest.mock import patch
from jarvis.paths import ROOT,initialize
initialize()
from jarvis.config import Settings
from jarvis.desktop import DesktopState,DesktopServer
from jarvis.navigation import map_config,parse_navigation,NavigationBridge,build_proxy_url,proxy_authorized,normalize_proxy_response
from jarvis.storage import Store
from jarvis.api import ServiceError,CloudAPI

class NavigationTests(unittest.TestCase):
    def test_missing_credentials_is_not_a_mock_map(self):
        config=map_config(Settings())
        self.assertFalse(config["configured"])
        self.assertEqual(config["key"],"")
        self.assertIn("F2",config["message"])

    def test_public_map_config_never_returns_security_code(self):
        config=map_config(Settings(AMAP_JS_KEY="test-js-key",AMAP_SECURITY_JSCODE="test-security-code"))
        self.assertTrue(config["configured"])
        self.assertEqual(config["key"],"test-js-key")
        self.assertNotIn("test-security-code",json.dumps(config))

    def test_route_intent(self):
        result=parse_navigation("请导航从苏州站到拙政园。")
        self.assertEqual((result["origin"],result["destination"],result["mode"]),("苏州站","拙政园","compare"))

    def test_walking_intent(self):
        result=parse_navigation("步行导航从苏州站到拙政园")
        self.assertEqual(result["mode"],"walking")

    def test_missing_origin_stays_missing(self):
        result=parse_navigation("导航到金鸡湖")
        self.assertEqual(result["origin"],"")
        self.assertEqual(result["destination"],"金鸡湖")

    def test_non_navigation_text_stays_conversation(self):
        self.assertIsNone(parse_navigation("解释一下导航的定义"))
        self.assertIsNone(parse_navigation("今天很开心"))

    def test_open_map_intent(self):
        self.assertEqual(parse_navigation("打开高德地图")["action"],"open")

    def test_navigation_event_ids(self):
        bridge=NavigationBridge()
        self.assertEqual(bridge.accept("打开地图","苏州")["id"],1)
        self.assertIsNone(bridge.accept("普通对话","苏州"))
        self.assertEqual(bridge.accept("导航从甲地到乙地","苏州")["id"],3)

    def test_jarvis_phrase_uses_saved_origin(self):
        result=parse_navigation("贾维斯，我要去拙政园，帮我规划路线。","苏州","苏州站")
        self.assertEqual((result["origin"],result["destination"]),("苏州站","拙政园"))

    def test_wait_for_origin_then_continue(self):
        bridge=NavigationBridge()
        result=bridge.accept("贾维斯，我要去金鸡湖，帮我规划路线","苏州")
        self.assertEqual(result["action"],"await_origin")
        result=bridge.accept("从苏州站出发","苏州")
        self.assertEqual((result["action"],result["origin"],result["destination"]),("route","苏州站","金鸡湖"))
        self.assertIsNone(bridge.pending)

    def test_setting_origin_resumes_pending_route(self):
        bridge=NavigationBridge()
        bridge.accept("我要去金鸡湖","苏州")
        self.assertEqual(bridge.accept("开始导航","苏州","苏州站")["origin"],"苏州站")

    def test_cancel_route_without_pending_origin(self):
        bridge=NavigationBridge()
        bridge.accept("我要去金鸡湖","苏州","苏州站")
        self.assertEqual(bridge.accept("取消导航","苏州")["action"],"cancel")
        self.assertIsNone(bridge.pending)

    def test_common_origin_length_is_validated(self):
        with self.assertRaises(ValueError):
            Settings(AMAP_DEFAULT_ORIGIN="地"*121).validated()

    def test_proxy_jsonp_uses_javascript_mime_for_nosniff(self):
        body=b'__amap_callback__({"status":"1","info":"OK"});'
        output,mime=normalize_proxy_response(body,"application/json","callback=__amap_callback__")
        self.assertEqual(output,body)
        self.assertEqual(mime,"text/javascript; charset=utf-8")

    def test_proxy_plain_json_keeps_original_mime(self):
        body=b'{"status":"1"}'
        self.assertEqual(normalize_proxy_response(body,"application/json","key=test"),(body,"application/json"))

    def test_proxy_error_json_is_delivered_to_sdk_callback(self):
        body=b'{"status":"0","info":"INVALID_USER_KEY"}'
        output,mime=normalize_proxy_response(body,"application/json","callback=AMap.callback")
        self.assertTrue(output.startswith(b"AMap.callback("))
        self.assertIn(b"INVALID_USER_KEY",output)
        self.assertIn("javascript",mime)

    def test_proxy_callback_cannot_inject_code(self):
        with self.assertRaises(ServiceError):
            normalize_proxy_response(b'{}',"application/json","callback=alert(1)")

    def test_proxy_injects_only_server_credentials(self):
        settings=Settings(AMAP_JS_KEY="actual-key",AMAP_SECURITY_JSCODE="actual-secret")
        url=build_proxy_url("/_AMapService/v3/direction/driving","key=attacker&jscode=wrong&origin=120,31",settings)
        parts=parse.urlsplit(url)
        self.assertEqual(parts.hostname,"restapi.amap.com")
        query=parse.parse_qs(parts.query)
        self.assertEqual(query["key"],["actual-key"])
        self.assertEqual(query["jscode"],["actual-secret"])

    def test_styles_use_the_documented_style_host(self):
        url=build_proxy_url("/_AMapService/v4/map/styles","id=test",Settings(AMAP_JS_KEY="key",AMAP_SECURITY_JSCODE="secret"))
        self.assertEqual(parse.urlsplit(url).hostname,"webapi.amap.com")

    def test_proxy_cannot_forward_arbitrary_hosts_or_paths(self):
        config=Settings(AMAP_JS_KEY="key",AMAP_SECURITY_JSCODE="secret")
        for path in ("/_AMapService/https://evil.test","/_AMapService/v3/../config",
                     "/_AMapService/v3/%2e%2e/secret","/_AMapService//evil.test/a","/elsewhere/v3/search"):
            with self.subTest(path=path),self.assertRaises(ServiceError):
                build_proxy_url(path,"",config)

    def test_proxy_requires_cookie_and_local_origin(self):
        headers={"Host":"127.0.0.1:1234","Cookie":"jarvis_map_gate=run-token"}
        self.assertTrue(proxy_authorized(headers,"run-token","http://127.0.0.1:1234",1234))
        self.assertFalse(proxy_authorized({**headers,"Origin":"https://evil.test"},"run-token","http://127.0.0.1:1234",1234))
        self.assertFalse(proxy_authorized({"Host":"127.0.0.1:1234"},"run-token","http://127.0.0.1:1234",1234))

    def test_map_credentials_reject_control_characters(self):
        with self.assertRaises(ValueError):
            Settings(AMAP_SECURITY_JSCODE="secret\ninvalid").validated()

class MapHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/"tmp")
        self.addCleanup(self.temp.cleanup)
        settings=Settings(API_KEY="chat-private",AMAP_JS_KEY="js-public",AMAP_SECURITY_JSCODE="map-private")
        self.state=DesktopState(settings,Store(Path(self.temp.name)/"maps.sqlite3"))
        self.server=DesktopServer(self.state)
        self.server.start()
        self.addCleanup(self.server.close)
        self.opener=request.build_opener(request.ProxyHandler({}))

    def get(self,path,headers=None):
        return self.opener.open(request.Request(self.server.origin+path,headers=headers or {}),timeout=3)

    def test_settings_mask_all_credentials(self):
        with self.get("/api/config",{"X-Jarvis-Token":self.server.token}) as response:
            config=json.load(response)
        self.assertEqual(config["API_KEY"],"")
        self.assertEqual(config["AMAP_JS_KEY"],"")
        self.assertEqual(config["AMAP_SECURITY_JSCODE"],"")
        self.assertTrue(config["AMAP_SECURITY_JSCODE_PRESENT"])

    def test_map_config_requires_session_token(self):
        with self.assertRaises(error.HTTPError) as caught:
            self.get("/api/map/config")
        self.assertEqual(caught.exception.code,403)
        caught.exception.close()

    def test_map_config_contains_no_cloud_or_map_secret(self):
        with self.get("/api/map/config",{"X-Jarvis-Token":self.server.token}) as response:
            body=response.read().decode()
        self.assertNotIn("chat-private",body)
        self.assertNotIn("map-private",body)
        self.assertIn("js-public",body)

    def test_configured_map_allows_documented_sdk_renderer_scripts(self):
        with self.get("/") as response:
            csp=response.headers["Content-Security-Policy"]
        self.assertIn("https://jsapi-service.amap.com",csp)
        self.assertIn("script-src-elem 'self' 'unsafe-inline'",csp)
        self.assertIn("script-src-attr 'none'",csp)
        self.assertNotIn("script-src *",csp)

    def test_unconfigured_map_keeps_strict_script_policy(self):
        self.state.settings=replace(self.state.settings,AMAP_JS_KEY="",AMAP_SECURITY_JSCODE="")
        with self.get("/") as response:
            csp=response.headers["Content-Security-Policy"]
        self.assertNotIn("'unsafe-inline'",csp)
        self.assertNotIn("jsapi-service.amap.com",csp)

    def test_root_sets_httponly_cookie_for_sdk_proxy(self):
        with self.get("/") as response:
            cookie=response.headers.get("Set-Cookie")
        self.assertIn("HttpOnly",cookie)
        self.assertIn("SameSite=Strict",cookie)
        self.assertIn("Path=/_AMapService",cookie)

    def test_proxy_without_cookie_never_contacts_provider(self):
        with patch("jarvis.desktop.fetch_proxy") as upstream:
            with self.assertRaises(error.HTTPError) as caught:
                self.get("/_AMapService/v3/direction/driving")
            self.assertEqual(caught.exception.code,403)
            caught.exception.close()
            upstream.assert_not_called()

    def test_authenticated_sdk_proxy_wiring(self):
        with patch("jarvis.desktop.fetch_proxy",return_value=(b'{"status":"1"}',"application/json")) as upstream:
            with self.get("/_AMapService/v3/direction/driving?origin=120,31",
                          {"Cookie":"jarvis_map_gate="+self.server.token}) as response:
                self.assertEqual(json.load(response)["status"],"1")
            self.assertEqual(upstream.call_args.args[0],"/_AMapService/v3/direction/driving")

    def test_empty_settings_preserve_map_credentials(self):
        with patch("jarvis.desktop.save_settings") as save:
            self.state.config_save({"AMAP_JS_KEY":"","AMAP_SECURITY_JSCODE":""})
        self.assertEqual(save.call_args.args[0].AMAP_JS_KEY,"js-public")
        self.assertEqual(save.call_args.args[0].AMAP_SECURITY_JSCODE,"map-private")

    def test_saving_common_origin_resumes_conversation_request(self):
        self.state.navigation.accept("我要去金鸡湖","苏州")
        with patch("jarvis.desktop.save_settings") as save:
            self.state.config_save({"AMAP_DEFAULT_ORIGIN":"苏州站"})
        self.assertEqual(save.call_args.args[0].AMAP_DEFAULT_ORIGIN,"苏州站")
        event=self.state.navigation.snapshot()
        self.assertEqual((event["action"],event["origin"],event["destination"]),("route","苏州站","金鸡湖"))

    def test_navigation_prompt_uses_enabled_voice_output(self):
        settings=replace(self.state.settings,AUTO_SPEAK="true",TTS_MODE="windows")
        with patch.object(self.state.audio,"prepare"),patch.object(self.state.audio,"speak") as speak:
            self.state._reply("贾维斯，我要去金鸡湖，帮我规划路线",settings)
        self.assertIn("从哪里出发",speak.call_args.args[0])
        self.assertEqual(speak.call_count,1)

    def test_navigation_does_not_wait_for_chat_model(self):
        self.state.settings=replace(self.state.settings,CHAT_MODE="api",API_BASE_URL="https://example.com/v1",API_MODEL="test")
        with patch.object(CloudAPI,"chat",side_effect=AssertionError("Should not call model")):
            self.state._reply("导航从苏州站到拙政园",self.state.settings)
        self.assertEqual(self.state.navigation.snapshot()["destination"],"拙政园")
        self.assertEqual(len(self.state.store.history(self.state.sid)),2)