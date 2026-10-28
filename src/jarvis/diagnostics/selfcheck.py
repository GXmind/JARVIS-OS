"""Checks never send cloud requests or put a key in the report."""
from dataclasses import replace
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
import threading
import time
import uuid
import wave

from jarvis.infrastructure.audio.service import Audio, devices
from jarvis.domain.settings import Settings
from jarvis.infrastructure.config.env_file import load_settings
from jarvis.infrastructure.system.paths import ROOT
from jarvis.application.conversation import Conversation
from jarvis.infrastructure.persistence.sqlite import Store

def report_save(name, report):
    path = ROOT / "logs" / name
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return path

def run(check_audio=False, check_tts=False):
    result = {"root": str(ROOT), "python": sys.version.split()[0], "checks": {}, "cloud": "未调用，需用户配置密钥后验证"}
    checks = result["checks"]
    def check(name, fn):
        try:
            checks[name] = {"ok": True, "detail": fn()}
        except Exception as exc:
            # Do not expose raw third-party errors that may include credentials.
            checks[name] = {"ok": False, "detail": type(exc).__name__}
    def writable():
        file = ROOT / "tmp" / ("write_" + uuid.uuid4().hex + ".txt")
        file.write_text("ok", encoding="utf-8")
        file.unlink()
        return "读写通过"
    check("root_writable", writable)
    def config_check():
        cfg = load_settings()
        return {"chat_mode": cfg.CHAT_MODE, "key_present": bool(cfg.API_KEY), "model_present": bool(cfg.API_MODEL)}
    check("configuration", config_check)
    def persistence():
        path = ROOT / "tmp" / ("selfcheck_" + uuid.uuid4().hex + ".sqlite3")
        store = Store(path)
        sid = store.new_session()
        answer, state = Conversation(store).reply(sid, "你好，自检", Settings())
        assert "模拟" in answer and len(store.history(sid)) == 2
        store.remember("自检参考记忆")
        assert Store(path).memories()[0][1] == "自检参考记忆"
        return {"simulation": True, "sqlite_persistence": True, "trained_emotion_model": state.trained_model}
    check("simulation_and_database", persistence)
    def tk_check():
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.update()
        root.destroy()
        return "Tk 窗口创建成功"
    check("tkinter", tk_check)
    check("audio_devices", devices)
    if check_audio:
        def microphone():
            cfg = replace(load_settings(), MAX_RECORD_SECONDS="1")
            audio = Audio()
            audio.prepare()
            path = audio.recording(cfg)
            with wave.open(str(path), "rb") as wav:
                raw = wav.readframes(wav.getnframes())
                samples = struct.unpack("<" + "h" * (len(raw) // 2), raw)
                rms = math.sqrt(sum(value * value for value in samples) / max(1, len(samples)))
                seconds = wav.getnframes() / wav.getframerate()
            audio.prepare()
            audio.play(path, cfg)
            return {"file": str(path), "seconds": round(seconds, 2), "rms": round(rms, 2),
                    "playback_stream": "成功；是否听到需用户确认"}
        check("microphone_and_playback", microphone)
    if check_tts:
        def speech():
            cfg = replace(load_settings(), TTS_MODE="windows")
            audio = Audio()
            audio.prepare()
            return audio.speak("贾维斯语音自检。系统已就绪。", cfg)
        check("windows_speech", speech)
    result["ok"] = all(item["ok"] for item in checks.values())
    report_save("selfcheck.json", result)
    return 0 if result["ok"] else 1

def gui_smoke(check_audio=False):
    import tkinter as tk
    from jarvis.presentation.legacy.gui import App
    root = tk.Tk()
    db_path = ROOT / "tmp" / ("gui_smoke_" + uuid.uuid4().hex + ".sqlite3")
    smoke_settings = replace(Settings(), MAX_RECORD_SECONDS="1") if check_audio else Settings()
    app = App(root, smoke_settings, store=Store(db_path))
    report = {"ok": False, "heartbeat_count": 0, "checks": []}
    deadline = time.monotonic() + 25
    audio_heartbeats = [0]
    phase = [0]
    def heartbeat():
        if not app.closing:
            report["heartbeat_count"] += 1
            root.after(20, heartbeat)
    def fail(message):
        report["checks"].append(message)
        report_save("gui_smoke.json", report)
        app.close()
    def tick():
        if time.monotonic() > deadline:
            fail("GUI 测试超时")
            return
        if app.busy:
            root.after(100, tick)
            return
        if phase[0] == 0:
            root.update_idletasks()
            bottom = root.winfo_rooty() + root.winfo_height()
            for widget in (app.input, app.send_button, app.record_button, app.status_label):
                if not widget.winfo_ismapped() or widget.winfo_rooty() + widget.winfo_height() > bottom:
                    fail("输入、按钮或状态栏超出可见区域")
                    return
            app.input.insert("1.0", "/记住 自检专用记忆")
            app.send_button.invoke()
            phase[0] += 1
        elif phase[0] == 1:
            if not app.store.memories():
                fail("记忆按钮流程失败")
                return
            app.input.insert("1.0", "你好，谢谢")
            app.send_button.invoke()
            phase[0] += 1
        elif phase[0] == 2:
            if "模拟" not in app.last_answer or len(app.store.history(app.session_id)) != 4:
                fail("异步模拟对话失败")
                return
            if check_audio:
                audio_heartbeats[0] = report["heartbeat_count"]
                app.record_button.invoke()
                phase[0] = 3
            else:
                finish()
                return
        elif phase[0] == 3:
            if app.last_record is None:
                fail("GUI 真实录音失败")
                return
            report["audio_worker_heartbeats"] = report["heartbeat_count"] - audio_heartbeats[0]
            if report["audio_worker_heartbeats"] < 20:
                fail("录音期间 GUI 心跳不足")
                return
            app.play_button.invoke()
            phase[0] = 4
        else:
            if "播放结束" not in app.status.get():
                fail("GUI 录音回放失败")
                return
            finish()
            return
        root.after(250, tick)
    def finish():
        app.notebook.select(2)
        root.update_idletasks()
        if not all(var.get() == getattr(smoke_settings, key) for key, var in app.fields.items()):
            fail("设置字段不完整")
            return
        report["ok"] = report["heartbeat_count"] > 5
        report["checks"] = ["窗口创建", "发送按钮", "后台模拟回复", "SQLite 历史与显式记忆",
                            "设置字段", "设备枚举回退", "GUI 心跳未阻塞", "输入/按钮/状态栏可见"]
        if check_audio:
            report["checks"].append("真实录音与回放期间 GUI 保持响应")
        report_save("gui_smoke.json", report)
        app.close()
    root.after(20, heartbeat)
    root.after(700, tick)
    root.mainloop()
    return 0 if report["ok"] else 1