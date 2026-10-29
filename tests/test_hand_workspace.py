"""Independent transferred maps, camera mailbox, display placement and capability tests."""
import json,math,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from urllib import request,error
from unittest.mock import Mock,patch
from jarvis.domain.map_workspace import MapWorkspace
from jarvis.domain.errors import ServiceError
from jarvis.domain.settings import Settings
from jarvis.bootstrap import create_state,create_server
from jarvis.infrastructure.persistence.sqlite import Store
from jarvis.infrastructure.system.paths import ROOT
from jarvis.presentation.desktop.map_windows import choose_display,MapWindows
VIEW={"cityYaw":0,"cityPitch":.62,"cityZoom":1,"cityPanX":0,"cityPanY":0,"cityHeightScale":16}
def snapshot(identifier=2):return {"state":{**VIEW,"mapOpen":True,"mapReady":True},"command":{"id":identifier},"options":[]}
class WorkspaceTests(unittest.TestCase):
 def setUp(self):self.now=0;self.w=MapWorkspace(lambda:self.now);self.w.publish(snapshot())
 def connected(self):
  self.w.request_detach();self.w.replica_ready(self.w.epoch,self.w.transfer_revision)
  for event in ("depart","dispatch","arrive","complete"):self.w.transition(self.w.epoch,event)
 def test_primary_keeps_map_until_destination_ready(self):
  self.w.request_detach();self.assertFalse(self.w.detached);self.w.replica_ready(self.w.epoch,1);self.assertFalse(self.w.detached)
  self.assertEqual(self.w.stage,"prepared");self.w.transition(self.w.epoch,"depart");self.assertFalse(self.w.detached)
  self.w.transition(self.w.epoch,"dispatch");self.assertTrue(self.w.detached)
 def test_primary_new_route_never_replaces_transferred_content(self):
  self.connected();self.w.publish(snapshot(3));self.assertEqual(self.w.replica_poll()["snapshot"]["command"]["id"],2)
 def test_primary_closing_navigation_does_not_close_independent_map(self):
  self.connected();s=snapshot(3);s["state"]["mapOpen"]=False;self.w.publish(s);self.assertTrue(self.w.requested)
 def test_primary_view_changes_never_change_destination_view(self):
  self.connected();self.w.patch_view({"view":{**VIEW,"cityYaw":5}});self.assertEqual(self.w.replica_poll()["snapshot"]["state"]["cityYaw"],0)
 def test_secondary_does_not_require_primary_polling_or_heartbeat(self):
  self.connected();self.now=120;self.assertTrue(self.w.metadata()["requested"]);self.assertFalse(self.w.metadata()["connected"])
 def test_geometry_seed_not_repeated_on_every_poll(self):
  self.connected();self.assertNotIn("snapshot",self.w.replica_poll(1))
 def test_old_window_cannot_acknowledge_a_new_transfer(self):
  self.connected();epoch=self.w.epoch;self.w.close_map();self.w.request_detach()
  with self.assertRaises(ServiceError):self.w.replica_ready(epoch,1)
 def test_old_primary_navigation_cannot_publish(self):
  s=snapshot(1);s["base_revision"]=0
  with self.assertRaises(ServiceError):self.w.publish(s)
 def test_manual_map_without_navigation_id_can_be_transferred_after_a_route(self):
  self.w.publish(snapshot(0));self.w.request_detach();self.assertEqual(self.w.transfer_snapshot["command"]["id"],0)
 def test_camera_queue_bounded_and_consumed_by_secondary_only(self):
  self.connected()
  for i in range(100):self.w.enqueue({"epoch":self.w.epoch,"action":{"type":"pan","dx":.01,"dy":0}})
  self.assertEqual(len(self.w.replica_poll(1)["commands"]),32);self.assertNotIn("commands",self.w.primary_poll())
  self.assertFalse(self.w.replica_poll(1,after=100)["commands"])
 def test_old_camera_session_cannot_control_new_window(self):
  self.connected();epoch=self.w.epoch;self.w.close_map();self.w.request_detach();self.w.replica_ready(self.w.epoch,2)
  with self.assertRaises(ServiceError):self.w.enqueue({"epoch":epoch,"action":{"type":"end"}})
 def test_nonfinite_camera_movement_rejected(self):
  self.connected()
  for value in (math.nan,math.inf,"1",True,1):
   with self.subTest(value=value),self.assertRaises(ServiceError):self.w.enqueue({"epoch":self.w.epoch,"action":{"type":"orbit","dx":value,"dy":0}})
 def test_transferred_snapshot_is_an_independent_copy(self):
  s=snapshot();self.w.publish(s);self.connected();s["state"]["mapReady"]=False;self.w.snapshot["state"]["mapReady"]=False
  self.assertTrue(self.w.transfer_snapshot["state"]["mapReady"])
 def test_existing_independent_map_cannot_be_silently_overwritten(self):
  self.connected()
  with self.assertRaises(ServiceError):self.w.request_detach()
 def test_secondary_close_does_not_restore_old_primary_content(self):
  self.connected();self.w.publish(snapshot(3));self.w.close_map();self.assertEqual(self.w.snapshot["command"]["id"],3);self.assertIsNone(self.w.transfer_snapshot)
 def test_out_of_order_stages_cannot_reveal_map(self):
  self.w.request_detach()
  for event in ("dispatch","arrive","complete"):
   with self.assertRaises(ServiceError):self.w.transition(self.w.epoch,event)
  self.assertFalse(self.w.detached)
 def test_late_ready_does_not_rewind_independent_map(self):
  self.connected();self.w.replica_ready(self.w.epoch,self.w.transfer_revision);self.assertEqual(self.w.stage,"independent")
 def test_gestures_wait_until_assembly_finished(self):
  self.w.request_detach();self.w.replica_ready(self.w.epoch,self.w.transfer_revision)
  for event in ("depart","dispatch","arrive"):self.w.transition(self.w.epoch,event)
  with self.assertRaises(ServiceError):self.w.enqueue({"epoch":self.w.epoch,"action":{"type":"end"}})
