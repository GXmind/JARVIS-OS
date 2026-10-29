"""Install pinned browser hand runtime to F:\\Javis_os\\cache; no pip dependencies."""
from pathlib import Path
import hashlib,json,tarfile,urllib.request
ROOT=Path(r"F:\Javis_os")
if Path(__file__).resolve().parent.parent!=ROOT:raise SystemExit("请将项目放在 F:\\Javis_os。")
manifest=json.loads((ROOT/"config/hand-runtime.json").read_text(encoding="utf-8"))
cache=ROOT/"cache/hand-runtime";cache.mkdir(parents=True,exist_ok=True)
def download(url,path,sha):
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==sha:return
    temporary=path.with_suffix(path.suffix+".part")
    with urllib.request.urlopen(url,timeout=60) as response,temporary.open("wb") as output:
        while data:=response.read(1024*1024):output.write(data)
    if hashlib.sha256(temporary.read_bytes()).hexdigest()!=sha:
        temporary.unlink();raise RuntimeError("下载内容校验失败，请重试。")
    temporary.replace(path)
archive=cache/"tasks-vision-0.10.21.tgz"
download(manifest["archive_url"],archive,manifest["archive_sha256"])
with tarfile.open(archive) as tar:
    for name,details in manifest["files"].items():
        path=(cache/name).resolve()
        if not path.is_relative_to(cache.resolve()):raise RuntimeError("Invalid runtime path")
        path.parent.mkdir(parents=True,exist_ok=True)
        if details["archive_member"]:
            data=tar.extractfile(details["archive_member"]).read()
            if hashlib.sha256(data).hexdigest()!=details["sha256"]:raise RuntimeError("运行库校验失败。")
            path.write_bytes(data)
        else:download(manifest["model_url"],path,details["sha256"])
print("手势识别运行库安装完成。请重启 JARVIS，按 F9 启用摄像头。")
