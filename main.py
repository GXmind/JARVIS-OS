"""The only application entry point. Bootstrap paths before importing packages."""
import os
from pathlib import Path
import sys

ROOT = Path(r"F:\Javis_os")
if Path(__file__).resolve().parent != ROOT.resolve():
    raise SystemExit(r"项目必须位于 F:\Javis_os。")
sys.dont_write_bytecode = True
sys.pycache_prefix = str(ROOT / "cache/python")
sys.path.insert(0, str(ROOT / "src"))
for folder in ("tmp", "cache", "logs"):
    (ROOT / folder).mkdir(parents=True, exist_ok=True)
for name in ("TEMP", "TMP", "TMPDIR"):
    os.environ[name] = str(ROOT / "tmp")
os.environ["PIP_CACHE_DIR"] = str(ROOT / "cache/pip")
os.environ["XDG_CACHE_HOME"] = str(ROOT / "cache")
os.environ["PYTHONUSERBASE"] = str(ROOT / "cache/python-user")

from jarvis.infrastructure.system.paths import initialize
initialize()

from jarvis.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
