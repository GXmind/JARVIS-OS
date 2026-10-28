"""Serve only pinned, project-local hand assets; no camera frames enter Python."""
from functools import lru_cache
import hashlib
import json
from jarvis.infrastructure.system.paths import ROOT

@lru_cache(maxsize=1)
def verified_files():
    try:
        manifest=json.loads((ROOT/"config/hand-runtime.json").read_text(encoding="utf-8"))
        files={}
        for name,details in manifest["files"].items():
            path=(ROOT/"cache/hand-runtime"/name).resolve()
            if not path.is_relative_to((ROOT/"cache/hand-runtime").resolve()):return {}
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=details["sha256"]:return {}
            files[name]=path
        return files if len(files)==6 else {}
    except (OSError,ValueError,KeyError,TypeError):return {}

def status():
    ready=bool(verified_files())
    return {"ready":ready,"engine":"MediaPipe Hand Landmarker 0.10.21", "local_only":True,
        "message":"" if ready else "手势运行库尚未安装或校验失败，请运行 scripts/install_hand.cmd 后重启。"}

def read_asset(path):
    prefix="/runtime/hand/"
    if not path.startswith(prefix):return None
    name=path[len(prefix):];file=verified_files().get(name)
    if file is None:return None
    mime="application/wasm" if file.suffix==".wasm" else "application/octet-stream" if file.suffix==".task" else "text/javascript; charset=utf-8"
    return file.read_bytes(),mime
