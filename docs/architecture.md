# 架构与模块

main.py 检查唯一工作根目录，初始化配置、日志和应用锁，再启动 Python 本机 HTTP 服务及 Edge 普通应用窗口。

- desktop.py：受本机随机令牌保护的界面/API、状态轮询、交互任务管理。
- space_ui/scene.js：状态栏、快捷键和设置；visual.js：能量体、WebGL 后处理；city.js：真实轮廓生成立体粒子建筑、道路与双向变形。
- space_ui/navigation.js：地图 SDK 加载、地点核验、并行交通比较；places.js：本市地点排序、歧义检查。
- navigation.py：可解释导航意图、上下文与取消状态；city_data.py / vector_city.py：受限城市范围的公开矢量获取与解析。
- api.py：OpenAI-compatible 对话、识别和播报协议；独立 ASR 凭证避免错发给对话服务。
- audio.py / native_audio.py：音频适配、WinMM 排队播放、系统 TTS 和行字幕时间点。耗时工作在后台执行。
- storage.py：SQLite 历史和显式长期记忆；emotion.py：未训练的规则情绪接口。
- weather.py / telemetry.py：天气来源与过期状态、运行负载。
- gui.py / hud.py：保留的早期 tkinter 界面模块；当前默认入口使用网页界面。

默认不依赖本地大模型，不建立外接硬件连接。所有应用文件写入 F:\Javis_os 子目录。浏览器加载的第三方地图 SDK 与联网云服务需要用户配置各自凭证。

当前为原型，规则导航不覆盖全部自然语言；长期记忆不是向量数据库。训练参考与运行代码独立，没有交付训练权重。
