# 协作说明

本项目是 Windows 上的 JARVIS 原型，默认以 Python 本机服务和网页界面运行。请先阅读 [构建说明](BUILDING.md)、[API 申请与配置](docs/API_SETUP.md) 和 [架构说明](docs/architecture.md)。

## 分支与同步

`main` 是当前可运行基线。地图更新已通过 [PR #1](https://github.com/GXmind/JARVIS-OS/pull/1) 合入；分支名称不代表功能仍待合并。新工作使用目的明确的分支，是否同步 main 按用户当前授权执行，不另加确认流程。不要强制推送或重写共享历史。

开始前查看 `git status --short --branch`，正常获取远程记录并检查差异，保留已有未提交工作。提交说明问题、最终行为、验证与外部限制。远程出现新提交时先整合，不覆盖远程历史。

## 运行目录与文件

程序严格使用 `F:\Javis_os`。源码、配置、日志、缓存、数据库、录音和临时文件均留在这个根目录的明确子目录。保持 `Javis_os` 拼写，不自行改成其他目录或用户桌面。

不要提交：

- `config/.env`、真实 API Key 或安全密钥；
- `data`、`recordings`、`logs`、`cache`、`tmp`、`backups`、`.venv`；
- 含私人住址、行程、对话、设备标识或密钥的截图和诊断输出；
- 模型权重、未审查的真实对话数据、自动生成的训练输出。

修改前备份有价值的本机设置和数据；备份保存在根目录内，且不放入 Git。调试前后检查暂存文件，不要直接用 `git add -A` 把整个运行目录提交。公开测试采用公共地点或合成样例；不得以用户住宅作为回归测试常量。

## 代码落点与依赖边界

详细目录见 [架构说明](docs/architecture.md)。保持单向依赖，禁止为图省事重新创建平铺模块或反向导入。

| 修改内容 | 位置 | 协作要求 |
| --- | --- | --- |
| 导航意图、设置校验、情绪、分行 | domain/ | 纯规则，无数据库、网络或设备 |
| 对话、记忆流程、录音/播报编排 | application/ | 依赖 ports，通过 SessionServices 注入 |
| 新模型、ASR、音频、地图或天气供应方 | infrastructure/ 对应领域 | 实现端口，清理服务错误与凭证 |
| 具体服务组合 | bootstrap.py | 正式服务只在这里装配 |
| HTTP、窗口与快捷键 | presentation/web、desktop | 传输层不写 SQL、不实现业务规则 |
| 页面状态栏或设置 | web/assets/ui/ | 保持用户已验收布局 |
| 导航与手势 | web/assets/features/ | 控制器和纯规则分别测试 |
| 能量体、城市粒子与 GPU 资源 | web/assets/rendering/ | 纯几何与 GPU 生命周期分开 |
| 自检与诊断 | diagnostics/、scripts/ | 使用新包路径和隔离数据 |

新增外部能力时：先定义 application/ports.py 中所需接口，在 infrastructure 实现，再在 bootstrap 注入；用替身验证应用流程。不要把服务商 Key、HTTP 请求或 SQL 放入 application。设置增加字段时同时更新 domain.Settings、无密钥 .env.example、F2 表单、配置校验测试与 API 说明。

`presentation/legacy` 是早期 Tkinter 保留区，其直接装配是历史例外；新功能不得继续扩展这一路径。窗口层读取固定路径属于明确例外，其他默认界面不得创建具体服务适配器。

地图必须使用实际服务回执；数据缺失不能用随机城市填充。源高度与视觉强调分离。对话、ASR、TTS 分开，独立 ASR 必须使用独立凭证。情绪当前是透明规则，保留 trained_model=false 与第三方许可。

## 验证与提交

按改动范围验证：

| 改动 | 验证 |
| --- | --- |
| Python 服务、导航、设置、存储 | Python 单元测试及架构依赖测试 |
| 地图几何、地点或操作 | Node 几何、生命周期和手势测试 |
| UI 和粒子渲染 | `main.py --smoke-ui` 和地图压力脚本，检查实际渲染与资源 |
| 外部服务接入 | 使用本机凭证单独联调，明确标注与模拟测试的区别 |
| 音频 | 分别记录自动检查和人耳听感，不把写入设备成功等同于音质已确认 |
| 文档 | 检查命令、相对链接、当前分支适用范围和敏感信息 |

完整命令见 [BUILDING.md](BUILDING.md)。不要为了通过测试而替换真实逻辑，也不要把本机日志直接上传为测试证据。

提交前：

```powershell
git diff --check
git diff --stat
git diff --cached --name-only
git diff --cached
```

确认提交内容后正常 commit/push。涉及密钥时立即停止公开上传，先从暂存区和待发布内容中移除；不要在聊天或 issue 中粘贴真实密钥。

## 问题反馈

请提供分支与提交号、可复现指令、预期和实际结果，以及已经排除敏感字段的错误摘要。涉及同名地点时使用公共 POI；录音或日志需要分享前先检查私人信息。真实服务的权限、配额、网络和地理覆盖应与程序错误分开记录。
