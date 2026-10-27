"""Cached public weather, refreshed in a background thread; never blocks audio/UI."""
from datetime import datetime,timezone,timedelta
import json
import logging
import threading
import time
from urllib import request,parse
from .paths import ROOT

LOG=logging.getLogger("jarvis")
TZ=timezone(timedelta(hours=8))
def weather_label(code):
    if code==0:return "晴"
    if code in (1,2):return "少云" if code==1 else "多云"
    if code==3:return "阴"
    if code in (45,48):return "雾"
    if code in (51,53,55,56,57):return "小雨"
    if code in (61,63,65,66,67):return "雨"
    if code in (71,73,75,77,85,86):return "雪"
    if code in (80,81,82):return "阵雨"
    if code in (95,96,99):return "雷雨"
    return "天气更新中"

def request_json(url):
    last=None
    # Respect system proxy first, then try a verified direct connection.
    for opener in (request.build_opener(),request.build_opener(request.ProxyHandler({}))):
        try:
            with opener.open(request.Request(url,headers={"User-Agent":"JARVIS-Desktop/0.2"}),timeout=7) as response:
                raw=response.read(1_500_001)
            if len(raw)>1_500_000:raise ValueError("Weather response too large")
            return json.loads(raw)
        except Exception as exc:
            last=exc
    raise RuntimeError("Weather network unavailable") from last

class Weather:
    def __init__(self,city="苏州"):
        self.city=city.strip()
        self.lock=threading.Lock()
        self.fetching=False
        self.next_refresh=0.0
        self.data=None
        self.status="loading"
        self.live_received=0.0
        self.cache=ROOT/"cache/weather.json"
        try:
            saved=json.loads(self.cache.read_text(encoding="utf-8"))
            if saved.get("city")==self.city:
                self.data=saved
                self.status="cached"
        except (OSError,ValueError):
            pass

    def reset(self,city):
        with self.lock:
            if city!=self.city:
                self.city=city.strip()
                self.data=None
                self.next_refresh=0
                self.status="loading"

    def snapshot(self,refresh=True):
        with self.lock:
            result=dict(self.data or {})
            if result.get("source","").startswith("高德") and time.monotonic()-self.live_received>900:
                self.status="stale"
            result.update(city=self.city,source=result.get("source","Open-Meteo 区域预报"),status=self.status)
            launch=refresh and not self.fetching and time.monotonic()>=self.next_refresh
            if launch:self.fetching=True
        if launch:
            threading.Thread(target=self._refresh,daemon=True,name="jarvis-weather").start()
        return result

    def accept_live(self,values):
        if str(values.get("adcode",""))!="320505" or "虎丘" not in self.city:
            return
        temperature=float(values["temperature"]);humidity=float(values["humidity"])
        if not -60<=temperature<=60 or not 0<=humidity<=100:raise ValueError("天气数值异常")
        with self.lock:
            data=dict(self.data or {})
            data.update(city=self.city,temperature=temperature,humidity=humidity,label=str(values.get("weather",""))[:40],
                        wind=None,wind_power=str(values.get("windPower",""))[:20],observation=str(values.get("reportTime",values.get("reporttime","")))[:30],
                        source="高德 · 虎丘区实况",adcode="320505",feels_like=None,
                        updated=datetime.now(TZ).isoformat(timespec="seconds"))
            self.data=data;self.status="live";self.live_received=time.monotonic();self.next_refresh=time.monotonic()+600

    def _coordinates(self,city):
        if "虎丘" in city:
            # District-scale fallback point, not the PC's position or a house-level observation.
            return 31.331282,120.4290851
        cached=ROOT/"cache/suzhou_geocoding.json"
        candidates=[]
        if city in ("苏州","苏州市") and cached.exists():
            try:candidates=json.loads(cached.read_text(encoding="utf-8")).get("results",[])
            except (OSError,ValueError):pass
        if not candidates:
            query=parse.urlencode({"name":city,"count":8,"language":"zh","countryCode":"CN"})
            candidates=request_json("https://geocoding-api.open-meteo.com/v1/search?"+query).get("results",[])
        if not candidates:raise ValueError("City not found")
        match=next((row for row in candidates if row.get("name","").rstrip("市")==city.rstrip("市")),candidates[0])
        return match["latitude"],match["longitude"]

    def _refresh(self):
        city=self.city
        try:
            if not city:raise ValueError("City not configured")
            latitude,longitude=self._coordinates(city)
            query=parse.urlencode({
                "latitude":latitude,"longitude":longitude,"timezone":"Asia/Shanghai",
                "current":"temperature_2m,relative_humidity_2m,apparent_temperature,is_day,weather_code,wind_speed_10m",
                "daily":"weather_code,temperature_2m_max,temperature_2m_min",
                "wind_speed_unit":"ms","forecast_days":3,
            })
            raw=request_json("https://api.open-meteo.com/v1/forecast?"+query)
            current=raw["current"]
            if not isinstance(current.get("temperature_2m"),(int,float)):
                raise ValueError("Missing weather temperature")
            daily=raw.get("daily",{})
            forecast=[]
            for i,date in enumerate(daily.get("time",[])[:3]):
                forecast.append({"date":date,"high":daily["temperature_2m_max"][i],
                                 "low":daily["temperature_2m_min"][i],
                                 "code":daily["weather_code"][i],"label":weather_label(daily["weather_code"][i])})
            data={"city":city,"source":"Open-Meteo 区域预报","temperature":current["temperature_2m"],
                  "humidity":current.get("relative_humidity_2m"),"feels_like":current.get("apparent_temperature"),
                  "wind":current.get("wind_speed_10m"),"code":current.get("weather_code",0),
                  "label":weather_label(current.get("weather_code",0)),"is_day":current.get("is_day",1),
                  "observation":current.get("time"),"updated":datetime.now(TZ).isoformat(timespec="seconds"),
                  "forecast":forecast,"forecast_source":"Open-Meteo 区域预报"}
            with self.lock:
                if city==self.city:
                    if self.data and self.data.get("source","").startswith("高德") and time.monotonic()-self.live_received<900:
                        self.data["forecast"]=forecast
                        self.data["forecast_source"]="Open-Meteo 区域预报"
                        self.next_refresh=time.monotonic()+600
                        return
                    self.data=data
                    self.status="live"
                    self.next_refresh=time.monotonic()+900
                    temporary=self.cache.with_suffix(".tmp")
                    temporary.write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
                    temporary.replace(self.cache)
        except Exception:
            LOG.warning("weather_refresh_failed")
            with self.lock:
                self.status="live" if self.data and self.data.get("source","").startswith("高德") and time.monotonic()-self.live_received<900 else "stale" if self.data else "offline"
                self.next_refresh=time.monotonic()+90
        finally:
            with self.lock:self.fetching=False