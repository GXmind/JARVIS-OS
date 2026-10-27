"""OpenAI-compatible HTTP adapter using the standard library, no SDK cache."""
from dataclasses import replace
from urllib.parse import urlsplit
import json
import logging
import socket
from urllib import request, error
import uuid
from .config import api_base
from .paths import local_path

LOG = logging.getLogger("jarvis")

class ServiceError(RuntimeError):
    """Sanitized message that may safely appear in the GUI."""

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward a bearer token to a redirected host.

class CloudAPI:
    def __init__(self, settings):
        self.settings = settings
        self.base = api_base(settings.API_BASE_URL) if settings.API_BASE_URL else ""
        self.opener = request.build_opener(NoRedirect())

    def _post(self, endpoint, payload, content_type="application/json", max_bytes=8_000_000):
        if not self.base:
            raise ServiceError("尚未配置此功能的 API 基础地址，请在 F2 设置中填写。")
        if not self.settings.API_KEY.strip():
            raise ServiceError("尚未配置 API 密钥，请在设置页填写，或切换到模拟模式。")
        req = request.Request(
            self.base + endpoint, data=payload, method="POST",
            headers={"Authorization": "Bearer " + self.settings.API_KEY,
                     "Content-Type": content_type, "User-Agent": "JARVIS-Desktop/0.1"},
        )
        try:
            with self.opener.open(req, timeout=int(self.settings.REQUEST_TIMEOUT)) as response:
                data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise ServiceError("云端响应超过大小限制，请缩短内容后重试。")
            return data
        except error.HTTPError as exc:
            exc.close()
            LOG.warning("api_http_error status=%s", exc.code)
            detail = {
                400: "请求格式或模型不受服务商支持，请检查模型和兼容接口。",
                401: "密钥无效或已过期。",
                403: "账户没有此接口的权限。",
                404: "端点或模型不存在，请检查基础地址及模型名。",
                413: "音频或请求过大，请缩短录音。",
                429: "额度不足或请求过于频繁，请稍后再试。",
            }.get(exc.code, "云端服务返回错误，请稍后重试。")
            raise ServiceError(f"API 错误 {exc.code}：{detail}") from None
        except (error.URLError, socket.timeout, TimeoutError, OSError, ValueError):
            LOG.warning("api_transport_error")
            raise ServiceError("无法连接云端或请求超时，请检查网络、基础地址和超时设置。") from None

    def _json(self, endpoint, payload):
        raw = self._post(endpoint, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise ServiceError("服务商返回的不是有效 JSON。") from None

    def chat(self, messages):
        result = self._json("/chat/completions",
                            {"model": self.settings.API_MODEL, "messages": messages, "stream": False})
        try:
            text = result["choices"][0]["message"]["content"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError()
            return text.strip()
        except (KeyError, IndexError, TypeError, ValueError):
            raise ServiceError("云端响应缺少文字回复；请确认模型支持 Chat Completions。") from None

    def transcription_client(self):
        base,key=self.settings.asr_connection()
        if urlsplit(base).hostname=="api.deepseek.com":
            raise ServiceError("语音识别配置不匹配：DeepSeek 官方接口不提供录音转文字。请在 F2 单独填写语音识别地址、密钥及识别模型；deepseek-flash 可继续用于对话。")
        if not key or not self.settings.ASR_MODEL.strip():
            raise ServiceError("请在 F2 填写语音识别密钥和识别模型。")
        return CloudAPI(replace(self.settings,API_BASE_URL=base,API_KEY=key))

    def transcribe(self, path):
        client=self.transcription_client()
        path = local_path(path)
        if path.stat().st_size > 24_000_000:
            raise ServiceError("录音超过 24 MB，请缩短后重试。")
        boundary = "Jarvis" + uuid.uuid4().hex
        parts = []
        for key, value in (("model", self.settings.ASR_MODEL), ("response_format", "json")):
            parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n"
                          f"{value}\r\n").encode("utf-8"))
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
                      f"filename=\"recording.wav\"\r\nContent-Type: audio/wav\r\n\r\n").encode())
        parts.extend((path.read_bytes(), f"\r\n--{boundary}--\r\n".encode()))
        try:
            raw = client._post("/audio/transcriptions", b"".join(parts),
                               f"multipart/form-data; boundary={boundary}")
        except ServiceError as exc:
            raise ServiceError("语音识别失败："+str(exc)+" 请确认服务商支持 /audio/transcriptions，且此处填写的是语音识别模型。") from None
        try:
            text = json.loads(raw)["text"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError()
            return text.strip()
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise ServiceError("语音识别未返回文字；录音已保留，可以手动输入。") from None

    def synthesize(self, text, path):
        payload = {"model": self.settings.TTS_MODEL, "voice": self.settings.TTS_VOICE,
                   "input": text[:2000], "response_format": "wav"}
        data = self._post("/audio/speech", json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          max_bytes=24_000_000)
        if not data.startswith(b"RIFF") or data[8:12] != b"WAVE":
            raise ServiceError("播报接口没有返回 WAV 音频；请检查服务商是否支持该格式。")
        local_path(path).write_bytes(data)