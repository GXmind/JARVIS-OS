import json,math,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from jarvis.domain.center import validate_plan,preset,intent,decode_plan
from jarvis.domain.errors import ServiceError
from jarvis.domain.settings import Settings
from jarvis.bootstrap import create_state
from jarvis.infrastructure.persistence.sqlite import Store
from jarvis.infrastructure.system.paths import ROOT
class SceneRules(unittest.TestCase):
 def test_presets_have_bounded_finite_primitives(self):
  for text in ("生成一个太阳系","创建一个火箭","画一辆汽车","用粒子展示DNA双螺旋","生成一个爱心","生成一个银河","生成一个立方体","展示地球模型","用粒子写出‘你好’"):
   with self.subTest(text=text):self.assertTrue(intent(text));self.assertTrue(validate_plan(preset(text))["nodes"])
 def test_tutorial_and_writing_are_not_models(self):
  for text in ("如何建模汽车","给我生成一个文章方案","写一篇文章","今天你好"):
   self.assertIsNone(intent(text))
 def test_arbitrary_explicit_object_can_use_cloud(self):
  self.assertEqual(intent("创建一只蝴蝶")["action"],"show");self.assertIsNone(preset("创建一只蝴蝶"))
 def test_invalid_shape_coordinates_and_budget_rejected(self):
  for value in ({"nodes":[]},{"nodes":[{"shape":"eval"}]},{"nodes":[{"shape":"sphere","scale":[1,0,1]}]},{"nodes":[{"shape":"sphere","position":[math.nan,0,0]}]},{"nodes":[{"shape":"box"}]*33},{"nodes":[{"shape":"box"}],"speed":True}):
   with self.subTest(value=value),self.assertRaises(ServiceError):validate_plan(value)
 def test_executable_text_is_not_a_scene(self):
  with self.assertRaises(ServiceError):decode_plan("import os; os.system('example')")
 def test_pause_color_and_explosion_are_explicit(self):
  self.assertTrue(intent("暂停动画",True)["paused"]);self.assertEqual(intent("把它改成粉色",True)["color"],"rose");self.assertEqual(intent("让它散开",True)["explode"],1)
 def test_paused_plan_survives_validation(self):
  self.assertTrue(validate_plan({"nodes":[{"shape":"box"}],"paused":True})["paused"])
class CenterSession(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=ROOT/"tmp");self.addCleanup(self.temp.cleanup);self.state=create_state(Settings(),Store(Path(self.temp.name)/"center.sqlite3"));self.addCleanup(self.state.close);self.state._speak_answer=Mock()
 def test_show_update_close_and_history(self):
  self.state._reply("生成一个火箭",self.state.settings);before=self.state.center["build"];self.assertTrue(self.state.center["active"])
  self.state._reply("暂停动画",self.state.settings);self.assertEqual(self.state.center["build"],before);self.assertTrue(self.state.center["plan"]["paused"])
  self.state._reply("让它散开",self.state.settings);self.assertEqual(self.state.center["explode"],1)
  self.state._reply("恢复能量体",self.state.settings);self.assertFalse(self.state.center["active"]);self.assertEqual(len(self.state.store.history(self.state.sid)),8)
 def test_late_cloud_design_cannot_reopen_closed_scene(self):
  started=threading.Event();finish=threading.Event()
  def design(*args):started.set();finish.wait(2);return preset("火箭"),"cloud"
  with patch("jarvis.application.session.SceneDesigner.design",side_effect=design):
   self.state.send("创建一只蝴蝶");self.assertTrue(started.wait(1));self.state.close_center();finish.set();self.state.wait_workers(2)
  self.assertFalse(self.state.center["active"])
 def test_missing_cloud_never_invents_an_unknown_model(self):
  with self.assertRaises(ServiceError):self.state._reply("创建一只蝴蝶",self.state.settings)
  self.assertFalse(self.state.center["active"])