class DisplaySelectionTests(unittest.TestCase):
 def test_negative_coordinate_left_monitor_and_direction(self):
  rows=[{"id":0,"left":0,"top":0,"width":1920,"height":1080,"primary":True},{"id":1,"left":-1920,"top":0,"width":1920,"height":1080,"primary":False},{"id":2,"left":1920,"top":0,"width":2560,"height":1440,"primary":False}]
  self.assertEqual(choose_display(rows,direction="left")["id"],1);self.assertEqual(choose_display(rows,direction="right")["id"],2)
 def test_auto_target_uses_assistant_screen_rather_than_os_primary(self):self.assertEqual(choose_display([{"id":0,"primary":True},{"id":1,"primary":False}],source_id=1)["id"],0)
 def test_vertical_display_direction(self):
  rows=[{"id":0,"left":0,"top":0,"width":1920,"height":1080,"primary":True},{"id":1,"left":0,"top":-1080,"width":1920,"height":1080,"primary":False},{"id":2,"left":0,"top":1080,"width":1920,"height":1080,"primary":False}]
  self.assertEqual(choose_display(rows,direction="up")["id"],1);self.assertEqual(choose_display(rows,direction="down")["id"],2)
 def test_single_monitor_regular_window(self):
  row={"id":0,"primary":True};self.assertEqual(choose_display([row]),row)
 def test_disconnected_or_invalid_target_rejected(self):
  for target in (5,True,"0"):
   with self.subTest(target=target),self.assertRaises(ServiceError):choose_display([{"id":0}],target=target)
class NativeWindowLifecycleTests(unittest.TestCase):
 def test_recreated_map_handle_does_not_close_workspace(self):
  window=MapWindows();window.handle=123;window.origin="http://127.0.0.1:12345"
  with patch("jarvis.presentation.desktop.map_windows.C.windll.user32.IsWindow",return_value=0),patch("jarvis.presentation.desktop.map_windows.find_map_window",return_value=456):
   self.assertFalse(window.status()["closed"]);self.assertEqual(window.handle,456)
 def test_transient_missing_handle_has_a_grace_period(self):
  window=MapWindows();window.handle=123;window.origin="http://127.0.0.1:12345"
  with patch("jarvis.presentation.desktop.map_windows.C.windll.user32.IsWindow",return_value=0),patch("jarvis.presentation.desktop.map_windows.find_map_window",return_value=None),patch("jarvis.presentation.desktop.map_windows.time.monotonic",return_value=100) as clock:
   self.assertFalse(window.status()["closed"]);clock.return_value=101;self.assertFalse(window.status()["closed"])
   clock.return_value=102.1;self.assertTrue(window.status()["closed"])
class ReplicaHTTPTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/"tmp");self.addCleanup(self.temp.cleanup)
  self.state=create_state(Settings(),Store(Path(self.temp.name)/"map.sqlite3"));self.server=create_server(self.state)
  self.windows=Mock();self.windows.status.return_value={"error":""};self.city=Mock(return_value={"roads":[],"buildings":[]})
  self.server.services=replace(self.server.services,map_windows=self.windows,city_context=self.city);self.server.start();self.addCleanup(self.server.close)
  self.opener=request.build_opener(request.ProxyHandler({}))
 def call(self,path,body=None,map_role=False):
  return self.opener.open(request.Request(self.server.origin+path,data=None if body is None else json.dumps(body).encode(),headers={"X-Jarvis-Token":self.server.map_token if map_role else self.server.token,"Content-Type":"application/json"}),timeout=3)
 def test_replica_cannot_record_send_configure_stop_quit_or_replace_seed(self):
  for path in ("/api/wake","/api/map/depart","/api/map/dispatch","/api/record","/api/send","/api/stop","/api/config","/api/close","/api/map/publish","/api/map/view","/api/map/detach","/api/map/gesture"):
   with self.subTest(path=path):
    with self.assertRaises(error.HTTPError) as caught:self.call(path,{},True)
    self.assertEqual(caught.exception.code,403);caught.exception.close()
  self.assertFalse(self.state.closed.is_set());self.assertFalse(self.state.busy)
 def test_replica_cannot_read_settings_or_audio_devices(self):
  for path in ("/api/config","/api/devices","/api/state","/api/displays"):
   with self.subTest(path=path),self.assertRaises(error.HTTPError) as caught:self.call(path,map_role=True)
   caught.exception.close()
 def test_map_page_has_own_token_and_blocks_camera_and_microphone(self):
  with self.call("/map") as response:html=response.read().decode();policy=response.headers["Permissions-Policy"]
  self.assertIn(self.server.map_token,html);self.assertNotIn(self.server.token,html);self.assertEqual(policy,"microphone=(), camera=()")
  self.assertNotIn('id="voiceTrigger"',html);self.assertNotIn('id="command"',html)
 def test_primary_supports_local_wasm_worker(self):
  with self.call("/") as response:self.assertIn("wasm-unsafe-eval",response.headers["Content-Security-Policy"]);self.assertIn("camera=(self)",response.headers["Permissions-Policy"])
 def test_replica_can_independently_load_geographic_city_context(self):
  with self.call("/api/city/context",{"path":[[120.6,31.31],[120.61,31.32]]},True):pass
  self.city.assert_called_once()
 def test_secondary_close_is_independent_and_does_not_quit_main(self):
  self.state.map_workspace.publish(snapshot());self.state.map_workspace.request_detach()
  with self.call("/api/map/close",{"epoch":self.state.map_workspace.epoch},True):pass
  self.assertFalse(self.state.closed.is_set());self.windows.close.assert_called()
 def test_primary_publish_does_not_close_independent_native_window(self):
  self.state.map_workspace.publish(snapshot());self.state.map_workspace.request_detach();self.windows.reset_mock()
  s=snapshot(3);s["state"]["mapOpen"]=False
  with self.call("/api/map/publish",s):pass
  self.windows.close.assert_not_called();self.assertTrue(self.state.map_workspace.requested)
 def test_old_window_cannot_close_new_map(self):
  w=self.state.map_workspace;w.publish(snapshot());w.request_detach();epoch=w.epoch;w.close_map();w.request_detach()
  with self.assertRaises(error.HTTPError) as caught:self.call("/api/map/close",{"epoch":epoch},True)
  caught.exception.close();self.assertTrue(w.requested)
 def test_hand_asset_cannot_expose_other_cache_files(self):
  for path in ("/runtime/hand/../space-browser/Local%20State","/runtime/hand/config/.env"):
   with self.subTest(path=path),self.assertRaises(error.HTTPError) as caught:self.call(path)
   caught.exception.close()