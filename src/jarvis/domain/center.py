"""Bounded particle scene descriptions and natural-language intentions. No I/O or execution."""
import json,math,re
from jarvis.domain.errors import ServiceError
SHAPES=("sphere","box","torus","cone","cylinder","helix","heart","galaxy","wave","text","drawing","curve","lathe","patch","mesh")
MOTIONS=("none","rotate","pulse","wave","orbit","fly")
PALETTES=("galaxy","violet","rose","gold","ice")
def vector(value,default,low,high):
 if isinstance(value,dict) and all(k in value for k in ("x","y","z")):value=[value[k] for k in ("x","y","z")]
 if value is None:return list(default)
 if not isinstance(value,list) or len(value)!=3 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low<=v<=high for v in value):raise ServiceError("粒子模型坐标超出支持范围。")
 return value

def color(value,default="galaxy"):
 return value if isinstance(value,str) and (value in PALETTES or re.fullmatch(r"#[0-9a-fA-F]{6}",value)) else default

def finite_number(value,low,high):
 return not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value) and low<=value<=high

def freeform(node):
 shape=node["shape"];result={}
 if shape in ("curve","patch","mesh"):
  key="points" if shape=="curve" else "control" if shape=="patch" else "vertices"
  points=node.get(key,node.get("controlPoints",node.get("control_points")))
  if shape=="patch":
   if points is None:points=node.get("points")
   rows=node.get("rows");cols=node.get("cols",node.get("columns"))
   if isinstance(points,list) and 2<=len(points)<=8 and all(isinstance(row,list) and 2<=len(row)<=8 and all(isinstance(point,(list,dict)) for point in row) for row in points):
    rows=len(points);cols=len(points[0])
    if any(len(row)!=cols for row in points):raise ServiceError("patch 的控制点行长度必须一致。")
    points=[point for row in points for point in row]
   if isinstance(points,list) and points and all(isinstance(v,(int,float)) for v in points) and len(points)%3==0:points=[points[i:i+3] for i in range(0,len(points),3)]
   if rows is None or cols is None:
    side=int(math.sqrt(len(points))) if isinstance(points,list) else 0
    if side*side==(len(points) if isinstance(points,list) else -1):rows=cols=side
   if isinstance(rows,bool) or isinstance(cols,bool) or not isinstance(rows,int) or not isinstance(cols,int) or not 2<=rows<=8 or not 2<=cols<=8 or not isinstance(points,list) or len(points)!=rows*cols:raise ServiceError("patch 需要 control 数字三维点，支持 2–8 行×2–8 列点阵，或指定 rows/cols 的一维点数组。")
   result.update(rows=rows,cols=cols)
  low,high=(4,64) if shape=="patch" else (3,2048) if shape=="mesh" else (2,128)
  if not isinstance(points,list) or not low<=len(points)<=high:raise ServiceError(shape+" 的 "+key+" 需要 "+str(low)+"–"+str(high)+" 个数字三维点。")
  if any(point is None for point in points):raise ServiceError(shape+" 的控制点不能为空。")
  result[key]=[vector(point,[0,0,0],-8,8) for point in points]
 if shape=="curve":
  radius=node.get("radius",.025)
  if not finite_number(radius,.002,2):raise ServiceError("曲线半径无效。")
  result.update(radius=radius,closed=bool(node.get("closed",False)))
 if shape=="mesh":
  faces=node.get("faces")
  if not isinstance(faces,list) or not 1<=len(faces)<=4096:raise ServiceError("网格三角面数量无效。")
  if any(not isinstance(f,list) or len(f)!=3 or any(isinstance(i,bool) or not isinstance(i,int) or not 0<=i<len(result["vertices"]) for i in f) for f in faces):raise ServiceError("网格索引超出顶点范围。")
  result["faces"]=faces
 if shape=="lathe":
  profile=node.get("profile")
  if not isinstance(profile,list) or not 2<=len(profile)<=128 or any(not isinstance(p,list) or len(p)!=2 or not finite_number(p[0],0,6) or not finite_number(p[1],-8,8) for p in profile):raise ServiceError("旋转曲面的剖面无效。")
  result["profile"]=profile
 if shape=="drawing":
  paths=node.get("paths");box=node.get("viewBox",[0,0,512,512])
  if not isinstance(box,list) or len(box)!=4 or not all(finite_number(v,-2048,2048) for v in box) or box[2]<=0 or box[3]<=0:raise ServiceError("自由绘制画布无效。")
  if not isinstance(paths,list) or not 1<=len(paths)<=64:raise ServiceError("自由绘制需要 1–64 条路径。")
  result.update(viewBox=box,paths=[])
  for path in paths:
   d=path.get("d","") if isinstance(path,dict) else ""
   if not isinstance(d,str) or not 1<=len(d)<=6000 or not re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZzEe0-9+.,\s-]+",d):raise ServiceError("自由绘制仅接受有限的 SVG 路径数据。")
   numbers=re.findall(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?",d)
   if any(not math.isfinite(float(n)) or abs(float(n))>100000 for n in numbers):raise ServiceError("自由路径坐标过大。")
   width=path.get("width",1.2)
   if not finite_number(width,0,30):raise ServiceError("自由绘制线宽无效。")
   fill=path.get("fill",False);stroke=path.get("stroke",True)
   result["paths"].append({"d":d,"color":color(path.get("color"),color(node.get("color"))),"fill":bool(fill),"stroke":bool(stroke) and width>0,"width":width})
 return result

def animation(node):
 result={}
 if "pivot" in node:result["pivot"]=vector(node["pivot"],[0,0,0],-8,8)
 if "frames" in node or "keyframes" in node:
  frames=node.get("frames",node.get("keyframes"))
  if not isinstance(frames,list) or not 2<=len(frames)<=8:raise ServiceError("动画需要 2–8 个关键帧。")
  out=[];previous=-1
  for frame in frames:
   if isinstance(frame,dict):frame={**frame,"t":frame.get("t",frame.get("time"))}
   if not isinstance(frame,dict) or not finite_number(frame.get("t"),0,30) or frame["t"]<=previous:raise ServiceError("动画关键帧时间必须递增。")
   previous=frame["t"];out.append({"t":previous,"move":vector(frame.get("move",frame.get("position")),[0,0,0],-8,8),"turn":vector(frame.get("turn",frame.get("rotation")),[0,0,0],-12.6,12.6),"stretch":vector(frame.get("stretch",frame.get("scale")),[1,1,1],.01,6)})
  if out[0]["t"]!=0:raise ServiceError("动画必须从第 0 秒开始。")
  result.update(frames=out,loop=bool(node.get("loop",True)))
 return result

def validate_plan(value):
 if not isinstance(value,dict):raise ServiceError("模型应返回 JSON 场景描述。")
 nodes=value.get("nodes")
 if not isinstance(nodes,list) or not 1<=len(nodes)<=32:raise ServiceError("粒子模型需要 1–32 个构件。")
 result=[]
 for node in nodes:
  if not isinstance(node,dict) or node.get("shape") not in SHAPES:raise ServiceError("场景包含不支持的粒子构件。")
  result.append({"shape":node["shape"],"position":vector(node.get("position"),[0,0,0],-8,8),"scale":vector(node.get("scale"),[1,1,1],.01,6),"rotation":vector(node.get("rotation"),[0,0,0],-6.3,6.3),
   "color":color(node.get("color")),"motion":node.get("motion") if node.get("motion") in ("none","spin","orbit","bob","flap","flow","pulse") else "none","text":str(node.get("text",""))[:24],**freeform(node),**animation(node)})
 speed=value.get("speed",1)
 if isinstance(speed,bool) or not isinstance(speed,(int,float)) or not math.isfinite(speed):raise ServiceError("动画速度无效。")
 return {"title":str(value.get("title","粒子概念模型"))[:48],"nodes":result,"motion":value.get("motion") if value.get("motion") in MOTIONS else "rotate","speed":max(.1,min(3,speed)),"paused":bool(value.get("paused",False)),"version":1}

def decode_plan(text):
 text=str(text).strip()
 if text.startswith("```"):text=re.sub(r"^```(?:json)?\s*|\s*```$","",text)
 if len(text)>240000:raise ServiceError("模型描述过长，请简化构件。")
 try:return validate_plan(json.loads(text))
 except (ValueError,TypeError):raise ServiceError("未得到有效的粒子场景，请换一种描述重试。") from None

def node(shape,position=(0,0,0),scale=(1,1,1),**extra):return {"shape":shape,"position":list(position),"scale":list(scale),**extra}
def preset(text):
 t=text.lower();nodes=None;title="";motion="rotate"
 if any(s in t for s in ("太阳系","solar")):
  title="太阳系 · 粒子轨道演示";motion="none";nodes=[node("sphere",scale=(.4,.4,.4),color="gold",motion="spin")]
  for i in range(6):
   radius=.8+i*.4;size=.07+i*.018
   nodes.extend([node("sphere",(radius,0,0),(size,size,size),color=("ice" if i%2 else "rose"),motion="orbit"),node("torus",scale=(radius,.01,radius),color="violet")])
 elif any(s in t for s in ("火箭","rocket","飞船")):
  title="星际飞船 · 粒子概念模型";motion="fly";nodes=[node("cylinder",scale=(.32,1.1,.32),color="ice"),node("cone",(0,1.4,0),(.32,.6,.32),color="rose"),node("torus",(0,.5,0),(.33,.04,.33),color="gold"),node("cone",(0,-1.5,0),(.22,.6,.22),color="gold",motion="flow",rotation=[3.14,0,0])]
  for x in (-1,1):nodes.append(node("box",(.43*x,-.7,0),(.26,.5,.10),color="violet",rotation=[0,0,-x*.4]))
 elif any(s in t for s in ("汽车","小车","跑车","car")):
  title="汽车 · 粒子概念模型";nodes=[node("box",(0,-.2,0),(1.5,.32,.65),color="violet"),node("box",(.1,.32,0),(.7,.4,.58),color="ice")]
  for x in (-.95,.95):
   for z in (-.69,.69):nodes.append(node("torus",(x,-.48,z),(.3,.3,.13),rotation=[1.57,0,0],color="rose",motion="spin"))
 elif any(s in t for s in ("dna","双螺旋")):title="DNA · 双螺旋";nodes=[node("helix",color="rose")]
 elif any(s in t for s in ("爱心","心形","heart")):title="星光之心";nodes=[node("heart",color="rose")];motion="pulse"
 elif any(s in t for s in ("银河","星系","galaxy")):title="旋臂星系";nodes=[node("galaxy")];motion="rotate"
 elif any(s in t for s in ("波浪","海浪","wave")):title="星际波面";nodes=[node("wave",color="violet")];motion="wave"
 elif any(s in t for s in ("立方体","正方体","cube")):title="晶格立方体";nodes=[node("box",color="violet")]
 elif any(s in t for s in ("地球","球体","sphere")):title="星球 · 粒子球面";nodes=[node("sphere",color="ice"),node("torus",scale=(1.5,.025,1.5),color="rose")]
 elif any(s in t for s in ("文字","写出","写上")):
  match=re.search(r"[‘“\"《](.{1,24}?)[’”\"》]",text);label=match.group(1) if match else re.split(r"文字|写出|写上",text,maxsplit=1)[-1].strip(" ：:。")[:16] or "JARVIS"
  title="星光文字 · "+label;nodes=[node("text",text=label)];motion="pulse"
 return validate_plan({"title":title,"nodes":nodes,"motion":motion}) if nodes else None

def intent(text,active=False):
 t=text.lower().strip().strip("。！？!?")
 if re.fullmatch(r"(?:请)?(?:收起|关闭|退出|取消).{0,6}(?:模型|动画|图景|绘制|粒子展示)",t) or re.fullmatch(r"(?:恢复|返回|回到).{0,4}能量体",t):return {"action":"close"}
 if active:
  simple=re.sub(r"^(?:请|帮我|让它|让模型|让动画|把它|将它|模型|动画|它)","",t)
  if simple in ("暂停动画","停止旋转","暂停模型","暂停"):return {"action":"update","paused":True}
  if simple in ("散开","解体","爆开"):return {"action":"update","explode":1}
  if simple in ("重新汇聚","重组","还原模型"):return {"action":"update","explode":0}
  if simple in ("旋转起来","开始旋转","转起来","恢复动画"):return {"action":"update","paused":False,"motion":"rotate"}
  if simple in ("快一点","慢一点"):return {"action":"update","speed_factor":1.4 if "快" in simple else .7}
  match=re.fullmatch(r"(?:改成|换成|变成|调整为)(紫色|粉色|金色|蓝色|红色|绿色|星空色|#[0-9a-f]{6})",simple)
  if match:return {"action":"update","color":{"紫色":"violet","粉色":"rose","金色":"gold","蓝色":"ice","红色":"#ff4a5f","绿色":"#48dc9d","星空色":"galaxy"}.get(match[1],match[1])}
  for word,motion in (("呼吸","pulse"),("波动","wave"),("起飞","fly"),("公转","orbit")):
   if simple==word:return {"action":"update","motion":motion,"paused":False}
 if re.search(r"(?:如何|怎么|原理|教程)",t) and not re.search(r"(?:请|帮我).{0,5}(?:生成|创建|建模|画|做)",t):return None
 if active and not re.search(r"(?:为什么|怎么|如何|天气|导航)",t) and re.search(r"^(?:请)?(?:把|给|将|让|在|添加|修改|调整|改成|换成|加上|去掉|删除)",t):return {"action":"show","prompt":text,"edit":True}
 match=re.match(r"(?:请|请你|帮我|我想|我要|能不能|可以|贾维斯|jarvis|，|,|\s)*(画|绘制|建模|生成|创建)",t,re.I)
 if match and (match[1] in ("画","绘制","建模") or not re.search(r"文章|故事|代码|诗|方案|回复|文案|报告|计划|总结|表格|清单|教程",t)):return {"action":"show","prompt":text}
 if re.search(r"建模|(?:创建|展示|显示|构建|模拟|做).{0,40}(?:模型|粒子|动画)|(?:用粒子|粒子特效).{0,25}(?:画|写|显示|展示|做)",t):return {"action":"show","prompt":text}
 return None
