# JARVIS-OS

Windows 上的中文个人助手原型：Python 后端配合 Three.js 网页界面，用电脑麦克风和扬声器完成交互。中央能量体可重组成三维粒子城市，显示真实地图服务返回的导航路线。

![无密钥模拟模式界面](docs/preview.png)

## 当前功能

- 普通窗口运行的星海界面、能量带和细粒子；不默认全屏。
- 文本输入、F8 按键录音、可独立配置的语音识别、Windows 或云端播报。
- OpenAI-compatible Chat API；端点、模型、密钥均通过本机配置保存。
- SQLite 对话历史与显式长期记忆、日志、设备选择和 F2 设置页。
- 高德地点核验与驾车、打车、公共交通、步行比较；默认使用保存的常用起点。
- 中央局部楼宇、道路网和绿色路线粒子，约 2.6 秒展开或收拢；结束导航或切换到无关话题时恢复能量体。
- 虎丘区天气实况与单独注明来源的区域预报。

界面使用 Three.js / WebGL2，默认音频使用 Windows WinMM 和 System.Speech。对话模型在云端运行，无需在电脑上部署大模型。情绪模块目前为可解释规则接口，没有训练好的情感模型。

## 安装与启动

需要 Windows 10/11、Python 3.10+（建议 3.12，包含 tkinter）和 Microsoft Edge，浏览器需开启图形加速。默认功能只依赖 Python 标准库；Three.js 已随源码附带。可选音频后端依赖另列在 requirements-audio.txt。

当前程序严格要求唯一工作目录为 **F:\\Javis_os**，其他位置会提示错误。

首次安装到尚不存在的目标目录：

    git clone https://github.com/GXmind/JARVIS-OS.git F:\Javis_os
    cd /d F:\Javis_os
    start.cmd

也可下载源码并放到该目录，双击 start.cmd。启动脚本在项目下创建 .venv 和运行子目录。已有配置和数据不会自动覆盖；已有项目请先妥善备份，不要删除目录来强行重新克隆。

## 操作

| 操作 | 按键或方法 |
| --- | --- |
| 输入文字 | Enter，输入后提交 |
| 开始/停止录音 | F8 或麦克风按钮 |
| 设置模型、音频、地图凭证 | F2 |
| 手动展开/收起地图 | F3 |
| 调整特效质量 | F6 |
| 收起导航/关闭当前浮层 | Esc |
| 退出程序 | 主界面 Esc，选择退出 |
| 检查城市 | 拖动旋转、滚轮缩放，左侧切换街区或全程 |
| 切换路线 | 左侧打车、自驾、公共交通、步行 |

说或输入“贾维斯，我要去拙政园，帮我规划路线”，会使用 F2 保存的起点。也可明确说“帮我规划从苏州站到虎丘景区的路线，打车前往”。缺少起点或可靠地点匹配时会提示补充，不编造路线。

## 配置 API

首次启动从 config/.env.example 创建 config/.env。也可以在 F2 中填写；真实密钥不应提交到仓库。

| 用途 | 主要配置 |
| --- | --- |
| 对话 | CHAT_MODE=api，API_BASE_URL、API_MODEL、API_KEY |
| 录音转文字 | ASR_MODE=api，ASR_BASE_URL、ASR_MODEL、ASR_API_KEY |
| 播报 | TTS_MODE=windows / api / off，AUTO_SPEAK=true / false |
| 音频设备 | INPUT_DEVICE、OUTPUT_DEVICE；留空使用系统默认 |
| 高德地图 | AMAP_JS_KEY、AMAP_SECURITY_JSCODE、AMAP_CITY、AMAP_DEFAULT_ORIGIN |
| 天气 | WEATHER_CITY、WEATHER_ADCODE；虎丘区示例编码为 320505 |

对话、识别和播报是三项独立能力。DeepSeek 等文本对话接口不能直接承担录音识别；请为识别配置支持音频转写的服务。云端播报需要服务商支持 speech 接口。默认 mock 模式不调用云端；ASR 关闭时可用 Enter 输入文字。

