"""All application-managed writes stay in the one user-approved root."""
import os
from pathlib import Path
import tempfile

ROOT = Path(r"F:\Javis_os")
DIRECTORIES = (
    "config", "data", "logs", "cache", "cache/pip", "cache/python",
    "recordings", "tmp", "tests", "scripts", "docs",
)

def initialize():
    if Path(__file__).resolve().parents[2] != ROOT.resolve():
        raise RuntimeError(r"请将项目放在唯一工作目录 F:\Javis_os。")
    ROOT.mkdir(parents=True, exist_ok=True)
    for item in DIRECTORIES:
        (ROOT / item).mkdir(parents=True, exist_ok=True)
    for key in ("TEMP", "TMP", "TMPDIR"):
        os.environ[key] = str(ROOT / "tmp")
    os.environ["PIP_CACHE_DIR"] = str(ROOT / "cache/pip")
    os.environ["PYTHONPYCACHEPREFIX"] = str(ROOT / "cache/python")
    tempfile.tempdir = str(ROOT / "tmp")
    os.chdir(ROOT)

def local_path(path):
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise ValueError("应用文件路径不能离开 F:\\Javis_os")
    return resolved