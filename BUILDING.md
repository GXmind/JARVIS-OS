# Windows 构建与运行说明

本项目的当前“构建”方式是准备 Python 环境后直接运行源码。网页资源和 Three.js 已随源码提供，没有 webpack/Vite 编译步骤，也不需要安装 Node 才能启动助手。仓库没有已验证的独立 exe 安装包。

## 环境

| 项目 | 要求 |
| --- | --- |
| 系统 | Windows 10/11 |
| Python | 3.10+；本机验证使用 3.12.7，建议 3.12 |
| GUI | Microsoft Edge，启用图形加速和 WebGL2 |
| 录音/播放 | Windows 音频设备和相应权限 |
| Node.js | 22+，仅运行前端回归测试时需要 |
| 网络 | 云端对话、ASR、地图、天气与城市数据按需使用 |

默认 Python 运行依赖为标准库、Windows WinMM 和 System.Speech；`requirements.txt` 没有必须下载的第三方包。`requirements-audio.txt` 仅用于可选 sounddevice 后端。Python 环境说明见 [Windows 官方文档](https://docs.python.org/3.12/using/windows.html) 和 [venv 文档](https://docs.python.org/3.12/library/venv.html)。

## 1. 获取源码

目标目录尚不存在时，在 PowerShell 运行：

```powershell
git clone --branch main https://github.com/GXmind/JARVIS-OS.git F:\Javis_os
Set-Location -LiteralPath F:\Javis_os
```

如要测试地图开发分支，可在干净的 Git 工作区内切换：

```powershell
git fetch origin
git switch feature/map-update
```

若目标目录已存在，不要删除目录或强制 reset 来重新安装。先检查 `git status` 并保留本机数据；如果现有目录并非 Git 仓库，先整理备份和迁移方案，避免直接覆盖已有文件。

## 2. 一键运行

```powershell
.\start.cmd
```

启动脚本检查固定根目录、创建项目内 .venv 和运行目录，再启动普通 Edge 应用窗口。没有 Python 时会提示安装；不要求本地大模型。第一次启动从无密钥模板生成本机配置，已有 .env 不会自动覆盖。

默认 mock 对话、关闭 ASR；Windows 播报可按 F2 配置。模型与地图接入见 [API_SETUP.md](docs/API_SETUP.md)。

## 3. 手动准备环境

需要调试或运行测试时，可显式创建环境。以下命令不要求激活虚拟环境：

```powershell
Set-Location -LiteralPath F:\Javis_os
New-Item -ItemType Directory -Force -Path .\tmp,.\cache\pip,.\logs | Out-Null
$env:TEMP = 'F:\Javis_os\tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:PIP_CACHE_DIR = 'F:\Javis_os\cache\pip'
$env:PYTHONPYCACHEPREFIX = 'F:\Javis_os\cache\python'
$env:PYTHONIOENCODING = 'utf-8'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -B main.py --self-check
```

使用其他已安装且受支持的 Python 时，替换 `py -3.12`。默认运行不需要 `pip install`。只有需要可选音频后端时，才运行 `scripts\install_audio.cmd`；下载缓存仍留在根目录。

## 4. 自动检查

Python 单元测试：

```powershell
Set-Location -LiteralPath F:\Javis_os
$env:PYTHONPATH = 'F:\Javis_os\src'
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
```

也可双击 `scripts\test.cmd`。当前 main 的基线为 105 项；feature/map-update 增加地图精度与配置测试后为 113 项。实际数量以运行结果为准。

前端几何、地点及操作测试：

```powershell
$env:NPM_CONFIG_CACHE = 'F:\Javis_os\cache\npm'
npm test
```

`package.json` 没有 npm 运行依赖，不需要先运行 npm install。不同分支的 test 脚本覆盖其对应实现。

真实浏览器自检：

```powershell
.\.venv\Scripts\python.exe -B main.py --smoke-ui
```

此检查验证 WebGL、交互、合成地图 SDK、设置和退出流程，使用隔离测试数据。它不等于真实高德服务或真实云端模型已通过。

音频自检：

```powershell
.\.venv\Scripts\python.exe -B main.py --self-check --audio --tts
```

这个命令会实际录音和播放。结果保存在本机 logs；播放调用成功仍需人耳确认声音和音质。

## 5. 构建产物与发布内容

源码运行不生成 dist。可公开的内容为源码、启动脚本、无密钥配置模板、测试、许可和通用文档。不要将 .venv、浏览器 profile、缓存、数据库或录音复制进发布包。

若未来新增 exe 打包流程，应另外验证资源路径、固定根目录、系统 TTS、Edge 启动与第三方许可，再在文档中记录；当前不能把未验证的打包命令写成可用安装包。

## 故障定位

| 现象 | 检查 |
| --- | --- |
| 双击没有窗口 | logs/launcher_stderr.log、Python 安装、Edge 是否可用 |
| 提示目录错误 | 源码必须直接位于 F:\Javis_os，不应再套一层仓库名目录 |
| 图形黑屏或报 WebGL 错误 | Edge 图形加速、显卡驱动；尝试 F6 节能特效 |
| 语音输入无文字 | 麦克风权限、输入设备、独立 ASR 地址/Key/模型 |
| Windows 播报无声 | 输出设备、音量、系统语音包、AUTO_SPEAK |
| 地图停在准备阶段 | 看中央实际阶段及左侧地点候选，不要只看上一句语音字幕 |
| 楼宇缺失 | 城市矢量数据源覆盖及网络；不要拿随机模型填补 |

本机服务绑定 127.0.0.1，不是面向公网部署的 Web 服务。不要为了远程访问而直接改成公开监听。
