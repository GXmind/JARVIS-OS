# API 申请与配置说明

核对日期：2026-10-27。平台界面、模型和额度可能调整；申请与可用能力以服务商控制台和下列官方文档为准。此文不提供真实密钥。

## 需要哪些服务

| 功能 | 是否需要 API | 本项目配置 |
| --- | --- | --- |
| 模拟对话、文字输入、能量体 | 不需要 | CHAT_MODE=mock |
| 云端对话 | 需要兼容 Chat Completions 的服务 | API_BASE_URL、API_MODEL、API_KEY |
| 麦克风录音 | 不需要云端 Key | INPUT_DEVICE 等本机设备设置 |
| 录音转文字 | 需要支持音频转写的服务 | ASR_BASE_URL、ASR_MODEL、ASR_API_KEY |
| Windows 系统播报 | 不需要 | TTS_MODE=windows、AUTO_SPEAK=true |
| 云端播报 | 需要支持 audio/speech 的服务 | 复用 API_BASE_URL、API_KEY；另填 TTS_MODEL、TTS_VOICE |
| 高德地点、路线和优先天气实况 | 需要 Web 端 JS API Key 与安全密钥 | AMAP_JS_KEY、AMAP_SECURITY_JSCODE |
| 局部城市矢量 | 本项目无需额外填写 Key | 由公开 OpenFreeMap 数据源提供 |

对话、ASR 和 TTS 不是同一个模型。文本对话服务不能自动识别录音，也不能因为能聊天就认定支持语音播报。

## 高德地图

1. 进入 [高德开放平台](https://lbs.amap.com/) 并登录开发者控制台。
2. 在应用管理中建立用于本项目的应用，添加平台类型为 **Web端（JS API）** 的 Key。
3. 获取该 Key 配套的安全密钥（securityJsCode），按控制台要求配置该应用的权限、配额和来源限制。
4. 在本机按 F2，分别填写“高德 Web端（JS API）Key”和“高德安全密钥”，保存。不要把 Web 服务 API Key 或移动端 Key 混填到 JS API 字段。
5. 地图城市填写“苏州”等实际城市；常用出发地填具体地址或公共 POI。只说目的地时会使用这个起点，电脑没有 GPS 定位保证。

本项目启动本机随机端口的 127.0.0.1 页面。若账号设置来源/白名单限制，按当前控制台的本机调试规则核对，不要填写无关域名。正式网络部署需要另外设计固定来源和受保护代理，本项目默认只用于本机运行。

JS Key 会用于浏览器 SDK；配套安全密钥由本机 Python 代理使用。不要把“使用代理”误解为 JS Key 不会出现在浏览器中。相关机制见 [高德准备说明](https://lbs.amap.com/api/javascript-api-v2/prerequisites) 和 [安全密钥与代理说明](https://lbs.amap.com/api/javascript-api-v2/guide/abc/jscode)。

此版本不要求在项目中再填写一套独立 Web 服务 Key，也没有对应字段。若平台报权限错误，应检查账户、Key 类型、服务权限和配额，而不是随便更换成其他平台类型。

### 验证

先输入“帮我导航从苏州站到拙政园”。确认左侧显示实际匹配的 POI 名称和地址，以及打车、自驾、公共交通、步行。多个可靠的同名地点需要选择；不应继续沿用“正在调用高德”的过期字幕。

Key 无效、平台不匹配、安全码错误、配额不足和网络超时都应按界面实际原因排查。没有建筑数据不等于高德路线失败：楼宇来自另一个数据源。

天气默认示例为苏州虎丘区，WEATHER_ADCODE=320505。更改地区时应核对对应行政区编码；区县实况不等于住宅或室内温度。

## 对话 API：以 DeepSeek 为例

通过 [DeepSeek 官方接入文档](https://api-docs.deepseek.com/zh-cn/) 中的控制台入口创建 API Key，并确认账号能使用所选模型。

在 F2 中填写：

| 字段 | 示例 |
| --- | --- |
| CHAT_MODE | api |
| API_BASE_URL | https://api.deepseek.com |
| API_MODEL | deepseek-flash |
| API_KEY | 在本机填写自己申请的 Key |

上述模型名来自核对日的官方文档；如果平台调整名称，以控制台可用模型为准。其他服务可以填写自己的兼容地址和模型，不要求只能使用某一模型家族。

本项目向基础地址追加 chat/completions；不要把控制台网页地址或 API Key 管理页填成 API 基础地址。先用文字输入验证一问一答，再启用音频链路。

DeepSeek 的这组配置用于对话，不能把 deepseek-flash 填入 ASR_MODEL 期待它接收录音。

## 语音识别：以 SiliconFlow 为例

在 [SiliconFlow 平台](https://cloud.siliconflow.cn/) 登录，创建 API Key，并在模型服务中确认有权调用音频转写模型。请求格式与支持模型见 [官方音频转写接口](https://docs.siliconflow.cn/docs/api/audio-transcriptions-post)。

| 字段 | 示例 |
| --- | --- |
| ASR_MODE | api |
| ASR_BASE_URL | https://api.siliconflow.cn/v1 |
| ASR_MODEL | FunAudioLLM/SenseVoiceSmall |
| ASR_API_KEY | 在本机填写对应服务的 Key |

模型例子以核对日官方接口为依据。独立识别地址必须配自己的 Key；本项目不会把另一个对话服务的 Key 自动发送过去。识别基础地址不应填成控制台网址。

测试时按 F8 开始录音，再按 F8 结束，确认先得到文字，再进入对话或导航。若没有声音输入，先检查 Windows 麦克风权限和设备；若有录音但提示 401/404/额度错误，再检查服务配置。真实识别会向所填服务上传录音。

## 播报

默认可使用 Windows System.Speech，无需另申请语音 Key：

```dotenv
TTS_MODE="windows"
AUTO_SPEAK="true"
```

需要电脑安装可用中文语音并选择正确扬声器。F2 的输出设备编号留空使用系统默认。远程桌面音频路由也会影响能否听到。

云端播报需服务商支持相应 audio/speech 接口和音频格式。当前 TTS 复用通用 API_BASE_URL/API_KEY，没有独立的 TTS 服务地址字段；如果通用地址只有文本对话功能，使用 Windows 播报，不能只改模型名来补出不存在的音频接口。

## 保存配置与保护数据

- 首次启动使用 config/.env.example；本机配置保存到 config/.env，密钥不写进源码。
- 通过 F2 保存时，密钥输入留空会保留已保存值；一般设置按界面实际值保存。
- .env 是本机明文文件，不提交、不截图、不发到 issue。
- 申请时检查平台当前额度和计费规则，本说明不承诺免费或固定价格。
- 日志、录音、行程和聊天历史只保留在项目根目录的运行子目录。

## 地图分支附加设置

main 仍保持已发布基线。feature/map-update 额外提供 MAP_VIEW_METERS（600–5000，默认1600）与 MAP_HEIGHT_SCALE（1–32，默认16），用于显示尺度与楼高强调，不需要另申请 API。高度强调不是地理数据源的实际高度。
