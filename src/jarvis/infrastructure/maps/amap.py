"""Fixed-host AMap proxy; security credentials never follow redirects."""
import json
import re
from urllib import request,error,parse
from jarvis.domain.errors import ServiceError
from jarvis.infrastructure.http.transport import NoRedirect

def build_proxy_url(path,query,settings):
    if not settings.AMAP_JS_KEY or not settings.AMAP_SECURITY_JSCODE:
        raise ServiceError("高德地图尚未配置完整，请填写 JS API Key 和安全密钥。")
    if len(query)>32000:
        raise ServiceError("地图请求过长。")
    prefix="/_AMapService"
    if not path.startswith(prefix+"/"):
        raise ServiceError("地图代理路径无效。")
    suffix=parse.unquote(path[len(prefix):])
    if any(char in suffix for char in ("\r","\n","\\","?","#","@")) or ".." in suffix or "//" in suffix:
        raise ServiceError("地图代理路径无效。")
    if not suffix.startswith(("/v3/","/v4/","/v5/")):
        raise ServiceError("不支持的地图服务路径。")
    host="https://webapi.amap.com" if suffix.startswith("/v4/map/styles") else "https://restapi.amap.com"
    pairs=[(k,v) for k,v in parse.parse_qsl(query,keep_blank_values=True,max_num_fields=100)
           if k.lower() not in ("key","jscode")]
    pairs.extend((("key",settings.AMAP_JS_KEY),("jscode",settings.AMAP_SECURITY_JSCODE)))
    return host+suffix+"?"+parse.urlencode(pairs)


def normalize_proxy_response(body,mime,query):
    """Preserve nosniff while correctly identifying provider JSONP as JavaScript."""
    pairs=parse.parse_qs(query,keep_blank_values=True,max_num_fields=100)
    callback=(pairs.get("callback") or [""])[0]
    if not callback:
        return body,mime
    if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*",callback):
        raise ServiceError("地图回调名称无效。")
    raw=body.decode("utf-8-sig")
    if re.match(r"^\s*"+re.escape(callback)+r"\s*\(",raw):
        return body,"text/javascript; charset=utf-8"
    # Some provider errors omit the callback wrapper; make these readable to the SDK too.
    try:
        payload=json.loads(raw)
    except (ValueError,UnicodeError):
        return body,mime
    return (callback+"("+json.dumps(payload,ensure_ascii=True)+");").encode("utf-8"),"text/javascript; charset=utf-8"


def fetch_proxy(path,query,settings,origin):
    url=build_proxy_url(path,query,settings)
    # No redirects: security credentials only travel to the fixed AMap hosts above.
    for opener in (request.build_opener(NoRedirect()),request.build_opener(request.ProxyHandler({}),NoRedirect())):
        try:
            req=request.Request(url,headers={"User-Agent":"JARVIS-Desktop/0.2","Referer":origin+"/"})
            with opener.open(req,timeout=8) as response:
                body=response.read(12_000_001)
                mime=response.headers.get("Content-Type","application/json")
            if len(body)>12_000_000:raise ServiceError("地图响应超过大小限制。")
            if not any(value in mime.lower() for value in ("json","javascript","text/plain")):
                raise ServiceError("地图服务返回了不支持的数据格式。")
            return normalize_proxy_response(body,mime,query)
        except error.HTTPError as exc:
            exc.close()
            raise ServiceError("高德服务请求失败，请检查应用权限、白名单和调用配额。") from None
        except (error.URLError,TimeoutError,OSError):
            continue
    raise ServiceError("高德服务连接失败，请检查网络；未生成导航路线。")
