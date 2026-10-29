"""Prompt-driven particle drawing and modeling; cloud output is data, never code."""
import json
from dataclasses import replace
from jarvis.domain.center import preset,decode_plan
from jarvis.domain.errors import ServiceError
SCENE_PROMPT="""你是自由提示词驱动的粒子绘图、概念建模和动画设计器。必须完整遵循用户给出的主体、数量、颜色、构图、形态、细节和动作，不按关键词替换成固定模板。只输出一个JSON对象，无Markdown、程序或URL。颜色可为任意#RRGGBB，默认银河靛蓝/紫/粉。二维画图优先用自由SVG路径drawing，三维建模可自由组合curve/patch/mesh/lathe和基础几何，不能只依靠几个预设对象。
格式：{"title":"简短中文名","motion":"rotate","speed":1,"nodes":[...]}
最多32节点，位置最好在[-3,3]，合法[-8,8]，scale为3个[.01,6]的数，rotation为3个[-6.3,6.3]弧度，color可任意#RRGGBB或galaxy/violet/rose/gold/ice。
节点类型：
1. drawing: {"shape":"drawing","viewBox":[0,0,512,512],"paths":[{"d":"M 50 80 C 120 10 160 180 240 100 Z","color":"#88aaff","fill":true,"stroke":true,"width":1.2}]}。d仅SVG路径M/L/H/V/C/S/Q/T/A/Z及其小写，最多64路径，每条6000字符。请设计完整可辨识的自由轮廓与内部细节，使用多条路径、填色和光线。二维作品全局motion通常none；不要画一个框或写字代替主体。
2. curve: points为2–128个三维控制点，radius .002–2，closed布尔；采样平滑空间管线，可绘轮廓、触须、树枝。
3. patch: control为数字三维控制点，推荐4×4点阵，支持2–8行×2–8列Bezier曲面；可给二维点阵，或一维点数组并含rows/cols，可绘自由弯曲的翅膀、花瓣、尾鳍、外壳。
4. mesh: vertices为3–2048个三维顶点，faces为1–4096个三角面索引，例如[[0,1,2]]，用于自由多面造型。
5. lathe: profile为2–128个[半径,Y]剖面点，半径0–6、Y[-8,8]，沿Y旋转成任意轮廓曲面。
6. sphere/box/torus/cone/cylinder/helix/heart/galaxy/wave/text可作为辅助；box尺度为半尺寸，cylinder/cone沿Y，torus在XZ面；text含text最多24字。
节点motion为none/spin/orbit/bob/flap/flow/pulse，orbit围绕原点，flap让左右翅膀绕原点开合，flow产生喷流；全局motion为none/rotate/pulse/wave/orbit/fly，speed[.1,3]。构件须充分体现用户动作。二维绘图避免默认旋转导致侧面消失。若上下文有已有场景，按本条提示词编辑它，保留未要求改变的细节。节点还可提供自由动画frames：2–8个关键帧，例如[{"t":0,"move":[0,0,0],"turn":[0,0,0],"stretch":[1,1,1]},{"t":2,"turn":[0,0,0.4]},{"t":4,"turn":[0,0,0]}]。t从0开始递增至最多30秒，move/turn/stretch是相对基础姿态的平移/弧度旋转/缩放；loop默认true。pivot可指定世界坐标铰点（翅根、尾根等），未指定时使用position。用关键帧真实表达用户动作，不能用整体旋转代替局部摆动。所有坐标必须是明确的数字数组，不得输出表达式、代码、公式、省略号或占位符。输出是粒子概念绘制数据，不是假装精密CAD、照片或真实物理仿真。"""
class SceneDesigner:
 def __init__(self,cloud_factory):self.cloud_factory=cloud_factory
 def design(self,text,settings,previous=None,cancel=None):
  if not isinstance(text,str) or not text.strip() or len(text)>20000:raise ServiceError("绘制提示词需为 1–20000 字。")
  if settings.CHAT_MODE!="api":
   plan=preset(text)
   if plan:return plan,"offline-demo"
   raise ServiceError("自由提示词绘制需要云端对话 API。请在 F2 配置；当前仅可展示内置离线演示。")
  settings=replace(settings,RESPONSE_MODE=settings.VISUAL_RESPONSE_MODE)
  messages=[{"role":"system","content":SCENE_PROMPT}]
  if previous:messages.append({"role":"assistant","content":json.dumps(previous,ensure_ascii=False)})
  messages.append({"role":"user","content":text})
  gateway=self.cloud_factory(settings)
  def request_scene():
   if settings.CHAT_STREAM=="true" and callable(getattr(type(gateway),"chat_stream",None)):
    pieces=[];size=0
    for piece in gateway.chat_stream(messages,cancel):
     pieces.append(piece);size+=len(piece)
     if size>240000:raise ServiceError("场景描述过长，请简化提示词。")
    if cancel and cancel.is_set():raise ServiceError("绘制已取消。")
    return "".join(pieces)
   return gateway.chat(messages)
  raw=request_scene()
  try:plan=decode_plan(raw)
  except ServiceError as exc:
   if cancel and cancel.is_set():raise
   # One bounded repair preserves the full user prompt instead of substituting a preset.
   messages.extend([{"role":"assistant","content":raw[:240000]},{"role":"user","content":"请保留原提示词的全部构图和细节，仅修正场景协议错误："+str(exc)+"。返回完整 JSON。"}])
   plan=decode_plan(request_scene())
  return plan,"cloud"
