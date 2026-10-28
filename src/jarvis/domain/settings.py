"""Validated application settings and public map configuration; no persistence."""
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

def api_base(value):
    value = value.strip().rstrip("/")
    parts = urlsplit(value)
    try:
        parts.port
    except ValueError:
        raise ValueError("API 地址端口无效。") from None
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("API 地址必须是无用户名、密码、查询参数的基础地址。")
    if parts.scheme != "https" and not (
        parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")
    ):
        raise ValueError("云端 API 必须使用 HTTPS；仅本机测试地址允许 HTTP。")
    # Accept pasted full Chat Completions URL as a convenience.
    path = parts.path.rstrip("/")
    if path.endswith("/chat/completions"):
        path = path[:-len("/chat/completions")]
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


@dataclass(frozen=True)
class Settings:
    API_BASE_URL: str = ""
    API_MODEL: str = ""
    API_KEY: str = ""
    CHAT_MODE: str = "mock"
    ASR_MODE: str = "off"
    ASR_MODEL: str = ""
    ASR_BASE_URL: str = ""
    ASR_API_KEY: str = ""
    TTS_MODE: str = "windows"
    TTS_MODEL: str = ""
    TTS_VOICE: str = "alloy"
    INPUT_DEVICE: str = ""
    OUTPUT_DEVICE: str = ""
    SAMPLE_RATE: str = "16000"
    MAX_RECORD_SECONDS: str = "60"
    REQUEST_TIMEOUT: str = "45"
    AUTO_SPEAK: str = "false"
    WEATHER_CITY: str = "苏州虎丘区"
    WEATHER_ADCODE: str = "320505"
    AMAP_JS_KEY: str = ""
    AMAP_SECURITY_JSCODE: str = ""
    AMAP_CITY: str = "苏州"
    AMAP_DEFAULT_ORIGIN: str = ""
    MAP_VIEW_METERS: str = "1600"
    MAP_HEIGHT_SCALE: str = "16"

    def asr_connection(self):
        # An explicit speech provider must have its own credential.
        # Never send the chat provider's key to another configured host.
        if self.ASR_BASE_URL.strip():
            base=api_base(self.ASR_BASE_URL)
            if base.endswith("/audio/transcriptions"):
                base=base[:-len("/audio/transcriptions")]
            return base,self.ASR_API_KEY.strip()
        return api_base(self.API_BASE_URL),self.ASR_API_KEY.strip() or self.API_KEY.strip()

    def validated(self):
        for key,low,high in (("MAP_VIEW_METERS",600,5000),("MAP_HEIGHT_SCALE",1,32)):
            try:value=float(getattr(self,key))
            except (TypeError,ValueError):raise ValueError(key+" 必须为数字。") from None
            if not low<=value<=high:raise ValueError(key+" 超出支持范围。")
        if self.WEATHER_ADCODE and not (self.WEATHER_ADCODE.isdigit() and len(self.WEATHER_ADCODE)==6):
            raise ValueError("天气行政区编码应为 6 位数字。")
        if len(self.AMAP_DEFAULT_ORIGIN)>120:
            raise ValueError("常用出发地名称过长。")
        if len(self.AMAP_CITY)>60:
            raise ValueError("地图城市名称过长。")
        for field in ("AMAP_JS_KEY","AMAP_SECURITY_JSCODE"):
            value=getattr(self,field)
            if len(value)>512 or any(ord(char)<32 or ord(char)>126 for char in value):
                raise ValueError("地图凭证须为不含换行的 ASCII 字符串。")
        if len(self.WEATHER_CITY)>60:
            raise ValueError("天气城市名称过长。")
        if self.API_BASE_URL:
            api_base(self.API_BASE_URL)
        if self.ASR_BASE_URL:
            api_base(self.ASR_BASE_URL)
        needs_shared_base=self.CHAT_MODE=="api" or self.TTS_MODE=="api" or (self.ASR_MODE=="api" and not self.ASR_BASE_URL)
        if needs_shared_base and not self.API_BASE_URL:
            raise ValueError("启用云端功能前请填写对应的 API 基础地址。")
        for key, modes in {
            "CHAT_MODE": ("mock", "api"),
            "ASR_MODE": ("off", "api"),
            "TTS_MODE": ("off", "windows", "api"),
            "AUTO_SPEAK": ("true", "false"),
        }.items():
            if getattr(self, key) not in modes:
                raise ValueError(f"{key} 的选项无效。")
        for key, lo, hi in (
            ("SAMPLE_RATE", 8000, 96000), ("MAX_RECORD_SECONDS", 1, 120),
            ("REQUEST_TIMEOUT", 5, 120),
        ):
            try:
                number = int(getattr(self, key))
            except ValueError:
                raise ValueError(f"{key} 必须为整数。") from None
            if not lo <= number <= hi:
                raise ValueError(f"{key} 必须在 {lo}–{hi} 之间。")
        for name in ("INPUT_DEVICE", "OUTPUT_DEVICE"):
            value = getattr(self, name)
            if value and (not value.isdigit() or int(value) < 0):
                raise ValueError("设备编号必须为空或非负整数。")
        if self.CHAT_MODE == "api" and (not self.API_KEY.strip() or not self.API_MODEL.strip()):
            raise ValueError("云端对话需要填写 API 密钥及模型名；也可以选择 mock 模式。")
        if self.ASR_MODE == "api":
            _,key=self.asr_connection()
            if not key or not self.ASR_MODEL.strip():
                raise ValueError("云端识别需要语音识别模型及密钥；填写独立识别地址时，也必须填写独立识别密钥。")
        if self.TTS_MODE == "api" and (not self.API_KEY.strip() or not self.TTS_MODEL.strip() or not self.TTS_VOICE.strip()):
            raise ValueError("云端播报需要 API 密钥、语音模型及音色。")
        if any(ord(c) < 32 for c in self.API_KEY+self.ASR_API_KEY):
            raise ValueError("API 密钥不能包含换行或控制字符。")
        return self


SECRET_FIELDS=("API_KEY","ASR_API_KEY","AMAP_JS_KEY","AMAP_SECURITY_JSCODE")

def map_config(settings):
    key=settings.AMAP_JS_KEY.strip()
    secret=settings.AMAP_SECURITY_JSCODE.strip()
    return {"configured":bool(key and secret),"has_key":bool(key),"has_security_code":bool(secret),
            "key":key if key and secret else "","city":settings.AMAP_CITY or "苏州",
            "view_meters":float(settings.MAP_VIEW_METERS),"height_scale":float(settings.MAP_HEIGHT_SCALE),
            "provider":"AMap","service_path":"/_AMapService","default_origin":settings.AMAP_DEFAULT_ORIGIN,"weather_city":settings.WEATHER_CITY,"weather_adcode":settings.WEATHER_ADCODE,
            "message":"" if key and secret else "请在 F2 设置中填写高德 Web端（JS API）Key 和配套安全密钥。"}