高德凭证需申请“Web端（JS API）”类型及配套安全密钥。当前由本机代理转发受限的地图请求。地点先限定城市搜索，核实名称与地址后按坐标规划；同名歧义通过左侧候选选择，不直接接受服务自动猜测的异地终点。

## 地图表现与边界

导航路线来自高德，局部楼宇与道路矢量来自 OpenFreeMap / OpenMapTiles / OpenStreetMap，坐标转换后在同一 Three.js 场景渲染。建筑轮廓是真实地图数据，楼高可能为提供值或估计值，并有纵向视觉夸张；这不是测绘级数字孪生，也不是高德官方三维楼模。

街区视图保持局部城市大小，全程视图用于查看完整线路。城市数据不可用时会明确提示，不用随机建筑冒充真实楼宇。路线用时随路况变化，打车预估不含等车且不会下单。

没有 ESP32/MCXN947 硬件通信、持续唤醒词监听、自动驾驶或设备控制。训练目录仅提供规划、候选合成示例和微调配置参考，没有训练权重；示例需审核和划分数据后再用于训练。

## 数据与隐私

应用的源码、配置、录音、日志、缓存、数据库和临时文件均存放在 F:\Javis_os 的明确子目录。系统 Python、驱动和 Windows 语音服务来自系统安装位置。

- config/.env 保存本机密钥；data 保存 SQLite 历史与记忆。
- recordings 保存录音；cache 保存音频和地图缓存；logs 保存日志；tmp 保存临时文件。
- 这些私人运行目录、虚拟环境和历史备份均被 .gitignore 排除。
- 启用云端对话会发送当前输入与有限上下文；语音识别会发送录音；云端播报会发送待合成文本。地图请求会发送起终点，可能消耗服务商额度。
- 密钥、数据库与录音目前没有应用层加密；请自行保管并定期备份。

公开仓库不包含真实密钥、录音、聊天历史、私人住址、运行日志、训练权重或本机环境。测试中的地点为公共景点或通用样例。

## 检查与测试

在 F:\Javis_os 下运行：

    .\.venv\Scripts\python.exe -B main.py --self-check
    .\.venv\Scripts\python.exe -B main.py --smoke-ui

单元测试：

    scripts\test.cmd

几何和地点匹配测试需要 Node.js 22+，不需要安装 npm 依赖：

    npm test

实际录音与系统播报自检：

    .\.venv\Scripts\python.exe -B main.py --self-check --audio --tts

麦克风测试会实际录音；播放调用成功不能代替人耳确认音质。常规浏览器自检使用模拟 SDK 和独立数据库，不使用真实地图凭证；真实服务联调需要使用者自行配置。发布前本机 116 项 Python 单元测试和实际 WebGL 正反向动画检查已通过。

## 项目结构

    src/jarvis/             Python 后端、音频、导航、存储与设置
    src/jarvis/space_ui/    网页界面与 Three.js 粒子渲染
    config/.env.example    无密钥配置模板
    scripts/               Windows 启动、自检、测试辅助
    tests/                 离线单元测试及 SDK/几何测试
    training/              训练设计与待审核合成示例
    docs/                  公开架构说明与界面预览

更多说明见 [架构与模块](docs/architecture.md) 和 [开发验证](docs/verification.md)。

## 许可

项目沿用仓库现有的 [Apache License 2.0](LICENSE)。Three.js 使用 MIT，eviltransform 使用 BSD，原始许可随相应文件附带。地图数据及归属说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## feature/map-update

本分支改善近景几何、建筑内院和底高，增加 ×1–×32 楼高强调与完整水平环绕、俯仰、平移、缩放及复位。详见 [地图更新说明](docs/map-update.md)。

全程与浏览修订：默认显示完整起终点和周边路网；左键拖动移动地理视野，右键/Shift 拖动环绕，滚轮放大加载街区。“查看全程”恢复整段路线，地图不会覆盖两侧状态栏。

渲染卡顿与退出的修订及可复现压力检查见 [稳定性说明](docs/map-stability.md)。