class FreePromptTests(unittest.TestCase):
 def test_cloud_never_substitutes_a_car_preset(self):
  from jarvis.application.center import SceneDesigner
  prompt="请绘制一辆绿色三轮敞篷汽车，车尾有两只白色翅膀，背景有七颗星星。"
  gateway=Mock();gateway.chat.return_value=json.dumps({"nodes":[{"shape":"drawing","paths":[{"d":"M 1 1 L 50 50","color":"#00ff00"}]}],"motion":"none"})
  factory=Mock(return_value=gateway);plan,source=SceneDesigner(factory).design(prompt,Settings(CHAT_MODE="api"))
  self.assertEqual(source,"cloud");self.assertEqual(gateway.chat.call_args.args[0][-1]["content"],prompt);self.assertEqual(plan["nodes"][0]["shape"],"drawing")
 def test_general_surfaces_and_paths_are_data_not_programs(self):
  from jarvis.domain.center import validate_plan
  shapes=[{"shape":"curve","points":[[0,0,0],[1,1,0]],"radius":.02},{"shape":"lathe","profile":[[0,0],[1,1],[.5,2]]},{"shape":"patch","control":[[i%4/3,i//4/3,.1] for i in range(16)]},{"shape":"mesh","vertices":[[0,0,0],[1,0,0],[0,1,0]],"faces":[[0,1,2]]}]
  self.assertEqual(len(validate_plan({"nodes":shapes})["nodes"]),4)
  with self.assertRaises(ServiceError):validate_plan({"nodes":[{"shape":"drawing","paths":[{"d":"javascript:alert(1)"}]}]})
 def test_edits_preserve_previous_scene_as_reference(self):
  from jarvis.application.center import SceneDesigner
  g=Mock();g.chat.return_value=json.dumps({"nodes":[{"shape":"sphere"}]});old=preset("火箭")
  SceneDesigner(Mock(return_value=g)).design("给它加一双弯曲的翅膀",Settings(CHAT_MODE="api"),old)
  self.assertEqual(json.loads(g.chat.call_args.args[0][1]["content"]),old)
 def test_forced_prompt_needs_no_keyword(self):
  with tempfile.TemporaryDirectory(dir=ROOT/"tmp") as temp:
   state=create_state(Settings(),Store(Path(temp)/"free.sqlite3"));state._speak_answer=Mock()
   with patch("jarvis.application.session.SceneDesigner.design",return_value=(preset("银河"),"cloud")) as design:
    state.send("紫色星海中的鲸鱼，尾巴摆动",visual=True);state.wait_workers(2);self.assertTrue(state.center["active"]);self.assertEqual(design.call_args.args[0],"紫色星海中的鲸鱼，尾巴摆动")
   state.close()

class DetailedPromptRegression(unittest.TestCase):
 def test_local_controls_never_swallow_detailed_requests(self):
  for text in ("把鲸鱼身体改成蓝色，尾巴保持粉色","画一个散开的红色星球，周围有环形星云","让蝴蝶的翅膀快一点，身体保持不动"):
   command=intent(text,True);self.assertEqual(command["action"],"show");self.assertEqual(command["prompt"],text)

class FreeDrawingCompatibility(unittest.TestCase):
 def test_fill_only_svg_path_can_use_zero_stroke_width(self):
  plan=validate_plan({"nodes":[{"shape":"drawing","paths":[{"d":"M 0 0 L 10 0 L 10 10 Z","fill":True,"width":0}]}]})
  self.assertFalse(plan["nodes"][0]["paths"][0]["stroke"])

class CenterSnapshotBudget(unittest.TestCase):
 def test_unchanged_geometry_is_not_repeated_on_each_state_poll(self):
  with tempfile.TemporaryDirectory(dir=ROOT/"tmp") as temp:
   state=create_state(Settings(),Store(Path(temp)/"snapshot.sqlite3"));state._speak_answer=Mock();state._reply("生成一个火箭",state.settings)
   first=state.snapshot();self.assertIn("plan",first["center"]);second=state.snapshot(first["center"]["id"]);self.assertNotIn("plan",second["center"]);self.assertTrue(second["center"]["same"])
   state._reply("暂停动画",state.settings);self.assertIn("plan",state.snapshot(first["center"]["id"])["center"]);state.close()

class SurfaceCompatibility(unittest.TestCase):
 def test_grid_and_flat_control_points_normalize_to_one_schema(self):
  grid=[[[x/3,y/3,.2] for x in range(4)] for y in range(4)]
  a=validate_plan({"nodes":[{"shape":"patch","control":grid}]})["nodes"][0]
  b=validate_plan({"nodes":[{"shape":"patch","control_points":[point for row in grid for point in row]}]})["nodes"][0]
  self.assertEqual(a["control"],b["control"]);self.assertEqual(a["rows"],4);self.assertEqual(a["cols"],4)
 def test_quadratic_patch_and_explicit_keyframes_are_supported(self):
  points=[[x/2,y/2,.2] for y in range(3) for x in range(3)]
  node=validate_plan({"nodes":[{"shape":"patch","control":points,"keyframes":[{"time":0,"rotation":[0,0,0]},{"time":1,"rotation":[0,0,.3]}]}]})["nodes"][0]
  self.assertEqual(node["rows"],3);self.assertEqual(node["frames"][1]["turn"],[0,0,.3])

class DrawingSubjectFreedom(unittest.TestCase):
 def test_explicit_drawing_does_not_restrict_subject_words(self):
  for text in ("画一幅诗歌的意境","画一张代码架构图","我想画一个故事中的城市"):
   self.assertEqual(intent(text)["action"],"show")
