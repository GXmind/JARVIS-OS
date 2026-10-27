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

from jarvis.paths import initialize
initialize()

def main():
    import argparse
    from jarvis.logging_setup import configure_logging
    logger = configure_logging()
    parser = argparse.ArgumentParser(description="JARVIS Windows 桌面上位机")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--audio", action="store_true", help="自检时实际录制约一秒并播放")
    parser.add_argument("--tts", action="store_true", help="自检时实际生成并播放 Windows 语音")
    parser.add_argument("--smoke-ui", action="store_true", help="自动验证 GUI 后关闭，不修改正式对话")
    args = parser.parse_args()
    if args.self_check:
        from jarvis.selfcheck import run
        return run(args.audio, args.tts)
    if args.smoke_ui:
        from jarvis.spacecheck import run as gui_smoke
        return gui_smoke(args.audio)
    # Prevent two GUI instances from racing settings or audio devices.
    import msvcrt
    lockfile = (ROOT / "tmp/gui.lock").open("a+b")
    lockfile.seek(0, 2)
    if lockfile.tell() == 0:
        lockfile.write(b"0")
        lockfile.flush()
    lockfile.seek(0)
    try:
        msvcrt.locking(lockfile.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("JARVIS", "JARVIS 已运行，请查看任务栏中的窗口。", parent=root)
        root.destroy()
        lockfile.close()
        return 0
    try:
        from jarvis.config import load_settings, Settings, DEFAULT_ENV, save_settings
        config_error = None
        try:
            if not DEFAULT_ENV.exists():
                with DEFAULT_ENV.open("x", encoding="utf-8") as target:
                    target.write((ROOT / "config/.env.example").read_text(encoding="utf-8"))
            settings = load_settings()
        except (ValueError, OSError) as exc:
            logger.warning("config_load_failed category=%s", type(exc).__name__)
            config_error = str(exc) if isinstance(exc, ValueError) else "无法读取配置文件，请检查 config 目录权限。"
            settings = Settings()
        from jarvis.desktop import run
        from jarvis.api import ServiceError
        try:
            return run(settings, config_error)
        except ServiceError as exc:
            logger.error("space_desktop_launch_failed")
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("JARVIS", str(exc), parent=root)
            root.destroy()
            return 1
    finally:
        lockfile.seek(0)
        msvcrt.locking(lockfile.fileno(), msvcrt.LK_UNLCK, 1)
        lockfile.close()

if __name__ == "__main__":
    raise SystemExit(main())