"""AMap integration: deterministic intents and a fixed-host security proxy."""
from http.cookies import SimpleCookie
import json
import re
import threading
from urllib import request,error,parse
from .api import ServiceError,NoRedirect

SECRET_FIELDS=("API_KEY","ASR_API_KEY","AMAP_JS_KEY","AMAP_SECURITY_JSCODE")

def map_config(settings):
    key=settings.AMAP_JS_KEY.strip()
    secret=settings.AMAP_SECURITY_JSCODE.strip()
    return {"configured":bool(key and secret),"has_key":bool(key),"has_security_code":bool(secret),
            "key":key if key and secret else "","city":settings.AMAP_CITY or "苏州",
            "provider":"AMap","service_path":"/_AMapService","default_origin":settings.AMAP_DEFAULT_ORIGIN,"weather_city":settings.WEATHER_CITY,"weather_adcode":settings.WEATHER_ADCODE,
            "message":"" if key and secret else "请在 F2 设置中填写高德 Web端（JS API）Key 和配套安全密钥。"}

def parse_navigation(text,city="苏州",default_origin=""):
    text=str(text).strip().strip("。！？!? ")
    text=re.sub(r"^(?:贾维斯|jarvis)[，,：:\s]*","",text,flags=re.I).strip()
    if re.fullmatch(r"(?:(?:请|帮我)?(?:打开|显示|进入)(?:高德)?地图|(?:高德)?地图(?:导航)?|/地图|/map)",text,re.I):
        return {"action":"open","origin":"","destination":"","city":city,"mode":"compare"}
    route_words=("导航","规划","路线","怎么走","怎么去","我要去","我想去","带我去","出行方式")
    if not any(word in text for word in route_words) and not re.match(r"^(?:去|到|从).+",text):
        return None
    mode="walking" if "步行" in text else "transit" if any(w in text for w in ("公交","地铁","公共交通")) else "taxi" if any(w in text for w in ("打车","出租车")) else "driving" if any(w in text for w in ("自驾","开车","驾车")) else "compare"
    match=re.search(r"从\s*(.+?)\s*(?:到|前往)\s*(.+)$",text)
    explicit=bool(match)
    if match:origin,destination=match.groups()
    else:
        match=re.search(r"(?:导航到|导航去|路线规划到|规划路线到|规划(?:一下)?(?:到|去)|我要去|我想去|带我去|^去|^到)\s*(.+)$",text)
        if not match:return None
        origin,destination=str(default_origin).strip(),match.group(1)
    # Spoken follow-up requests belong to the instruction, not the destination POI.
    destination=re.split(r"[，,；;]\s*(?:(?:请|麻烦)(?:你)?\s*)?(?:帮我|给我|为我)?\s*(?:(?:规划|安排|提供|推荐|显示)(?:一下|一条|一个|个)?(?:导航|出行)?路线|(?:一条|个)?(?:导航|出行)?路线|(?:怎么走|怎么去))",destination,maxsplit=1)[0]
    # Strip transport instructions before the route suffix, preserving the actual POI name.
    destination=re.split(r"[，,；;]\s*(?:请|帮我|我想|我准备|选择|使用|改为|乘坐|乘|坐)?(?:打车|出租车|自驾|开车|驾车|公共交通|公交车|公交|地铁|步行)",destination,maxsplit=1)[0]
    destination=re.sub(r"[，,；;\s]*(?:请|帮我|我想|选择|使用|改为)?(?:打车|出租车|自驾|开车|驾车|公共交通|公交|地铁|步行)(?:的方式|方式)?(?:前往|过去|出发|导航|走|去)?(?:吧|谢谢)?$","",destination)
    destination=re.sub(r"[，,\s]*(?:请|帮我|给我)?(?:规划|安排)(?:一下)?(?:驾车|步行|公交|打车|自驾)?路线$","",destination)
    destination=re.sub(r"[，,\s]*(?:的)?(?:驾车|步行|公交|公共交通|打车|出租车|自驾)?(?:导航|路线规划|路线|怎么走|怎么去)$","",destination).strip(" ，,。！？!?")
    origin=re.sub(r"(?:出发|作为起点)$","",origin).strip(" ，,。")
    if not destination or len(destination)>120 or len(origin)>120:
        raise ServiceError("请使用简短地点名称，例如：帮我规划从苏州站到虎丘景区的路线，打车前往。")
    return {"action":"route","origin":origin,"destination":destination,"city":city,"mode":mode,
            "origin_source":"explicit" if explicit else "saved" if origin else "missing"}

class NavigationBridge:
    def __init__(self):
        self.lock=threading.Lock()
        self.current={"id":0,"action":"none"}
        self.pending=None
        self.active=None

    def _emit(self,command):
        self.current={"id":self.current["id"]+1,**command}
        return dict(self.current)

    def accept(self,text,city,default_origin=""):
        text=text.strip().strip("。！？!? ")
        text=re.sub(r"^(?:贾维斯|jarvis)[，,：:\s]*","",text,flags=re.I).strip()
        with self.lock:
            if any(w in text for w in ("取消导航","导航结束","结束导航","退出导航","不用导航了","返回能量体")) or text=="不去了":
                self.pending=None;self.active=None
                return self._emit({"action":"cancel"})
            command=parse_navigation(text,city,default_origin)
            if command is None and self.pending:
                match=re.fullmatch(r"(?:从|我在|出发地是|起点是)\s*(.{1,120}?)(?:出发)?",text)
                origin=match.group(1).strip() if match else ""
                if not origin and text in ("开始导航","帮我规划路线","规划路线"):origin=default_origin
                if origin:command={**self.pending,"origin":origin,"origin_source":"explicit" if match else "saved","action":"route"}
            if command is None and self.active and any(w in text for w in ("出行方式","交通方式","怎么出行","怎么去","怎么走","还有什么方式","打车","公交","公共交通","自驾","开车","地铁","比较路线","还有什么路线")):
                mode="taxi" if "打车" in text else "transit" if any(w in text for w in ("公交","公共交通","地铁")) else "driving" if any(w in text for w in ("自驾","开车")) else "compare"
                command={**self.active,"action":"route","mode":mode}
            if command is None:
                if self.active or self.pending:
                    self.active=None;self.pending=None
                    self._emit({"action":"close","reason":"topic_changed"})
                return None
            if command["action"]=="route" and not command.get("origin"):
                self.pending=dict(command);command={**command,"action":"await_origin"}
            elif command["action"]=="route":
                self.pending=None;self.active=dict(command)
            elif command["action"]=="open":
                self.active=dict(command)
            return self._emit(command)

    def snapshot(self):
        with self.lock:return dict(self.current)

def proxy_authorized(headers,token,origin,port):
    if headers.get("Host")!=f"127.0.0.1:{port}":return False
    if headers.get("Origin") not in (None,origin):return False
    if headers.get("Sec-Fetch-Site")=="cross-site":return False
    try:
        cookie=SimpleCookie()
        cookie.load(headers.get("Cookie",""))
        return "jarvis_map_gate" in cookie and cookie["jarvis_map_gate"].value==token
    except Exception:
        return False

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
