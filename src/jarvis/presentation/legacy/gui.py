import json
import logging
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
from dataclasses import asdict
from datetime import datetime

from jarvis import __version__
from jarvis.infrastructure.http.openai_compatible import CloudAPI
from jarvis.domain.errors import ServiceError
from jarvis.infrastructure.audio.service import Audio, devices
from jarvis.domain.settings import Settings
from jarvis.infrastructure.config.env_file import save_settings
from jarvis.infrastructure.system.paths import ROOT
from jarvis.application.conversation import Conversation
from jarvis.infrastructure.persistence.sqlite import Store
from jarvis.presentation.legacy.hud import ReactorHUD

LOG = logging.getLogger("jarvis")

FIELD_LABELS = {
    "API_BASE_URL": "API 基础地址（通常以 /v1 结尾）",
    "API_MODEL": "对话模型名（按服务商填写）",
    "API_KEY": "API 密钥",
    "CHAT_MODE": "对话：mock 模拟 / api 云端",
    "ASR_MODE": "识别：off 手动输入 / api 云端",
    "ASR_MODEL": "语音识别模型名（录音转文字）",
    "ASR_BASE_URL": "独立语音识别地址（留空沿用）",
    "ASR_API_KEY": "独立语音识别密钥",
    "TTS_MODE": "播报：windows 系统 / api 云端 / off",
    "TTS_MODEL": "云端语音模型名",
    "TTS_VOICE": "云端音色",
    "INPUT_DEVICE": "输入设备编号（留空使用系统默认）",
    "OUTPUT_DEVICE": "输出设备编号（留空使用系统默认）",
    "SAMPLE_RATE": "录音采样率 Hz（建议 16000）",
    "MAX_RECORD_SECONDS": "最长录音秒数（1–120）",
    "REQUEST_TIMEOUT": "云端超时秒数（5–120）",
    "AUTO_SPEAK": "自动播报回复：true / false",
}
CHOICES = {
    "CHAT_MODE": ("mock", "api"), "ASR_MODE": ("off", "api"),
    "TTS_MODE": ("windows", "api", "off"), "AUTO_SPEAK": ("false", "true"),
}

