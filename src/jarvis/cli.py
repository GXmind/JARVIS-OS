"""Command-line dispatch, single-instance lock and user-facing startup errors."""
from jarvis.infrastructure.system.paths import ROOT

def main():
    import argparse
    from jarvis.infrastructure.system.logging import configure_logging
    logger = configure_logging()
    parser = argparse.ArgumentParser(description="JARVIS Windows 桌面上位机")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--audio", action="store_true", help="自检时实际录制约一秒并播放")
    parser.add_argument("--tts", action="store_true", help="自检时实际生成并播放 Windows 语音")
    parser.add_argument("--smoke-ui", action="store_true", help="自动验证 GUI 后关闭，不修改正式对话")
    args = parser.parse_args()
    if args.self_check:
        from jarvis.diagnostics.selfcheck import run
        return run(args.audio, args.tts)
    if args.smoke_ui:
        from jarvis.diagnostics.browser_check import run as gui_smoke
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
        from jarvis.infrastructure.config.env_file import load_settings, DEFAULT_ENV
        from jarvis.domain.settings import Settings
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
        from jarvis.bootstrap import run_desktop as run
        from jarvis.domain.errors import ServiceError
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
