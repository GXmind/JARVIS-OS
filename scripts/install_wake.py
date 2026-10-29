"""Download a pinned offline keyword model, with bounded retries and digest validation."""
from pathlib import Path
import hashlib,json,subprocess,sys,zipfile
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(r"F:\Javis_os")
if Path(__file__).resolve().parent.parent!=ROOT:raise SystemExit("项目必须位于 F:\\Javis_os")
manifest=json.loads((ROOT/"config/wake-runtime.json").read_text(encoding="utf-8"));cache=ROOT/"cache/wake";cache.mkdir(parents=True,exist_ok=True)
archive=cache/(manifest["version"]+".zip")
def valid():return archive.exists() and hashlib.sha256(archive.read_bytes()).hexdigest()==manifest["sha256"]
if not valid():
 parts=cache/"parts";parts.mkdir(exist_ok=True);total=manifest["bytes"];size=(total+7)//8
 def download(index):
  start=index*size;end=min(total-1,start+size-1);part=parts/(str(index)+".part")
  result=subprocess.run(["curl.exe","--silent","--show-error","--fail","--location","--connect-timeout","10","--max-time","240","--retry","1","--range",f"{start}-{end}","--output",str(part),manifest["url"]])
  return result.returncode==0 and part.exists() and part.stat().st_size==end-start+1
 with ThreadPoolExecutor(max_workers=8) as pool:complete=all(pool.map(download,range(8)))
 if complete:
  with archive.open("wb") as output:
   for index in range(8):output.write((parts/(str(index)+".part")).read_bytes())
 if not valid():
  mirror=manifest.get("mirror")
  if mirror:subprocess.run(["curl.exe","--fail","--location","--connect-timeout","10","--max-time","240","--output",str(archive),mirror])
 if not valid():raise SystemExit("模型下载失败或校验不匹配，请稍后重试。")
with zipfile.ZipFile(archive) as model:
 for name in model.namelist():
  path=(cache/name).resolve()
  if not path.is_relative_to(cache.resolve()):raise RuntimeError("Invalid model path")
  if name.endswith("/"):path.mkdir(parents=True,exist_ok=True)
  else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(model.read(name))
print("唤醒模型已就绪。重新启动后，说 hi jarvis，听到提示音再说指令。")