class App:
    def __init__(self, root, settings, config_error=None, store=None):
        self.root, self.settings = root, settings
        self.store = store or Store()
        self.conversation = Conversation(self.store,cloud_factory=CloudAPI)
        self.audio = Audio()
        self.events = queue.Queue()
        self.busy = False
        self.recording = False
        self.closing = False
        self.pending_speech = None
        self.last_answer = ""
        self.last_record = None
        self.session_id = self.store.new_session()
        self.sessions_data = []
        self.workers = []
        self.task_kind = ""
        self.task_label = ""
        self.error_until = 0.0
        self.memory_count = 0
        self.clock_after = None
        self.fx_quality = "high"
        self.status = tk.StringVar(value="就绪 · 可直接输入文字；F8 开始/停止录音")
        self.mode = tk.StringVar()
        self.emotion = tk.StringVar(value="情绪状态：中性 · 关键词规则，未训练情感模型")
        self._build()
        self.update_mode()
        self.refresh_sessions()
        self.refresh_memories()
        if config_error:
            self.status.set("配置无效，已临时使用模拟模式；请在设置页修正后保存。")
            root.after(300, lambda: messagebox.showwarning("配置需要修正", config_error, parent=root))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Control-Return>", lambda event: self.send())
        self.root.bind("<KeyRelease-F8>", lambda event: self.toggle_record())
        self.root.after(80, self.poll)
        self.root.after(200, self.refresh_devices)
        self.clock_after = self.root.after(400, self.update_hud_info)
        self.root.bind("<F11>", lambda event: self.toggle_fullscreen())
        self.root.bind("<Escape>", lambda event: self.root.attributes("-fullscreen", False))

    def _build(self):
        root = self.root
        root.title(f"JARVIS · 全息交互中枢 {__version__}")
        width = min(1520, root.winfo_screenwidth() - 60)
        height = min(900, root.winfo_screenheight() - 90)
        root.geometry(f"{width}x{height}")
        root.minsize(min(1040, width), min(680, height))
        root.configure(bg="#030a0d")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 9), background="#071217", foreground="#b8dece")
        style.configure("TFrame", background="#071217")
        style.configure("TLabel", background="#071217", foreground="#a3caba")
        style.configure("TButton", padding=(9, 7), background="#0d2523", foreground="#a1dcc6",
                        bordercolor="#29554a", lightcolor="#29554a", darkcolor="#102b26", relief="flat")
        style.map("TButton", background=[("active", "#174337"), ("disabled", "#0b1818")],
                  foreground=[("disabled", "#3c6053")])
        style.configure("Primary.TButton", background="#a5f5c1", foreground="#06241c", font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Primary.TButton", background=[("active", "#d7ffe2"), ("disabled", "#254236")],
                  foreground=[("disabled", "#5a7a69")])
        style.configure("TNotebook", background="#030a0d", borderwidth=0, tabmargins=(0, 0, 0, 6))
        style.configure("TNotebook.Tab", padding=(20, 9), background="#071217", foreground="#4e8b78",
                        bordercolor="#173f33", lightcolor="#173f33")
        style.map("TNotebook.Tab", background=[("selected", "#0b2921")], foreground=[("selected", "#a5f5c1")])
        style.configure("TEntry", fieldbackground="#0a211e", foreground="#d6f9e8", insertcolor="#a9ffd5",
                        bordercolor="#2b5648", lightcolor="#2b5648", darkcolor="#122e25")
        style.configure("TCombobox", fieldbackground="#0a211e", foreground="#d6f9e8", background="#102d25",
                        arrowcolor="#80c4a7", bordercolor="#2b5648")
        style.map("TCombobox", foreground=[("readonly", "#d6f9e8")], fieldbackground=[("readonly", "#0a211e")])
        style.configure("Treeview", fieldbackground="#061612", background="#061612", foreground="#a5d6bd", rowheight=28,
                        bordercolor="#173a2c")
        style.configure("Treeview.Heading", background="#102a20", foreground="#9fd5b9", relief="flat")
        style.map("Treeview", background=[("selected", "#1d5742")])
        style.configure("Vertical.TScrollbar", background="#17392c", troughcolor="#06120f", arrowcolor="#4c816b",
                        bordercolor="#071217")

        header = tk.Frame(root, bg="#030a0d")
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 14))
        brand = tk.Frame(header, bg="#030a0d")
        brand.pack(side="left")
        tk.Label(brand, text="J A R V I S", font=("Consolas", 27, "bold"), fg="#c3ffdc", bg="#030a0d").pack(anchor="w")
        tk.Label(brand, text="P E R S O N A L   I N T E R F A C E", font=("Consolas", 7),
                 fg="#4a8b6a", bg="#030a0d").pack(anchor="w", padx=2)
        tk.Frame(header, bg="#234c3a", width=1, height=40).pack(side="left", padx=24)
        mode_panel = tk.Frame(header, bg="#030a0d")
        mode_panel.pack(side="left")
        tk.Label(mode_panel, text="INTERACTION CENTER / 交互中枢", font=("Consolas", 9), fg="#64977e", bg="#030a0d").pack(anchor="w")
        tk.Label(mode_panel, textvariable=self.mode, font=("Microsoft YaHei UI", 9), fg="#b0dfbd", bg="#030a0d").pack(anchor="w", pady=(5, 0))
        self.clock = tk.StringVar(value=datetime.now().strftime("%H:%M:%S"))
        tk.Label(header, textvariable=self.clock, font=("Consolas", 18), fg="#82cfa8", bg="#030a0d").pack(side="right", padx=(20, 0))
        self.fx_button = ttk.Button(header, text="特效 · 高", command=self.cycle_effects)
        self.fx_button.pack(side="right", padx=(8, 0))
        ttk.Button(header, text="全屏 F11", command=self.toggle_fullscreen).pack(side="right")

        self.notebook = ttk.Notebook(root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=20)
        chat = ttk.Frame(self.notebook, padding=0)
        memory = ttk.Frame(self.notebook, padding=16)
        settings = ttk.Frame(self.notebook, padding=16)
        self.notebook.add(chat, text="01  交互中枢")
        self.notebook.add(memory, text="02  记忆档案")
        self.notebook.add(settings, text="03  系统设置")
        self._chat(chat)
        self._memory(memory)
        self._settings(settings)
        footer = tk.Frame(root, bg="#030a0d")
        footer.grid(row=2, column=0, sticky="ew", padx=22, pady=(9, 3))
        tk.Label(footer, textvariable=self.emotion, font=("Microsoft YaHei UI", 8),
                 fg="#49745e", bg="#030a0d").pack(side="left")
        tk.Label(footer, text="F8  VOICE   /   CTRL+ENTER  SEND", font=("Consolas", 8),
                 fg="#55866b", bg="#030a0d").pack(side="right")
        self.status_label = tk.Label(root, textvariable=self.status, anchor="w", bg="#071711", fg="#93c6aa",
                                     font=("Microsoft YaHei UI", 9), padx=12, pady=7, wraplength=width - 65)
        self.status_label.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 12))

    def _chat(self, parent):
        parent.columnconfigure(0, weight=7, minsize=420)
        parent.columnconfigure(1, weight=5, minsize=360)
        parent.rowconfigure(0, weight=1)
        visual = tk.Frame(parent, bg="#030a0d", highlightbackground="#1c4232", highlightthickness=1)
        visual.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        visual.columnconfigure(0, weight=1)
        visual.rowconfigure(0, weight=1)
        self.hud = ReactorHUD(visual, self.hud_snapshot, cursor="hand2")
        self.hud.grid(row=0, column=0, sticky="nsew")
        self.hud.bind("<Button-1>", lambda event: self.toggle_record())
        archive = tk.Frame(visual, bg="#071711", padx=12, pady=8)
        archive.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        archive.columnconfigure(1, weight=1)
        tk.Label(archive, text="SESSION\nARCHIVE", font=("Consolas", 8), fg="#61977a", bg="#071711", justify="left").grid(row=0, column=0, rowspan=2, padx=(0, 14))
        self.session_list = tk.Listbox(archive, height=2, width=20, bg="#071711", fg="#8dc8a9",
                                      selectbackground="#1d4431", selectforeground="#d4ffe2", borderwidth=0,
                                      highlightthickness=0, exportselection=False, font=("Microsoft YaHei UI", 8))
        self.session_list.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(0, 10))
        self.session_list.bind("<<ListboxSelect>>", self.select_session)
        self.new_button = ttk.Button(archive, text="＋ 新对话", command=self.new_session)
        self.new_button.grid(row=0, column=2, sticky="ew", pady=(0, 3))
        self.export_button = ttk.Button(archive, text="导出记录", command=self.export_history)
        self.export_button.grid(row=1, column=2, sticky="ew")
        shell = tk.Frame(parent, bg="#071217", highlightbackground="#28513f", highlightthickness=1)
        shell.grid(row=0, column=1, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)
        top = tk.Frame(shell, bg="#0b2019", padx=14, pady=12)
        top.grid(row=0, column=0, sticky="ew")
        tk.Label(top, text="COMMUNICATION", font=("Consolas", 11, "bold"), fg="#b9edcf", bg="#0b2019").pack(side="left")
        self.console_state = tk.StringVar(value="● READY")
        tk.Label(top, textvariable=self.console_state, font=("Consolas", 8), fg="#73b892", bg="#0b2019").pack(side="right")
        self.transcript = ScrolledText(shell, width=28, height=10, wrap="word", state="disabled", bg="#06110f",
                                       fg="#afd7bf", insertbackground="#b8ffce", relief="flat", borderwidth=0,
                                       font=("Microsoft YaHei UI", 10), padx=17, pady=14,
                                       highlightthickness=0, spacing1=3, spacing3=5)
        self.transcript.grid(row=1, column=0, sticky="nsew", padx=10, pady=(10, 4))
        self.transcript.vbar.configure(bg="#17392c", troughcolor="#06110f", activebackground="#276447",
                                       highlightthickness=0, bd=0, width=9)
        self.transcript.tag_configure("user", foreground="#d5ffdb", spacing1=12, spacing3=9)
        self.transcript.tag_configure("assistant", foreground="#99d4b8", spacing1=12, spacing3=9)
        self.transcript.tag_configure("notice", foreground="#548a70", spacing1=8, spacing3=8)
        self.append("交互中枢已就绪。\n\n输入指令开始对话，或按 F8 录音。\n点击左侧能量体也可开始 / 停止录音。", "notice")
        ttk.Label(shell, text="指令输入  /  COMMAND INPUT", font=("Microsoft YaHei UI", 8)).grid(row=2, column=0, sticky="w", padx=14, pady=(6, 5))
        self.input = tk.Text(shell, height=3, width=24, wrap="word", bg="#0b241b", fg="#e0ffe9",
                             insertbackground="#bcffd2", font=("Microsoft YaHei UI", 10), relief="flat",
                             highlightbackground="#2c5940", highlightcolor="#7ecb9f", highlightthickness=1,
                             padx=10, pady=8)
        self.input.grid(row=3, column=0, sticky="ew", padx=12)
        buttons = ttk.Frame(shell)
        buttons.grid(row=4, column=0, sticky="ew", padx=12, pady=(9, 11))
        for col in range(4):
            buttons.columnconfigure(col, weight=1, uniform="actions")
        self.record_button = ttk.Button(buttons, text="● 录音 F8", command=self.toggle_record)
        self.record_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.play_button = ttk.Button(buttons, text="回放", command=self.play_record)
        self.play_button.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.speak_button = ttk.Button(buttons, text="播报", command=lambda: self.speak(self.last_answer))
        self.speak_button.grid(row=0, column=2, sticky="ew", padx=(0, 4))
        ttk.Button(buttons, text="停止", command=self.stop_audio).grid(row=0, column=3, sticky="ew")
        self.send_button = ttk.Button(buttons, text="发送指令  ↗", style="Primary.TButton", command=self.send)
        self.send_button.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))

    def hud_snapshot(self):
        capturing = getattr(self.audio, "capture_active", False)
        if time.monotonic() < self.error_until:
            state = "ERROR"
        elif capturing:
            state = "LISTENING"
        elif self.busy:
            if self.task_kind == "reply" or self.task_kind == "record":
                state = "THINKING"
            elif "播放" in self.task_label or "语音" in self.task_label:
                state = "SPEAKING"
            else:
                state = "STANDBY"
        else:
            state = "STANDBY"
        return {"state": state, "level": getattr(self.audio, "level", 0.0), "capturing": capturing,
                "mock": self.settings.CHAT_MODE == "mock", "memories": self.memory_count,
                "sessions": len(self.sessions_data), "devices": len(getattr(self, "device_data", {}))}

    def update_hud_info(self):
        if self.closing:
            return
        self.clock.set(datetime.now().strftime("%H:%M:%S"))
        self.console_state.set("● " + self.hud_snapshot()["state"])
        self.clock_after = self.root.after(400, self.update_hud_info)

    def cycle_effects(self):
        modes = ("high", "low", "off")
        self.fx_quality = modes[(modes.index(self.fx_quality) + 1) % len(modes)]
        self.hud.set_quality(self.fx_quality)
        self.fx_button.configure(text="特效 · " + {"high": "高", "low": "节能", "off": "静态"}[self.fx_quality])

    def toggle_fullscreen(self):
        self.root.attributes("-fullscreen", not bool(self.root.attributes("-fullscreen")))

    def _memory(self, parent):
        ttk.Label(parent, text="仅保存您明确添加的内容；云端对话可能使用相关记忆（最多 5 条）。").pack(anchor="w", pady=(0, 12))
        self.memory_tree = ttk.Treeview(parent, columns=("id", "text", "created"), show="headings", selectmode="browse")
        for name, title, width in (("id", "编号", 65), ("text", "记忆内容", 620), ("created", "保存时间（UTC）", 185)):
            self.memory_tree.heading(name, text=title)
            self.memory_tree.column(name, width=width, stretch=name == "text")
        self.memory_tree.pack(fill="both", expand=True)
        self.memory_tree.bind("<<TreeviewSelect>>", self.select_memory)
        self.memory_detail = tk.Text(parent, height=4, wrap="word", bg="#061612", fg="#a5d6bd",
                                     font=("Microsoft YaHei UI", 10), state="disabled", relief="flat")
        self.memory_detail.pack(fill="x", pady=10)
        self.memory_input = ttk.Entry(parent)
        self.memory_input.pack(fill="x", pady=(4, 10))
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Button(row, text="保存这条记忆", command=self.add_memory).pack(side="left")
        ttk.Button(row, text="删除选中记忆", command=self.delete_memory).pack(side="left", padx=8)
        ttk.Button(row, text="刷新", command=self.refresh_memories).pack(side="left")

    def _settings(self, outer):
        canvas = tk.Canvas(outer, bg="#071217", highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        parent = ttk.Frame(canvas, padding=(0, 0, 8, 0))
        item_id = canvas.create_window((0, 0), window=parent, anchor="nw")
        parent.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item_id, width=event.width))
        def scroll(event):
            if self.notebook.index(self.notebook.select()) == 2:
                if event.widget is not self.device_tree:
                    canvas.yview_scroll(-int(event.delta / 120), "units")
        self.root.bind_all("<MouseWheel>", scroll, add="+")
        grid = ttk.Frame(parent)
        grid.pack(fill="x")
        self.fields = {}
        for index, (key, value) in enumerate(asdict(self.settings).items()):
            # Two columns of fields keep the page usable on common laptop displays.
            column, row = index // 8, index % 8
            area = ttk.Frame(grid)
            area.grid(row=row, column=column, sticky="ew", padx=(0, 18), pady=3)
            ttk.Label(area, text=FIELD_LABELS.get(key,key), font=("Microsoft YaHei UI", 9)).pack(anchor="w")
            var = tk.StringVar(value=value)
            if key in CHOICES:
                widget = ttk.Combobox(area, textvariable=var, values=CHOICES[key], state="readonly")
            else:
                widget = ttk.Entry(area, textvariable=var, show="●" if key.endswith("_KEY") or key=="AMAP_SECURITY_JSCODE" else "")
            widget.pack(fill="x", pady=(3, 0))
            self.fields[key] = var
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(10, 8))
        self.save_button = ttk.Button(row, text="保存并应用", command=self.apply_settings)
        self.save_button.pack(side="left")
        self.devices_button = ttk.Button(row, text="刷新设备列表", command=self.refresh_devices)
        self.devices_button.pack(side="left", padx=8)
        ttk.Label(row, text=r"配置：F:\Javis_os\config\.env", font=("Microsoft YaHei UI", 9)).pack(side="right")
        ttk.Label(parent, text="设备编号可能在重启后变化。下方选择设备会填入编号，再点击“保存并应用”。",
                  wraplength=950).pack(anchor="w")
        self.device_tree = ttk.Treeview(parent, columns=("id", "name", "kind", "api", "rate"), show="headings", height=4)
        for name, title, width in (("id", "编号", 50), ("name", "设备名称", 370), ("kind", "通道 / 默认", 150),
                                    ("api", "驱动", 110), ("rate", "建议/默认采样率", 125)):
            self.device_tree.heading(name, text=title)
            self.device_tree.column(name, width=width, stretch=name == "name")
        self.device_tree.pack(fill="both", expand=True, pady=7)
        device_row = ttk.Frame(parent)
        device_row.pack(fill="x")
        ttk.Button(device_row, text="选中设备作为输入", command=lambda: self.choose_device("INPUT_DEVICE")).pack(side="left")
        ttk.Button(device_row, text="选中设备作为输出", command=lambda: self.choose_device("OUTPUT_DEVICE")).pack(side="left", padx=8)
        ttk.Label(parent, text="api 模式会将对话、相关记忆或录音发往所填服务商。Windows 播报使用已安装系统语音。"
                  "密钥以明文保存在 .env；不要分享该文件。", wraplength=990, font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(8, 0))
        self.device_data = {}

    def append(self, text, role):
        self.transcript.configure(state="normal")
        label = {"user": "你", "assistant": "JARVIS"}.get(role, "提示")
        self.transcript.insert("end", f"{label}  ·  {text}\n\n", role)
        self.transcript.configure(state="disabled")
        self.transcript.see("end")

    def update_mode(self):
        mode = "模拟模式 · 无云端请求" if self.settings.CHAT_MODE == "mock" else f"云端 · {self.settings.API_MODEL}"
        self.mode.set(mode)

    def controls(self):
        state = "disabled" if self.busy else "normal"
        for button in (self.send_button, self.new_button, self.export_button, self.play_button,
                       self.speak_button, self.save_button, self.devices_button):
            button.configure(state=state)
        self.record_button.configure(state="normal" if self.recording or not self.busy else "disabled",
                                     text="■ 停止 F8" if self.recording else "● 录音 F8")
        self.session_list.configure(state=state)

    def start(self, label, fn, kind):
        if self.busy or self.closing:
            return False
        self.busy = True
        self.task_kind = kind
        self.task_label = label
        self.status.set(label)
        self.controls()
        def worker():
            try:
                self.events.put((kind, fn()))
            except (ServiceError, ValueError) as exc:
                self.events.put(("error", str(exc)))
            except Exception as exc:
                LOG.error("worker_failed category=%s", type(exc).__name__)
                self.events.put(("error", "操作失败，详细事件类别已记录在 logs\\jarvis.log。"))
            finally:
                self.events.put(("idle", None))
        thread = threading.Thread(target=worker, daemon=True, name="jarvis-" + kind)
        self.workers = [item for item in self.workers if item.is_alive()]
        self.workers.append(thread)
        thread.start()
        return True

    def poll(self):
        if self.closing:
            return
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "error":
                    self.error_until = time.monotonic() + 5
                    self.status.set(payload)
                    self.append(payload, "notice")
                    self.pending_speech = None
                elif kind == "idle":
                    self.busy = self.recording = False
                    self.controls()
                    if self.pending_speech:
                        text, self.pending_speech = self.pending_speech, None
                        self.speak(text)
                elif kind == "reply":
                    answer, state = payload
                    self.last_answer = answer
                    self.append(answer, "assistant")
                    self.emotion.set(f"情绪状态：{state.label} · {state.reason}（规则，未训练）")
                    self.status.set("回复完成")
                    self.refresh_sessions()
                    self.refresh_memories()
                    if self.settings.AUTO_SPEAK == "true":
                        self.pending_speech = answer
                elif kind == "record":
                    path, text = payload
                    self.last_record = path
                    self.append(f"录音已保存：{path}", "notice")
                    if text:
                        self.input.insert("end", text)
                        self.status.set("识别完成；请检查输入框中的文字，再点击发送。")
                    else:
                        self.status.set("录音已保存；语音识别未启用，请手动输入文字，或在设置页开启 api 识别。")
                elif kind == "devices":
                    for item in self.device_tree.get_children():
                        self.device_tree.delete(item)
                    self.device_data = {str(item["index"]): item for item in payload}
                    for item in payload:
                        marks = (" 默认输入" if item["default_in"] else "") + (" 默认输出" if item["default_out"] else "")
                        self.device_tree.insert("", "end", iid=str(item["index"]),
                            values=(item["index"], item["name"], f"入{item['inputs']} / 出{item['outputs']}{marks}",
                                    item["hostapi"], item["rate"]))
                    self.status.set(f"检测到 {len(payload)} 个音频设备/驱动条目。")
                elif kind == "notice":
                    self.status.set(payload)
        except queue.Empty:
            pass
        self.root.after(80, self.poll)

    def send(self):
        if self.busy or self.closing:
            return "break"
        text = self.input.get("1.0", "end").strip()
        if not text:
            return "break"
        if len(text) > 20000:
            self.status.set("输入超过 20000 字，请缩短。")
            return "break"
        sid, settings = self.session_id, self.settings
        self.input.delete("1.0", "end")
        self.append(text, "user")
        self.start("正在生成回复…", lambda: self.conversation.reply(sid, text, settings), "reply")
        return "break"

    def toggle_record(self):
        if self.recording:
            self.audio.stop()
            self.status.set("正在停止录音并保存…")
            return
        if self.busy:
            return
        self.audio.prepare()
        settings = self.settings
        self.recording = True
        def record():
            path = self.audio.recording(settings)
            if settings.ASR_MODE == "api":
                self.events.put(("notice", "录音已保存，正在上传至配置的服务商识别…"))
                try:
                    text = CloudAPI(settings).transcribe(path)
                except ServiceError as exc:
                    # Preserve access to playback even when cloud ASR fails.
                    self.events.put(("record", (path, "")))
                    raise exc
                return path, text
            return path, ""
        if not self.start(f"录音中 · 再按 F8 停止 · 最长 {settings.MAX_RECORD_SECONDS} 秒", record, "record"):
            self.recording = False

    def stop_audio(self):
        self.audio.stop()
        self.status.set("已请求停止音频；正在进行的云端请求会在完成或超时后结束。")

    def play_record(self):
        if self.last_record is None:
            self.status.set("请先录制一段音频。")
            return
        self.audio.prepare()
        path, settings = self.last_record, self.settings
        def play():
            self.audio.play(path, settings)
            return "录音播放结束。"
        self.start("正在播放录音…", play, "notice")

    def speak(self, text):
        if self.busy:
            return
        if not text:
            self.status.set("请先发送一条消息，获得回复后再播报。")
            return
        self.audio.prepare()
        settings = self.settings
        self.start("正在生成/播放语音…", lambda: self.audio.speak(text, settings), "notice")

    def refresh_sessions(self):
        self.sessions_data = self.store.sessions()
        self.session_list.delete(0, "end")
        for index, (sid, title, _) in enumerate(self.sessions_data):
            self.session_list.insert("end", title)
            if sid == self.session_id:
                self.session_list.selection_set(index)

    def select_session(self, event=None):
        if self.busy:
            return
        selection = self.session_list.curselection()
        if not selection:
            return
        self.session_id = self.sessions_data[selection[0]][0]
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self.last_answer = ""
        for message in self.store.history(self.session_id, 300):
            self.append(message["content"], message["role"])
            if message["role"] == "assistant":
                self.last_answer = message["content"]
        self.status.set("已载入对话（最近 300 条）。")

    def new_session(self):
        if self.busy:
            return
        self.session_id = self.store.new_session()
        self.last_answer = ""
        self.refresh_sessions()
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self.append("新对话已创建，长期记忆继续保留。", "notice")

    def export_history(self):
        try:
            name = "history_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json"
            path = ROOT / "data" / name
            path.write_text(json.dumps(self.store.history(self.session_id, 100000), ensure_ascii=False, indent=2), encoding="utf-8")
            self.status.set(f"已导出：{path}")
        except Exception:
            self.status.set("导出失败，请检查 data 目录写入权限。")

    def refresh_memories(self):
        for item in self.memory_tree.get_children():
            self.memory_tree.delete(item)
        rows = self.store.memories()
        self.memory_count = len(rows)
        for memory_id, text, created in rows:
            self.memory_tree.insert("", "end", iid=str(memory_id), values=(memory_id, text[:100], created))

    def select_memory(self, event=None):
        selection = self.memory_tree.selection()
        if not selection:
            return
        record = next((item for item in self.store.memories() if str(item[0]) == selection[0]), None)
        if record:
            self.memory_detail.configure(state="normal")
            self.memory_detail.delete("1.0", "end")
            self.memory_detail.insert("1.0", record[1])
            self.memory_detail.configure(state="disabled")

    def add_memory(self):
        try:
            self.store.remember(self.memory_input.get())
            self.memory_input.delete(0, "end")
            self.refresh_memories()
            self.status.set("长期记忆已保存。")
        except Exception as exc:
            self.status.set(str(exc) if isinstance(exc, ValueError) else "保存记忆失败，请检查数据库。")

    def delete_memory(self):
        selection = self.memory_tree.selection()
        if selection:
            try:
                self.store.forget(selection[0])
                self.refresh_memories()
                self.memory_detail.configure(state="normal")
                self.memory_detail.delete("1.0", "end")
                self.memory_detail.configure(state="disabled")
                self.status.set("已删除选中记忆。")
            except Exception:
                self.status.set("删除记忆失败，请检查数据库。")

    def apply_settings(self):
        if self.busy:
            return
        try:
            settings = Settings(**{key: var.get().strip() for key, var in self.fields.items()}).validated()
            save_settings(settings)
            self.settings = settings
            self.update_mode()
            self.status.set("配置已保存并应用。密钥只保存在 config\\.env。")
            LOG.info("settings_saved")
        except (ValueError, OSError) as exc:
            messagebox.showerror("无法保存配置", str(exc) if isinstance(exc, ValueError) else "配置目录无法写入。", parent=self.root)

    def refresh_devices(self):
        self.start("正在检查本机音频设备…", devices, "devices")

    def choose_device(self, target):
        selection = self.device_tree.selection()
        if not selection:
            self.status.set("请先在设备表中选中一行。")
            return
        device = self.device_data[selection[0]]
        if not device["inputs" if target == "INPUT_DEVICE" else "outputs"]:
            self.status.set("所选设备不支持此方向，请选择另一项。")
            return
        self.fields[target].set(selection[0])
        self.status.set("设备编号已填入，请点击“保存并应用”。")

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.audio.close()
        self.hud.stop()
        if self.clock_after:
            self.root.after_cancel(self.clock_after)
        LOG.info("application_closing")
        self.root.destroy()
